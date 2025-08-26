# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Tuple, Callable, Optional
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

from PIL import Image

from settings import AppSettings, RootConfig
from services.discovery import scan_posts
from services.image_ops import load_image
from services.resize import resize_contain
from services.watermark import add_text_watermark
from services.writer import save_image  # ✅ 고속 저장(옵션 튜닝)

class AppController:
    def __init__(self):
        self._processed = 0
        # 미리보기/반복 리사이즈 캐시(LRU)
        self._canvas_cache: "OrderedDict[tuple, Image.Image]" = OrderedDict()
        self._canvas_cache_limit = 64

    def _resolve_wm_text(self, rc: RootConfig, settings: AppSettings) -> str:
        """
        루트별 텍스트가 ''(빈 문자열)로 명시되면 워터마크 '비활성'.
        그 외에는 루트별 텍스트 우선, 없으면 기본값.
        """
        if rc.wm_text is not None and rc.wm_text.strip() == "":
            return ""  # 명시적 비활성
        if (rc.wm_text or "").strip():
            return rc.wm_text.strip()
        return (settings.default_wm_text or "").strip()

    # ---------- 스캔 ----------
    def scan_posts_multi(self, roots: List[RootConfig]) -> Dict[str, dict]:
        """
        - 루트에 바로 이미지가 있으면 단일 게시물로 간주(__SELF__)
        - 아니면 하위 폴더를 게시물로 스캔
        """
        posts: Dict[str, dict] = {}
        for rc in roots:
            root = rc.path
            sub = scan_posts(root)
            for post_name, files in sub.items():
                if post_name == "__SELF__":
                    key = root.name
                    post_dir = root
                    display_post = root.name
                else:
                    key = f"{root.name}/{post_name}"
                    post_dir = root / post_name
                    display_post = post_name
                posts[key] = {
                    "root": rc,
                    "post_name": display_post,
                    "files": files,
                    "post_dir": post_dir,  # 저장시 사용할 실제 폴더
                }
        return posts

    # ---------- 공통 유틸 ----------
    def _choose_anchor(self, meta: dict, settings: AppSettings, src: Optional[Path] = None):
        # 우선순위: 이미지 앵커 > 게시물 앵커 > 기본 앵커
        if src is not None:
            img_map = meta.get("img_anchors") or {}
            if src in img_map:
                return img_map[src]
        if meta.get("anchor"):
            return meta["anchor"]
        return settings.wm_anchor

    def _canvas_key(self, src: Path, target: Tuple[int, int], bg_rgb: Tuple[int, int, int]):
        try:
            mt = src.stat().st_mtime_ns
        except Exception:
            mt = 0
        return (str(src), mt, int(target[0]), int(target[1]), tuple(bg_rgb))

    def _get_resized_canvas(self, src: Path, target: Tuple[int, int], bg_rgb: Tuple[int, int, int]) -> Image.Image:
        key = self._canvas_key(src, target, bg_rgb)
        if key in self._canvas_cache:
            im = self._canvas_cache.pop(key)
            self._canvas_cache[key] = im
            return im

        base = load_image(src)  # 이미 RGB Image 보장
        if not isinstance(base, Image.Image):
            raise ValueError(f"이미지 로드 실패(타입 불일치): {src}")

        canvas = base if tuple(target) == (0, 0) else resize_contain(base, target, bg_rgb)
        self._canvas_cache[key] = canvas
        if len(self._canvas_cache) > self._canvas_cache_limit:
            self._canvas_cache.popitem(last=False)
        return canvas

    # ---------- 미리보기 ----------
    def preview_by_key(
        self,
        key: str,
        posts: Dict[str, dict],
        settings: AppSettings,
        selected_src: Optional[Path] = None
    ) -> tuple[Image.Image, Image.Image]:
        meta = posts.get(key)
        if not meta or not meta["files"]:
            raise ValueError("No images in this post.")
        src = selected_src or meta["files"][0]

        before = load_image(src)
        if not isinstance(before, Image.Image):
            raise ValueError(f"이미지 로드 실패(타입 불일치): {src}")

        tgt = settings.sizes[0]
        canvas = before.copy() if tuple(tgt) == (0, 0) else self._get_resized_canvas(src, tgt, settings.bg_color).copy()

        wm_text = self._resolve_wm_text(meta["root"], settings)
        if not wm_text:
            return before, canvas

        anchor = self._choose_anchor(meta, settings, src)
        after = add_text_watermark(
            canvas,
            text=wm_text,
            opacity_pct=settings.wm_opacity,
            scale_pct=settings.wm_scale_pct,
            fill_rgb=settings.wm_fill_color,
            stroke_rgb=settings.wm_stroke_color,
            stroke_width=settings.wm_stroke_width,
            anchor_norm=anchor,
            font_path=settings.wm_font_path,
        )
        return before, after

    # ---------- 출력 경로 ----------
    def _output_dir_for(self, src: Path, rc: RootConfig, out_root: Path, post_name: str) -> Path:
        """
        출력 경로: out_root / rc.path.name / (src.parent relative to rc.path)
        - 계정/게시물 업로드:  out_root/계정/게시물
        - 게시물만 업로드:    out_root/게시물
        - 내부 더 깊은 구조도 그대로 보존
        """
        base = out_root / rc.path.name
        try:
            rel = src.parent.relative_to(rc.path)
        except Exception:
            rel = Path(post_name) if (rc.path / post_name).exists() else Path()
        return (base / rel) if str(rel) not in ("", ".") else base

    # ---------- 일괄 처리(병렬) ----------
    def start_batch(
        self,
        settings: AppSettings,
        posts: Dict[str, dict],
        progress_cb: Callable[[int], None],
        done_cb: Callable[[int], None],
        error_cb: Callable[[str], None] | None = None,
    ):
        """
        ThreadPoolExecutor로 병렬 처리.
        - JPEG 저장 옵션: quality=90, optimize=False, progressive=False (빠른 저장)
        - progress_cb / error_cb / done_cb는 기존과 동일하게 호출
        """
        self._processed = 0

        # 작업 목록 생성
        jobs: List[tuple[RootConfig, dict, Path, int, int]] = []
        for _, meta in posts.items():
            rc: RootConfig = meta["root"]
            for src in meta["files"]:
                for (w, h) in settings.sizes:
                    jobs.append((rc, meta, src, int(w), int(h)))

        total = len(jobs)
        if total == 0:
            if done_cb: done_cb(0)
            return

        # 워커 함수
        def _do(rc: RootConfig, meta: dict, src: Path, w: int, h: int) -> None:
            wm_text = self._resolve_wm_text(rc, settings)
            anchor = self._choose_anchor(meta, settings, src)
            # 리사이즈 베이스(일괄 처리도 동일 경로 → 캐시 활용)
            canvas = self._get_resized_canvas(src, (w, h), settings.bg_color)
            if not wm_text:
                out_img = canvas
            else:
                # ✅ 캐시 공유 이미지 보호: 워터마크 적용 시에만 복사본 생성
                out_img = add_text_watermark(
                    canvas.copy(),
                    text=wm_text,
                    opacity_pct=settings.wm_opacity,
                    scale_pct=settings.wm_scale_pct,
                    fill_rgb=settings.wm_fill_color,
                    stroke_rgb=settings.wm_stroke_color,
                    stroke_width=settings.wm_stroke_width,
                    anchor_norm=anchor,
                    font_path=settings.wm_font_path,
                )
            # 저장
            out_dir = self._output_dir_for(src, rc, settings.output_root, meta["post_name"])
            dst = out_dir / f"{src.stem}_wm.jpg"
            save_image(
                out_img,
                dst,
                quality=90,         # 속도/용량 균형
                optimize=False,     # 빠르게
                progressive=False   # 빠르게
            )

        # 병렬 실행
        max_workers = min(8, (os.cpu_count() or 4))
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                futs = [ex.submit(_do, rc, meta, src, w, h) for (rc, meta, src, w, h) in jobs]
                for f in as_completed(futs):
                    try:
                        f.result()
                    except Exception as e:
                        if error_cb:
                            error_cb(str(e))
                    finally:
                        self._processed += 1
                        if progress_cb:
                            progress_cb(self._processed)
        except Exception as e:
            if error_cb:
                error_cb(str(e))
        finally:
            if done_cb:
                done_cb(self._processed)

    # ---------- 단일 이미지 처리(내부) ----------
    def _process_image(
            self,
            src: Path,
            target: Tuple[int, int],
            settings: AppSettings,
            wm_text: str,
            anchor
    ) -> Image.Image:
        im = load_image(src)  # 이미 RGB Image
        if not isinstance(im, Image.Image):
            raise ValueError(f"이미지 로드 실패(타입 불일치): {src}")

        canvas = im if tuple(target) == (0, 0) else resize_contain(im, target, settings.bg_color)
        if not (wm_text or "").strip():
            return canvas

        out = add_text_watermark(
            canvas,
            text=wm_text,
            opacity_pct=settings.wm_opacity,
            scale_pct=settings.wm_scale_pct,
            fill_rgb=settings.wm_fill_color,
            stroke_rgb=settings.wm_stroke_color,
            stroke_width=settings.wm_stroke_width,
            anchor_norm=anchor,
            font_path=settings.wm_font_path,
        )
        return out


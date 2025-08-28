# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Tuple, Callable, Optional
import threading

from PIL import Image

from services.discovery import scan_posts
from services.image_ops import load_image
from services.resize import resize_contain
from services.watermark import add_text_watermark
from services.writer import save_image  # 고속 저장
from settings import AppSettings, RootConfig, DEFAULT_WM_TEXT, IMAGES_VROOT

IMG_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}

class AppController:
    def __init__(self):
        self._processed = 0
        self._canvas_cache: "OrderedDict[tuple, Image.Image]" = OrderedDict()
        self._canvas_cache_limit = 64
        self._cache_lock = threading.Lock()

    def _flat_output_dir(self, out_root: Path) -> Path:
        """
        항상 출력 루트에만 저장(폴더 감싸지 않음).
        """
        try:
            out_root.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return out_root

    def _filename_for(self, src: Path, w: int, h: int) -> str:
        """
        크기 지정 시 파일명에 _{WxH} 태그를 붙여 다중 크기 저장 시 충돌 방지.
        원본 크기(0,0)일 땐 태그 생략.
        """
        size_tag = "" if (w, h) == (0, 0) else f"_{w}x{h}"
        return f"{src.stem}{size_tag}_wm.jpg"

    def _unique_path(self, out_dir: Path, filename: str) -> Path:
        """
        같은 이름이 있으면 _1, _2 … 를 붙여 고유 경로를 만든다.
        """
        dst = out_dir / filename
        if not dst.exists():
            return dst
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        i = 1
        while True:
            cand = out_dir / f"{stem}_{i}{suffix}"
            if not cand.exists():
                return cand
            i += 1

    def _resolve_wm_text(self, rc: RootConfig, settings: AppSettings) -> str:
        if getattr(rc, "wm_text", None) is not None and str(rc.wm_text).strip() == "":
            return ""
        if (getattr(rc, "wm_text", "") or "").strip():
            return str(rc.wm_text).strip()
        return (settings.default_wm_text or "").strip()

    # ---------- 스캔 ----------
    def scan_posts_multi(
            self,
            roots: List[RootConfig],
            dropped_images: Optional[List[Path]] = None
    ) -> Dict[str, dict]:
        posts: Dict[str, dict] = {}
        dropped_images = list(dropped_images or [])
        for rc in roots:
            root = rc.path

            # 🔹 가상 루트: 드롭한 이미지 모음
            if str(root) == IMAGES_VROOT:
                imgs = [p for p in dropped_images if p.is_file() and p.suffix.lower() in IMG_EXTS]
                if imgs:
                    key = "이미지"  # 게시물 리스트에 보일 이름
                    posts[key] = {
                        "root": rc,
                        "post_name": key,
                        "files": imgs,
                        "post_dir": root,  # 더미(실제 폴더 아님)
                    }
                continue

            # 🔹 일반 루트: 기존 폴더 스캔
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
                    "post_dir": post_dir,
                }
        return posts

    # ---------- 공통 유틸 ----------
    def _choose_anchor(self, meta: dict, settings: AppSettings, src: Optional[Path] = None):
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
        with self._cache_lock:
            if key in self._canvas_cache:
                im = self._canvas_cache.pop(key)
                self._canvas_cache[key] = im
                return im

        base = load_image(src)  # RGB Image 보장
        if not isinstance(base, Image.Image):
            raise ValueError(f"이미지 로드 실패(타입 불일치): {src}")

        canvas = base if tuple(target) == (0, 0) else resize_contain(base, target, bg_rgb)

        with self._cache_lock:
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
        if str(rc.path) == IMAGES_VROOT:
            return out_root

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
        self._processed = 0

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

        def _do(rc: RootConfig, meta: dict, src: Path, w: int, h: int) -> None:
            wm_text = self._resolve_wm_text(rc, settings)
            anchor = self._choose_anchor(meta, settings, src)
            canvas = self._get_resized_canvas(src, (w, h), settings.bg_color)
            out_img = (
                canvas if not wm_text else
                add_text_watermark(
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
            )

            # 저장 경로 결정
            if str(rc.path) == IMAGES_VROOT:
                # ✅ 드롭한 '이미지' 가상 루트: 출력 루트에 플랫 저장
                out_dir = settings.output_root
            else:
                # ✅ 폴더에서 온 항목: 계정/게시물 구조 보존
                out_dir = self._output_dir_for(src, rc, settings.output_root, meta["post_name"])

            # 디렉터리 보장
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

            # 파일명: 크기 태그(0,0이면 생략) + _wm.jpg
            fname = self._filename_for(src, w, h)

            # 이름 충돌 방지(특히 플랫 저장 시 중요)
            dst = self._unique_path(out_dir, fname)

            save_image(
                out_img,
                dst,
                quality=90,
                optimize=False,
                progressive=False
            )

        max_workers = min(8, (os.cpu_count() or 4))
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                futs = [ex.submit(_do, rc, meta, src, w, h) for (rc, meta, src, w, h) in jobs]
                for f in as_completed(futs):
                    try:
                        f.result()
                    except Exception as e:
                        if error_cb: error_cb(str(e))
                    finally:
                        self._processed += 1
                        if progress_cb: progress_cb(self._processed)
        except Exception as e:
            if error_cb: error_cb(str(e))
        finally:
            if done_cb: done_cb(self._processed)

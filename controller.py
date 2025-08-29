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
from services.resize import resize_contain, resize_contain_fast  # ✅ fast 경로 사용
from services.watermark import add_text_watermark
from services.writer import save_image
from settings import AppSettings, RootConfig, IMAGES_VROOT

IMG_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}

class AppController:
    def __init__(self):
        self._processed = 0
        self._canvas_cache: "OrderedDict[tuple, Image.Image]" = OrderedDict()
        self._canvas_cache_limit = 256
        self._cache_lock = threading.Lock()

        # ✅ 프리뷰 전용 캐시 (before/after가 동일 조건이면 즉시 반환)
        self._preview_cache: "OrderedDict[tuple, tuple[Image.Image, Image.Image]]" = OrderedDict()
        self._preview_cache_limit = 128
        self._preview_lock = threading.Lock()

        # ✅ 프리뷰 최대 긴 변(원본 그대로일 때도 화면용으로 다운스케일)
        self._max_preview_side = 1400

    # ---------- 내부 유틸 ----------
    # def _filename_for(self, src: Path, w: int, h: int) -> str:
    #     """
    #     크기 지정 시 파일명에 _{WxH} 태그를 붙여 다중 크기 저장 시 충돌 방지.
    #     원본 크기(0,0)일 땐 태그 생략.
    #     """
    #     size_tag = "" if (w, h) == (0, 0) else f"_{w}x{h}"
    #     return f"{src.stem}{size_tag}_wm.jpg"

    def _filename_for(self, src: Path, w: int, h: int) -> str:
        size_tag = "" if (w, h) == (0, 0) else f"_{w}x{h}"
        ext = src.suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"):
            ext = ".jpg"  # 알 수 없는 포맷은 jpg로
        return f"{src.stem}{size_tag}_wm{ext}"

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

    def resolve_wm_for_meta(self, meta: dict, settings: AppSettings) -> str:
        if "wm_text_edit" in meta:
            return (meta.get("wm_text_edit") or "").strip()
        rc: RootConfig = meta["root"]
        return self._resolve_wm_text(rc, settings)

    def _cfg_key(self, cfg: dict | None) -> tuple:
        """워터마크 설정을 캐시 키로 만들기(불변 튜플). None이면 빈 키."""
        if not cfg:
            return ()
        return (
            (cfg.get("text") or "").strip(),
            int(cfg.get("opacity", 0)),
            int(cfg.get("scale_pct", 0)),
            tuple(cfg.get("fill", (0, 0, 0))),
            tuple(cfg.get("stroke", (255, 255, 255))),
            int(cfg.get("stroke_w", 0)),
            str(cfg.get("font_path") or ""),
        )

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

    def _get_resized_canvas(self, src: Path, target: Tuple[int, int], bg_rgb: Tuple[int, int, int], *, fast: bool = False) -> Image.Image:
        """원본을 target에 contain 후 배경을 깔아 준 캔버스를 LRU 캐시."""
        key = self._canvas_key(src, target, bg_rgb) + (1 if fast else 0,)  # ✅ fast 여부도 키에 포함
        with self._cache_lock:
            if key in self._canvas_cache:
                im = self._canvas_cache.pop(key)
                self._canvas_cache[key] = im
                return im

        base = load_image(src)  # RGB Image (캐시됨)
        if not isinstance(base, Image.Image):
            raise ValueError(f"이미지 로드 실패: {src}")

        if tuple(target) == (0, 0):
            canvas = base
        else:
            canvas = (resize_contain_fast if fast else resize_contain)(base, target, bg_rgb)

        with self._cache_lock:
            self._canvas_cache[key] = canvas
            if len(self._canvas_cache) > self._canvas_cache_limit:
                self._canvas_cache.popitem(last=False)

        return canvas

    def _suggest_preview_target(self, wh: tuple[int, int]) -> tuple[int, int]:
        """원본 그대로(0,0)일 때 화면용으로 다운샘플 목표 크기 제안."""
        w, h = map(int, wh)
        if w == 0 or h == 0:
            return (0, 0)
        m = float(self._max_preview_side)
        if max(w, h) <= m:
            return (w, h)
        if w >= h:
            return (int(m), int(round(h * (m / w))))
        else:
            return (int(round(w * (m / h))), int(m))

    # ---------- 설정 병합 ----------
    # controller.py

    def resolve_wm_config(self, meta: dict, settings: AppSettings, src: Optional[Path]) -> Optional[dict]:
        """
        최종 워터마크 설정 병합 (배치/미리보기 공용):
        우선순위 (text 기준)
          1) 이미지 개별 오버라이드 img_overrides[src]["text"] (있으면 최우선)
          2) 이미지 인라인 편집 meta["img_wm_text_edits"][src]
          3) 게시물 인라인 편집 meta["wm_text_edit"]
          4) 루트/앱 기본(self._resolve_wm_text)
        text == "" 이면 '워터마크 없음' → None 반환
        나머지 키들(fill/stroke/…​)은 img_overrides가 있으면 해당 키만 덮어씀
        """
        # ---- 1) 기본값(현재 UI/설정) 준비
        base = {
            "opacity": settings.wm_opacity,
            "scale_pct": settings.wm_scale_pct,
            "fill": settings.wm_fill_color,
            "stroke": settings.wm_stroke_color,
            "stroke_w": settings.wm_stroke_width,
            "font_path": str(settings.wm_font_path) if settings.wm_font_path else "",
        }

        # ---- 2) 텍스트 우선순위
        final_text: Optional[str] = None

        # 1) 이미지 오버라이드 우선 (text가 명시되어 있으면 그 값을 그대로 사용)
        ov_all = meta.get("img_overrides") or {}
        ov_for_img = ov_all.get(src) or {} if src is not None else {}
        if "text" in ov_for_img:
            final_text = (ov_for_img.get("text") or "").strip()

        # 2) 이미지 인라인 편집
        if final_text is None and src is not None:
            img_edits = meta.get("img_wm_text_edits") or {}
            if src in img_edits:
                final_text = (img_edits[src] or "").strip()

        # 3) 게시물 인라인 편집
        if final_text is None and ("wm_text_edit" in meta):
            final_text = (meta.get("wm_text_edit") or "").strip()

        # 4) 루트/앱 기본
        if final_text is None:
            rc: RootConfig = meta["root"]
            final_text = self._resolve_wm_text(rc, settings).strip()

        # 빈문자면 '없음'
        if final_text == "":
            return None

        # ---- 3) 나머지 키 병합 (개별 오버라이드에 있는 키만 덮어쓰기)
        cfg = {**base, **{k: v for k, v in ov_for_img.items() if k != "text"}}
        cfg["text"] = final_text
        return cfg

    # ---------- 스캔 ----------
    def scan_posts_multi(self, roots: List[RootConfig], dropped_images: Optional[List[Path]] = None) -> Dict[str, dict]:
        posts: Dict[str, dict] = {}
        dropped_images = list(dropped_images or [])
        for rc in roots:
            root = rc.path
            if str(root) == IMAGES_VROOT:
                imgs = [p for p in dropped_images if p.is_file() and p.suffix.lower() in IMG_EXTS]
                if imgs:
                    key = "이미지"
                    posts[key] = {
                        "root": rc,
                        "post_name": key,
                        "files": imgs,
                        "post_dir": root,
                    }
                continue

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

    # ---------- 미리보기 ----------
    def preview_by_key(self, key: str, posts: Dict[str, dict], settings: AppSettings, selected_src: Optional[Path] = None) -> tuple[Image.Image, Image.Image]:
        meta = posts.get(key)
        if not meta or not meta["files"]:
            raise ValueError("No images in this post.")
        src = selected_src or meta["files"][0]

        # ✅ 타겟 계산: '원본 그대로(0,0)'이면 화면용 축소 목표 사용
        tgt = settings.sizes[0]
        if tuple(tgt) == (0, 0):
            # 원본 크기 확인 후 화면용 목표 산출
            base = load_image(src)
            tgt = self._suggest_preview_target(base.size)

        # ✅ 캐시 키
        anchor = self._choose_anchor(meta, settings, src)
        wm_cfg = self.resolve_wm_config(meta, settings, src)
        pkey = (
            str(src),
            src.stat().st_mtime_ns if src.exists() else 0,
            int(tgt[0]), int(tgt[1]),
            tuple(settings.bg_color),
            tuple(anchor),
            self._cfg_key(wm_cfg),
        )

        with self._preview_lock:
            if pkey in self._preview_cache:
                val = self._preview_cache.pop(pkey)
                self._preview_cache[pkey] = val
                return val

        # ✅ 프리뷰는 빠른 리사이즈 경로 사용(fast=True)
        before_canvas = self._get_resized_canvas(src, tgt, settings.bg_color, fast=True).copy()

        if not wm_cfg:
            after_canvas = before_canvas.copy()
        else:
            after_canvas = add_text_watermark(
                before_canvas.copy(),
                text=wm_cfg["text"],
                opacity_pct=int(wm_cfg["opacity"]),
                scale_pct=int(wm_cfg["scale_pct"]),
                fill_rgb=tuple(wm_cfg["fill"]),
                stroke_rgb=tuple(wm_cfg["stroke"]),
                stroke_width=int(wm_cfg["stroke_w"]),
                anchor_norm=anchor,
                font_path=Path(wm_cfg["font_path"]) if wm_cfg.get("font_path") else None,
            )

        with self._preview_lock:
            self._preview_cache[pkey] = (before_canvas, after_canvas)
            if len(self._preview_cache) > self._preview_cache_limit:
                self._preview_cache.popitem(last=False)

        return before_canvas, after_canvas

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
            anchor = self._choose_anchor(meta, settings, src)
            # ✅ 배치는 정확도 우선(LANCZOS). 단, 0x0(원본)은 스킵.
            canvas = self._get_resized_canvas(src, (w, h), settings.bg_color, fast=False)

            wm_cfg = self.resolve_wm_config(meta, settings, src)
            if not wm_cfg:
                out_img = canvas
            else:
                out_img = add_text_watermark(
                    canvas.copy(),
                    text=wm_cfg["text"],
                    opacity_pct=int(wm_cfg["opacity"]),
                    scale_pct=int(wm_cfg["scale_pct"]),
                    fill_rgb=tuple(wm_cfg["fill"]),
                    stroke_rgb=tuple(wm_cfg["stroke"]),
                    stroke_width=int(wm_cfg["stroke_w"]),
                    anchor_norm=anchor,
                    font_path=Path(wm_cfg["font_path"]) if wm_cfg.get("font_path") else None,
                )

            out_dir = settings.output_root if str(rc.path) == IMAGES_VROOT else self._output_dir_for(src, rc, settings.output_root, meta["post_name"])
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

            fname = self._filename_for(src, w, h)
            dst = self._unique_path(out_dir, fname)

            save_image(out_img, dst, quality=90, optimize=False, progressive=False)

        # ✅ CPU 수에 맞춰 워커 수 상향 + 과도한 스레드 방지
        max_workers = min(32, max(4, (os.cpu_count() or 4) * 2))
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

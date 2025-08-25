# -*- coding: utf-8 -*-
"""
Controller: 스캔/미리보기/배치 실행 오케스트레이션
UI와 services 사이 경계
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple, Callable
from PIL import Image

from settings import AppSettings
from services.discovery import scan_posts
from services.image_ops import load_image
from services.resize import resize_contain
from services.watermark import add_center_watermark
from services.writer import save_jpeg

class AppController:
    def __init__(self):
        self._processed = 0

    # -------- Scan --------
    def scan_posts(self, input_root: Path) -> Dict[str, List[Path]]:
        return scan_posts(input_root)

    # -------- Preview --------
    def preview_first_of_post(
        self, post_name: str, posts: Dict[str, List[Path]], settings: AppSettings
    ) -> tuple[Image.Image, Image.Image]:
        files = posts.get(post_name, [])
        if not files:
            raise ValueError("No images in this post.")
        src = files[0]
        before = load_image(src).convert("RGB")
        canvas = resize_contain(before, settings.sizes[0], settings.bg_color)
        after = add_center_watermark(
            canvas, text=settings.wm_text,
            opacity_pct=settings.wm_opacity, scale_pct=settings.wm_scale_pct
        )
        return before, after

    # -------- Batch --------
    def start_batch(
        self,
        settings: AppSettings,
        posts: Dict[str, List[Path]],
        progress_cb: Callable[[int], None],
        done_cb: Callable[[int], None],
        error_cb: Callable[[str], None] | None = None,
    ):
        import threading
        total = sum(len(v) for v in posts.values()) * len(settings.sizes)
        self._processed = 0

        def worker():
            try:
                for post, files in posts.items():
                    for src in files:
                        for (w, h) in settings.sizes:
                            try:
                                img = self._process_image(src, (w, h), settings)
                                dst = settings.output_root / post / f"{w}x{h}" / (src.stem + "_wm.jpg")
                                save_jpeg(img, dst)
                            except Exception as e:
                                if error_cb: error_cb(f"{src} {w}x{h}: {e}")
                            finally:
                                self._processed += 1
                                if progress_cb: progress_cb(self._processed)
                if done_cb: done_cb(self._processed)
            except Exception as e:
                if error_cb: error_cb(str(e))

        threading.Thread(target=worker, daemon=True).start()

    # -------- Internal --------
    def _process_image(self, src: Path, target: Tuple[int, int], settings: AppSettings) -> Image.Image:
        im = load_image(src)
        canvas = resize_contain(im, target, settings.bg_color)
        out = add_center_watermark(
            canvas, text=settings.wm_text,
            opacity_pct=settings.wm_opacity, scale_pct=settings.wm_scale_pct
        )
        return out

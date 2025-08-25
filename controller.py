# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple, Callable
from PIL import Image

from settings import AppSettings, RootConfig
from services.discovery import scan_posts
from services.image_ops import load_image
from services.resize import resize_contain
from services.watermark import add_center_watermark
from services.writer import save_jpeg

class AppController:
    def __init__(self):
        self._processed = 0

    def scan_posts_multi(self, roots: List[RootConfig]) -> Dict[str, dict]:
        posts: Dict[str, dict] = {}
        for rc in roots:
            root = rc.path
            sub = scan_posts(root)
            for post_name, files in sub.items():
                key = f"{root.name}/{post_name}"
                posts[key] = {"root": rc, "post_name": post_name, "files": files}
        return posts

    def preview_by_key(self, key: str, posts: Dict[str, dict], settings: AppSettings) -> tuple[Image.Image, Image.Image]:
        meta = posts.get(key)
        if not meta or not meta["files"]:
            raise ValueError("No images in this post.")
        src = meta["files"][0]
        before = load_image(src).convert("RGB")

        canvas = resize_contain(before, settings.sizes[0], settings.bg_color)
        wm_text = (meta["root"].wm_text or "").strip() or settings.default_wm_text
        after = add_center_watermark(
            canvas,
            text=wm_text,
            opacity_pct=settings.wm_opacity,
            scale_pct=settings.wm_scale_pct,
            fill_rgb=settings.wm_fill_color,
            stroke_rgb=settings.wm_stroke_color,
            stroke_width=settings.wm_stroke_width,
        )
        return before, after

    def start_batch(
        self,
        settings: AppSettings,
        posts: Dict[str, dict],
        progress_cb: Callable[[int], None],
        done_cb: Callable[[int], None],
        error_cb: Callable[[str], None] | None = None,
    ):
        import threading
        total = sum(len(meta["files"]) for meta in posts.values()) * len(settings.sizes)
        self._processed = 0

        def worker():
            try:
                for key, meta in posts.items():
                    post = meta["post_name"]
                    rc: RootConfig = meta["root"]
                    wm_text = (rc.wm_text or "").strip() or settings.default_wm_text
                    for src in meta["files"]:
                        for (w, h) in settings.sizes:
                            try:
                                img = self._process_image(src, (w, h), settings, wm_text)
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

    def _process_image(self, src: Path, target: Tuple[int, int], settings: AppSettings, wm_text: str) -> Image.Image:
        im = load_image(src)
        canvas = resize_contain(im, target, settings.bg_color)
        out = add_center_watermark(
            canvas,
            text=wm_text,
            opacity_pct=settings.wm_opacity,
            scale_pct=settings.wm_scale_pct,
            fill_rgb=settings.wm_fill_color,
            stroke_rgb=settings.wm_stroke_color,
            stroke_width=settings.wm_stroke_width,
        )
        return out

# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Tuple, Callable
from PIL import Image

from settings import AppSettings, RootConfig
from services.discovery import scan_posts
from services.image_ops import load_image
from services.resize import resize_contain
from services.watermark import add_text_watermark
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

    def preview_by_key(self, key: str, posts: Dict[str, dict], settings: AppSettings):
        meta = posts.get(key)
        if not meta or not meta["files"]:
            raise ValueError("No images in this post.")
        src = meta["files"][0]
        before = load_image(src).convert("RGB")

        # ✅ (0,0) 이면 리사이즈 생략(원본 크기)
        tgt = settings.sizes[0]
        if tuple(tgt) == (0, 0):
            canvas = before.copy()
        else:
            canvas = resize_contain(before, tgt, settings.bg_color)

        wm_text = (meta["root"].wm_text or "").strip() or settings.default_wm_text
        anchor = meta.get("anchor") or settings.wm_anchor  # ✅ 세션 내 anchor만 사용
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
                    rc: RootConfig = meta["root"]
                    post = meta["post_name"]
                    root_label = rc.path.name
                    wm_text = (rc.wm_text or "").strip() or settings.default_wm_text
                    anchor = meta.get("anchor") or settings.wm_anchor  # ✅ 세션 anchor

                    for src in meta["files"]:
                        for (w, h) in settings.sizes:
                            try:
                                img = self._process_image(src, (w, h), settings, wm_text, anchor)
                                size_folder = "original" if (w, h) == (0, 0) else f"{w}x{h}"  # ✅ 폴더명
                                dst = (
                                        settings.output_root
                                        / root_label
                                        / post
                                        / size_folder
                                        / f"{src.stem}_wm.jpg"
                                )
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

    def _process_image(self, src: Path, target: Tuple[int, int], settings: AppSettings, wm_text: str,
                       anchor) -> Image.Image:
        im = load_image(src).convert("RGB")
        # ✅ (0,0) 이면 리사이즈 생략
        if tuple(target) == (0, 0):
            canvas = im
        else:
            canvas = resize_contain(im, target, settings.bg_color)
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

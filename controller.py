from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Tuple, Callable, Optional
from PIL import Image

from settings import AppSettings, RootConfig
from services.discovery import scan_posts
from services.image_ops import load_image
from services.resize import resize_contain
from services.watermark import add_text_watermark
from services.writer import save_image  # ✅ save_image 사용

class AppController:
    def __init__(self):
        self._processed = 0

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
                    key = root.name                  # 이 폴더 자체가 게시물
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
                    "post_dir": post_dir,            # 저장시 사용할 실제 폴더
                }
        return posts

    def _choose_anchor(self, meta: dict, settings: AppSettings, src: Optional[Path] = None):
        # 우선순위: 이미지 앵커 > 게시물 앵커 > 기본 앵커
        if src is not None:
            img_map = meta.get("img_anchors") or {}
            if src in img_map:
                return img_map[src]
        if meta.get("anchor"):
            return meta["anchor"]
        return settings.wm_anchor

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
        before = load_image(src).convert("RGB")

        tgt = settings.sizes[0]
        if tuple(tgt) == (0, 0):  # 원본 그대로
            canvas = before.copy()
        else:
            canvas = resize_contain(before, tgt, settings.bg_color)

        wm_text = (meta["root"].wm_text or "").strip() or settings.default_wm_text
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

    def start_batch(
        self,
        settings: AppSettings,
        posts: Dict[str, dict],
        progress_cb, done_cb, error_cb=None,
    ):
        import threading
        total = sum(len(meta["files"]) for meta in posts.values()) * len(settings.sizes)
        self._processed = 0

        def worker():
            try:
                for key, meta in posts.items():
                    rc: RootConfig = meta["root"]
                    post_dir: Path = meta.get("post_dir") or (rc.path / meta["post_name"])
                    wm_text = (rc.wm_text or "").strip() or settings.default_wm_text

                    # ✅ 항상 게시물 폴더에 저장
                    base_dir = post_dir

                    for src in meta["files"]:
                        for (w, h) in settings.sizes:
                            try:
                                anchor = self._choose_anchor(meta, settings, src)
                                img = self._process_image(src, (w, h), settings, wm_text, anchor)
                                dst = base_dir / f"{src.stem}_wm.jpg"   # ✅ 사이즈 하위폴더 없음
                                save_image(img, dst)
                            except Exception as e:
                                if error_cb: error_cb(f"{src} {w}x{h}: {e}")
                            finally:
                                self._processed += 1
                                if progress_cb: progress_cb(self._processed)
                if done_cb: done_cb(self._processed)
            except Exception as e:
                if error_cb: error_cb(str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _process_image(self, src: Path, target: Tuple[int, int],
                       settings: AppSettings, wm_text: str, anchor) -> Image.Image:
        im = load_image(src).convert("RGB")
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

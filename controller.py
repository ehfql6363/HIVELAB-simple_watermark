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

    def _resolve_wm_text(self, rc: RootConfig, settings: AppSettings) -> Optional[str]:
        """
        None -> 기본값 사용
        ""(빈 문자열) -> 비활성화
        그 외 문자열 -> 그대로 사용
        """
        raw = getattr(rc, "wm_text", None)
        if raw is None:
            t = (settings.default_wm_text or "").strip()
            return t if t else None
        t = (raw or "").strip()
        return t if t else None

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

        canvas = before.copy() if tuple(tgt) == (0, 0) else resize_contain(before, tgt, settings.bg_color)

        wm_text = self._resolve_wm_text(meta["root"], settings)
        anchor = self._choose_anchor(meta, settings, src)

        if wm_text:  # 텍스트가 있을 때만 적용
            after = add_text_watermark(
                canvas, text=wm_text,
                opacity_pct=settings.wm_opacity, scale_pct=settings.wm_scale_pct,
                fill_rgb=settings.wm_fill_color, stroke_rgb=settings.wm_stroke_color,
                stroke_width=settings.wm_stroke_width, anchor_norm=anchor,
                font_path=settings.wm_font_path,
            )
        else:
            after = canvas.copy()
        return before, after

    def start_batch(self, settings, posts, progress_cb, done_cb, error_cb=None):
        import threading
        total = sum(len(meta["files"]) for meta in posts.values()) * len(settings.sizes)
        self._processed = 0

        def _output_dir_for(src: Path, rc, out_root: Path, post_name: str) -> Path:
            """
            출력 경로: out_root / rc.path.name / (src.parent relative to rc.path)
            - 계정/게시물 업로드:  out_root/계정/게시물
            - 게시물만 업로드:    out_root/게시물
            - 게시물 내부에 더 깊은 하위 폴더가 있으면 그 구조도 그대로 보존
            """
            base = out_root / rc.path.name
            try:
                rel = src.parent.relative_to(rc.path)
            except Exception:
                # 혹시 relative_to 실패하면 최소한 post_name 폴더는 유지
                rel = Path(post_name) if (rc.path / post_name).exists() else Path()
            return (base / rel) if str(rel) not in ("", ".") else base

        def worker():
            try:
                for key, meta in posts.items():
                    rc = meta["root"]
                    wm_text = self._resolve_wm_text(rc, settings)  # ← 여기!

                    for src in meta["files"]:
                        for (w, h) in settings.sizes:
                            try:
                                anchor = self._choose_anchor(meta, settings, src)
                                im = self._process_image(src, (w, h), settings, wm_text, anchor)

                                out_dir = _output_dir_for(src, rc, settings.output_root, post)
                                dst = out_dir / f"{src.stem}_wm.jpg"
                                save_image(im, dst, quality=92)  # ← 폴더 생성 포함

                            except Exception as e:
                                if error_cb: error_cb(f"{src} {w}x{h}: {e}")
                            finally:
                                self._processed += 1
                                if progress_cb: progress_cb(self._processed)
                if done_cb: done_cb(self._processed)
            except Exception as e:
                if error_cb: error_cb(str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _process_image(self, src, target, settings, wm_text, anchor) -> Image.Image:
        im = load_image(src).convert("RGB")
        canvas = im if tuple(target) == (0, 0) else resize_contain(im, target, settings.bg_color)
        if not wm_text:  # ← 비어있으면 워터마크 적용 안 함
            return canvas
        return add_text_watermark(
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

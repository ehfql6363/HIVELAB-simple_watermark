# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Tuple, Callable, Optional
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

from PIL import Image

from settings import AppSettings, RootConfig, DEFAULT_WM_TEXT
from services.discovery import scan_posts, IMG_EXTS
from services.image_ops import load_image
from services.resize import resize_contain
from services.watermark import add_text_watermark
from services.writer import save_image  # 고속 저장

IMG_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}

class AppController:
    def __init__(self):
        self._processed = 0
        self._canvas_cache: "OrderedDict[tuple, Image.Image]" = OrderedDict()
        self._canvas_cache_limit = 64

    def _resolve_wm_text(self, rc: RootConfig, settings: AppSettings) -> str:
        if getattr(rc, "wm_text", None) is not None and str(rc.wm_text).strip() == "":
            return ""
        if (getattr(rc, "wm_text", "") or "").strip():
            return str(rc.wm_text).strip()
        return (settings.default_wm_text or "").strip()

    # ---------- 스캔 ----------
    def scan_posts_multi(self, roots: List[RootConfig], loose_images: Optional[List[Path]] = None) -> Dict[str, dict]:
        posts: Dict[str, dict] = {}

        # 1) 루트들 스캔
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
                    "post_dir": post_dir,
                }

        # 2) 느슨한(폴더 밖) 이미지 → '이미지' 가상 게시물
        if loose_images:
            valid = [p for p in loose_images if p.exists() and p.is_file() and p.suffix.lower() in IMG_EXTS]
            valid = sorted(set(valid), key=lambda p: (p.parent, p.name.lower()))
            if valid:
                # wm_text=None → 기본값 사용, ""이면 비활성화가 되니 None 추천
                posts["이미지"] = {
                    "root": RootConfig(path=Path("__LOOSE__"), wm_text=None),
                    "post_name": "이미지",
                    "files": valid,
                    "post_dir": Path("."),   # 의미 없음 (저장은 out_root 바로 아래)
                    "is_loose": True,
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
        if key in self._canvas_cache:
            im = self._canvas_cache.pop(key)
            self._canvas_cache[key] = im
            return im

        base = load_image(src)  # RGB Image 보장
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
        # ✅ 느슨한 이미지는 out_root 바로 아래에 저장
        try:
            if rc.path.name == "__LOOSE__":
                return out_root
        except Exception:
            pass

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
            out_dir = self._output_dir_for(src, rc, settings.output_root, meta["post_name"], bool(meta.get("is_loose")))
            dst = out_dir / f"{src.stem}_wm.jpg"
            save_image(out_img, dst, quality=90, optimize=False, progressive=False)

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

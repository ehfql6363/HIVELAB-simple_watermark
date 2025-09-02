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

        self._rev = 0
        self._posts_ref: Dict[str, dict] | None = None

    # ---------- 내부 유틸 ----------
    def attach_posts(self, posts: Dict[str, dict]) -> None:
        """MainWindow가 소유한 posts 딕셔너리를 컨트롤러에 연결해 둔다."""
        self._posts_ref = posts

    def _next_rev(self) -> int:
        self._rev += 1
        return self._rev

    @staticmethod
    def _to_rgb(value):
        """#RRGGBB / (r,g,b) / [r,g,b] → (r,g,b) 정규화."""
        if isinstance(value, (list, tuple)) and len(value) == 3:
            return (int(value[0]), int(value[1]), int(value[2]))
        s = str(value or "").strip()
        if not s:
            return (0, 0, 0)
        if s.startswith("#"):
            s = s[1:]
        if len(s) == 3:
            s = "".join(c * 2 for c in s)
        try:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
        except Exception:
            return (0, 0, 0)

    def set_post_overrides(self, post_key: str, changes: dict | None):
        """
        게시물 단위 오버라이드 저장 (필드별 latest-wins rev 부여).
        changes 가 빈 dict/None 이면 오버라이드 제거.
        허용 필드: text, font_path, scale(=scale_pct), opacity, fill, stroke, stroke_w
        """
        posts = self._posts_ref or {}
        meta = posts.get(post_key)
        if not meta:
            return
        if not changes:
            meta.pop("post_overrides", None)
            meta.pop("post_overrides_rev", None)
            return

        po = meta.setdefault("post_overrides", {})
        pr = meta.setdefault("post_overrides_rev", {})
        for k, v in changes.items():
            if k in ("fill", "stroke"):
                v = self._to_rgb(v)
            if k == "scale":
                k = "scale_pct"
            po[k] = v
            pr[k] = self._next_rev()

    def clear_post_overrides(self, post_key: str):
        posts = self._posts_ref or {}
        meta = posts.get(post_key)
        if not meta:
            return
        meta.pop("post_overrides", None)
        meta.pop("post_overrides_rev", None)

    def set_image_override(self, post_key: str, path, field: str, value):
        posts = self._posts_ref or {}
        meta = posts.get(post_key)
        if not meta:
            return
        io = meta.setdefault("img_overrides", {})
        ir = meta.setdefault("img_overrides_rev", {})
        img_o = io.setdefault(path, {})
        img_r = ir.setdefault(path, {})

        if field in ("fill", "stroke") and value is not None:
            value = self._to_rgb(value)
        if field == "scale":
            field = "scale_pct"

        if value is None:
            img_o.pop(field, None)
            img_r.pop(field, None)
            if not img_o:
                io.pop(path, None)
                ir.pop(path, None)
        else:
            img_o[field] = value
            img_r[field] = self._next_rev()

        # ☆ 사용자가 개별 텍스트를 손대면, 더 이상 "게시물에서 뿌린 텍스트"가 아님
        if field == "text":
            m = meta.get("img_text_from_post_rev")
            if isinstance(m, dict) and path in m:
                m.pop(path, None)
                if not m:
                    meta.pop("img_text_from_post_rev", None)

    def clear_image_overrides(self, post_key: str, path):
        posts = self._posts_ref or {}
        meta = posts.get(post_key)
        if not meta:
            return
        io = meta.get("img_overrides") or {}
        ir = meta.get("img_overrides_rev") or {}
        io.pop(path, None)
        ir.pop(path, None)
        if not io:
            meta.pop("img_overrides", None)
        if not ir:
            meta.pop("img_overrides_rev", None)

    def reset_post_scope(self, post_key: str, settings) -> None:
        """
        게시물 옵션 초기화(롤백):
        - 게시물 오버라이드 제거
        - 각 이미지에 '설정 전(글로벌/루트 기본값)'을 명시적으로 다시 써주되,
          rev는 새로 크게 발급하여 최신-우선 규칙에서 이기게 함.
        - 적용 필드: text, font_path, scale_pct, fill, stroke, stroke_w
        - 레거시 인라인 텍스트/마커는 정리
        """
        posts = self._posts_ref or {}
        meta = posts.get(post_key)
        if not meta:
            return

        # 0) 롤백 기준값(설정 전): 루트/글로벌에서 계산
        root = meta.get("root")
        base_text = ""
        try:
            root_text = getattr(root, "wm_text", None) if root is not None else None
            base_text = (root_text if root_text is not None else settings.default_wm_text) or ""
            base_text = str(base_text).strip()
        except Exception:
            pass

        base = {
            "text": base_text,
            "font_path": str(getattr(settings, "wm_font_path", "") or ""),
            "scale_pct": int(getattr(settings, "wm_scale_pct", 18)),
            "fill": tuple(getattr(settings, "wm_fill_color", (0, 0, 0))),
            "stroke": tuple(getattr(settings, "wm_stroke_color", (255, 255, 255))),
            "stroke_w": int(getattr(settings, "wm_stroke_width", 2)),
        }

        # 1) 게시물 오버라이드 제거
        meta.pop("post_overrides", None)
        meta.pop("post_overrides_rev", None)

        # 2) 레거시 인라인/마커 정리
        meta.pop("img_wm_text_edits", None)
        meta.pop("img_text_from_post_rev", None)

        # 3) 각 이미지에 '롤백 기본값'을 새 rev로 강제 적용 (텍스트/폰트/스케일/색)
        files = list(meta.get("files") or [])
        for p in files:
            # 텍스트
            self.set_image_override(post_key, p, "text", base["text"])
            # 폰트
            self.set_image_override(post_key, p, "font_path", base["font_path"])
            # 스케일
            self.set_image_override(post_key, p, "scale_pct", base["scale_pct"])
            # 색상 (글자색/외곽선/굵기/불투명)
            self.set_image_override(post_key, p, "fill", base["fill"])
            self.set_image_override(post_key, p, "stroke", base["stroke"])
            self.set_image_override(post_key, p, "stroke_w", base["stroke_w"])
            self.set_image_override(post_key, p, "opacity", int(getattr(settings, "wm_opacity", 60)))


    def apply_post_text_to_all_images(self, post_key: str):
        """게시물 오버라이드의 text를 모든 이미지에 복사하고, 출처 rev를 마킹."""
        posts = self._posts_ref or {}
        meta = posts.get(post_key)
        if not meta:
            return

        po = meta.get("post_overrides") or {}
        pr = meta.get("post_overrides_rev") or {}
        text = (po.get("text") or "").strip()
        if text == "":
            return
        post_text_rev = int(pr.get("text", self._rev))

        files = list(meta.get("files") or [])
        if not files:
            return

        mark = meta.setdefault("img_text_from_post_rev", {})
        for p in files:
            # 텍스트 복사(이미지별 새 rev 발행)
            self.set_image_override(post_key, p, "text", text)
            # 출처 rev 기록
            mark[p] = post_text_rev

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
    def resolve_wm_config(self, meta: dict, settings: AppSettings, src: Optional[Path]) -> Optional[dict]:
        """
        최신-우선(latest-wins) 병합.
        각 필드(text, font_path, scale_pct, opacity, fill, stroke, stroke_w)에 대해
        이미지/게시물/루트/전역의 'rev'를 비교하여 가장 최근 rev의 value를 채택.
        - 전역 settings: rev=-2
        - 루트 text(없으면 전역 text): rev=-1 (text만)
        - 레거시 인라인(meta["img_wm_text_edits"], meta["wm_text_edit"]): rev=0 (text만)
        - 게시물/이미지 오버라이드: 저장된 rev 사용
        텍스트가 ""(빈문자)면 워터마크 없음 → None 반환.
        """
        # 0) 전역 기본값 (rev=-2)
        g = {
            "text": (settings.default_wm_text or "").strip(),
            "font_path": str(settings.wm_font_path) if settings.wm_font_path else "",
            "scale_pct": int(settings.wm_scale_pct),
            "opacity": int(settings.wm_opacity),
            "fill": tuple(settings.wm_fill_color),
            "stroke": tuple(settings.wm_stroke_color),
            "stroke_w": int(settings.wm_stroke_width),
        }
        g_rev = {k: -2 for k in g.keys()}

        # 1) 루트 텍스트 (rev=-1, text만)
        root = meta.get("root")
        if root is not None:
            root_text = getattr(root, "wm_text", None)
            if root_text is None:
                root_text = g["text"]
            r_text = (root_text or "").strip()
        else:
            r_text = g["text"]
        r_rev = -1

        # 2) 게시물 오버라이드
        po = meta.get("post_overrides") or {}
        pr = meta.get("post_overrides_rev") or {}

        # 3) 이미지 오버라이드
        if src is not None:
            io_all = meta.get("img_overrides") or {}
            ir_all = meta.get("img_overrides_rev") or {}
            io = io_all.get(src) or {}
            ir = ir_all.get(src) or {}
        else:
            io, ir = {}, {}

        # 4) 레거시 인라인(항상 rev=0) — text만
        legacy_img_text = None
        if src is not None:
            imgs_map = meta.get("img_wm_text_edits") or {}
            if src in imgs_map:
                legacy_img_text = (imgs_map[src] or "").strip()
        legacy_post_text = (meta.get("wm_text_edit") or "").strip() if ("wm_text_edit" in meta) else None

        # 필드별 후보를 rev와 함께 모아 선택
        def choose(field, is_text=False):
            candidates = []
            # 전역
            candidates.append((g[field], g_rev[field], 5))  # tie-break idx

            # 루트(text만)
            if is_text:
                candidates.append((r_text, r_rev, 4))

            # 게시물 오버라이드
            if field in po:
                candidates.append((po[field], int(pr.get(field, 0)), 2))

            # 이미지 오버라이드
            if field in io:
                candidates.append((io[field], int(ir.get(field, 0)), 1))

            # 레거시 인라인(text만)
            if is_text:
                if legacy_img_text is not None:
                    candidates.append((legacy_img_text, 0, 0))  # 이미지 인라인
                if legacy_post_text is not None:
                    candidates.append((legacy_post_text, 0, 3))

            # rev 최대 → 동률이면 tie-break가 낮은 것
            best_val, best_rev, best_tb = None, -9999, 99
            for val, rev, tb in candidates:
                if rev > best_rev or (rev == best_rev and tb < best_tb):
                    best_val, best_rev, best_tb = val, rev, tb
            return best_val

        text = choose("text", is_text=True)
        if (text or "").strip() == "":
            return None

        cfg = {
            "text": (text or "").strip(),
            "font_path": str(choose("font_path") or ""),
            "scale_pct": int(choose("scale_pct")),
            "opacity": int(choose("opacity")),
            "fill": tuple(choose("fill")),
            "stroke": tuple(choose("stroke")),
            "stroke_w": int(choose("stroke_w")),
        }
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
    def preview_by_key(self, key: str, posts: Dict[str, dict], settings: AppSettings,
                       selected_src: Optional[Path] = None) -> tuple[Image.Image, Image.Image]:
        meta = posts.get(key)
        if not meta or not meta["files"]:
            raise ValueError("No images in this post.")
        src = selected_src or meta["files"][0]

        # ✅ 원본은 항상 '그대로' (EXIF 회전/색공간 변환된 RGB) + 방어적 copy()
        before = load_image(src).copy()

        tgt = settings.sizes[0]
        # 적용쪽만 타겟 캔버스로
        if tuple(tgt) == (0, 0):
            canvas = before.copy()
        else:
            canvas = self._get_resized_canvas(src, tgt, settings.bg_color).copy()

        wm_cfg = self.resolve_wm_config(meta, settings, src)
        if not wm_cfg:
            return before, canvas  # 워터마크 없음

        anchor = self._choose_anchor(meta, settings, src)
        after = add_text_watermark(
            canvas,
            text=wm_cfg["text"],
            opacity_pct=int(wm_cfg["opacity"]),
            scale_pct=int(wm_cfg["scale_pct"]),
            fill_rgb=tuple(wm_cfg["fill"]),
            stroke_rgb=tuple(wm_cfg["stroke"]),
            stroke_width=int(wm_cfg["stroke_w"]),
            anchor_norm=anchor,
            font_path=Path(wm_cfg["font_path"]) if wm_cfg.get("font_path") else None,
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

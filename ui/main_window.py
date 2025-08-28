# -*- coding: utf-8 -*-
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox
from typing import Dict, Optional, Tuple

from controller import AppController
from settings import AppSettings, DEFAULT_WM_TEXT, hex_to_rgb, RootConfig, IMAGES_VROOT
from ui.options_panel import OptionsPanel
from ui.post_list import PostList
from ui.preview_pane import PreviewPane
from ui.thumb_gallery import ThumbGallery
from ui.status_bar import StatusBar
from ui.image_wm_editor import ImageWMEditor  # ★ 분리된 에디터

# 이미지 처리 유틸 (개별 오버라이드 미리보기 계산용)
from services.image_ops import load_image
from services.resize import resize_contain
from services.watermark import add_text_watermark

# DnD 지원 루트
try:
    from tkinterdnd2 import TkinterDnD  # type: ignore
    class BaseTk(TkinterDnD.Tk): ...
except Exception:
    class BaseTk(tk.Tk): ...

class MainWindow(BaseTk):
    def __init__(self, controller: AppController):
        super().__init__()
        self.title("게시물 워터마크 & 리사이즈")
        self.geometry("1180x860")
        # 창 너무 작아질 때 하단 상태바가 가려지지 않도록 최소 크기
        try: self.minsize(1024, 720)
        except Exception: pass

        self.controller = controller
        self.posts: Dict[str, dict] = {}

        self.app_settings = AppSettings.load()
        self._wm_anchor: Tuple[float, float] = tuple(self.app_settings.wm_anchor)
        self._active_src: Optional[Path] = None

        # 루트 시그니처(루트 목록이 바뀌면 자동 스캔 대체 등록)
        self._roots_sig: Tuple[Tuple[str, str], ...] = tuple()

        # ── 상단 옵션(출력/워터마크/루트 목록) ───────────────────────────────
        self.header = ttk.Frame(self)
        self.header.pack(side="top", fill="x", padx=8, pady=(8, 0))
        self._build_header(self.header)

        # ── 중간: 좌(게시물+에디터) / 우(프리뷰+썸네일) ─────────────────────
        self._build_middle(self)

        # ── 하단 상태바 ───────────────────────────────────────────────────
        self.status = StatusBar(self, on_start=self.on_start_batch)
        self.status.pack(side="bottom", fill="x", padx=8, pady=8)

        # 옵션 패널 초기값 채우기
        self.opt.set_initial_options(self.app_settings)

        if self.app_settings.output_root and not self.opt.var_output.get().strip():
            self.opt.var_output.set(str(self.app_settings.output_root))

        if self.app_settings.wm_font_path and not self.opt.var_font.get().strip():
            self.opt.var_font.set(str(self.app_settings.wm_font_path))

        # 최초 옵션 반영 → 루트 변경 감지로 게시물 등록
        self._on_options_changed()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ──────────────────────────────────────────────────────────────────────
    # 빌드
    # ──────────────────────────────────────────────────────────────────────
    def _build_header(self, parent: ttk.Frame):
        # 버튼바(스캔/미리보기) 제거 요구사항 반영 → 오직 옵션 패널만
        self.opt = OptionsPanel(parent, on_change=self._on_options_changed)
        self.opt.pack(fill="x")

    def _build_middle(self, parent):
        # 가로 분할: 좌(게시물+에디터) / 우(프리뷰+썸네일)
        mid = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        mid.pack(fill="both", expand=True, padx=8, pady=(8, 8))

        # 좌: 세로 분할(게시물, 에디터)
        left = ttk.PanedWindow(mid, orient=tk.VERTICAL)
        mid.add(left, weight=1)

        # ── 게시물(트리) ──
        post_frame = ttk.Frame(left)
        self.post_list = PostList(
            post_frame,
            on_select=self.on_select_post,
        )
        self.post_list.pack(fill="both", expand=True)
        left.add(post_frame, weight=3)

        # ── 개별 이미지 워터마크 에디터(분리) ──
        editor_frame = ttk.Frame(left)
        self.wm_editor = ImageWMEditor(
            editor_frame,
            on_apply=self._on_image_wm_override,
            on_clear=self._on_image_wm_clear
        )
        self.wm_editor.pack(fill="x", expand=False, pady=(6, 0))
        left.add(editor_frame, weight=2)

        # 우: 세로 분할(프리뷰, 썸네일)
        right = ttk.PanedWindow(mid, orient=tk.VERTICAL)
        mid.add(right, weight=4)

        # PreviewPane
        pre_frame = ttk.Frame(right)
        self.preview = PreviewPane(
            pre_frame,
            on_anchor_change=self._on_anchor_change,
            on_apply_all=self._on_apply_all,
            on_clear_individual=self._on_clear_individual
        )
        self.preview.pack(fill="both", expand=True)
        right.add(pre_frame)  # weight만 사용

        # ThumbGallery
        gal_frame = ttk.Frame(right)
        # pack_propagate(False) 사용 금지(0px로 눌릴 수 있음)
        self.gallery = ThumbGallery(
            gal_frame,
            on_activate=self._on_activate_image,
            thumb_size=168, cols=6, height=200  # 방법 C: 내부 높이 힌트
        )
        self.gallery.pack(fill="x", expand=False)
        right.add(gal_frame)

        # 오른쪽 PanedWindow에 ‘사이즈 최소치’ 강제 (minsize 대용)
        MIN_PREVIEW, MIN_GALLERY = 360, 180
        self._right_sash_job = None

        def _apply_right_sash():
            self._right_sash_job = None
            try:
                total = right.winfo_height()
                if total <= 0:
                    return
                pos = right.sashpos(0)
                lo = MIN_PREVIEW
                hi = max(MIN_PREVIEW, total - MIN_GALLERY)
                pos = min(max(pos, lo), hi)
                if pos != right.sashpos(0):
                    right.sashpos(0, pos)
            except Exception:
                pass

        def _debounced_enforce(_=None):
            if self._right_sash_job:
                try: self.after_cancel(self._right_sash_job)
                except Exception: pass
            self._right_sash_job = self.after(60, _apply_right_sash)

        right.bind("<Configure>", _debounced_enforce)
        self.after(0, _apply_right_sash)

    # ──────────────────────────────────────────────────────────────────────
    # 옵션/루트 변경 → 게시물 등록(스캔 버튼 삭제를 대체)
    # ──────────────────────────────────────────────────────────────────────
    def _roots_signature(self, roots: list[RootConfig]) -> Tuple[Tuple[str, str], ...]:
        sig = []
        for rc in roots:
            path_str = str(rc.path)
            wm = (rc.wm_text or "").strip()
            sig.append((path_str, wm))
        return tuple(sig)

    def _rebuild_posts_from_roots(self):
        roots = self.opt.get_roots()
        dropped = self.opt.get_dropped_images()
        self.posts = self.controller.scan_posts_multi(roots, dropped_images=dropped)
        # 트리 갱신
        if hasattr(self.post_list, "set_posts"):
            self.post_list.set_posts(self.posts)
        # 갤러리/프리뷰 초기화
        self._active_src = None
        self.gallery.clear()
        self.preview.clear()
        self.preview.set_anchor(tuple(self.app_settings.wm_anchor))
        self.wm_editor.set_active_image_and_defaults(None, None)

    def _on_options_changed(self):
        (sizes, bg_hex, wm_opacity, wm_scale, out_root_str, roots,
         wm_fill_hex, wm_stroke_hex, wm_stroke_w, wm_font_path_str) = self.opt.collect_options()
        recent_out, recent_font = self.opt.get_recent_dirs()

        s = self.app_settings
        s.output_root = Path(out_root_str) if out_root_str else s.output_root
        s.sizes = sizes
        s.bg_color = hex_to_rgb(bg_hex or "#FFFFFF")
        s.wm_opacity = int(wm_opacity)
        s.wm_scale_pct = int(wm_scale)
        s.wm_fill_color = hex_to_rgb(wm_fill_hex or "#000000")
        s.wm_stroke_color = hex_to_rgb(wm_stroke_hex or "#FFFFFF")
        s.wm_stroke_width = int(wm_stroke_w)
        s.wm_font_path = Path(wm_font_path_str) if wm_font_path_str else None
        if recent_out: s.last_dir_output_dialog = recent_out
        if recent_font: s.last_dir_font_dialog = recent_font
        try: s.save()
        except Exception: pass

        # 루트 변경 감지 → 게시물 즉시 반영
        sig = self._roots_signature(roots)
        if sig != self._roots_sig:
            self._roots_sig = sig
            self._rebuild_posts_from_roots()

    # ──────────────────────────────────────────────────────────────────────
    # 좌측: 게시물 선택/이미지 선택
    # ──────────────────────────────────────────────────────────────────────
    def on_select_post(self, key: Optional[str]):
        self._active_src = None
        if not key or key not in self.posts:
            self.gallery.clear()
            self.preview.clear()
            self.wm_editor.set_active_image_and_defaults(None, None)
            return

        meta = self.posts[key]
        files = meta.get("files", [])
        default_anchor = tuple(meta.get("anchor") or self.app_settings.wm_anchor)
        img_map = meta.get("img_anchors") or {}
        self.gallery.set_files(files, default_anchor=default_anchor, img_anchor_map=img_map)
        self.gallery.set_active(None)
        self._wm_anchor = default_anchor

        # 새 게시물 선택 시, 에디터는 비움
        self.wm_editor.set_active_image_and_defaults(None, None)
        self.on_preview()

    def _on_activate_image(self, path: Path):
        self._active_src = path
        self.gallery.set_active(path)

        key = self.post_list.get_selected_post()
        if not key or key not in self.posts:
            return
        meta = self.posts[key]
        overrides = meta.get("img_overrides") or {}
        cfg = overrides.get(path)

        # 에디터에 현재 이미지/기본값 반영
        self.wm_editor.set_active_image_and_defaults(path, cfg)
        self.on_preview()

    # ──────────────────────────────────────────────────────────────────────
    # 프리뷰 (개별 오버라이드 지원)
    # ──────────────────────────────────────────────────────────────────────
    def on_preview(self):
        key = self.post_list.get_selected_post()
        if not key:
            return
        if key not in self.posts or not self.posts[key]["files"]:
            messagebox.showinfo("미리보기", "이 게시물에는 이미지가 없습니다.")
            return

        settings = self._collect_settings()
        meta = self.posts[key]

        # 워터마크 텍스트(루트 설정 우선)
        _raw = meta["root"].wm_text
        _root_txt = ("" if _raw is None else _raw.strip())
        wm_text_default = "" if _root_txt == "" else (_root_txt or settings.default_wm_text)

        # 프리뷰 오버레이(유령) 설정
        wm_cfg_overlay = None
        if wm_text_default:
            wm_cfg_overlay = {
                "text": wm_text_default,
                "opacity": settings.wm_opacity,
                "scale_pct": settings.wm_scale_pct,
                "fill": settings.wm_fill_color,
                "stroke": settings.wm_stroke_color,
                "stroke_w": settings.wm_stroke_width,
                "font_path": str(settings.wm_font_path) if settings.wm_font_path else "",
            }

        # 개별 이미지 오버라이드(있으면 프리뷰/유령 모두 해당 설정 우선)
        active_src = self._active_src
        overrides = meta.get("img_overrides") or {}
        ov = overrides.get(active_src) if active_src else None
        if ov:
            wm_cfg_overlay = {
                "text": ov.get("text", ""),
                "opacity": int(ov.get("opacity", settings.wm_opacity)),
                "scale_pct": int(ov.get("scale_pct", settings.wm_scale_pct)),
                "fill": tuple(ov.get("fill", settings.wm_fill_color)),
                "stroke": tuple(ov.get("stroke", settings.wm_stroke_color)),
                "stroke_w": int(ov.get("stroke_w", settings.wm_stroke_width)),
                "font_path": ov.get("font_path", str(settings.wm_font_path) if settings.wm_font_path else ""),
            }

        self.preview.set_wm_preview_config(wm_cfg_overlay)

        # 앵커(개별 → 게시물 → 앱 기본)
        img_anchor_map = meta.get("img_anchors") or {}
        if active_src and active_src in img_anchor_map:
            anchor = tuple(img_anchor_map[active_src])
        elif meta.get("anchor"):
            anchor = tuple(meta["anchor"])
        else:
            anchor = tuple(self.app_settings.wm_anchor)
        self._wm_anchor = anchor

        # --- 프리뷰 이미지 생성 ---
        try:
            if ov and active_src:
                # 오버라이드가 있으면 수동 합성
                before = load_image(active_src)
                tgt = settings.sizes[0]
                canvas = before.copy() if tuple(tgt) == (0, 0) else resize_contain(before, tgt, settings.bg_color).copy()
                txt = (ov.get("text") or "").strip()
                if txt == "":
                    after = canvas
                else:
                    after = add_text_watermark(
                        canvas,
                        text=txt,
                        opacity_pct=int(ov.get("opacity", settings.wm_opacity)),
                        scale_pct=int(ov.get("scale_pct", settings.wm_scale_pct)),
                        fill_rgb=tuple(ov.get("fill", settings.wm_fill_color)),
                        stroke_rgb=tuple(ov.get("stroke", settings.wm_stroke_color)),
                        stroke_width=int(ov.get("stroke_w", settings.wm_stroke_width)),
                        anchor_norm=anchor,
                        font_path=Path(ov.get("font_path")) if ov.get("font_path") else settings.wm_font_path,
                    )
                before_img = load_image(active_src)  # 원본
                after_img = after
            else:
                # 기존 기본 프리뷰 경로
                before_img, after_img = self.controller.preview_by_key(
                    key, self.posts, settings, selected_src=active_src
                )
        except Exception as e:
            messagebox.showerror("미리보기 오류", str(e))
            return

        self.preview.show(before_img, after_img)
        self.preview.set_anchor(anchor)

    def _collect_settings(self) -> AppSettings:
        (sizes, bg_hex, wm_opacity, wm_scale, out_root_str, _roots,
         wm_fill_hex, wm_stroke_hex, wm_stroke_w, wm_font_path_str) = self.opt.collect_options()

        # 출력 루트 폴백
        if not out_root_str and self.app_settings.output_root:
            out_root = self.app_settings.output_root
        else:
            out_root = Path(out_root_str) if out_root_str else Path("")

        # 폰트 폴백
        if not wm_font_path_str and self.app_settings.wm_font_path:
            wm_font_path = self.app_settings.wm_font_path
        else:
            wm_font_path = Path(wm_font_path_str) if wm_font_path_str else None

        return AppSettings(
            output_root=out_root,
            sizes=sizes,
            bg_color=hex_to_rgb(bg_hex or "#FFFFFF"),
            wm_opacity=int(wm_opacity),
            wm_scale_pct=int(wm_scale),
            default_wm_text=DEFAULT_WM_TEXT,
            wm_fill_color=hex_to_rgb(wm_fill_hex or "#000000"),
            wm_stroke_color=hex_to_rgb(wm_stroke_hex or "#FFFFFF"),
            wm_stroke_width=int(wm_stroke_w),
            wm_anchor=self.app_settings.wm_anchor,
            wm_font_path=wm_font_path,
        )

    # ──────────────────────────────────────────────────────────────────────
    # 앵커 변경/적용/해제
    # ──────────────────────────────────────────────────────────────────────
    def _on_anchor_change(self, norm_xy):
        key = self.post_list.get_selected_post()
        if not key or key not in self.posts:
            return
        meta = self.posts[key]
        if self._active_src:
            img_map = meta.get("img_anchors")
            if img_map is None:
                img_map = meta["img_anchors"] = {}
            img_map[self._active_src] = (float(norm_xy[0]), float(norm_xy[1]))
        else:
            meta["anchor"] = (float(norm_xy[0]), float(norm_xy[1]))

        self._wm_anchor = (float(norm_xy[0]), float(norm_xy[1]))
        self._refresh_gallery_overlay(key)
        self.on_preview()

    def _on_apply_all(self, anchor):
        key = self.post_list.get_selected_post()
        if not key or key not in self.posts:
            return

        meta = self.posts[key]
        files = meta.get("files") or []
        img_map = meta.get("img_overrides") or {}  # 개별 오버라이드와 충돌 없음

        meta["anchor"] = (float(anchor[0]), float(anchor[1]))
        # 개별 지정 앵커는 손대지 않음
        self._refresh_gallery_overlay(key)
        self._wm_anchor = meta["anchor"]
        self.on_preview()

        messagebox.showinfo("모든 이미지에 적용", "기본 위치를 업데이트했습니다.")

    def _on_clear_individual(self):
        key = self.post_list.get_selected_post()
        if not key or key not in self.posts or not self._active_src:
            messagebox.showinfo("개별 지정 해제", "해제할 이미지를 먼저 선택하세요.")
            return
        meta = self.posts[key]
        img_map = meta.get("img_anchors") or {}
        if self._active_src in img_map:
            del img_map[self._active_src]
            if not img_map:
                meta["img_anchors"] = {}
            self._refresh_gallery_overlay(key)
            self.on_preview()
            messagebox.showinfo("개별 지정 해제", "현재 이미지가 게시물 기본 위치를 따르도록 복구되었습니다.")
        else:
            messagebox.showinfo("개별 지정 해제", "이 이미지에는 개별 지정이 없습니다.")

    def _refresh_gallery_overlay(self, key: str):
        meta = self.posts.get(key) or {}
        default_anchor = tuple(meta.get("anchor") or self.app_settings.wm_anchor)
        img_map = meta.get("img_anchors") or {}
        self.gallery.update_anchor_overlay(default_anchor, img_map)

    # ──────────────────────────────────────────────────────────────────────
    # 에디터 콜백(저장/해제)
    # ──────────────────────────────────────────────────────────────────────
    def _on_image_wm_override(self, path: Path, ov: dict):
        key = self.post_list.get_selected_post()
        if not key or key not in self.posts:
            return
        meta = self.posts[key]
        overrides = meta.setdefault("img_overrides", {})
        overrides[path] = ov
        self.on_preview()

    def _on_image_wm_clear(self, path: Path):
        key = self.post_list.get_selected_post()
        if not key or key not in self.posts:
            return
        meta = self.posts[key]
        overrides = meta.get("img_overrides") or {}
        try:
            del overrides[path]
        except Exception:
            pass
        self.on_preview()

    # ──────────────────────────────────────────────────────────────────────
    # 배치 시작
    # ──────────────────────────────────────────────────────────────────────
    def on_start_batch(self):
        if not self.posts:
            messagebox.showinfo("시작", "등록된 게시물이 없습니다.")
            return

        out_root_str = (self.opt.get_output_root_str() or "").strip()
        if not out_root_str and self.app_settings.output_root:
            out_root_str = str(self.app_settings.output_root)
        if not out_root_str:
            messagebox.showinfo("출력 폴더", "출력 루트 폴더를 먼저 지정하세요.")
            return

        settings = self._collect_settings()
        out_root = Path(out_root_str)
        try:
            out_root.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror("출력 폴더", f"출력 루트를 만들 수 없습니다:\n{e}")
            return

        self.status.set_output_root(out_root)
        self.status.enable_open_button(True)

        total = sum(len(meta["files"]) for meta in self.posts.values()) * len(settings.sizes)
        self.status.reset(total)

        def on_prog(n): self.status.update_progress(n)
        def on_done(n, _out=out_root):
            self.status.finish(n)
            self.status.log_info(f"저장 위치: {_out}")
            self.status.enable_open_button(True)
        def on_err(msg): self.status.log_error(msg)

        self.controller.start_batch(settings, self.posts, on_prog, on_done, on_err)

    def _on_close(self):
        try:
            self._on_options_changed()
        except Exception:
            pass
        self.destroy()

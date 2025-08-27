# -*- coding: utf-8 -*-
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox
from typing import Dict, Optional

from controller import AppController
from settings import AppSettings, DEFAULT_SIZES, DEFAULT_WM_TEXT, hex_to_rgb
from ui.options_panel import OptionsPanel
from ui.post_list import PostList
from ui.preview_pane import PreviewPane
from ui.scrollframe import ScrollFrame
from ui.status_bar import StatusBar
from ui.thumb_gallery import ThumbGallery

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

        self.controller = controller
        self.posts: Dict[str, dict] = {}

        self.app_settings = AppSettings.load()
        self._wm_anchor = tuple(self.app_settings.wm_anchor)
        self._active_src: Optional[Path] = None

        self.header = ScrollFrame(self, height=300)
        self.header.pack(side="top", fill="x", padx=8, pady=(6, 0))
        self._build_header(self.header.inner)

        self._build_middle(self)

        self.status = StatusBar(self, on_start=self.on_start_batch)
        self.status.pack(side="bottom", fill="x", padx=8, pady=8)

        self.opt.set_initial_options(self.app_settings)

        if self.app_settings.output_root and not self.opt.var_output.get().strip():
            self.opt.var_output.set(str(self.app_settings.output_root))

        if self.app_settings.wm_font_path and not self.opt.var_font.get().strip():
            self.opt.var_font.set(str(self.app_settings.wm_font_path))

        self._on_options_changed()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_header(self, parent):
        self.opt = OptionsPanel(parent, on_change=self._on_options_changed)
        self.opt.pack(fill="x", pady=(0, 6))

        tbar = ttk.Frame(parent)
        tbar.pack(fill="x", pady=(0, 6))
        ttk.Button(tbar, text="게시물 스캔", command=self.on_scan).pack(side="left")
        ttk.Button(tbar, text="미리보기", command=self.on_preview).pack(side="left", padx=6)

    def _on_apply_all(self, anchor):
        key = self.post_list.get_selected_post()
        if not key or key not in self.posts:
            return

        meta = self.posts[key]
        files = meta.get("files") or []
        img_map = meta.get("img_anchors") or {}

        meta["anchor"] = (float(anchor[0]), float(anchor[1]))

        if self._active_src and self._active_src in img_map:
            try:
                del img_map[self._active_src]
            except Exception:
                pass
            if not img_map:
                meta["img_anchors"] = {}

        self._refresh_gallery_overlay(key)
        self._wm_anchor = meta["anchor"]
        self.on_preview()

        total = len(files)
        overridden = len(img_map)
        affected = max(0, total - overridden)
        messagebox.showinfo(
            "모든 이미지에 적용",
            f"기본 위치를 업데이트했습니다.\n"
            f"- 총 이미지: {total}\n"
            f"- 개별 지정 제외: {overridden}\n"
            f"- 적용 대상: {affected}\n"
            f"(현재 보던 이미지는 기본 위치에 포함되었습니다.)"
        )

    def _build_middle(self, parent):
        mid = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        mid.pack(fill="both", expand=True)

        self.post_list = PostList(mid, on_select=self.on_select_post)
        mid.add(self.post_list, weight=1)

        right = ttk.PanedWindow(mid, orient=tk.VERTICAL)
        mid.add(right, weight=4)

        pre_frame = ttk.Frame(right)
        self.preview = PreviewPane(
            pre_frame,
            on_anchor_change=self._on_anchor_change,
            on_apply_all=self._on_apply_all,
            on_clear_individual = self._on_clear_individual
        )
        self.preview.pack(fill="both", expand=True)
        right.add(pre_frame, weight=5)

        gal_frame = ttk.Frame(right)
        gal_frame.pack_propagate(False)
        self.gallery = ThumbGallery(
            gal_frame,
            on_activate=self._on_activate_image,
            thumb_size=168, cols=6, height=240
        )
        self.gallery.pack(fill="x", expand=False)
        right.add(gal_frame, weight=1)

        MIN_PREVIEW, MIN_GALLERY = 360, 140
        self._sash_job = None

        def _apply_minsize():
            self._sash_job = None
            try:
                total = right.winfo_height()
                if total <= 0: return
                pos = right.sashpos(0)
                if pos < MIN_PREVIEW: pos = MIN_PREVIEW
                if (total - pos) < MIN_GALLERY:
                    pos = max(total - MIN_GALLERY, MIN_PREVIEW)
                if pos != right.sashpos(0):
                    right.sashpos(0, pos)
            except Exception:
                pass

        def _enforce(_=None):
            if self._sash_job:
                self.after_cancel(self._sash_job)
            self._sash_job = self.after(100, _apply_minsize)

        right.bind("<Configure>", _enforce)
        self.after(0, _apply_minsize)

    # ---- 콜백/로직 ----
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
        if recent_out:
            s.last_dir_output_dialog = recent_out
        if recent_font:
            s.last_dir_font_dialog = recent_font
        try:
            s.save()
        except Exception:
            pass

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

    def _collect_settings(self) -> AppSettings:
        (sizes, bg_hex, wm_opacity, wm_scale, out_root_str, _roots,
         wm_fill_hex, wm_stroke_hex, wm_stroke_w, wm_font_path_str) = self.opt.collect_options()

        # ✅ 출력 루트 폴백: 입력칸이 비어 있으면 저장돼 있던 경로 사용
        if not out_root_str and self.app_settings.output_root:
            out_root = self.app_settings.output_root
        else:
            out_root = Path(out_root_str) if out_root_str else Path("")

        # ✅ 폰트 폴백(이미 적용한 것과 동일)
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

    def on_scan(self):
        roots = self.opt.get_roots()
        if not roots:
            messagebox.showinfo("루트 폴더", "먼저 루트 폴더를 추가하세요.")
            return

        dropped = self.opt.get_dropped_images()
        self.posts = self.controller.scan_posts_multi(
            roots,
            dropped_images=dropped
        )
        self.post_list.set_posts(self.posts)
        # 초기화
        self._active_src = None
        self.gallery.clear()
        self.gallery.update_anchor_overlay((0.5, 0.5), {})

    def on_select_post(self, key: str | None):
        self._active_src = None
        if key and key in self.posts:
            meta = self.posts[key]
            files = meta.get("files", [])
            default_anchor = tuple(meta.get("anchor") or self.app_settings.wm_anchor)
            img_map = meta.get("img_anchors") or {}
            self.gallery.set_files(files, default_anchor=default_anchor, img_anchor_map=img_map)
            self.gallery.set_active(None)
            self._wm_anchor = default_anchor
            self.on_preview()

    def _on_activate_image(self, path: Path):
        self._active_src = path
        self.gallery.set_active(path)
        self.on_preview()

    def on_preview(self):
        key = self.post_list.get_selected_post()
        if not key:
            messagebox.showinfo("미리보기", "게시물을 하나 선택하세요.")
            return
        if key not in self.posts or not self.posts[key]["files"]:
            messagebox.showinfo("미리보기", "이 게시물에는 이미지가 없습니다.")
            return

        settings = self._collect_settings()
        meta = self.posts[key]

        _raw = meta["root"].wm_text
        _root_txt = ("" if _raw is None else _raw.strip())
        wm_text = "" if _root_txt == "" else (_root_txt or settings.default_wm_text)

        wm_cfg = None
        if wm_text:
            wm_cfg = {
                "text": wm_text,
                "opacity": settings.wm_opacity,
                "scale_pct": settings.wm_scale_pct,
                "fill": settings.wm_fill_color,
                "stroke": settings.wm_stroke_color,
                "stroke_w": settings.wm_stroke_width,
                "font_path": str(settings.wm_font_path) if settings.wm_font_path else "",
            }
        self.preview.set_wm_preview_config(wm_cfg)

        img_anchor_map = meta.get("img_anchors") or {}
        if self._active_src and self._active_src in img_anchor_map:
            anchor = tuple(img_anchor_map[self._active_src])
        elif meta.get("anchor"):
            anchor = tuple(meta["anchor"])
        else:
            anchor = tuple(self.app_settings.wm_anchor)

        self._wm_anchor = anchor

        try:
            before_img, after_img = self.controller.preview_by_key(
                key, self.posts, settings, selected_src=self._active_src
            )
        except Exception as e:
            messagebox.showerror("미리보기 오류", str(e))
            return

        self.preview.show(before_img, after_img)
        self.preview.set_anchor(anchor)

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

    def _refresh_gallery_overlay(self, key: str):
        meta = self.posts.get(key) or {}
        default_anchor = tuple(meta.get("anchor") or self.app_settings.wm_anchor)
        img_map = meta.get("img_anchors") or {}
        self.gallery.update_anchor_overlay(default_anchor, img_map)

    def on_start_batch(self):
        if not self.posts:
            messagebox.showinfo("시작", "스캔된 게시물이 없습니다.")
            return

        out_root_str = (self.opt.get_output_root_str() or "").strip()
        # ✅ 폴백: 입력칸이 비어 있어도 저장값이 있으면 사용
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

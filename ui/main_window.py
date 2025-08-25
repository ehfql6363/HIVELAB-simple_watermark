# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Dict
from tkinter import ttk, messagebox
import tkinter as tk

# DnD는 선택적
try:
    from tkinterdnd2 import TkinterDnD  # type: ignore
    BaseTk = TkinterDnD.Tk
except Exception:
    BaseTk = tk.Tk

from settings import AppSettings, DEFAULT_SIZES, hex_to_rgb, DEFAULT_WM_TEXT, RootConfig
from controller import AppController
from ui.post_list import PostList
from ui.preview_pane import PreviewPane
from ui.options_panel import OptionsPanel
from ui.status_bar import StatusBar

class MainWindow(BaseTk):
    def __init__(self, controller: AppController):
        super().__init__()
        self.title("Post Watermark & Resize (Phase 3 + Multi-Roots + DnD)")
        self.geometry("1180x760")

        self.controller = controller
        # 스캔 결과 전체(원본)
        self.posts: Dict[str, dict] = {}

        self._build_ui()

    def _build_ui(self):
        self.opt = OptionsPanel(self)
        self.opt.pack(fill="x", padx=8, pady=6)

        mid = ttk.PanedWindow(self, orient=tk.HORIZONTAL); mid.pack(fill="both", expand=True, padx=8, pady=6)
        self.post_list = PostList(mid, on_select=self.on_select_post); mid.add(self.post_list, weight=1)
        self.preview = PreviewPane(mid); mid.add(self.preview, weight=3)

        tbar = ttk.Frame(self); tbar.pack(fill="x", padx=8)
        ttk.Button(tbar, text="Scan Posts", command=self.on_scan).pack(side="left")
        ttk.Button(tbar, text="Preview Selected", command=self.on_preview).pack(side="left", padx=6)

        self.status = StatusBar(self, on_start=self.on_start_batch)
        self.status.pack(fill="x", padx=8, pady=6)

    # -------- Callbacks --------
    def on_scan(self):
        roots = self.opt.get_roots()
        if not roots:
            messagebox.showerror("Error", "Add at least one Input Root."); return
        self.posts = self.controller.scan_posts_multi(roots)
        self.post_list.set_posts(self.posts)   # 리스트에 채우고, 여기서부터는 리스트에 남아있는 항목만 처리

    def on_select_post(self, _name: str | None):
        self.preview.clear()

    def _collect_settings(self) -> AppSettings:
        (sizes, bg_hex, wm_opacity, wm_scale, out_root_str, roots,
         wm_fill_hex, wm_stroke_hex, wm_stroke_w) = self.opt.collect_options()

        if not out_root_str and roots:
            messagebox.showinfo("Output", "Output Root is empty. It will be created as <first_root>/export.")
        default_out = (Path(roots[0].path) / "export") if roots else Path("export")

        return AppSettings(
            output_root=Path(out_root_str) if out_root_str else default_out,
            sizes=sizes if sizes else list(DEFAULT_SIZES),
            bg_color=hex_to_rgb(bg_hex or "#FFFFFF"),
            wm_opacity=int(wm_opacity),
            wm_scale_pct=int(wm_scale),
            default_wm_text=DEFAULT_WM_TEXT,
            wm_fill_color=hex_to_rgb(wm_fill_hex or "#000000"),
            wm_stroke_color=hex_to_rgb(wm_stroke_hex or "#FFFFFF"),
            wm_stroke_width=int(wm_stroke_w),
        )

    def on_preview(self):
        key = self.post_list.get_selected_post()
        if not key:
            messagebox.showinfo("Preview", "Select a post from the list."); return
        if key not in self.posts or not self.posts[key]["files"]:
            messagebox.showinfo("Preview", "No images in this post."); return

        settings = self._collect_settings()
        try:
            before_img, after_img = self.controller.preview_by_key(key, self.posts, settings)
        except Exception as e:
            messagebox.showerror("Preview Error", str(e)); return
        self.preview.show(before_img, after_img)

    def on_start_batch(self):
        # 현재 리스트에 남아있는 항목만 처리
        visible_keys = self.post_list.get_all_keys()
        if not visible_keys:
            messagebox.showinfo("Run", "No posts to process. (The list is empty)"); return

        # 원본 dict에서 필요한 것만 추출
        visible_posts = {k: self.posts[k] for k in visible_keys if k in self.posts}

        settings = self._collect_settings()
        total = sum(len(meta["files"]) for meta in visible_posts.values()) * len(settings.sizes)
        if total == 0:
            messagebox.showinfo("Run", "Nothing to process."); return

        self.status.reset(total)

        def on_progress(val: int):
            self.status.set_progress(val)
        def on_done(processed: int):
            messagebox.showinfo("Done", f"Finished. Processed {processed} items.")
            self.status.finish()
        def on_error(msg: str):
            messagebox.showerror("Run Error", msg)

        self.controller.start_batch(settings, visible_posts, on_progress, on_done, on_error)

# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple
import tkinter as tk
from tkinter import ttk, messagebox

from PIL import Image, ImageTk

from settings import AppSettings, DEFAULT_SIZES, hex_to_rgb
from controller import AppController
from ui.post_list import PostList
from ui.preview_pane import PreviewPane
from ui.options_panel import OptionsPanel
from ui.status_bar import StatusBar

class MainWindow(tk.Tk):
    def __init__(self, controller: AppController):
        super().__init__()
        self.title("Post Watermark & Resize (Phase 3)")
        self.geometry("1120x720")

        self.controller = controller
        self.posts: Dict[str, List[Path]] = {}

        self._build_ui()

    # ---------- UI Build ----------
    def _build_ui(self):
        # top: options panel
        self.opt = OptionsPanel(self)
        self.opt.pack(fill="x", padx=8, pady=6)

        # middle: split (post list | preview)
        mid = ttk.PanedWindow(self, orient=tk.HORIZONTAL); mid.pack(fill="both", expand=True, padx=8, pady=6)
        self.post_list = PostList(mid, on_select=self.on_select_post); mid.add(self.post_list, weight=1)
        self.preview = PreviewPane(mid); mid.add(self.preview, weight=3)

        # toolbar (scan/preview)
        tbar = ttk.Frame(self); tbar.pack(fill="x", padx=8)
        ttk.Button(tbar, text="Scan Posts", command=self.on_scan).pack(side="left")
        ttk.Button(tbar, text="Preview Selected", command=self.on_preview).pack(side="left", padx=6)

        # status bar (progress + start)
        self.status = StatusBar(self, on_start=self.on_start_batch)
        self.status.pack(fill="x", padx=8, pady=6)

    # ---------- Callbacks ----------
    def on_scan(self):
        in_root = self.opt.get_input_root()
        if not in_root:
            messagebox.showerror("Error", "Select Input Root."); return
        root = Path(in_root)
        if not root.exists():
            messagebox.showerror("Error", "Input root does not exist."); return
        self.posts = self.controller.scan_posts(root)
        self.post_list.set_posts(self.posts)

    def on_select_post(self, _name: str | None):
        self.preview.clear()

    def collect_settings(self) -> AppSettings:
        sizes, bg_hex, wm_text, wm_opacity, wm_scale, in_root, out_root = self.opt.collect_options()
        bg = hex_to_rgb(bg_hex or "#FFFFFF")
        return AppSettings(
            input_root=Path(in_root) if in_root else Path(""),
            output_root=Path(out_root) if out_root else (Path(in_root) / "export" if in_root else Path("export")),
            sizes=sizes if sizes else list(DEFAULT_SIZES),
            bg_color=bg,
            wm_text=wm_text,
            wm_opacity=int(wm_opacity),
            wm_scale_pct=int(wm_scale),
        )

    def on_preview(self):
        name = self.post_list.get_selected_post()
        if not name:
            messagebox.showinfo("Preview", "Select a post from the list."); return
        if not self.posts.get(name):
            messagebox.showinfo("Preview", "No images in this post."); return
        settings = self.collect_settings()
        try:
            before_img, after_img = self.controller.preview_first_of_post(name, self.posts, settings)
        except Exception as e:
            messagebox.showerror("Preview Error", str(e)); return
        self.preview.show(before_img, after_img)

    def on_start_batch(self):
        if not self.posts:
            messagebox.showinfo("Run", "No posts found. Click 'Scan Posts' first."); return
        settings = self.collect_settings()
        total = sum(len(v) for v in self.posts.values()) * len(settings.sizes)
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

        self.controller.start_batch(settings, self.posts, on_progress, on_done, on_error)

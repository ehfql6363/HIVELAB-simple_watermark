# -*- coding: utf-8 -*-
"""
MainWindow: 전체 UI 조립 (멀티 루트 + DnD 지원 베이스)
- DnD는 선택적 의존성: pip install tkinterdnd2
  모듈이 없으면 자동으로 일반 Tk로 동작합니다(드래그앤드롭만 비활성).
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List
from tkinter import ttk, messagebox
import tkinter as tk

# TkinterDnD가 있으면 그걸로 루트 창을 만들고, 없으면 기본 Tk 사용
try:
    from tkinterdnd2 import TkinterDnD  # type: ignore
    BaseTk = TkinterDnD.Tk
    DND_AVAILABLE = True
except Exception:
    BaseTk = tk.Tk
    DND_AVAILABLE = False

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

        # 상태 표시(선택): DnD 가능 여부 안내
        if not DND_AVAILABLE:
            tip = ttk.Label(self, text="(Optional) Drag & Drop: pip install tkinterdnd2", foreground="#777")
            tip.pack(anchor="w", padx=10, pady=(0, 8))

    # -------- Callbacks --------
    def on_scan(self):
        roots = self.opt.get_roots()
        if not roots:
            messagebox.showerror("Error", "Add at least one Input Root."); return
        self.posts = self.controller.scan_posts_multi(roots)
        self.post_list.set_posts(self.posts)

    def on_select_post(self, _name: str | None):
        self.preview.clear()

    def _collect_settings(self) -> AppSettings:
        sizes, bg_hex, wm_opacity, wm_scale, out_root_str, roots = self.opt.collect_options()
        if not out_root_str:
            messagebox.showinfo("Output", "Output Root is empty. It will be created as <first_root>/export.")
        if roots:
            default_out = Path(roots[0].path) / "export"
        else:
            default_out = Path("export")
        settings = AppSettings(
            output_root=Path(out_root_str) if out_root_str else default_out,
            sizes=sizes if sizes else list(DEFAULT_SIZES),
            bg_color=hex_to_rgb(bg_hex or "#FFFFFF"),
            wm_opacity=int(wm_opacity),
            wm_scale_pct=int(wm_scale),
            default_wm_text=DEFAULT_WM_TEXT,
        )
        return settings

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
        if not self.posts:
            messagebox.showinfo("Run", "No posts found. Click 'Scan Posts' first."); return
        settings = self._collect_settings()
        total = sum(len(meta["files"]) for meta in self.posts.values()) * len(settings.sizes)
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

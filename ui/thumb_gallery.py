# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from typing import Callable, List, Optional, Dict
from PIL import Image, ImageTk

class ThumbGallery(ttk.Frame):
    """썸네일 그리드. 더블클릭으로 활성화 콜백 호출."""
    def __init__(self, master, on_activate: Optional[Callable[[Path], None]] = None,
                 thumb_size: int = 160, cols: int = 5, height: int = 220):
        super().__init__(master)
        self.on_activate = on_activate
        self.thumb_size = int(thumb_size)
        self.cols = int(cols)
        self.fixed_height = int(height)

        self.canvas = tk.Canvas(self, highlightthickness=0, height=self.fixed_height)
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vbar.set)
        self.inner = tk.Frame(self.canvas)
        self.win_id = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vbar.pack(side="right", fill="y")

        self.inner.bind("<Configure>", self._on_inner_config)
        self.canvas.bind("<Configure>", self._on_canvas_config)

        self._enable_wheel_for(self.canvas)
        self._enable_wheel_for(self.inner)

        self._tiles: Dict[Path, tk.Frame] = {}
        self._imgs: Dict[Path, ImageTk.PhotoImage] = {}
        self._active: Optional[Path] = None

    def clear(self):
        for w in self.inner.winfo_children():
            w.destroy()
        self._tiles.clear()
        self._imgs.clear()
        self._active = None
        self._update_scroll()

    def set_files(self, files: List[Path]):
        self.clear()
        if not files:
            return
        size = self.thumb_size
        pad = 8
        for i, p in enumerate(files):
            r, c = divmod(i, self.cols)
            tile = tk.Frame(self.inner, bd=1, relief="groove")
            tile.grid(row=r, column=c, padx=pad, pady=pad, sticky="nsew")

            # 썸네일 만들기 (정사각형 캔버스 안에 contain)
            try:
                im = Image.open(p)
                im.thumbnail((size, size), Image.Resampling.LANCZOS)
                bg = Image.new("RGB", (size, size), (245, 245, 245))
                ox = (size - im.width) // 2
                oy = (size - im.height) // 2
                bg.paste(im, (ox, oy))
                tkim = ImageTk.PhotoImage(bg)
            except Exception:
                bg = Image.new("RGB", (size, size), (200, 200, 200))
                tkim = ImageTk.PhotoImage(bg)

            lbl_img = tk.Label(tile, image=tkim)
            lbl_img.image = tkim  # 강참조
            self._imgs[p] = tkim
            lbl_img.pack(padx=4, pady=(4, 0))

            lbl_txt = tk.Label(tile, text=p.name, wraplength=size, justify="center")
            lbl_txt.pack(padx=4, pady=(2, 6))

            # 더블클릭 활성화
            def _activate(ev=None, path=p):
                self.set_active(path)
                if callable(self.on_activate):
                    self.on_activate(path)
            tile.bind("<Double-Button-1>", _activate)
            lbl_img.bind("<Double-Button-1>", _activate)
            lbl_txt.bind("<Double-Button-1>", _activate)

            self._tiles[p] = tile

        # 그리드 확장성
        for c in range(self.cols):
            self.inner.grid_columnconfigure(c, weight=1)
        self._update_scroll()

    def set_active(self, path: Optional[Path]):
        # 기존 강조 해제
        if self._active and self._active in self._tiles:
            self._tiles[self._active].configure(bd=1, relief="groove")
        self._active = path
        if path and path in self._tiles:
            self._tiles[path].configure(bd=2, relief="solid")

    # --- scroll helpers ---
    def _on_inner_config(self, _):
        self._update_scroll()

    def _on_canvas_config(self, e):
        self.canvas.itemconfigure(self.win_id, width=e.width)

    def _update_scroll(self):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    # --- wheel helpers ---
    def _enable_wheel_for(self, widget):
        widget.bind("<Enter>", lambda e: self._bind_wheel())
        widget.bind("<Leave>", lambda e: self._unbind_wheel())

    def _bind_wheel(self):
        # Windows/macOS
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        # Linux
        self.canvas.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-3, "units"))
        self.canvas.bind("<Button-5>", lambda e: self.canvas.yview_scroll(+3, "units"))

    def _unbind_wheel(self):
        self.canvas.unbind("<MouseWheel>")
        self.canvas.unbind("<Button-4>")
        self.canvas.unbind("<Button-5>")

    def _on_wheel(self, e):
        delta = e.delta
        if delta == 0:
            return "break"
        step = -1 * int(delta / 120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
        self.canvas.yview_scroll(step, "units")
        return "break"  # ✅ 이벤트 소비(부모 스크롤로 전파 방지)
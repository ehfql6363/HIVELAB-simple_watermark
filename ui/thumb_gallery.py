# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from typing import Callable, List, Optional, Dict, Tuple
from PIL import Image, ImageTk

class ThumbGallery(ttk.Frame):
    """썸네일 그리드. 더블클릭으로 활성화. 앵커 점/배지 오버레이 지원."""
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

        # 타일/이미지/지오메트리/캔버스
        self._tiles: Dict[Path, tk.Frame] = {}
        self._imgs: Dict[Path, ImageTk.PhotoImage] = {}
        self._canv: Dict[Path, tk.Canvas] = {}
        # (size, im_w, im_h, ox, oy)
        self._geom: Dict[Path, Tuple[int,int,int,int,int]] = {}
        self._active: Optional[Path] = None

        # 오버레이 상태
        self._default_anchor: Tuple[float,float] = (0.5, 0.5)
        self._img_anchors: Dict[Path, Tuple[float,float]] = {}

    def clear(self):
        for w in self.inner.winfo_children():
            w.destroy()
        self._tiles.clear(); self._imgs.clear(); self._geom.clear(); self._canv.clear()
        self._active = None
        self._update_scroll()

    def set_files(self, files: List[Path],
                  default_anchor: Tuple[float,float] | None = None,
                  img_anchor_map: Dict[Path, Tuple[float,float]] | None = None):
        self.clear()
        if default_anchor is not None:
            self._default_anchor = (float(default_anchor[0]), float(default_anchor[1]))
        self._img_anchors = dict(img_anchor_map or {})

        if not files:
            return
        size = self.thumb_size
        pad = 8
        for i, p in enumerate(files):
            r, c = divmod(i, self.cols)
            tile = tk.Frame(self.inner, bd=1, relief="groove")
            tile.grid(row=r, column=c, padx=pad, pady=pad, sticky="nsew")

            # 썸네일 + 배경 합성
            try:
                im = Image.open(p)
                im.thumbnail((size, size), Image.Resampling.LANCZOS)
                bg = Image.new("RGB", (size, size), (245, 245, 245))
                ox = (size - im.width) // 2
                oy = (size - im.height) // 2
                bg.paste(im, (ox, oy))
                tkim = ImageTk.PhotoImage(bg)
                im_w, im_h = im.width, im.height
            except Exception:
                bg = Image.new("RGB", (size, size), (200, 200, 200))
                tkim = ImageTk.PhotoImage(bg)
                ox = oy = 0; im_w = im_h = size

            # 이미지 표시용 Canvas (오버레이 가능)
            cnv = tk.Canvas(tile, width=size, height=size, highlightthickness=0, bg="#f5f5f5")
            cnv.pack(padx=4, pady=(4, 0))
            cnv.create_image(0, 0, image=tkim, anchor="nw", tags="pic")

            lbl_txt = tk.Label(tile, text=p.name, wraplength=size, justify="center")
            lbl_txt.pack(padx=4, pady=(2, 6))

            # 활성화(더블클릭)
            def _activate(ev=None, path=p):
                self.set_active(path)
                if callable(self.on_activate):
                    self.on_activate(path)
            for w in (tile, cnv, lbl_txt):
                w.bind("<Double-Button-1>", _activate)

            self._tiles[p] = tile
            self._imgs[p] = tkim
            self._canv[p] = cnv
            self._geom[p] = (size, im_w, im_h, ox, oy)

            # 첫 렌더 오버레이
            self._draw_overlay_for(p)

        for c in range(self.cols):
            self.inner.grid_columnconfigure(c, weight=1)
        self._update_scroll()

    def set_active(self, path: Optional[Path]):
        if self._active and self._active in self._tiles:
            self._tiles[self._active].configure(bd=1, relief="groove")
        self._active = path
        if path and path in self._tiles:
            self._tiles[path].configure(bd=2, relief="solid")

    # ---- 앵커 오버레이 업데이트 ----
    def update_anchor_overlay(self,
                              default_anchor: Tuple[float,float],
                              img_anchor_map: Dict[Path, Tuple[float,float]] | None = None):
        self._default_anchor = (float(default_anchor[0]), float(default_anchor[1]))
        self._img_anchors = dict(img_anchor_map or {})
        for p in list(self._tiles.keys()):
            self._draw_overlay_for(p)

    def _draw_overlay_for(self, path: Path):
        cnv = self._canv.get(path)
        geom = self._geom.get(path)
        if not cnv or not geom: return
        size, iw, ih, ox, oy = geom
        cnv.delete("anchor"); cnv.delete("badge")

        # 어떤 앵커를 사용할지 결정(개별 > 기본)
        if path in self._img_anchors:
            nx, ny = self._img_anchors[path]
            # 배지(A)
            cnv.create_rectangle(size-28, 4, size-4, 20, fill="#ffcc00", outline="", tags="badge")
            cnv.create_text(size-16, 12, text="A", font=("", 8, "bold"), tags="badge")
        else:
            nx, ny = self._default_anchor

        try:
            nx = float(nx); ny = float(ny)
        except:
            nx, ny = 0.5, 0.5
        nx = min(1.0, max(0.0, nx))
        ny = min(1.0, max(0.0, ny))

        x = ox + nx * iw
        y = oy + ny * ih
        r = 4
        cnv.create_oval(x-r, y-r, x+r, y+r, fill="#28a4ff", outline="", tags="anchor")

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
        self.canvas.bind("<MouseWheel>", self._on_wheel)
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
        return "break"

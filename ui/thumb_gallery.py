# -*- coding: utf-8 -*-
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from pathlib import Path
from typing import Callable, List, Optional, Dict, Tuple
from PIL import Image, ImageTk, ImageDraw, ImageFont

# -------------------- overlay helpers --------------------

def _measure_text_bbox(d: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, stroke_w: int) -> Tuple[int, int]:
    try:
        l, t, r, b = d.textbbox((0, 0), text, font=font, stroke_width=max(0, stroke_w))
        return r - l, b - t
    except Exception:
        w, h = font.getsize(text)
        return int(w), int(h)

def _draw_anchor_marker(square_img: Image.Image, content_box: Tuple[int,int,int,int],
                        anchor: Tuple[float,float], color=(30,144,255), radius=6):
    x0, y0, x1, y1 = content_box
    iw, ih = max(1, x1 - x0), max(1, y1 - y0)
    nx = min(1.0, max(0.0, float(anchor[0])))
    ny = min(1.0, max(0.0, float(anchor[1])))
    cx = int(x0 + nx * iw)
    cy = int(y0 + ny * ih)
    d = ImageDraw.Draw(square_img, "RGBA")
    r = max(2, int(radius))
    d.ellipse((cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1), fill=(255, 255, 255, 230))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(color[0], color[1], color[2], 230))

def _draw_badge(square_img: Image.Image, text="•", bg=(76,175,80), fg=(255,255,255)):
    W, H = square_img.size
    r = 9
    cx, cy = W - r - 6, r + 6
    d = ImageDraw.Draw(square_img, "RGBA")
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(bg[0], bg[1], bg[2], 255))
    try:
        font = ImageFont.truetype("arial.ttf", 12)
    except Exception:
        font = ImageFont.load_default()
    tw, th = _measure_text_bbox(d, text, font, 0)
    d.text((cx - tw // 2, cy - th // 2 - 1), text, font=font, fill=fg)

# -------------------- gallery --------------------

class ThumbGallery(ttk.Frame):
    """썸네일 그리드(스크롤 가능) + 앵커 오버레이/배지.
       - 클릭 한 번으로 on_activate 호출
       - 갤러리/썸네일 어디 위든 휠 스크롤 동작(전역 바인딩 + 포인터 가드)
    """
    def __init__(self, master, on_activate: Optional[Callable[[Path], None]] = None,
                 thumb_size: int = 160, cols: int = 5, height: int = 220):
        super().__init__(master)
        self.on_activate = on_activate
        self.thumb_size = int(thumb_size)
        self.cols = int(cols)
        self.fixed_height = int(height)

        # canvas + inner
        self.canvas = tk.Canvas(self, highlightthickness=0, height=self.fixed_height)
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vbar.set)
        self.inner = tk.Frame(self.canvas)
        self._win_id = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vbar.pack(side="right", fill="y")

        self.inner.bind("<Configure>", self._on_inner_config)
        self.canvas.bind("<Configure>", self._on_canvas_config)

        # ✅ 전역 휠 바인딩: 항상 켜둠(포인터 가드로 범위 제한)
        self._install_global_wheel()

        # state
        self._tiles: Dict[Path, tk.Frame] = {}
        self._imgs: Dict[Path, ImageTk.PhotoImage] = {}
        self._active: Optional[Path] = None

        self._default_anchor: Tuple[float, float] = (0.5, 0.5)
        self._img_anchor_map: Dict[Path, Tuple[float, float]] = {}

    # ---------- public API ----------

    def clear(self):
        for w in self.inner.winfo_children():
            w.destroy()
        self._tiles.clear()
        self._imgs.clear()
        self._active = None
        self._update_scroll()

    def set_files(self, files: List[Path],
                  default_anchor: Tuple[float, float] = (0.5, 0.5),
                  img_anchor_map: Optional[Dict[Path, Tuple[float, float]]] = None):
        self.clear()
        self._default_anchor = tuple(default_anchor)
        self._img_anchor_map = dict(img_anchor_map or {})
        if not files:
            return
        size, pad = self.thumb_size, 8

        for i, p in enumerate(files):
            r, c = divmod(i, self.cols)
            tile = tk.Frame(self.inner, bd=1, relief="groove")
            tile.grid(row=r, column=c, padx=pad, pady=pad, sticky="nsew")

            tkim = self._make_thumb_with_overlay(p, size)
            lbl_img = tk.Label(tile, image=tkim)
            lbl_img.image = tkim
            self._imgs[p] = tkim
            lbl_img.pack(padx=4, pady=(4, 0))

            lbl_txt = tk.Label(tile, text=p.name, wraplength=size, justify="center")
            lbl_txt.pack(padx=4, pady=(2, 6))

            def _activate(_=None, path=p):
                self.set_active(path)
                if callable(self.on_activate):
                    self.on_activate(path)
            # ✅ 단일 클릭 활성화(타일/이미지/텍스트 모두)
            for w in (tile, lbl_img, lbl_txt):
                w.bind("<Button-1>", _activate)

            self._tiles[p] = tile

        for c in range(self.cols):
            self.inner.grid_columnconfigure(c, weight=1)
        self._update_scroll()

    def set_active(self, path: Optional[Path]):
        if self._active and self._active in self._tiles:
            self._tiles[self._active].configure(bd=1, relief="groove")
        self._active = path
        if path and path in self._tiles:
            self._tiles[path].configure(bd=2, relief="solid")

    def set_badged(self, paths: set[Path]):
        pass  # 현재는 개별 앵커 보유 시 자동 배지

    def update_anchor_overlay(self, default_anchor: Tuple[float, float],
                              img_anchor_map: Dict[Path, Tuple[float, float]]):
        self._default_anchor = tuple(default_anchor)
        self._img_anchor_map = dict(img_anchor_map or {})
        for p, tile in self._tiles.items():
            if p in self._imgs:
                self._imgs[p] = self._make_thumb_with_overlay(p, self.thumb_size)
                for w in tile.winfo_children():
                    if isinstance(w, tk.Label) and getattr(w, "image", None) is not None:
                        w.configure(image=self._imgs[p]); w.image = self._imgs[p]
                        break

    # ---------- render ----------

    def _make_thumb_with_overlay(self, path: Path, size: int) -> ImageTk.PhotoImage:
        try:
            im = Image.open(path).convert("RGB")
            im.thumbnail((size, size), Image.Resampling.LANCZOS)
            bg = Image.new("RGBA", (size, size), (245, 245, 245, 255))
            ox = (size - im.width) // 2
            oy = (size - im.height) // 2
            bg.paste(im, (ox, oy))
            content_box = (ox, oy, ox + im.width, oy + im.height)
        except Exception:
            bg = Image.new("RGBA", (size, size), (200, 200, 200, 255))
            content_box = (4, 4, size - 4, size - 4)

        anchor = self._img_anchor_map.get(path, self._default_anchor)
        _draw_anchor_marker(bg, content_box, anchor, color=(30, 144, 255), radius=6)
        if path in self._img_anchor_map:
            _draw_badge(bg, text="•", bg=(76, 175, 80), fg=(255, 255, 255))

        return ImageTk.PhotoImage(bg.convert("RGB"))

    # ---------- scroll plumbing ----------

    def _on_inner_config(self, _=None):
        self._update_scroll()

    def _on_canvas_config(self, e):
        self.canvas.itemconfigure(self._win_id, width=e.width)

    def _update_scroll(self):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    # ---------- wheel handling (always-on bind_all + pointer guard) ----------

    def _install_global_wheel(self):
        root = self.winfo_toplevel()
        # Windows / macOS
        root.bind_all("<MouseWheel>", self._on_wheel, add="+")
        # X11 (Linux)
        root.bind_all("<Button-4>", self._on_btn4, add="+")
        root.bind_all("<Button-5>", self._on_btn5, add="+")

    def _pointer_inside_me(self, e) -> bool:
        try:
            w = self.winfo_containing(e.x_root, e.y_root)
            while w is not None:
                if w is self:
                    return True
                w = w.master
        except Exception:
            pass
        return False

    def _on_wheel(self, e):
        if not self._pointer_inside_me(e):
            return
        # delta를 단위 스텝으로 변환(트랙패드 연속 스크롤 대응)
        delta = e.delta
        steps = int(abs(delta) / 120) if abs(delta) >= 120 else 1
        direction = -1 if delta > 0 else 1
        self.canvas.yview_scroll(direction * steps, "units")
        return "break"

    def _on_btn4(self, e):
        if not self._pointer_inside_me(e):
            return
        self.canvas.yview_scroll(-3, "units")
        return "break"

    def _on_btn5(self, e):
        if not self._pointer_inside_me(e):
            return
        self.canvas.yview_scroll(+3, "units")
        return "break"

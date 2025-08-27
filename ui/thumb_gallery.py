# -*- coding: utf-8 -*-
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from pathlib import Path
from typing import Callable, List, Optional, Dict, Tuple
from PIL import Image, ImageTk, ImageDraw, ImageFont

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
    cx = int(x0 + nx * iw); cy = int(y0 + ny * ih)
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

class ThumbGallery(ttk.Frame):
    """썸네일 그리드(스크롤 가능) + 앵커 오버레이/배지.
       - 클릭 한 번으로 on_activate 호출
       - 갤러리/썸네일 어디 위든 휠 스크롤 동작(전역 바인딩 + 포인터 가드)
       - ← ↑ → ↓ 이동, ▶ 끝에서 다음 줄 첫 칸으로 랩, ◀ 처음에서 이전 줄 마지막 칸으로 랩
    """
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
        self._win_id = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vbar.pack(side="right", fill="y")

        self.inner.bind("<Configure>", self._on_inner_config)
        self.canvas.bind("<Configure>", self._on_canvas_config)

        self._install_global_wheel()
        self._install_keyboard_nav()

        self._tiles: Dict[Path, tk.Frame] = {}
        self._imgs: Dict[Path, ImageTk.PhotoImage] = {}
        self._active: Optional[Path] = None
        self._order: List[Path] = []

        self._default_anchor: Tuple[float, float] = (0.5, 0.5)
        self._img_anchor_map: Dict[Path, Tuple[float, float]] = {}

    # ---------- public API ----------

    def clear(self):
        for w in self.inner.winfo_children():
            w.destroy()
        self._tiles.clear()
        self._imgs.clear()
        self._order.clear()
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

        self._order = list(files)
        size, pad = self.thumb_size, 8

        for i, p in enumerate(files):
            r, c = divmod(i, self.cols)
            tile = tk.Frame(self.inner, bd=1, relief="groove", takefocus=1)
            tile.grid(row=r, column=c, padx=pad, pady=pad, sticky="nsew")

            tkim = self._make_thumb_with_overlay(p, size)
            lbl_img = tk.Label(tile, image=tkim, takefocus=0)
            lbl_img.image = tkim
            self._imgs[p] = tkim
            lbl_img.pack(padx=4, pady=(4, 0))

            lbl_txt = tk.Label(tile, text=p.name, wraplength=size, justify="center", takefocus=0)
            lbl_txt.pack(padx=4, pady=(2, 6))

            def _activate(_=None, path=p):
                self.set_active(path, fire=True)
                try: self.focus_set()
                except Exception: pass

            for w in (tile, lbl_img, lbl_txt):
                w.bind("<Button-1>", _activate)

            self._tiles[p] = tile

        for c in range(self.cols):
            self.inner.grid_columnconfigure(c, weight=1)
        self._update_scroll()

    def set_active(self, path: Optional[Path], fire: bool = False):
        if self._active and self._active in self._tiles:
            self._tiles[self._active].configure(bd=1, relief="groove")

        self._active = path

        if path and path in self._tiles:
            self._tiles[path].configure(bd=2, relief="solid")
            self._scroll_into_view(path)
            if fire and callable(self.on_activate):
                self.on_activate(path)

    def set_badged(self, paths: set[Path]):
        pass

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

    def _scroll_into_view(self, path: Path):
        try:
            self.update_idletasks()
            tile = self._tiles.get(path)
            if not tile: return
            tile_y = tile.winfo_y()
            tile_h = tile.winfo_height()
            inner_h = max(1, self.inner.winfo_height())
            can_h = self.canvas.winfo_height()
            top = self.canvas.canvasy(0)
            bottom = top + can_h
            if tile_y < top:
                self.canvas.yview_moveto(tile_y / inner_h)
            elif tile_y + tile_h > bottom:
                self.canvas.yview_moveto((tile_y + tile_h - can_h) / inner_h)
        except Exception:
            pass

    # ---------- wheel handling (bind_all + pointer guard) ----------

    def _install_global_wheel(self):
        root = self.winfo_toplevel()
        root.bind_all("<MouseWheel>", self._on_wheel, add="+")
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

    # ---------- keyboard navigation with wrapping ----------

    def _install_keyboard_nav(self):
        root = self.winfo_toplevel()
        for seq, handler in (
            ("<Left>", self._on_left),
            ("<Right>", self._on_right),
            ("<Up>", self._on_up),
            ("<Down>", self._on_down),
            ("<Home>", self._on_home),
            ("<End>", self._on_end),
        ):
            root.bind_all(seq, handler, add="+")

    def _has_focus_within(self) -> bool:
        try:
            w = self.focus_get()
            while w is not None:
                if w is self:
                    return True
                w = w.master
        except Exception:
            pass
        return False

    def _kbd_guard(self, e) -> bool:
        return self._pointer_inside_me(e) or self._has_focus_within()

    def _index_of(self, path: Optional[Path]) -> int:
        if path is None:
            return -1
        try:
            return self._order.index(path)
        except ValueError:
            return -1

    def _select_by_index(self, idx: int):
        if not self._order: return
        if idx < 0 or idx >= len(self._order): return
        self.set_active(self._order[idx], fire=True)

    def _move_selection(self, dc: int, dr: int, wrap_h: bool = False):
        if not self._order: return
        cur_idx = self._index_of(self._active)
        if cur_idx == -1:
            self._select_by_index(0); return
        cols = self.cols
        r, c = divmod(cur_idx, cols)
        nr, nc = r + dr, c + dc

        if dr == 0 and dc == +1 and wrap_h:
            # ▶ 오른쪽 랩: 다음 칸 없으면 다음 줄 첫 칸
            if nc >= cols or (nr*cols + nc) >= len(self._order):
                nr, nc = r + 1, 0
        elif dr == 0 and dc == -1 and wrap_h:
            # ◀ 왼쪽 랩: 이전 칸 없으면 이전 줄 마지막 유효 칸
            if nc < 0:
                prev_row_last_idx = r*cols - 1
                if prev_row_last_idx >= 0:
                    self._select_by_index(prev_row_last_idx)
                return

        nidx = nr * cols + nc
        if 0 <= nidx < len(self._order):
            self._select_by_index(nidx)

    def _on_left(self, e):
        if not self._kbd_guard(e): return
        self._move_selection(dc=-1, dr=0, wrap_h=True)
        return "break"

    def _on_right(self, e):
        if not self._kbd_guard(e): return
        self._move_selection(dc=+1, dr=0, wrap_h=True)
        return "break"

    def _on_up(self, e):
        if not self._kbd_guard(e): return
        self._move_selection(dc=0, dr=-1, wrap_h=False)
        return "break"

    def _on_down(self, e):
        if not self._kbd_guard(e): return
        self._move_selection(dc=0, dr=+1, wrap_h=False)
        return "break"

    def _on_home(self, e):
        if not self._kbd_guard(e): return
        self._select_by_index(0)
        return "break"

    def _on_end(self, e):
        if not self._kbd_guard(e): return
        self._select_by_index(len(self._order) - 1)
        return "break"

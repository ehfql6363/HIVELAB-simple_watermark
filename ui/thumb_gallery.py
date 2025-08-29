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

def _draw_badge(square_img: Image.Image, text="•", bg=(76,175,80), fg=(255,255,255), pos="tr"):
    W, H = square_img.size
    r = 9
    if pos == "tr":  cx, cy = W - r - 6, r + 6     # top-right
    elif pos == "tl": cx, cy = r + 6, r + 6        # top-left
    else: cx, cy = W - r - 6, r + 6
    d = ImageDraw.Draw(square_img, "RGBA")
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(bg[0], bg[1], bg[2], 255))
    try: font = ImageFont.truetype("arial.ttf", 12)
    except Exception: font = ImageFont.load_default()
    tw, th = _measure_text_bbox(d, text, font, 0)
    d.text((cx - tw // 2, cy - th // 2 - 1), text, font=font, fill=fg)

class ThumbGallery(ttk.Frame):
    def __init__(self, master, on_activate: Optional[Callable[[Path], None]] = None,
                 thumb_size: int = 160, cols: int = 5, height: int = 220):
        super().__init__(master)
        self.on_activate = on_activate
        self.thumb_size = int(thumb_size)
        self.cols = int(cols)
        self.fixed_height = int(height)

        self._sel_bars: Dict[Path, tk.Frame] = {}
        self._last_row_index: Optional[int] = None

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
        self._sel_bars.clear()
        self._update_scroll()

    def set_files(self, files: List[Path],
                  default_anchor: Tuple[float, float] = (0.5, 0.5),
                  img_anchor_map: Optional[Dict[Path, Tuple[float, float]]] = None):
        self.clear()
        self._default_anchor = tuple(default_anchor)
        self._img_anchor_map = dict(img_anchor_map or {})
        self._last_row_index = None
        if not files:
            return

        self._order = list(files)
        size, pad = self.thumb_size, 8

        # 라벨 예상 높이를 고정(두 줄 기준) → 타일 높이 고정
        label_h = 34
        tile_w = size + 16
        tile_h = size + 16 + label_h

        for i, p in enumerate(files):
            r, c = divmod(i, self.cols)

            # ★ 타일 고정 크기 + grid_propagate(False)로 자식 변경에도 크기 불변
            tile = tk.Frame(self.inner, bd=1, relief="groove", width=tile_w, height=tile_h, takefocus=1)
            tile.grid(row=r, column=c, padx=pad, pady=pad, sticky="nsew")
            tile.grid_propagate(False)

            # 컨텐츠 컨테이너
            body = tk.Frame(tile, bd=0, relief="flat")
            body.pack(fill="both", expand=True)

            # 이미지
            tkim = self._make_thumb_with_overlay(p, size)
            lbl_img = tk.Label(body, image=tkim, takefocus=0)
            lbl_img.image = tkim
            self._imgs[p] = tkim
            lbl_img.pack(padx=4, pady=(4, 0))

            # 파일명
            lbl_txt = tk.Label(body, text=p.name, wraplength=size, justify="center", takefocus=0)
            lbl_txt.pack(padx=4, pady=(2, 0))

            # ★ 항상 존재하는 하단 선택 바(높이 3px). 기본은 “투명처럼 보이는” 색.
            sel_bar = tk.Frame(tile, height=3, bg=tile.cget("background"))
            sel_bar.pack(side="bottom", fill="x")
            self._sel_bars[p] = sel_bar

            def _activate(_=None, path=p):
                self.set_active(path, fire=True)
                try:
                    self.focus_set()
                except Exception:
                    pass

            for w in (tile, lbl_img, lbl_txt):
                w.bind("<Button-1>", _activate)

            self._tiles[p] = tile

        for c in range(self.cols):
            self.inner.grid_columnconfigure(c, weight=1)
        self._update_scroll()

    def set_active(self, path: Optional[Path], fire: bool = False):
        # 같은 항목이면(중복 호출) 아무 것도 안 함
        if path == self._active:
            return

        # 이전 선택 표시 되돌리기
        if self._active and self._active in self._tiles:
            try:
                self._tiles[self._active].configure(bd=1, relief="groove")
            except Exception:
                pass

        self._active = path

        if path and path in self._tiles:
            try:
                self._tiles[path].configure(bd=2, relief="solid")
            except Exception:
                pass

            # 🔑 스크롤은 '사용자 동작(fire=True)'일 때만, 그리고 "행이 바뀐 경우"에만 수행
            if fire:
                try:
                    idx = self._order.index(path)
                except ValueError:
                    idx = -1
                row = (idx // self.cols) if idx >= 0 else None

                # 같은 행이면 스크롤하지 않음
                if row is not None and row != self._last_row_index:
                    self.after_idle(lambda p=path: self._scroll_into_view(p))
                    self._last_row_index = row

            if fire and callable(self.on_activate):
                self.on_activate(path)

    def _scroll_into_view(self, path: Path):
        try:
            self.update_idletasks()
            tile = self._tiles.get(path)
            if not tile:
                return

            # 전체/뷰 높이
            bbox_all = self.canvas.bbox("all")
            if not bbox_all:
                return
            content_h = bbox_all[3] - bbox_all[1]
            can_h = self.canvas.winfo_height()
            if can_h <= 0 or content_h <= 0:
                return

            # 현재 top/bottom
            top_px = int(self.canvas.canvasy(0))
            bottom_px = top_px + can_h

            # 타겟 위치/크기
            tile_y = tile.winfo_y()
            tile_h = tile.winfo_height()

            # 데드존(상/하단 24px 정도는 스크롤하지 않음)
            dead = 24
            visible_top = top_px + dead
            visible_bottom = bottom_px - dead

            # 이미 충분히 보이면 이동하지 않음
            if tile_y >= visible_top and (tile_y + tile_h) <= visible_bottom:
                return

            # 최소 이동만 계산
            new_top = top_px
            if tile_y < visible_top:
                new_top = tile_y - dead
            elif (tile_y + tile_h) > visible_bottom:
                new_top = tile_y + tile_h + dead - can_h

            # 범위 제한
            max_top = max(0, content_h - can_h)
            new_top = max(0, min(max_top, new_top))

            if abs(new_top - top_px) >= 1:
                self.canvas.yview_moveto(new_top / float(max_top if max_top > 0 else 1))
        except Exception:
            pass

    def set_badged(self, paths: set[Path]):
        pass

    def update_anchor_overlay(self, default_anchor, img_anchor_map, style_override_set=None):
        self._default_anchor = tuple(default_anchor)
        self._img_anchor_map = dict(img_anchor_map or {})
        self._style_override_set = set(style_override_set or set())  # ★ 추가 보관
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
            with Image.open(path) as im_src:
                im = im_src.convert("RGB").copy()  # ← 복사 후 원본 핸들 닫힘
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
            _draw_badge(bg, text="•", bg=(76, 175, 80), fg=(255, 255, 255), pos="tr")  # 초록점
        if getattr(self, "_style_override_set", None) and path in self._style_override_set:
            _draw_badge(bg, text="•", bg=(255, 152, 0), fg=(255, 255, 255), pos="tl")  # 주황점
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

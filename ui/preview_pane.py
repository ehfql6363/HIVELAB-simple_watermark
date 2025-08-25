# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

class _CheckerCanvas(tk.Canvas):
    """체크보드 배경 + 중앙 정렬 이미지 렌더 캔버스."""
    def __init__(self, master, tile=12, c1="#E6E6E6", c2="#C8C8C8", **kw):
        super().__init__(master, highlightthickness=0, background="white", **kw)
        self.tile = tile
        self.c1, self.c2 = c1, c2
        self._pil_img: Image.Image | None = None
        self._tk_img: ImageTk.PhotoImage | None = None
        self._img_id = None
        self.bind("<Configure>", self._on_resize)

    def set_image(self, pil_img: Image.Image | None):
        self._pil_img = pil_img
        self._render()

    # ---- internal ----
    def _on_resize(self, _evt):
        self._render()

    def _draw_checker(self, w: int, h: int):
        self.delete("checker")
        t = self.tile
        # 체크보드 타일 채우기
        # 성능을 위해 viewbox 전체를 정사각형으로 단순하게 칠함
        cols = (w + t - 1) // t
        rows = (h + t - 1) // t
        color = self.c1
        for r in range(rows):
            color = self.c1 if r % 2 == 0 else self.c2
            for c in range(cols):
                x0 = c * t
                y0 = r * t
                x1 = min(x0 + t, w)
                y1 = min(y0 + t, h)
                self.create_rectangle(x0, y0, x1, y1, fill=color, width=0, tags="checker")
                color = self.c2 if color == self.c1 else self.c1

    def _render(self):
        w = max(1, self.winfo_width())
        h = max(1, self.winfo_height())
        # 배경 체크보드
        self._draw_checker(w, h)

        # 이미지가 없으면 종료
        if self._pil_img is None:
            if self._img_id is not None:
                self.delete(self._img_id)
                self._img_id = None
            return

        # 캔버스에 맞게 이미지 축소 렌더
        W, H = self._pil_img.size
        scale = min(w / W, h / H, 1.0)
        newW, newH = max(1, int(W * scale)), max(1, int(H * scale))
        disp = self._pil_img.resize((newW, newH), Image.Resampling.LANCZOS)

        self._tk_img = ImageTk.PhotoImage(disp)
        if self._img_id is None:
            self._img_id = self.create_image(w // 2, h // 2, image=self._tk_img, anchor="center", tags="content")
        else:
            self.itemconfigure(self._img_id, image=self._tk_img)
            self.coords(self._img_id, w // 2, h // 2)


class PreviewPane(ttk.Frame):
    """Before/After 비교 뷰 + Swap 버튼 + 체크보드 배경."""
    def __init__(self, master):
        super().__init__(master)

        # 상단 캡션 + 스왑 버튼
        top = ttk.Frame(self); top.pack(fill="x", pady=(2, 0))
        self.lbl_before_cap = ttk.Label(top, text="Before", font=("", 10, "bold"))
        self.lbl_after_cap = ttk.Label(top, text="After", font=("", 10, "bold"))

        self.btn_swap = ttk.Button(top, text="Swap ◀▶", command=self._on_swap)
        self.lbl_before_cap.pack(side="left", padx=4)
        self.btn_swap.pack(side="left", padx=8)
        self.lbl_after_cap.pack(side="left", padx=4)

        # 본문: 테두리 있는 박스 안에 체크보드 캔버스
        grid = ttk.Frame(self); grid.pack(fill="both", expand=True, pady=4)

        self.box_before = tk.Frame(grid, bd=1, relief="solid")
        self.box_after  = tk.Frame(grid, bd=2, relief="solid")  # After 쪽을 살짝 강조
        self.box_before.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.box_after.grid(row=0, column=1, sticky="nsew", padx=4, pady=4)

        self.canvas_before = _CheckerCanvas(self.box_before)
        self.canvas_after  = _CheckerCanvas(self.box_after)
        self.canvas_before.pack(fill="both", expand=True)
        self.canvas_after.pack(fill="both", expand=True)

        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        grid.rowconfigure(0, weight=1)

        # 상태
        self._pil_before: Image.Image | None = None
        self._pil_after: Image.Image | None = None
        self._swapped = False

    # ---- public API ----
    def show(self, before_img: Image.Image, after_img: Image.Image):
        self._pil_before = before_img
        self._pil_after = after_img
        self._render_images()

    def clear(self):
        self._pil_before = None
        self._pil_after = None
        self._swapped = False
        self.canvas_before.set_image(None)
        self.canvas_after.set_image(None)

    # ---- internal ----
    def _on_swap(self):
        self._swapped = not self._swapped
        self._render_images()

    def _render_images(self):
        if self._swapped:
            left, right = self._pil_after, self._pil_before
            # 캡션도 스왑 표시(선택) — 필요 없으면 주석 처리 가능
            self.lbl_before_cap.configure(text="After (swapped)")
            self.lbl_after_cap.configure(text="Before (swapped)")
        else:
            left, right = self._pil_before, self._pil_after
            self.lbl_before_cap.configure(text="Before")
            self.lbl_after_cap.configure(text="After")

        self.canvas_before.set_image(left)
        self.canvas_after.set_image(right)

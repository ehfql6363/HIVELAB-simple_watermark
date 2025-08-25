# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

class PreviewPane(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)

        grid = ttk.Frame(self); grid.pack(fill="both", expand=True)

        # 캡션(항상 보이게)
        cap_before = ttk.Label(grid, text="Before", font=("", 10, "bold"))
        cap_after  = ttk.Label(grid, text="After",  font=("", 10, "bold"))
        cap_before.grid(row=0, column=0, sticky="w", padx=4, pady=(2,0))
        cap_after.grid(row=0, column=1, sticky="w", padx=4, pady=(2,0))

        # 이미지 컨테이너(테두리로 구분)
        box_before = tk.Frame(grid, bd=1, relief="solid")
        box_after  = tk.Frame(grid, bd=2, relief="solid")  # After를 살짝 더 강조
        box_before.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        box_after.grid(row=1, column=1, sticky="nsew", padx=4, pady=4)

        # 이미지 라벨
        self.lbl_before = tk.Label(box_before, bg="white")
        self.lbl_after  = tk.Label(box_after,  bg="white")
        self.lbl_before.pack(fill="both", expand=True)
        self.lbl_after.pack(fill="both", expand=True)

        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        grid.rowconfigure(1, weight=1)

        self._tk_before = None
        self._tk_after = None

    def _to_tk_image(self, img: Image.Image, max_w=520, max_h=520):
        W, H = img.size
        scale = min(max_w / W, max_h / H, 1.0)
        newW, newH = int(W * scale), int(H * scale)
        thumb = img.resize((newW, newH), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(thumb)

    def show(self, before_img, after_img):
        self._tk_before = self._to_tk_image(before_img)
        self._tk_after = self._to_tk_image(after_img)
        self.lbl_before.configure(image=self._tk_before)
        self.lbl_after.configure(image=self._tk_after)

    def clear(self):
        self.lbl_before.configure(image="", text="")
        self.lbl_after.configure(image="", text="")
        self._tk_before = None
        self._tk_after = None

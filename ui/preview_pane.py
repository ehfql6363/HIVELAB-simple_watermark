# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

class PreviewPane(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self._tk_before = None
        self._tk_after = None

        grid = ttk.Frame(self); grid.pack(fill="both", expand=True)
        self.lbl_before = ttk.Label(grid, text="Before")
        self.lbl_after = ttk.Label(grid, text="After")
        self.lbl_before.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.lbl_after.grid(row=0, column=1, sticky="nsew", padx=4, pady=4)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        grid.rowconfigure(0, weight=1)

    def _to_tk_image(self, img: Image.Image, max_w=520, max_h=520):
        W, H = img.size
        scale = min(max_w / W, max_h / H, 1.0)
        newW, newH = int(W * scale), int(H * scale)
        thumb = img.resize((newW, newH), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(thumb)

    def show(self, before_img, after_img):
        self._tk_before = self._to_tk_image(before_img)
        self._tk_after = self._to_tk_image(after_img)
        self.lbl_before.configure(image=self._tk_before, text="")
        self.lbl_after.configure(image=self._tk_after, text="")

    def clear(self):
        self.lbl_before.configure(image="", text="Before")
        self.lbl_after.configure(image="", text="After")
        self._tk_before = None
        self._tk_after = None

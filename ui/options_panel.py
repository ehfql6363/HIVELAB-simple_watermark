# -*- coding: utf-8 -*-
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog
from typing import Dict, Tuple, List

from settings import DEFAULT_SIZES

class OptionsPanel(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)

        # Input/Output
        top = ttk.Frame(self); top.pack(fill="x")
        ttk.Label(top, text="Input Root:").grid(row=0, column=0, sticky="w")
        self.var_input = tk.StringVar()
        ttk.Entry(top, textvariable=self.var_input, width=50).grid(row=0, column=1, sticky="we", padx=4)
        ttk.Button(top, text="Browse…", command=self._browse_input).grid(row=0, column=2, padx=4)

        ttk.Label(top, text="Output Root:").grid(row=1, column=0, sticky="w")
        self.var_output = tk.StringVar()
        ttk.Entry(top, textvariable=self.var_output, width=50).grid(row=1, column=1, sticky="we", padx=4)
        ttk.Button(top, text="Browse…", command=self._browse_output).grid(row=1, column=2, padx=4)

        # Sizes
        size_frame = ttk.Frame(top); size_frame.grid(row=0, column=3, rowspan=2, padx=8, sticky="w")
        ttk.Label(size_frame, text="Target Sizes:").grid(row=0, column=0, columnspan=3, sticky="w")
        self.size_vars: Dict[Tuple[int, int], tk.BooleanVar] = {}
        for i, (w, h) in enumerate(DEFAULT_SIZES):
            var = tk.BooleanVar(value=True)  # all ON
            ttk.Checkbutton(size_frame, text=f"{w}x{h}", variable=var).grid(row=1, column=i, padx=4, sticky="w")
            self.size_vars[(w, h)] = var

        # Watermark group
        wm = ttk.Frame(self); wm.pack(fill="x", pady=(6, 0))
        ttk.Label(wm, text="Watermark (center)").grid(row=0, column=0, columnspan=4, sticky="w")

        ttk.Label(wm, text="Text").grid(row=1, column=0, sticky="e")
        self.var_wm_text = tk.StringVar(value="© YourBrand")
        ttk.Entry(wm, textvariable=self.var_wm_text, width=24).grid(row=1, column=1, sticky="w", padx=4)

        ttk.Label(wm, text="Opacity").grid(row=1, column=2, sticky="e")
        self.var_wm_opacity = tk.IntVar(value=30)
        ttk.Spinbox(wm, from_=0, to=100, textvariable=self.var_wm_opacity, width=5).grid(row=1, column=3, sticky="w")

        ttk.Label(wm, text="Scale % (short side)").grid(row=2, column=0, sticky="e")
        self.var_wm_scale = tk.IntVar(value=5)
        ttk.Spinbox(wm, from_=1, to=50, textvariable=self.var_wm_scale, width=5).grid(row=2, column=1, sticky="w")

        ttk.Label(wm, text="BG #RRGGBB").grid(row=2, column=2, sticky="e")
        self.var_bg = tk.StringVar(value="#FFFFFF")
        ttk.Entry(wm, textvariable=self.var_bg, width=8).grid(row=2, column=3, sticky="w")

    # ----- API -----
    def get_input_root(self) -> str:
        return self.var_input.get().strip()

    def get_output_root(self) -> str:
        return self.var_output.get().strip()

    def collect_options(self):
        sizes = [s for s, var in self.size_vars.items() if var.get()]
        if not sizes: sizes = list(DEFAULT_SIZES)
        return (
            sizes,
            self.var_bg.get().strip(),
            self.var_wm_text.get(),
            int(self.var_wm_opacity.get()),
            int(self.var_wm_scale.get()),
            self.var_input.get().strip(),
            self.var_output.get().strip(),
        )

    # ----- Browse -----
    def _browse_input(self):
        path = filedialog.askdirectory(title="Select Input Root (Contains posts as subfolders)")
        if path: self.var_input.set(path)

    def _browse_output(self):
        path = filedialog.askdirectory(title="Select Output Root")
        if path: self.var_output.set(path)

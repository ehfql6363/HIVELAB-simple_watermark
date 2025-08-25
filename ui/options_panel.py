# -*- coding: utf-8 -*-
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox
from typing import Dict, Tuple, List

from pathlib import Path
from settings import DEFAULT_SIZES, DEFAULT_WM_TEXT, RootConfig

class OptionsPanel(ttk.Frame):
    """
    - 여러 개의 루트 등록 (각 루트에 워터마크 텍스트)
    - 공통 옵션: 출력 루트, 사이즈, BG, 불투명도/스케일
    """
    def __init__(self, master):
        super().__init__(master)

        # Output + Sizes
        top = ttk.Frame(self); top.pack(fill="x")
        ttk.Label(top, text="Output Root:").grid(row=0, column=0, sticky="w")
        self.var_output = tk.StringVar()
        ttk.Entry(top, textvariable=self.var_output, width=50).grid(row=0, column=1, sticky="we", padx=4)
        ttk.Button(top, text="Browse…", command=self._browse_output).grid(row=0, column=2, padx=4)

        size_frame = ttk.Frame(top); size_frame.grid(row=0, column=3, padx=8, sticky="w")
        ttk.Label(size_frame, text="Target Sizes:").grid(row=0, column=0, columnspan=3, sticky="w")
        self.size_vars: Dict[Tuple[int, int], tk.BooleanVar] = {}
        for i, (w, h) in enumerate(DEFAULT_SIZES):
            var = tk.BooleanVar(value=True)
            ttk.Checkbutton(size_frame, text=f"{w}x{h}", variable=var).grid(row=1, column=i, padx=4, sticky="w")
            self.size_vars[(w, h)] = var

        # Watermark common params (center)
        wm = ttk.Frame(self); wm.pack(fill="x", pady=(6, 0))
        ttk.Label(wm, text="Watermark (center)").grid(row=0, column=0, columnspan=6, sticky="w")

        ttk.Label(wm, text="Opacity").grid(row=1, column=0, sticky="e")
        self.var_wm_opacity = tk.IntVar(value=30)
        ttk.Spinbox(wm, from_=0, to=100, textvariable=self.var_wm_opacity, width=5).grid(row=1, column=1, sticky="w")

        ttk.Label(wm, text="Scale % (short side)").grid(row=1, column=2, sticky="e")
        self.var_wm_scale = tk.IntVar(value=5)
        ttk.Spinbox(wm, from_=1, to=50, textvariable=self.var_wm_scale, width=5).grid(row=1, column=3, sticky="w")

        ttk.Label(wm, text="BG #RRGGBB").grid(row=1, column=4, sticky="e")
        self.var_bg = tk.StringVar(value="#FFFFFF")
        ttk.Entry(wm, textvariable=self.var_bg, width=8).grid(row=1, column=5, sticky="w")

        # Roots (multi)
        roots = ttk.LabelFrame(self, text="Roots (루트 폴더별 워터마크 텍스트)")
        roots.pack(fill="both", expand=True, pady=8)

        cols = ("root", "wm_text")
        self.tree = ttk.Treeview(roots, columns=cols, show="headings", height=6)
        self.tree.heading("root", text="Root Path")
        self.tree.heading("wm_text", text="WM Text")
        self.tree.column("root", width=520)
        self.tree.column("wm_text", width=240)
        self.tree.pack(fill="both", expand=True, side="left", padx=(6,0), pady=6)

        scrollbar = ttk.Scrollbar(roots, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        # buttons
        btns = ttk.Frame(self); btns.pack(fill="x", pady=(0,6))
        ttk.Button(btns, text="Add Root…", command=self._add_root).pack(side="left")
        ttk.Button(btns, text="Edit WM", command=self._edit_wm).pack(side="left", padx=6)
        ttk.Button(btns, text="Remove", command=self._remove_root).pack(side="left")

    # ----- API -----
    def get_roots(self) -> List[RootConfig]:
        roots: List[RootConfig] = []
        for iid in self.tree.get_children():
            root = self.tree.set(iid, "root")
            wm = self.tree.set(iid, "wm_text")
            roots.append(RootConfig(path=Path(root), wm_text=wm or DEFAULT_WM_TEXT))
        return roots

    def collect_options(self):
        sizes = [s for s, var in self.size_vars.items() if var.get()]
        if not sizes: sizes = list(DEFAULT_SIZES)
        return (
            sizes,
            self.var_bg.get().strip(),
            int(self.var_wm_opacity.get()),
            int(self.var_wm_scale.get()),
            self.var_output.get().strip(),
            self.get_roots(),
        )

    # ----- Browse -----
    def _browse_output(self):
        path = filedialog.askdirectory(title="Select Output Root")
        if path: self.var_output.set(path)

    # ----- Roots mgmt -----
    def _add_root(self):
        path = filedialog.askdirectory(title="Select an Input Root (contains post folders)")
        if not path: return
        wm = simpledialog.askstring("Watermark Text", "Enter watermark text for this root:", initialvalue=DEFAULT_WM_TEXT, parent=self)
        if wm is None: return
        # dedup: if same path exists, update wm
        for iid in self.tree.get_children():
            if self.tree.set(iid, "root") == path:
                self.tree.set(iid, "wm_text", wm)
                return
        self.tree.insert("", "end", values=(path, wm))

    def _edit_wm(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Edit WM", "Select a root row first."); return
        iid = sel[0]
        cur = self.tree.set(iid, "wm_text")
        new_wm = simpledialog.askstring("Watermark Text", "Edit watermark text:", initialvalue=cur or DEFAULT_WM_TEXT, parent=self)
        if new_wm is None: return
        self.tree.set(iid, "wm_text", new_wm)

    def _remove_root(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Remove", "Select a root row first."); return
        for iid in sel:
            self.tree.delete(iid)

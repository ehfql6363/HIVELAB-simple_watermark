# -*- coding: utf-8 -*-
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox, colorchooser
from typing import Dict, Tuple, List
from pathlib import Path

from settings import DEFAULT_SIZES, DEFAULT_WM_TEXT, RootConfig

# DnD
try:
    from tkinterdnd2 import DND_FILES  # type: ignore
    DND_AVAILABLE = True
except Exception:
    DND_AVAILABLE = False
    DND_FILES = None  # type: ignore

def _make_swatch(parent, hex_color: str):
    sw = tk.Label(parent, text="  ", relief="groove", bd=1, width=2)
    try: sw.configure(bg=hex_color)
    except: sw.configure(bg="#FFFFFF")
    return sw

class OptionsPanel(ttk.Frame):
    """
    - 루트 다중 등록 + 루트별 워터마크 텍스트
    - 공통 옵션: 출력 루트, 단일 Target Size, BG, Opacity/Scale
    - 추가: WM Fill 색상/스와치/컬러피커, Stroke 색상/두께
    - 개선: DnD, 더블클릭 인라인 편집, Remove/Remove All
    """
    def __init__(self, master):
        super().__init__(master)

        # Output + Size(단일)
        top = ttk.Frame(self); top.pack(fill="x")
        ttk.Label(top, text="Output Root:").grid(row=0, column=0, sticky="w")
        self.var_output = tk.StringVar()
        ttk.Entry(top, textvariable=self.var_output, width=50).grid(row=0, column=1, sticky="we", padx=4)
        ttk.Button(top, text="Browse…", command=self._browse_output).grid(row=0, column=2, padx=4)

        size_frame = ttk.Frame(top); size_frame.grid(row=0, column=3, padx=8, sticky="w")
        ttk.Label(size_frame, text="Target Size:").grid(row=0, column=0, sticky="w")
        preset = [f"{w}x{h}" for (w, h) in DEFAULT_SIZES]
        self.var_size = tk.StringVar(value=preset[0])
        self.cb_size = ttk.Combobox(size_frame, textvariable=self.var_size, values=preset, width=12, state="readonly")
        self.cb_size.grid(row=1, column=0, sticky="w")

        # Watermark common params (center)
        wm = ttk.LabelFrame(self, text="Watermark (center)"); wm.pack(fill="x", pady=(6, 0))

        ttk.Label(wm, text="Opacity").grid(row=0, column=0, sticky="e", padx=(2,2))
        self.var_wm_opacity = tk.IntVar(value=30)
        ttk.Spinbox(wm, from_=0, to=100, textvariable=self.var_wm_opacity, width=5).grid(row=0, column=1, sticky="w")

        ttk.Label(wm, text="Scale % (short side)").grid(row=0, column=2, sticky="e")
        self.var_wm_scale = tk.IntVar(value=5)
        ttk.Spinbox(wm, from_=1, to=50, textvariable=self.var_wm_scale, width=5).grid(row=0, column=3, sticky="w")

        ttk.Label(wm, text="BG #RRGGBB").grid(row=0, column=4, sticky="e")
        self.var_bg = tk.StringVar(value="#FFFFFF")
        ttk.Entry(wm, textvariable=self.var_bg, width=9).grid(row=0, column=5, sticky="w")

        # 색상 & 외곽선
        # Fill
        ttk.Label(wm, text="Fill").grid(row=1, column=0, sticky="e", padx=(2,2), pady=(4,2))
        self.var_fill = tk.StringVar(value="#000000")
        self.ent_fill = ttk.Entry(wm, textvariable=self.var_fill, width=9)
        self.ent_fill.grid(row=1, column=1, sticky="w", pady=(4,2))
        self.sw_fill = _make_swatch(wm, self.var_fill.get()); self.sw_fill.grid(row=1, column=2, sticky="w", padx=4)
        ttk.Button(wm, text="Pick…", command=lambda: self._pick_color(self.var_fill, self.sw_fill)).grid(row=1, column=3, sticky="w")

        # Stroke
        ttk.Label(wm, text="Stroke").grid(row=1, column=4, sticky="e", padx=(12,2))
        self.var_stroke = tk.StringVar(value="#FFFFFF")
        self.ent_stroke = ttk.Entry(wm, textvariable=self.var_stroke, width=9)
        self.ent_stroke.grid(row=1, column=5, sticky="w")
        self.sw_stroke = _make_swatch(wm, self.var_stroke.get()); self.sw_stroke.grid(row=1, column=6, sticky="w", padx=4)
        ttk.Button(wm, text="Pick…", command=lambda: self._pick_color(self.var_stroke, self.sw_stroke)).grid(row=1, column=7, sticky="w")

        ttk.Label(wm, text="Stroke W").grid(row=1, column=8, sticky="e", padx=(12,2))
        self.var_stroke_w = tk.IntVar(value=2)
        ttk.Spinbox(wm, from_=0, to=20, textvariable=self.var_stroke_w, width=5).grid(row=1, column=9, sticky="w")

        # Roots (multi)
        roots = ttk.LabelFrame(self, text="Roots (루트 폴더별 워터마크 텍스트)")
        roots.pack(fill="both", expand=True, pady=8)

        cols = ("root", "wm_text")
        self.tree = ttk.Treeview(roots, columns=cols, show="headings", height=6)
        self.tree.heading("root", text="Root Path")
        self.tree.heading("wm_text", text="WM Text (double-click to edit)")
        self.tree.column("root", width=520)
        self.tree.column("wm_text", width=260)
        self.tree.pack(fill="both", expand=True, side="left", padx=(6,0), pady=6)

        scrollbar = ttk.Scrollbar(roots, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        # DnD
        if DND_AVAILABLE:
            try:
                self.tree.drop_target_register(DND_FILES)  # type: ignore
                self.tree.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                pass

        # 더블클릭 인라인 편집 + Delete 삭제
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self.tree.bind("<Delete>", lambda e: self._remove_root())

        # buttons
        btns = ttk.Frame(self); btns.pack(fill="x", pady=(0,6))
        ttk.Button(btns, text="Add Root…", command=self._add_root).pack(side="left")
        ttk.Button(btns, text="Remove", command=self._remove_root).pack(side="left", padx=6)
        ttk.Button(btns, text="Remove All", command=self._remove_all).pack(side="left")

        # 인라인 에디터 상태
        self._edit_entry: ttk.Entry | None = None
        self._edit_iid: str | None = None
        self._edit_col: str | None = None

        # 스와치 자동 갱신
        self.var_fill.trace_add("write", lambda *_: self._update_swatch(self.sw_fill, self.var_fill.get()))
        self.var_stroke.trace_add("write", lambda *_: self._update_swatch(self.sw_stroke, self.var_stroke.get()))

    # ----- API -----
    def get_roots(self) -> List[RootConfig]:
        roots: List[RootConfig] = []
        for iid in self.tree.get_children():
            root = self.tree.set(iid, "root")
            wm = self.tree.set(iid, "wm_text")
            roots.append(RootConfig(path=Path(root), wm_text=wm or DEFAULT_WM_TEXT))
        return roots

    def collect_options(self):
        # 단일 사이즈를 리스트 하나로 반환(호환성 유지)
        size_str = self.var_size.get().lower().replace(" ", "")
        try:
            w, h = map(int, size_str.split("x"))
            sizes = [(w, h)]
        except Exception:
            sizes = [DEFAULT_SIZES[0]]

        return (
            sizes,
            self.var_bg.get().strip(),
            int(self.var_wm_opacity.get()),
            int(self.var_wm_scale.get()),
            self.var_output.get().strip(),
            self.get_roots(),
            self.var_fill.get().strip() or "#000000",
            self.var_stroke.get().strip() or "#FFFFFF",
            int(self.var_stroke_w.get()),
        )

    # ----- Browse -----
    def _browse_output(self):
        path = filedialog.askdirectory(title="Select Output Root")
        if path: self.var_output.set(path)

    # ----- Roots mgmt -----
    def _insert_or_update_root(self, path_str: str, wm_text: str = DEFAULT_WM_TEXT):
        for iid in self.tree.get_children():
            if self.tree.set(iid, "root") == path_str:
                self.tree.set(iid, "wm_text", wm_text)
                return
        self.tree.insert("", "end", values=(path_str, wm_text))

    def _add_root(self):
        path = filedialog.askdirectory(title="Select an Input Root (contains post folders)")
        if not path: return
        self._insert_or_update_root(path, DEFAULT_WM_TEXT)

    def _remove_root(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Remove", "Select a root row first."); return
        for iid in sel:
            self.tree.delete(iid)

    def _remove_all(self):
        if not self.tree.get_children():
            return
        if messagebox.askyesno("Remove All", "Remove all roots from the list?"):
            for iid in self.tree.get_children():
                self.tree.delete(iid)

    # ----- DnD -----
    def _on_drop(self, event):
        try:
            paths = self.tk.splitlist(event.data)
        except Exception:
            paths = [event.data]
        for p in paths:
            p = (p or "").strip()
            if not p: continue
            path = Path(p)
            if path.is_dir():
                self._insert_or_update_root(str(path), DEFAULT_WM_TEXT)

    # ----- Inline edit -----
    def _on_tree_double_click(self, event):
        rowid = self.tree.identify_row(event.y)
        colid = self.tree.identify_column(event.x)
        if not rowid or colid != "#2":
            return
        self._end_edit(commit=False)
        x, y, w, h = self.tree.bbox(rowid, colid)
        cur = self.tree.set(rowid, "wm_text")
        self._edit_iid, self._edit_col = rowid, colid
        self._edit_entry = ttk.Entry(self.tree)
        self._edit_entry.insert(0, cur)
        self._edit_entry.select_range(0, tk.END)
        self._edit_entry.focus()
        self._edit_entry.place(x=x, y=y, width=w, height=h)
        self._edit_entry.bind("<Return>", lambda e: self._end_edit(True))
        self._edit_entry.bind("<Escape>", lambda e: self._end_edit(False))
        self._edit_entry.bind("<FocusOut>", lambda e: self._end_edit(True))

    def _end_edit(self, commit: bool):
        if not self._edit_entry:
            return
        if commit and self._edit_iid and self._edit_col == "#2":
            self.tree.set(self._edit_iid, "wm_text", self._edit_entry.get())
        self._edit_entry.destroy()
        self._edit_entry = None
        self._edit_iid = None
        self._edit_col = None

    # ----- Color helpers -----
    def _pick_color(self, var: tk.StringVar, swatch: tk.Label):
        initial = var.get() or "#000000"
        rgb, hx = colorchooser.askcolor(color=initial, title="Pick color")
        if hx:
            var.set(hx)
            self._update_swatch(swatch, hx)

    def _update_swatch(self, swatch: tk.Label, hx: str):
        try:
            swatch.configure(bg=hx)
        except Exception:
            swatch.configure(bg="#FFFFFF")

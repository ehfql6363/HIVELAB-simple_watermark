# -*- coding: utf-8 -*-
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox
from typing import Dict, Tuple, List
from pathlib import Path

from settings import DEFAULT_SIZES, DEFAULT_WM_TEXT, RootConfig

# DnD 이벤트 상수는 메인 윈도우에서 처리되어도 되지만,
# 여기서는 available 여부만 간단히 체크해 Entry 배치/Drop만 처리합니다.
try:
    from tkinterdnd2 import DND_FILES  # type: ignore
    DND_AVAILABLE = True
except Exception:
    DND_AVAILABLE = False
    DND_FILES = None  # type: ignore


class OptionsPanel(ttk.Frame):
    """
    - 여러 개의 루트 등록 (각 루트에 워터마크 텍스트)
    - 공통 옵션: 출력 루트, 사이즈, BG, 불투명도/스케일
    - 개선:
      * Root Tree에 폴더 Drag&Drop 지원 (tkinterdnd2 설치 시)
      * WM Text 더블클릭 인라인 편집
      * Remove / Remove All
      * Delete 키로 선택 삭제
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
        self.tree.heading("wm_text", text="WM Text (double-click to edit)")
        self.tree.column("root", width=520)
        self.tree.column("wm_text", width=260)
        self.tree.pack(fill="both", expand=True, side="left", padx=(6,0), pady=6)

        scrollbar = ttk.Scrollbar(roots, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        # DnD 지원
        if DND_AVAILABLE:
            try:
                self.tree.drop_target_register(DND_FILES)  # type: ignore
                self.tree.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                pass  # 환경에 따라 등록이 실패할 수 있으므로 조용히 무시

        # 더블 클릭 인라인 편집
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        # Delete 키로 삭제
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
    def _insert_or_update_root(self, path_str: str, wm_text: str = DEFAULT_WM_TEXT):
        # 중복 경로는 업데이트만
        for iid in self.tree.get_children():
            if self.tree.set(iid, "root") == path_str:
                self.tree.set(iid, "wm_text", wm_text)
                return
        self.tree.insert("", "end", values=(path_str, wm_text))

    def _add_root(self):
        path = filedialog.askdirectory(title="Select an Input Root (contains post folders)")
        if not path: return
        # 새 항목은 기본 WM으로 넣고, 필요 시 인라인 더블클릭으로 수정
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
            paths = self.tk.splitlist(event.data)  # 공백/중괄호 포함 경로 안전 분리
        except Exception:
            paths = [event.data]
        added = 0
        for p in paths:
            p = p.strip()
            if not p: continue
            path = Path(p)
            if path.is_dir():
                self._insert_or_update_root(str(path), DEFAULT_WM_TEXT)
                added += 1
        if added == 0:
            messagebox.showinfo("Drop", "드롭한 항목 중 폴더가 없습니다.")

    # ----- Inline edit -----
    def _on_tree_double_click(self, event):
        # 어느 셀인지 식별
        rowid = self.tree.identify_row(event.y)
        colid = self.tree.identify_column(event.x)  # "#1", "#2" ...
        if not rowid:
            return
        # WM Text 컬럼(#2)만 인라인 편집
        if colid != "#2":
            return
        # 편집 중이면 종료
        self._end_edit(commit=False)

        x, y, w, h = self.tree.bbox(rowid, colid)
        cur = self.tree.set(rowid, "wm_text")

        self._edit_iid = rowid
        self._edit_col = colid
        self._edit_entry = ttk.Entry(self.tree)
        self._edit_entry.insert(0, cur)
        self._edit_entry.select_range(0, tk.END)
        self._edit_entry.focus()
        self._edit_entry.place(x=x, y=y, width=w, height=h)

        self._edit_entry.bind("<Return>", lambda e: self._end_edit(commit=True))
        self._edit_entry.bind("<Escape>", lambda e: self._end_edit(commit=False))
        self._edit_entry.bind("<FocusOut>", lambda e: self._end_edit(commit=True))

    def _end_edit(self, commit: bool):
        if not self._edit_entry:
            return
        if commit and self._edit_iid and self._edit_col == "#2":
            new_val = self._edit_entry.get()
            self.tree.set(self._edit_iid, "wm_text", new_val)
        # clean up
        self._edit_entry.destroy()
        self._edit_entry = None
        self._edit_iid = None
        self._edit_col = None

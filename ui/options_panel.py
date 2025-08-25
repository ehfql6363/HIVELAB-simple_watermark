# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from typing import List
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
    def __init__(self, master):
        super().__init__(master)

        # 출력 + 타겟 크기(단일)
        top = ttk.Frame(self); top.pack(fill="x")
        ttk.Label(top, text="출력 폴더:").grid(row=0, column=0, sticky="w")
        self.var_output = tk.StringVar()
        ttk.Entry(top, textvariable=self.var_output, width=50).grid(row=0, column=1, sticky="we", padx=4)
        ttk.Button(top, text="찾기…", command=self._browse_output).grid(row=0, column=2, padx=4)

        size_frame = ttk.Frame(top); size_frame.grid(row=0, column=3, padx=8, sticky="w")
        ttk.Label(size_frame, text="타겟 크기:").grid(row=0, column=0, sticky="w")
        preset = [f"{w}x{h}" for (w, h) in DEFAULT_SIZES]
        self.var_size = tk.StringVar(value=preset[0])
        self.cb_size = ttk.Combobox(size_frame, textvariable=self.var_size, values=preset, width=12, state="readonly")
        self.cb_size.grid(row=1, column=0, sticky="w")

        # 워터마크 & 배경
        wm = ttk.LabelFrame(self, text="워터마크(기본: 가운데) · 배경")
        wm.pack(fill="x", pady=(6, 0))

        ttk.Label(wm, text="불투명도").grid(row=0, column=0, sticky="e")
        self.var_wm_opacity = tk.IntVar(value=30)
        ttk.Spinbox(wm, from_=0, to=100, textvariable=self.var_wm_opacity, width=5).grid(row=0, column=1, sticky="w")

        ttk.Label(wm, text="스케일 %").grid(row=0, column=2, sticky="e")
        self.var_wm_scale = tk.IntVar(value=5)
        ttk.Spinbox(wm, from_=1, to=50, textvariable=self.var_wm_scale, width=5).grid(row=0, column=3, sticky="w")

        ttk.Label(wm, text="배경색").grid(row=0, column=4, sticky="e")
        self.var_bg = tk.StringVar(value="#FFFFFF")
        self.ent_bg = ttk.Entry(wm, textvariable=self.var_bg, width=9)
        self.ent_bg.grid(row=0, column=5, sticky="w")
        self.sw_bg = _make_swatch(wm, self.var_bg.get()); self.sw_bg.grid(row=0, column=6, sticky="w", padx=4)
        ttk.Button(wm, text="선택…", command=lambda: self._pick_color(self.var_bg, self.sw_bg)).grid(row=0, column=7, sticky="w")

        ttk.Label(wm, text="글자색").grid(row=1, column=0, sticky="e", pady=(4,2))
        self.var_fill = tk.StringVar(value="#000000")
        self.ent_fill = ttk.Entry(wm, textvariable=self.var_fill, width=9); self.ent_fill.grid(row=1, column=1, sticky="w", pady=(4,2))
        self.sw_fill = _make_swatch(wm, self.var_fill.get()); self.sw_fill.grid(row=1, column=2, sticky="w", padx=4)
        ttk.Button(wm, text="선택…", command=lambda: self._pick_color(self.var_fill, self.sw_fill)).grid(row=1, column=3, sticky="w")

        ttk.Label(wm, text="외곽선").grid(row=1, column=4, sticky="e")
        self.var_stroke = tk.StringVar(value="#FFFFFF")
        self.ent_stroke = ttk.Entry(wm, textvariable=self.var_stroke, width=9); self.ent_stroke.grid(row=1, column=5, sticky="w")
        self.sw_stroke = _make_swatch(wm, self.var_stroke.get()); self.sw_stroke.grid(row=1, column=6, sticky="w", padx=4)
        ttk.Button(wm, text="선택…", command=lambda: self._pick_color(self.var_stroke, self.sw_stroke)).grid(row=1, column=7, sticky="w")

        ttk.Label(wm, text="외곽선 두께").grid(row=1, column=8, sticky="e")
        self.var_stroke_w = tk.IntVar(value=2)
        ttk.Spinbox(wm, from_=0, to=20, textvariable=self.var_stroke_w, width=5).grid(row=1, column=9, sticky="w")

        ttk.Label(wm, text="폰트 파일").grid(row=2, column=0, sticky="e", pady=(4,4))
        self.var_font = tk.StringVar(value="")
        ttk.Entry(wm, textvariable=self.var_font, width=50).grid(row=2, column=1, columnspan=5, sticky="we", padx=(0,4), pady=(4,4))
        ttk.Button(wm, text="찾기…", command=self._browse_font).grid(row=2, column=6, sticky="w", pady=(4,4))
        ttk.Button(wm, text="지우기", command=lambda: self.var_font.set("")).grid(row=2, column=7, sticky="w", pady=(4,4))

        # 루트 리스트
        roots = ttk.LabelFrame(self, text="루트 목록 (루트별 워터마크 텍스트)")
        roots.pack(fill="both", expand=True, pady=8)

        cols = ("root", "wm_text")
        self.tree = ttk.Treeview(roots, columns=cols, show="headings", height=6)
        self.tree.heading("root", text="루트 경로")
        self.tree.heading("wm_text", text="워터마크 텍스트(더블 클릭 편집)")
        self.tree.column("root", width=520); self.tree.column("wm_text", width=260)
        self.tree.pack(fill="both", expand=True, side="left", padx=(6,0), pady=6)

        scrollbar = ttk.Scrollbar(roots, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set); scrollbar.pack(side="right", fill="y")

        # 기존: 트리뷰 DnD 등록 (유지)
        if DND_AVAILABLE:
            try:
                self.tree.drop_target_register(DND_FILES)  # type: ignore
                self.tree.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                pass

        # 최상위 윈도우에도 드롭 받도록 백업 등록
        if DND_AVAILABLE:
            try:
                top = self.winfo_toplevel()
                top.drop_target_register(DND_FILES)  # type: ignore
                # 같은 핸들러 재사용 — 트리 위가 아니어도 정상 동작
                top.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                pass

        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self.tree.bind("<Delete>", lambda e: self._remove_root())

        btns = ttk.Frame(self); btns.pack(fill="x", pady=(0,6))
        ttk.Button(btns, text="루트 추가…", command=self._add_root).pack(side="left")
        ttk.Button(btns, text="삭제", command=self._remove_root).pack(side="left", padx=6)
        ttk.Button(btns, text="모두 삭제", command=self._remove_all).pack(side="left")

        self.var_bg.trace_add("write", lambda *_: self._update_swatch(self.sw_bg, self.var_bg.get()))
        self.var_fill.trace_add("write", lambda *_: self._update_swatch(self.sw_fill, self.var_fill.get()))
        self.var_stroke.trace_add("write", lambda *_: self._update_swatch(self.sw_stroke, self.var_stroke.get()))

        self._edit_entry = None; self._edit_iid = None; self._edit_col = None

    # ----- API -----
    def get_roots(self) -> List[RootConfig]:
        roots: List[RootConfig] = []
        for iid in self.tree.get_children():
            root = self.tree.set(iid, "root")
            wm = self.tree.set(iid, "wm_text")
            roots.append(RootConfig(path=Path(root), wm_text=wm or DEFAULT_WM_TEXT))
        return roots

    def collect_options(self):
        size_str = self.var_size.get().lower().replace(" ", "")
        try:
            w, h = map(int, size_str.split("x")); sizes = [(w, h)]
        except Exception:
            sizes = [DEFAULT_SIZES[0]]

        font_path = self.var_font.get().strip()
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
            font_path or "",
        )

    # ----- Browsers -----
    def _browse_output(self):
        path = filedialog.askdirectory(title="출력 폴더 선택")
        if path: self.var_output.set(path)

    def _browse_font(self):
        path = filedialog.askopenfilename(
            title="폰트 파일 선택 (TTF/OTF/TTC)",
            filetypes=[("Font files", "*.ttf *.otf *.ttc"), ("All files", "*.*")]
        )
        if path:
            self.var_font.set(path)

    # ----- Roots mgmt -----
    def _insert_or_update_root(self, path_str: str, wm_text: str = DEFAULT_WM_TEXT):
        for iid in self.tree.get_children():
            if self.tree.set(iid, "root") == path_str:
                self.tree.set(iid, "wm_text", wm_text); return
        self.tree.insert("", "end", values=(path_str, wm_text))

    def _add_root(self):
        path = filedialog.askdirectory(title="입력 루트 선택 (게시물 폴더 포함)")
        if path: self._insert_or_update_root(path, DEFAULT_WM_TEXT)

    def _remove_root(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("삭제", "먼저 루트 행을 선택하세요."); return
        for iid in sel: self.tree.delete(iid)

    def _remove_all(self):
        if not self.tree.get_children(): return
        if messagebox.askyesno("모두 삭제", "루트 목록을 모두 삭제할까요?"):
            for iid in self.tree.get_children(): self.tree.delete(iid)

    # ----- DnD -----
    def _on_drop(self, event):
        try: paths = self.tk.splitlist(event.data)
        except Exception: paths = [event.data]
        for p in paths:
            p = (p or "").strip()
            if not p: continue
            path = Path(p)
            if path.is_dir():
                self._insert_or_update_root(str(path), DEFAULT_WM_TEXT)

    # ----- Inline edit (wm_text) -----
    def _on_tree_double_click(self, event):
        rowid = self.tree.identify_row(event.y)
        colid = self.tree.identify_column(event.x)
        if not rowid or colid != "#2": return
        self._end_edit(commit=False)
        x, y, w, h = self.tree.bbox(rowid, colid)
        cur = self.tree.set(rowid, "wm_text")
        self._edit_iid, self._edit_col = rowid, colid
        self._edit_entry = ttk.Entry(self.tree)
        self._edit_entry.insert(0, cur); self._edit_entry.select_range(0, tk.END)
        self._edit_entry.focus(); self._edit_entry.place(x=x, y=y, width=w, height=h)
        self._edit_entry.bind("<Return>", lambda e: self._end_edit(True))
        self._edit_entry.bind("<Escape>", lambda e: self._end_edit(False))
        self._edit_entry.bind("<FocusOut>", lambda e: self._end_edit(True))

    def _end_edit(self, commit: bool):
        if not self._edit_entry: return
        if commit and self._edit_iid and self._edit_col == "#2":
            self.tree.set(self._edit_iid, "wm_text", self._edit_entry.get())
        self._edit_entry.destroy(); self._edit_entry = None; self._edit_iid = None; self._edit_col = None

    # ----- Color helpers -----
    def _pick_color(self, var: tk.StringVar, swatch: tk.Label):
        initial = var.get() or "#000000"
        _, hx = colorchooser.askcolor(color=initial, title="색상 선택")
        if hx:
            var.set(hx); self._update_swatch(swatch, hx)

    def _update_swatch(self, swatch: tk.Label, hx: str):
        try: swatch.configure(bg=hx)
        except Exception: swatch.configure(bg="#FFFFFF")

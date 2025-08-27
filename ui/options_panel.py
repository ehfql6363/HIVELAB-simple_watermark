# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from typing import List, Optional, Callable, Tuple, Dict
from pathlib import Path

from settings import DEFAULT_SIZES, DEFAULT_WM_TEXT, RootConfig, IMAGES_VROOT
from services.discovery import IMG_EXTS  # 이미지 확장자 활용

IMAGES_DISPLAY = "이미지"  # 가상 루트 표시 라벨(트리뷰에 이렇게 보임)

# DnD
try:
    from tkinterdnd2 import DND_FILES  # type: ignore
    DND_AVAILABLE = True
except Exception:
    DND_AVAILABLE = False
    DND_FILES = None  # type: ignore

def _make_swatch(parent, hex_color: str):
    sw = tk.Label(parent, text="  ", relief="groove", bd=1, width=2)
    try:
        sw.configure(bg=hex_color)
    except Exception:
        sw.configure(bg="#FFFFFF")
    return sw


class OptionsPanel(ttk.Frame):
    def __init__(self, master, on_change: Optional[Callable[[], None]] = None):
        super().__init__(master)
        self._on_change = on_change
        self._recent_root_dir: Optional[Path] = None
        self._recent_font_dir: Optional[Path] = None

        # 드롭 이미지 저장소
        self._dropped_images: List[Path] = []

        # ── 상단: 출력 루트 + 드롭 상태 ─────────────────────────────────────────
        top = ttk.Frame(self)
        top.pack(fill="x")

        out = ttk.Frame(top)
        out.grid(row=0, column=0, sticky="we", padx=0, pady=(0, 2))
        out.columnconfigure(1, weight=1)

        ttk.Label(out, text="출력 루트:").grid(row=0, column=0, sticky="w")
        self.var_output = tk.StringVar(value="")
        self.ent_output = ttk.Entry(out, textvariable=self.var_output)
        self.ent_output.grid(row=0, column=1, sticky="we", padx=(6, 6))
        ttk.Button(out, text="찾기…", command=self._browse_output).grid(row=0, column=2, sticky="w")

        info = ttk.Frame(top)
        info.grid(row=0, column=1, sticky="w")
        self._lbl_drop = ttk.Label(info, text="드롭한 이미지: 0개", foreground="#666")
        self._lbl_drop.pack(side="left")
        ttk.Button(info, text="비우기", command=self._clear_dropped).pack(side="left", padx=(8, 0))

        # 출력 루트가 바뀌면 변경 알림
        self.var_output.trace_add("write", lambda *_: self._notify_change())

        # ── 타겟 크기 프리셋 ───────────────────────────────────────────────────
        size_frame = ttk.Frame(top)
        size_frame.grid(row=0, column=2, padx=0, pady=(0, 2), sticky="w")
        ttk.Label(size_frame, text="타겟 크기:").grid(row=0, column=0, sticky="w")
        preset = ["원본 그대로"] + [f"{w}x{h}" for (w, h) in DEFAULT_SIZES]
        self.var_size = tk.StringVar(value=preset[1])
        self.cb_size = ttk.Combobox(size_frame, textvariable=self.var_size, values=preset,
                                    width=12, state="readonly")
        self.cb_size.grid(row=0, column=3, sticky="w")
        self.cb_size.bind("<<ComboboxSelected>>", lambda e: self._notify_change())

        # ── 워터마크/배경 ──────────────────────────────────────────────────────
        wm = ttk.LabelFrame(self, text="워터마크(기본: 가운데) · 배경")
        wm.pack(fill="x", pady=(6, 0))

        ttk.Label(wm, text="불투명도").grid(row=0, column=0, sticky="e")
        self.var_wm_opacity = tk.IntVar(value=30)
        ttk.Spinbox(wm, from_=0, to=100, textvariable=self.var_wm_opacity, width=5,
                    command=self._notify_change).grid(row=0, column=1, sticky="w")

        ttk.Label(wm, text="스케일 %").grid(row=0, column=2, sticky="e")
        self.var_wm_scale = tk.IntVar(value=20)
        ttk.Spinbox(wm, from_=1, to=50, textvariable=self.var_wm_scale, width=5,
                    command=self._notify_change).grid(row=0, column=3, sticky="w")

        ttk.Label(wm, text="배경색").grid(row=0, column=4, sticky="e")
        self.var_bg = tk.StringVar(value="#FFFFFF")
        self.ent_bg = ttk.Entry(wm, textvariable=self.var_bg, width=9)
        self.ent_bg.grid(row=0, column=5, sticky="w")
        self.sw_bg = _make_swatch(wm, self.var_bg.get()); self.sw_bg.grid(row=0, column=6, sticky="w", padx=4)
        ttk.Button(wm, text="선택…", command=lambda: self._pick_color(self.var_bg, self.sw_bg)).grid(row=0, column=7, sticky="w")

        ttk.Label(wm, text="전경색").grid(row=1, column=0, sticky="e", pady=(4, 2))
        self.var_fill = tk.StringVar(value="#000000")
        self.ent_fill = ttk.Entry(wm, textvariable=self.var_fill, width=9)
        self.ent_fill.grid(row=1, column=1, sticky="w", pady=(4, 2))
        self.sw_fill = _make_swatch(wm, self.var_fill.get()); self.sw_fill.grid(row=1, column=2, sticky="w", padx=4)
        ttk.Button(wm, text="선택…", command=lambda: self._pick_color(self.var_fill, self.sw_fill)).grid(row=1, column=3, sticky="w")

        ttk.Label(wm, text="외곽선").grid(row=1, column=4, sticky="e")
        self.var_stroke = tk.StringVar(value="#FFFFFF")
        self.ent_stroke = ttk.Entry(wm, textvariable=self.var_stroke, width=9)
        self.ent_stroke.grid(row=1, column=5, sticky="w")
        self.sw_stroke = _make_swatch(wm, self.var_stroke.get()); self.sw_stroke.grid(row=1, column=6, sticky="w", padx=4)
        ttk.Button(wm, text="선택…", command=lambda: self._pick_color(self.var_stroke, self.sw_stroke)).grid(row=1, column=7, sticky="w")

        ttk.Label(wm, text="외곽선 두께").grid(row=1, column=8, sticky="e")
        self.var_stroke_w = tk.IntVar(value=2)
        ttk.Spinbox(wm, from_=0, to=20, textvariable=self.var_stroke_w, width=5,
                    command=self._notify_change).grid(row=1, column=9, sticky="w")

        ttk.Label(wm, text="폰트 파일").grid(row=2, column=0, sticky="e", pady=(4, 4))
        self.var_font = tk.StringVar(value="")
        ttk.Entry(wm, textvariable=self.var_font, width=50).grid(
            row=2, column=1, columnspan=5, sticky="we", padx=(0, 4), pady=(4, 4)
        )
        ttk.Button(wm, text="찾기…", command=self._browse_font).grid(row=2, column=6, sticky="w", pady=(4, 4))
        ttk.Button(wm, text="지우기", command=self._clear_font).grid(row=2, column=7, sticky="w", pady=(4, 4))

        # ⬇⬇⬇ 추가: 사용자가 직접 타이핑해도 저장 반영
        self.var_font.trace_add("write", lambda *_: self._notify_change())

        # ── 루트 목록(루트별 워터마크 텍스트) ──────────────────────────────────
        roots = ttk.LabelFrame(self, text="루트 목록 (루트별 워터마크 텍스트)")
        roots.pack(fill="both", expand=True, pady=8)

        cols = ("root", "wm_text")
        self.tree = ttk.Treeview(roots, columns=cols, show="headings", height=6)
        self.tree.heading("root", text="루트 경로")
        self.tree.heading("wm_text", text="워터마크 텍스트(더블 클릭 편집)")
        self.tree.column("root", width=520)
        self.tree.column("wm_text", width=260)
        self.tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)

        scrollbar = ttk.Scrollbar(roots, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        # DnD 등록
        if DND_AVAILABLE:
            try:
                self.tree.drop_target_register(DND_FILES)  # type: ignore
                self.tree.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                pass
            try:
                topwin = self.winfo_toplevel()
                topwin.drop_target_register(DND_FILES)  # type: ignore
                topwin.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                pass

        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self.tree.bind("<Delete>", lambda e: self._remove_root())

        btns = ttk.Frame(self)
        btns.pack(fill="x", pady=(0, 6))
        ttk.Button(btns, text="루트 추가…", command=self._add_root).pack(side="left")
        ttk.Button(btns, text="삭제", command=self._remove_root).pack(side="left", padx=6)
        ttk.Button(btns, text="모두 삭제", command=self._remove_all).pack(side="left")

        # 스와치 동기
        self.var_bg.trace_add("write", lambda *_: self._update_swatch(self.sw_bg, self.var_bg.get()))
        self.var_fill.trace_add("write", lambda *_: self._update_swatch(self.sw_fill, self.var_fill.get()))
        self.var_stroke.trace_add("write", lambda *_: self._update_swatch(self.sw_stroke, self.var_stroke.get()))

        # 인라인 편집 상태
        self._edit_entry = None
        self._edit_iid = None
        self._edit_col = None

    # ---------- 외부 API ----------
    def get_output_root_str(self) -> str:
        try:
            return (self.var_output.get() or "").strip()
        except Exception:
            return ""

    def get_dropped_images(self) -> List[Path]:
        # 순서 보존 중복 제거
        seen = set()
        out: List[Path] = []
        for p in self._dropped_images:
            if p not in seen:
                seen.add(p)
                out.append(p)
        return out

    def _clear_dropped(self):
        self._dropped_images.clear()
        self._update_drop_label()
        self._notify_change()

    def _update_drop_label(self):
        self._lbl_drop.configure(text=f"드롭한 이미지: {len(self._dropped_images)}개")

    def get_roots(self) -> List[RootConfig]:
        roots: List[RootConfig] = []
        for iid in self.tree.get_children():
            root_disp = self.tree.set(iid, "root")
            wm = self.tree.set(iid, "wm_text")
            if root_disp == IMAGES_DISPLAY:
                # 가상 루트는 특수 경로(IMAGES_VROOT)로 표시
                roots.append(RootConfig(path=Path(IMAGES_VROOT), wm_text=wm or DEFAULT_WM_TEXT))
            else:
                roots.append(RootConfig(path=Path(root_disp), wm_text=wm or DEFAULT_WM_TEXT))
        return roots

    def collect_options(self):
        size_str = self.var_size.get().lower().replace(" ", "")
        if "원본" in size_str:
            sizes = [(0, 0)]
        else:
            try:
                w, h = map(int, size_str.split("x"))
                sizes = [(w, h)]
            except Exception:
                sizes = [DEFAULT_SIZES[0]]

        font_path = self.var_font.get().strip()
        out_root_str = self.get_output_root_str()
        return (
            sizes,
            self.var_bg.get().strip(),
            int(self.var_wm_opacity.get()),
            int(self.var_wm_scale.get()),
            out_root_str,              # ⬅ 여기서 반환
            self.get_roots(),
            self.var_fill.get().strip() or "#000000",
            self.var_stroke.get().strip() or "#FFFFFF",
            int(self.var_stroke_w.get()),
            font_path or "",
        )

    def set_initial_options(self, settings):
        # 최근 경로들
        self._recent_root_dir = settings.last_dir_output_dialog
        self._recent_font_dir = settings.last_dir_font_dialog

        # 출력 루트 초기값
        try:
            self.var_output.set(str(settings.output_root) if settings.output_root else "")
        except Exception:
            pass

        # 크기/색/폰트 초기값
        try:
            s0 = settings.sizes[0] if settings.sizes else None
            if s0 == (0, 0):
                self.var_size.set("원본 그대로")
            elif s0:
                self.var_size.set(f"{int(s0[0])}x{int(s0[1])}")
        except Exception:
            pass
        try:
            self.var_bg.set("#%02X%02X%02X" % settings.bg_color)
        except Exception:
            pass
        try:
            self.var_wm_opacity.set(int(settings.wm_opacity))
        except Exception:
            pass
        try:
            self.var_wm_scale.set(int(settings.wm_scale_pct))
        except Exception:
            pass
        try:
            self.var_fill.set("#%02X%02X%02X" % settings.wm_fill_color)
        except Exception:
            pass
        try:
            self.var_stroke.set("#%02X%02X%02X" % settings.wm_stroke_color)
        except Exception:
            pass
        try:
            self.var_stroke_w.set(int(settings.wm_stroke_width))
        except Exception:
            pass
        try:
            self.var_font.set(str(settings.wm_font_path) if settings.wm_font_path else "")
        except Exception:
            pass
        self._notify_change()

        try:
            self._update_swatch(self.sw_bg, self.var_bg.get())
            self._update_swatch(self.sw_fill, self.var_fill.get())
            self._update_swatch(self.sw_stroke, self.var_stroke.get())
        except Exception:
            pass

    def get_recent_dirs(self) -> Tuple[Optional[Path], Optional[Path]]:
        return (self._recent_root_dir, self._recent_font_dir)

    def set_recent_dirs(self, root_dir: Optional[Path], font_dir: Optional[Path]):
        self._recent_root_dir = root_dir
        self._recent_font_dir = font_dir

    # ---------- Browsers ----------
    def _browse_output(self):
        base = self._recent_root_dir or Path.home()
        path = filedialog.askdirectory(title="출력 루트 선택", initialdir=str(base))
        if path:
            self.var_output.set(path)
            try:
                self._recent_root_dir = Path(path)
            except Exception:
                pass
            self._notify_change()

    def _browse_font(self):
        curf = self.var_font.get().strip()
        parent = Path(curf).parent if curf else None
        initial = str(parent if (parent and parent.exists()) else (self._recent_font_dir or Path.home()))
        path = filedialog.askopenfilename(
            title="폰트 파일 선택 (TTF/OTF/TTC)",
            filetypes=[("Font files", "*.ttf *.otf *.ttc"), ("All files", "*.*")],
            initialdir=initial
        )
        if path:
            self.var_font.set(path)
            try:
                self._recent_font_dir = Path(path).parent
            except Exception:
                pass
            self._notify_change()

    def _clear_font(self):
        self.var_font.set("")
        self._notify_change()

    # ---------- Roots/Images mgmt ----------
    def _insert_or_update_root(self, path_str: str, wm_text: str = DEFAULT_WM_TEXT):
        for iid in self.tree.get_children():
            if self.tree.set(iid, "root") == path_str:
                self.tree.set(iid, "wm_text", wm_text)
                return
        self.tree.insert("", "end", values=(path_str, wm_text))

    def _ensure_images_row(self):
        # “이미지”(가상 루트) 행이 없으면 추가
        for iid in self.tree.get_children():
            if self.tree.set(iid, "root") == IMAGES_DISPLAY:
                return
        self.tree.insert("", "end", values=(IMAGES_DISPLAY, DEFAULT_WM_TEXT))

    def _add_root(self):
        base = self._recent_root_dir or Path.home()
        path = filedialog.askdirectory(title="입력 루트 선택 (게시물 폴더 포함)", initialdir=str(base))
        if path:
            self._insert_or_update_root(path, DEFAULT_WM_TEXT)
            try:
                self._recent_root_dir = Path(path)
            except Exception:
                pass
            self._notify_change()

    def _remove_root(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("삭제", "삭제할 루트를 선택하세요.")
            return
        for iid in sel:
            root_disp = self.tree.set(iid, "root")
            if root_disp == IMAGES_DISPLAY:
                # 가상 루트 삭제 시 드롭 목록 비움
                self._dropped_images.clear()
            self.tree.delete(iid)
        self._notify_change()

    def _remove_all(self):
        if not self.tree.get_children():
            return
        if messagebox.askyesno("모두 삭제", "루트 목록을 모두 삭제할까요? (드롭 이미지 포함)"):
            for iid in self.tree.get_children():
                self.tree.delete(iid)
            self._dropped_images.clear()
            self._notify_change()

    # ---------- DnD ----------
    def _on_drop(self, event):
        try:
            paths = self.tk.splitlist(event.data)
        except Exception:
            paths = [event.data]

        added_image = False
        for p in paths:
            p = (p or "").strip()
            if not p:
                continue
            path = Path(p)
            if path.is_dir():
                self._insert_or_update_root(str(path), DEFAULT_WM_TEXT)
                try:
                    self._recent_root_dir = path
                except Exception:
                    pass
            elif path.is_file() and path.suffix.lower() in IMG_EXTS:
                self._dropped_images.append(path)
                added_image = True
                try:
                    self._recent_root_dir = path.parent
                except Exception:
                    pass

        if added_image:
            self._ensure_images_row()

        self._update_drop_label()
        self._notify_change()

    # ---------- Inline edit ----------
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
        self._notify_change()

    # ---------- Color helpers ----------
    def _pick_color(self, var: tk.StringVar, swatch: tk.Label):
        initial = var.get() or "#000000"
        _, hx = colorchooser.askcolor(color=initial, title="색상 선택")
        if hx:
            var.set(hx)
            self._update_swatch(swatch, hx)
            self._notify_change()

    def _update_swatch(self, swatch: tk.Label, hx: str):
        try:
            swatch.configure(bg=hx)
        except Exception:
            swatch.configure(bg="#FFFFFF")

    # ---------- change notify ----------
    def _notify_change(self):
        if callable(self._on_change):
            self._on_change()

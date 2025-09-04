# ui/wm_panel.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, filedialog, colorchooser
from pathlib import Path
from typing import Callable, Optional, Tuple, List

from settings import DEFAULT_SIZES, DEFAULT_WM_TEXT
try:
    from services.discovery import IMG_EXTS  # 이미지 확장자
except Exception:
    IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"}

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

class WmPanel(ttk.LabelFrame):
    """
    B 패널: 출력 루트 / 드롭한 이미지 / 타겟 크기 / 워터마크 및 배경
    - main_window.py 에서 옵션값을 읽기/설정하기 위한 얇은 API 제공
    - 내부 값 변경 시 on_change 콜백 호출
    """
    def __init__(self, master, on_change: Optional[Callable[[], None]] = None,
                 title: str = "출력 · 드롭 · 타겟크기 · 워터마크/배경"):
        super().__init__(master, text=title, padding=(8, 6))
        self._on_change = on_change

        # 최근 경로
        self._recent_root_dir: Optional[Path] = None
        self._recent_font_dir: Optional[Path] = None

        # 드롭 이미지
        self._dropped_images: List[Path] = []

        # ── 1) 상단: 출력 루트 + 드롭 상태 ──────────────────────────────
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 6))

        top.grid_columnconfigure(0, weight=1)
        top.grid_columnconfigure(1, weight=0)

        out = ttk.Frame(top)
        out.grid(row=0, column=0, sticky="we", padx=(0, 8))
        out.columnconfigure(1, weight=1)

        ttk.Label(out, text="출력 루트:").grid(row=0, column=0, sticky="w")
        self.var_output = tk.StringVar(value="")
        ent_output = ttk.Entry(out, textvariable=self.var_output)
        ent_output.grid(row=0, column=1, sticky="we", padx=(6, 6))
        ttk.Button(out, text="찾기…", command=self._browse_output, style="secondary.TButton").grid(row=0, column=2, sticky="w")

        info = ttk.Frame(top)
        info.grid(row=0, column=1, sticky="e")
        self._lbl_drop = ttk.Label(info, text="드롭한 이미지: 0개", foreground="#666")
        self._lbl_drop.pack(side="left")
        ttk.Button(info, text="비우기", command=self._clear_dropped, style="secondary.TButton").pack(side="left", padx=(8, 0))

        # 출력 루트 변경 알림
        self.var_output.trace_add("write", lambda *_: self._notify_change())

        # ── 2) 타겟 크기 + 커스텀 ────────────────────────────────────────
        sizes_bar = ttk.Frame(self)
        sizes_bar.pack(fill="x", pady=(0, 8))

        ttk.Label(sizes_bar, text="타겟 크기:").pack(side="left")
        preset = ["원본 그대로"] + [f"{w}x{h}" for (w, h) in DEFAULT_SIZES] + ["직접 지정…"]
        self.var_size = tk.StringVar(value=preset[0])
        self.cb_size = ttk.Combobox(sizes_bar, textvariable=self.var_size, values=preset, width=12, state="readonly")
        self.cb_size.pack(side="left", padx=(6, 0))
        self.cb_size.bind("<<ComboboxSelected>>",
                          lambda e: (self._refresh_custom_size_state(), self._notify_change()))

        self.var_custom_w = tk.IntVar(value=1080)
        self.var_custom_h = tk.IntVar(value=1080)
        self.sp_w = ttk.Spinbox(sizes_bar, from_=32, to=10000, width=6, textvariable=self.var_custom_w,
                                command=self._notify_change, state="disabled")
        self.sp_w.pack(side="left", padx=(6, 0))
        ttk.Label(sizes_bar, text="x").pack(side="left", padx=(4, 4))
        self.sp_h = ttk.Spinbox(sizes_bar, from_=32, to=10000, width=6, textvariable=self.var_custom_h,
                                command=self._notify_change, state="disabled")
        self.sp_h.pack(side="left")

        self.var_custom_w.trace_add("write", lambda *_: self._notify_change())
        self.var_custom_h.trace_add("write", lambda *_: self._notify_change())

        # ── 3) 워터마크/배경 ─────────────────────────────────────────────
        wm = ttk.LabelFrame(self, text="워터마크(기본: 가운데) · 배경", padding=(8, 6))
        wm.pack(fill="x")

        for c in (1, 2, 3, 4, 5, 6, 7, 8, 9):
            wm.grid_columnconfigure(c, weight=1)

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
        ttk.Button(wm, text="선택…", command=lambda: self._pick_color(self.var_bg, self.sw_bg),
                   style="secondary.TButton").grid(row=0, column=7, sticky="w")

        ttk.Label(wm, text="글자색").grid(row=1, column=0, sticky="e", pady=(4, 2))
        self.var_fill = tk.StringVar(value="#000000")
        self.ent_fill = ttk.Entry(wm, textvariable=self.var_fill, width=9)
        self.ent_fill.grid(row=1, column=1, sticky="w", pady=(4, 2))
        self.sw_fill = _make_swatch(wm, self.var_fill.get()); self.sw_fill.grid(row=1, column=2, sticky="w", padx=4)
        ttk.Button(wm, text="선택…", command=lambda: self._pick_color(self.var_fill, self.sw_fill),
                   style="secondary.TButton").grid(row=1, column=3, sticky="w")

        ttk.Label(wm, text="외곽선").grid(row=1, column=4, sticky="e")
        self.var_stroke = tk.StringVar(value="#FFFFFF")
        self.ent_stroke = ttk.Entry(wm, textvariable=self.var_stroke, width=9)
        self.ent_stroke.grid(row=1, column=5, sticky="w")
        self.sw_stroke = _make_swatch(wm, self.var_stroke.get()); self.sw_stroke.grid(row=1, column=6, sticky="w", padx=4)
        ttk.Button(wm, text="선택…", command=lambda: self._pick_color(self.var_stroke, self.sw_stroke),
                   style="secondary.TButton").grid(row=1, column=7, sticky="w")

        ttk.Label(wm, text="외곽선 두께").grid(row=1, column=8, sticky="e")
        self.var_stroke_w = tk.IntVar(value=2)
        ttk.Spinbox(wm, from_=0, to=20, textvariable=self.var_stroke_w, width=5,
                    command=self._notify_change).grid(row=1, column=9, sticky="w")

        ttk.Label(wm, text="폰트 파일").grid(row=2, column=0, sticky="e", pady=(4, 4))
        self.var_font = tk.StringVar(value="")
        ttk.Entry(wm, textvariable=self.var_font, width=50).grid(
            row=2, column=1, columnspan=5, sticky="we", padx=(0, 4), pady=(4, 4)
        )
        ttk.Button(wm, text="찾기…", command=self._browse_font, style="secondary.TButton").grid(row=2, column=6, sticky="w", pady=(4, 4))
        ttk.Button(wm, text="지우기", command=self._clear_font, style="secondary.TButton").grid(row=2, column=7, sticky="w", pady=(4, 4))
        self.var_font.trace_add("write", lambda *_: self._notify_change())

        # 스와치 동기
        self.var_bg.trace_add("write", lambda *_: self._update_swatch(self.sw_bg, self.var_bg.get()))
        self.var_fill.trace_add("write", lambda *_: self._update_swatch(self.sw_fill, self.var_fill.get()))
        self.var_stroke.trace_add("write", lambda *_: self._update_swatch(self.sw_stroke, self.var_stroke.get()))

        # DnD: 이미지 파일만 수집(루트 추가는 RootPanel에서 함)
        if DND_AVAILABLE:
            try:
                pass
            except Exception:
                pass

        # 처음엔 커스텀 비활성
        self._refresh_custom_size_state()

        # 높이 제한용(옵션)
        self._max_height: Optional[int] = None

    # ───────── 외부 API ─────────
    def set_initial_options(self, settings):
        # 최근 경로 세팅
        self._recent_root_dir = settings.last_dir_output_dialog
        self._recent_font_dir = settings.last_dir_font_dialog

        # 크기
        try:
            s0 = settings.sizes[0] if settings.sizes else None
            preset_set = {(w, h) for (w, h) in DEFAULT_SIZES}
            if s0 == (0, 0):
                self.var_size.set("원본 그대로")
            elif s0 and s0 in preset_set:
                self.var_size.set(f"{int(s0[0])}x{int(s0[1])}")
            elif s0 and isinstance(s0, tuple) and len(s0) == 2:
                self.var_size.set("직접 지정…")
                try:
                    self.var_custom_w.set(int(s0[0]))
                    self.var_custom_h.set(int(s0[1]))
                except Exception:
                    pass
            self._refresh_custom_size_state()
        except Exception:
            pass

        # 색/수치/폰트
        try: self.var_bg.set("#%02X%02X%02X" % tuple(settings.bg_color))
        except Exception: pass
        try: self.var_wm_opacity.set(int(settings.wm_opacity))
        except Exception: pass
        try: self.var_wm_scale.set(int(settings.wm_scale_pct))
        except Exception: pass
        try: self.var_fill.set("#%02X%02X%02X" % tuple(settings.wm_fill_color))
        except Exception: pass
        try: self.var_stroke.set("#%02X%02X%02X" % tuple(settings.wm_stroke_color))
        except Exception: pass
        try: self.var_stroke_w.set(int(settings.wm_stroke_width))
        except Exception: pass
        try: self.var_font.set(str(settings.wm_font_path) if settings.wm_font_path else "")
        except Exception: pass

        # 스와치 즉시 반영
        try:
            self._update_swatch(self.sw_bg, self.var_bg.get())
            self._update_swatch(self.sw_fill, self.var_fill.get())
            self._update_swatch(self.sw_stroke, self.var_stroke.get())
        except Exception:
            pass

        self._notify_change()

    def collect_options(self):
        # 크기 결정
        size_str = (self.var_size.get() or "").lower().replace(" ", "")
        if "원본" in size_str:
            sizes = [(0, 0)]
        elif "직접" in size_str:
            try:
                w = int(self.var_custom_w.get()); h = int(self.var_custom_h.get())
                sizes = [(w, h)] if w > 0 and h > 0 else [DEFAULT_SIZES[0]]
            except Exception:
                sizes = [DEFAULT_SIZES[0]]
        else:
            try:
                w, h = map(int, size_str.split("x"))
                sizes = [(w, h)]
            except Exception:
                sizes = [DEFAULT_SIZES[0]]

        out_root_str = (self.var_output.get() or "").strip()
        font_path_str = (self.var_font.get() or "").strip()

        # roots 항목은 MainWindow에서 RootPanel로 별도 취급하므로 여기서는 빈 리스트(placeholder)

        return (
            sizes,
            self.var_bg.get().strip(),
            int(self.var_wm_opacity.get()),
            int(self.var_wm_scale.get()),
            out_root_str,
            self.var_fill.get().strip() or "#000000",
            self.var_stroke.get().strip() or "#FFFFFF",
            int(self.var_stroke_w.get()),
            font_path_str or "",
        )

    def get_output_root_str(self) -> str:
        return (self.var_output.get() or "").strip()

    def set_output_root_str(self, s: str):
        self.var_output.set(s or "")
        self._notify_change()

    def get_font_path_str(self) -> str:
        return (self.var_font.get() or "").strip()

    def set_font_path_str(self, s: str):
        self.var_font.set(s or "")
        self._notify_change()

    def get_recent_dirs(self) -> Tuple[Optional[Path], Optional[Path]]:
        return (self._recent_root_dir, self._recent_font_dir)

    def get_dropped_images(self) -> List[Path]:
        # 순서 보존 + 중복 제거
        seen = set()
        out: List[Path] = []
        for p in self._dropped_images:
            if p not in seen:
                seen.add(p); out.append(p)
        return out

    def set_max_height(self, max_h: int):
        """헤더 높이 클램프 (라벨프레임 자체에 고정 높이를 주고, geometry propagate를 끔)"""
        self._max_height = int(max_h)
        try:
            self.update_idletasks()
            self.configure(height=self._max_height)
            self.grid_propagate(False)
        except Exception:
            pass

    # ───────── 내부 핸들러 ─────────
    def _browse_output(self):
        base = self._recent_root_dir or Path.home()
        path = filedialog.askdirectory(title="출력 루트 선택", initialdir=str(base))
        if path:
            self.var_output.set(path)
            try: self._recent_root_dir = Path(path)
            except Exception: pass
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
            try: self._recent_font_dir = Path(path).parent
            except Exception: pass
            self._notify_change()

    def _clear_font(self):
        self.var_font.set("")
        self._notify_change()

    def _clear_dropped(self):
        self._dropped_images.clear()
        self._update_drop_label()
        self._notify_change()

    def _update_drop_label(self):
        try:
            self._lbl_drop.configure(text=f"드롭한 이미지: {len(self._dropped_images)}개")
        except Exception:
            pass

    def _on_drop(self, event):
        """상단 창에 이미지를 드롭하면 B 패널이 수집 (폴더 드롭은 무시; 루트 추가는 RootPanel 담당)"""
        try:
            paths = self.tk.splitlist(event.data)
        except Exception:
            paths = [event.data]

        added = False
        for p in paths:
            p = (p or "").strip()
            if not p:
                continue
            path = Path(p)
            if path.is_file() and path.suffix.lower() in IMG_EXTS:
                self._dropped_images.append(path)
                added = True
                try: self._recent_root_dir = path.parent
                except Exception: pass

        if added:
            self._update_drop_label()
            self._notify_change()

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

    def _refresh_custom_size_state(self):
        is_custom = "직접" in (self.var_size.get() or "")
        state = "normal" if is_custom else "disabled"
        for w in (self.sp_w, self.sp_h):
            w.configure(state=state)

    def _notify_change(self):
        if callable(self._on_change):
            self._on_change()

# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, colorchooser, filedialog
from pathlib import Path
from typing import Optional, Tuple, Callable

def _rgb_from_hex(hx: str) -> Tuple[int,int,int]:
    hx = (hx or "").strip()
    if not hx.startswith("#"):
        return (0,0,0)
    if len(hx) == 4:
        r = int(hx[1]*2, 16); g = int(hx[2]*2, 16); b = int(hx[3]*2, 16)
        return (r,g,b)
    if len(hx) >= 7:
        return (int(hx[1:3],16), int(hx[3:5],16), int(hx[5:7],16))
    return (0,0,0)

def _hex_from_rgb(rgb: Tuple[int,int,int]) -> str:
    try:
        r,g,b = rgb
        return f"#{r:02X}{g:02X}{b:02X}"
    except Exception:
        return "#000000"

class ImageWMEditor(ttk.Frame):
    """
    개별 이미지 워터마크 에디터(분리형)
      - set_active_image_and_defaults(path, cfg) 로 대상/기본값 주입
      - on_apply(path, override_dict) / on_clear(path)
    """
    def __init__(self, master,
                 on_apply: Optional[Callable[[Path, dict], None]] = None,
                 on_clear: Optional[Callable[[Path], None]] = None):
        super().__init__(master)
        self._on_apply = on_apply
        self._on_clear = on_clear
        self._active_path: Optional[Path] = None

        box = ttk.LabelFrame(self, text="개별 이미지 워터마크")
        box.pack(fill="x", expand=False)

        # 상태 변수
        self.var_wm_text = tk.StringVar(value="")
        self.var_opacity = tk.IntVar(value=30)
        self.var_scale = tk.IntVar(value=20)
        self.var_fill = tk.StringVar(value="#000000")   # 글자색
        self.var_stroke = tk.StringVar(value="#FFFFFF") # 외곽선색
        self.var_stroke_w = tk.IntVar(value=2)
        self.var_font = tk.StringVar(value="")

        # 그리드: 여백 통일
        pad_x, pad_y = (10, 6)

        # 1행: 텍스트
        ttk.Label(box, text="텍스트").grid(row=0, column=0, sticky="e", padx=(pad_x,6), pady=(pad_y,2))
        ent_text = ttk.Entry(box, textvariable=self.var_wm_text)
        ent_text.grid(row=0, column=1, columnspan=3, sticky="we", padx=(0,pad_x), pady=(pad_y,2))

        # 2행: 글자색/외곽선색 + 스와치
        ttk.Label(box, text="글자색").grid(row=1, column=0, sticky="e", padx=(pad_x,6), pady=(2,2))
        ent_fill = ttk.Entry(box, textvariable=self.var_fill, width=12)
        ent_fill.grid(row=1, column=1, sticky="w", padx=(0,6), pady=(2,2))
        self.sw_fill = tk.Canvas(box, width=28, height=16, highlightthickness=1, highlightbackground="#AAA")
        self.sw_fill.grid(row=1, column=1, sticky="e", padx=(0,6), pady=(2,2))
        self._update_swatch(self.sw_fill, self.var_fill.get())
        ttk.Button(box, text="선택", command=lambda: self._pick_color(self.var_fill, self.sw_fill)).grid(row=1, column=2, sticky="w", padx=(0,6), pady=(2,2))

        ttk.Label(box, text="외곽선색").grid(row=1, column=3, sticky="e", padx=(pad_x,6), pady=(2,2))
        ent_stroke = ttk.Entry(box, textvariable=self.var_stroke, width=12)
        ent_stroke.grid(row=1, column=4, sticky="w", padx=(0,6), pady=(2,2))
        self.sw_stroke = tk.Canvas(box, width=28, height=16, highlightthickness=1, highlightbackground="#AAA")
        self.sw_stroke.grid(row=1, column=4, sticky="e", padx=(0,6), pady=(2,2))
        self._update_swatch(self.sw_stroke, self.var_stroke.get())
        ttk.Button(box, text="선택", command=lambda: self._pick_color(self.var_stroke, self.sw_stroke)).grid(row=1, column=5, sticky="w", padx=(0,pad_x), pady=(2,2))

        # 3행: 불투명/스케일/외곽선 굵기
        ttk.Label(box, text="불투명(%)").grid(row=2, column=0, sticky="e", padx=(pad_x,6), pady=(2,2))
        ttk.Spinbox(box, from_=0, to=100, textvariable=self.var_opacity, width=6).grid(row=2, column=1, sticky="w", padx=(0,12), pady=(2,2))

        ttk.Label(box, text="스케일(%)").grid(row=2, column=2, sticky="e", padx=(6,6), pady=(2,2))
        ttk.Spinbox(box, from_=1, to=50, textvariable=self.var_scale, width=6).grid(row=2, column=3, sticky="w", padx=(0,12), pady=(2,2))

        ttk.Label(box, text="외곽선 굵기").grid(row=2, column=4, sticky="e", padx=(6,6), pady=(2,2))
        ttk.Spinbox(box, from_=0, to=20, textvariable=self.var_stroke_w, width=6).grid(row=2, column=5, sticky="w", padx=(0,pad_x), pady=(2,2))

        # 4행: 폰트 + 버튼
        ttk.Label(box, text="폰트").grid(row=3, column=0, sticky="e", padx=(pad_x,6), pady=(2,pad_y))
        ent_font = ttk.Entry(box, textvariable=self.var_font)
        ent_font.grid(row=3, column=1, columnspan=3, sticky="we", padx=(0,6), pady=(2,pad_y))
        ttk.Button(box, text="찾기…", command=self._browse_font).grid(row=3, column=4, sticky="w", padx=(0,6), pady=(2,pad_y))
        btns = ttk.Frame(box); btns.grid(row=3, column=5, sticky="e", padx=(0,pad_x), pady=(2,pad_y))
        ttk.Button(btns, text="적용", command=self._apply_clicked).pack(side="left", padx=(0,6))
        ttk.Button(btns, text="해제", command=self._clear_clicked).pack(side="left")

        # 컬럼 확장
        for c in (1,2,3):
            box.columnconfigure(c, weight=1)

        # 스와치 실시간 반영
        self.var_fill.trace_add("write", lambda *_: self._update_swatch(self.sw_fill, self.var_fill.get()))
        self.var_stroke.trace_add("write", lambda *_: self._update_swatch(self.sw_stroke, self.var_stroke.get()))

    # -------- helpers --------
    def _pick_color(self, var: tk.StringVar, sw: tk.Canvas):
        initial = var.get() or "#000000"
        _, hx = colorchooser.askcolor(color=initial, title="색상 선택")
        if hx:
            var.set(hx)
            self._update_swatch(sw, hx)

    def _update_swatch(self, sw: tk.Canvas, hx: str):
        try:
            sw.delete("all"); sw.create_rectangle(0, 0, 28, 16, outline="", fill=hx)
        except Exception:
            sw.delete("all"); sw.create_rectangle(0, 0, 28, 16, outline="", fill="#FFFFFF")

    def _browse_font(self):
        path = filedialog.askopenfilename(
            title="폰트 파일 선택 (TTF/OTF/TTC)",
            filetypes=[("Font files", "*.ttf *.otf *.ttc"), ("All files", "*.*")],
        )
        if path:
            self.var_font.set(path)

    # -------- public API --------
    def set_active_image_and_defaults(self, path: Optional[Path], cfg: Optional[dict]):
        self._active_path = path
        if not cfg:
            # 초기화
            self.var_wm_text.set("")
            self.var_opacity.set(30)
            self.var_scale.set(20)
            self.var_fill.set("#000000")
            self.var_stroke.set("#FFFFFF")
            self.var_stroke_w.set(2)
            self.var_font.set("")
            return
        self.var_wm_text.set(cfg.get("text", ""))
        self.var_opacity.set(int(cfg.get("opacity", 30)))
        self.var_scale.set(int(cfg.get("scale_pct", 20)))
        self.var_fill.set(_hex_from_rgb(tuple(cfg.get("fill", (0,0,0)))))
        self.var_stroke.set(_hex_from_rgb(tuple(cfg.get("stroke", (255,255,255)))))
        self.var_stroke_w.set(int(cfg.get("stroke_w", 2)))
        self.var_font.set(cfg.get("font_path", ""))

    def _apply_clicked(self):
        if not self._on_apply or not self._active_path:
            return
        ov = {
            "text": self.var_wm_text.get(),
            "opacity": int(self.var_opacity.get()),
            "scale_pct": int(self.var_scale.get()),
            "fill": _rgb_from_hex(self.var_fill.get()),
            "stroke": _rgb_from_hex(self.var_stroke.get()),
            "stroke_w": int(self.var_stroke_w.get()),
            "font_path": self.var_font.get().strip(),
        }
        self._on_apply(self._active_path, ov)

    def _clear_clicked(self):
        if self._on_clear and self._active_path:
            self._on_clear(self._active_path)

# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Optional, Dict
from pathlib import Path

class ImageWMEditor(ttk.LabelFrame):
    """
    개별 이미지 워터마크 편집기 (독립 위젯)
      - 좌측 '게시물' 트리뷰 아래에 배치
      - 활성 이미지 없음 -> 버튼 비활성
    콜백:
      on_apply(path: Path, override_dict: dict)
      on_clear(path: Path)
    """
    def __init__(self, master,
                 on_apply=None,
                 on_clear=None,
                 title: str = "개별 이미지 워터마크"):
        super().__init__(master, text=title)
        self._on_apply = on_apply
        self._on_clear = on_clear
        self._active_path: Optional[Path] = None

        # 상태 변수
        self.var_wm_text = tk.StringVar(value="")
        self.var_opacity = tk.IntVar(value=30)
        self.var_scale   = tk.IntVar(value=20)
        self.var_fill    = tk.StringVar(value="#000000")  # 글자색
        self.var_stroke  = tk.StringVar(value="#FFFFFF")  # 외곽선색
        self.var_stroke_w= tk.IntVar(value=2)
        self.var_font    = tk.StringVar(value="")

        # ── 레이아웃 ─────────────────────────────────────────────────────
        # 텍스트
        ttk.Label(self, text="텍스트").grid(row=0, column=0, sticky="e",
                                            padx=(10,6), pady=(8,6))
        ttk.Entry(self, textvariable=self.var_wm_text)\
           .grid(row=0, column=1, columnspan=3, sticky="we",
                 padx=(0,14), pady=(8,6))

        # 색상(글자색/외곽선색)
        col = ttk.Frame(self); col.grid(row=1, column=0, columnspan=4, sticky="we",
                                        padx=(10,14), pady=(4,10))
        col.columnconfigure(1, weight=1); col.columnconfigure(4, weight=1)

        ttk.Label(col, text="글자색").grid(row=0, column=0, sticky="e")
        ttk.Entry(col, textvariable=self.var_fill, width=12)\
           .grid(row=0, column=1, sticky="w", padx=(6,6))
        self.sw_fill = self._make_swatch(col, self.var_fill.get())
        self.sw_fill.grid(row=0, column=2, sticky="w", padx=(2,8))
        self.sw_fill.bind("<Button-1>", lambda e: self._pick_color(self.var_fill))
        ttk.Button(col, text="선택", command=lambda: self._pick_color(self.var_fill))\
           .grid(row=0, column=3, sticky="w")

        ttk.Label(col, text="외곽선색").grid(row=0, column=4, sticky="e")
        ttk.Entry(col, textvariable=self.var_stroke, width=12)\
           .grid(row=0, column=5, sticky="w", padx=(6,6))
        self.sw_stroke = self._make_swatch(col, self.var_stroke.get())
        self.sw_stroke.grid(row=0, column=6, sticky="w", padx=(2,8))
        self.sw_stroke.bind("<Button-1>", lambda e: self._pick_color(self.var_stroke))
        ttk.Button(col, text="선택", command=lambda: self._pick_color(self.var_stroke))\
           .grid(row=0, column=7, sticky="w")

        # 수치
        opts = ttk.Frame(self); opts.grid(row=2, column=0, columnspan=4, sticky="we",
                                          padx=(10,14), pady=(0,10))
        for c in range(6): opts.columnconfigure(c, weight=1)
        ttk.Label(opts, text="불투명(%)").grid(row=0, column=0, sticky="e")
        ttk.Spinbox(opts, from_=0, to=100, textvariable=self.var_opacity, width=6)\
           .grid(row=0, column=1, sticky="w", padx=(6,12))
        ttk.Label(opts, text="스케일(%)").grid(row=0, column=2, sticky="e")
        ttk.Spinbox(opts, from_=1, to=50, textvariable=self.var_scale, width=6)\
           .grid(row=0, column=3, sticky="w", padx=(6,12))
        ttk.Label(opts, text="외곽선 두께").grid(row=0, column=4, sticky="e")
        ttk.Spinbox(opts, from_=0, to=20, textvariable=self.var_stroke_w, width=6)\
           .grid(row=0, column=5, sticky="w", padx=(6,0))

        # 폰트 + 버튼
        frow = ttk.Frame(self); frow.grid(row=3, column=0, columnspan=4, sticky="we",
                                          padx=(10,14), pady=(0,12))
        frow.columnconfigure(1, weight=1)
        ttk.Label(frow, text="폰트").grid(row=0, column=0, sticky="e")
        ttk.Entry(frow, textvariable=self.var_font)\
           .grid(row=0, column=1, sticky="we", padx=(6,12))
        self.btn_apply = ttk.Button(frow, text="적용", command=self._apply)
        self.btn_apply.grid(row=0, column=2, sticky="e", padx=(0,6))
        self.btn_clear = ttk.Button(frow, text="해제", command=self._clear)
        self.btn_clear.grid(row=0, column=3, sticky="w")

        for c in range(6): self.columnconfigure(c, weight=1)

        # 값 바뀔 때 스와치 자동 동기
        self.var_fill.trace_add("write", lambda *_: self._update_swatch(self.sw_fill, self.var_fill.get()))
        self.var_stroke.trace_add("write", lambda *_: self._update_swatch(self.sw_stroke, self.var_stroke.get()))

        # 처음엔 비활성 (활성 이미지가 생기면 enable)
        self.set_enabled(False)

    # ── 외부 API ─────────────────────────────────────────────────────────
    def set_active_image_and_defaults(self, path: Optional[Path], wm_cfg: Optional[Dict]):
        self._active_path = path
        self.set_enabled(bool(path))
        if not wm_cfg:
            # override 없음 → 입력은 비워두어 상속 상태를 표현
            self.var_wm_text.set("")
            self.var_opacity.set(30); self.var_scale.set(20)
            self.var_fill.set("#000000"); self.var_stroke.set("#FFFFFF")
            self.var_stroke_w.set(2); self.var_font.set("")
        else:
            self.var_wm_text.set(wm_cfg.get("text", ""))
            self.var_opacity.set(int(wm_cfg.get("opacity", 30)))
            self.var_scale.set(int(wm_cfg.get("scale_pct", 20)))
            def _fmt(rgb):
                return "#%02X%02X%02X" % tuple(rgb) if isinstance(rgb,(list,tuple)) and len(rgb)==3 else "#000000"
            self.var_fill.set(_fmt(wm_cfg.get("fill", (0,0,0))))
            self.var_stroke.set(_fmt(wm_cfg.get("stroke", (255,255,255))))
            self.var_stroke_w.set(int(wm_cfg.get("stroke_w", 2)))
            self.var_font.set(wm_cfg.get("font_path", ""))

        # 초기 스와치 동기
        self._update_swatch(self.sw_fill, self.var_fill.get())
        self._update_swatch(self.sw_stroke, self.var_stroke.get())

    def set_enabled(self, flag: bool):
        st = "normal" if flag else "disabled"
        for w in (self,):
            pass
        for child in self.winfo_children():
            try:
                child.configure(state=st)
            except Exception:
                pass
        # 라벨프레임 캡션은 항상 보이게
        try:
            self.configure(text="개별 이미지 워터마크" + ("" if flag else " (이미지 선택 필요)"))
        except Exception:
            pass

    # ── 내부 ────────────────────────────────────────────────────────────
    def _make_swatch(self, parent, hex_color: str):
        sw = tk.Canvas(parent, width=28, height=16,
                       highlightthickness=1, highlightbackground="#AAA")
        sw.create_rectangle(0, 0, 28, 16, outline="", fill=hex_color)
        return sw

    def _update_swatch(self, sw: tk.Canvas, hx: str):
        try:
            sw.delete("all")
            sw.create_rectangle(0, 0, 28, 16, outline="", fill=hx)
        except Exception:
            sw.delete("all")
            sw.create_rectangle(0, 0, 28, 16, outline="", fill="#FFFFFF")

    def _pick_color(self, var: tk.StringVar):
        from tkinter import colorchooser
        initial = var.get() or "#000000"
        _, hx = colorchooser.askcolor(color=initial, title="색상 선택")
        if hx:
            var.set(hx)

    def _apply(self):
        if not (self._on_apply and self._active_path):
            return
        def _rgb(hx: str):
            hx = (hx or "").strip()
            if not hx.startswith("#"): return None
            if len(hx) == 7:
                try: return (int(hx[1:3],16), int(hx[3:5],16), int(hx[5:7],16))
                except: return None
            if len(hx) == 4:
                try: return (int(hx[1]*2,16), int(hx[2]*2,16), int(hx[3]*2,16))
                except: return None
            return None
        ov = {
            "text": self.var_wm_text.get(),
            "opacity": int(self.var_opacity.get()),
            "scale_pct": int(self.var_scale.get()),
            "fill": _rgb(self.var_fill.get()) or (0,0,0),
            "stroke": _rgb(self.var_stroke.get()) or (255,255,255),
            "stroke_w": int(self.var_stroke_w.get()),
            "font_path": self.var_font.get().strip(),
        }
        self._on_apply(self._active_path, ov)

    def _clear(self):
        if self._on_clear and self._active_path:
            self._on_clear(self._active_path)

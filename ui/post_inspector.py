from __future__ import annotations
import tkinter as tk
from tkinter import ttk, filedialog
from typing import Callable, Optional
from tkinter import colorchooser

OnPostOverridesChange = Callable[[str, dict], None]
OnApplyToAllImages = Callable[[str], None]

class PostInspector(ttk.LabelFrame):
    """게시물 단위 워터마크 옵션 (텍스트/폰트/스케일/불투명/색/외곽선)"""
    def __init__(self, master,
                 on_change: Optional[OnPostOverridesChange] = None,
                 on_apply_all: Optional[OnApplyToAllImages] = None,
                 default_font_path: str | None = None):
        super().__init__(master, text="📂 게시물 워터마크", padding=(8, 6))
        self.on_change = on_change
        self.on_apply_all = on_apply_all
        self._post_key: str | None = None

        self._global_font_path = default_font_path or ""

        # 상태
        self.var_enabled = tk.BooleanVar(master=self, value=False)
        self.var_text = tk.StringVar(master=self, value="")
        self.var_font = tk.StringVar(master=self, value="")
        self.var_scale = tk.IntVar(master=self, value=20)            # %
        self.var_opacity = tk.IntVar(master=self, value=30)          # %
        self.var_fill = tk.StringVar(master=self, value="#000000")   # HEX
        self.var_stroke = tk.StringVar(master=self, value="#FFFFFF") # HEX
        self.var_stroke_w = tk.IntVar(master=self, value=2)

        row = 0
        ttk.Checkbutton(self, text="이 게시물에서 기본값 오버라이드",
                        variable=self.var_enabled, command=self._emit)\
            .grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 6)); row += 1

        ttk.Label(self, text="텍스트").grid(row=row, column=0, sticky="w")
        e_text = ttk.Entry(self, textvariable=self.var_text)
        e_text.grid(row=row, column=1, columnspan=2, sticky="we", padx=(6, 0))
        e_text.bind("<KeyRelease>", lambda _: self._emit()); row += 1

        ttk.Label(self, text="폰트").grid(row=row, column=0, sticky="w")
        e_font = ttk.Entry(self, textvariable=self.var_font)
        e_font.grid(row=row, column=1, sticky="we", padx=(6, 4))
        ttk.Button(self, text="찾기…", command=self._pick_font)\
            .grid(row=row, column=2, sticky="we"); row += 1

        ttk.Label(self, text="스케일(%)").grid(row=row, column=0, sticky="w")
        s_scale = ttk.Scale(self, from_=8, to=60, orient="horizontal",
                            command=lambda v: self._on_scale(v))
        s_scale.set(self.var_scale.get())
        s_scale.grid(row=row, column=1, columnspan=2, sticky="we", padx=(6, 0)); row += 1

        ttk.Label(self, text="불투명(%)").grid(row=row, column=0, sticky="w")
        s_opacity = ttk.Scale(self, from_=10, to=100, orient="horizontal",
                              command=lambda v: self._on_opacity(v))
        s_opacity.set(self.var_opacity.get())
        s_opacity.grid(row=row, column=1, columnspan=2, sticky="we", padx=(6, 0)); row += 1

        ttk.Label(self, text="글자색").grid(row=row, column=0, sticky="w")
        frm_fill = ttk.Frame(self)
        frm_fill.grid(row=row, column=1, columnspan=2, sticky="we", padx=(6, 0))
        e_fill = ttk.Entry(frm_fill, textvariable=self.var_fill, width=12)
        e_fill.pack(side="left", fill="x", expand=True)
        sw_fill = self._make_swatch(frm_fill, self.var_fill)
        sw_fill.pack(side="left", padx=4)
        ttk.Button(frm_fill, text="선택…", command=lambda: self._pick_color(self.var_fill)).pack(side="left")
        row += 1
        e_fill.bind("<KeyRelease>", lambda _: self._emit()); row += 1

        ttk.Label(self, text="외곽선").grid(row=row, column=0, sticky="w")
        frm_st = ttk.Frame(self)
        frm_st.grid(row=row, column=1, columnspan=2, sticky="we", padx=(6, 0))
        e_st = ttk.Entry(frm_st, textvariable=self.var_stroke, width=12)
        e_st.pack(side="left", fill="x", expand=True)
        sw_st = self._make_swatch(frm_st, self.var_stroke)
        sw_st.pack(side="left", padx=4)
        ttk.Button(frm_st, text="선택…", command=lambda: self._pick_color(self.var_stroke)).pack(side="left")
        row += 1
        e_st.bind("<KeyRelease>", lambda _: self._emit()); row += 1

        ttk.Label(self, text="외곽선 굵기").grid(row=row, column=0, sticky="w")
        s_stw = ttk.Scale(self, from_=0, to=8, orient="horizontal",
                          command=lambda v: self._on_stroke_w(v))
        s_stw.set(self.var_stroke_w.get())
        s_stw.grid(row=row, column=1, columnspan=2, sticky="we", padx=(6, 0)); row += 1

        ttk.Button(self, text="↻ 모든 이미지에 적용", command=self._apply_all)\
            .grid(row=row, column=0, columnspan=2, sticky="we", pady=(8, 0))
        ttk.Button(self, text="초기화(상속 복원)", command=self._reset)\
            .grid(row=row, column=2, sticky="we", pady=(8, 0)); row += 1

        for c in range(3):
            self.columnconfigure(c, weight=1)
        self._sync_enabled()

    def _pick_color(self, var: tk.StringVar):
        initial = var.get() or "#000000"
        _, hx = colorchooser.askcolor(color=initial, title="색상 선택")
        if hx:
            var.set(hx.upper())
            self._emit()

    def _make_swatch(self, parent, var: tk.StringVar):
        sw = tk.Label(parent, text="   ", relief="groove", bd=1, width=3)

        def _update(*_):
            try:
                sw.configure(bg=var.get())
            except Exception:
                sw.configure(bg="#FFFFFF")

        var.trace_add("write", _update)
        _update()
        return sw

    # 외부 → 선택 게시물 바인딩
    def bind_post(self, post_key: str, overrides: dict | None):
        self._post_key = post_key
        ov = overrides or {}
        enabled = bool(ov)
        self.var_enabled.set(enabled)
        self.var_text.set(ov.get("text", "" if enabled else ""))
        font_from_ov = ov.get("font_path", "") if ov else ""
        self.var_font.set(font_from_ov or self._global_font_path)
        self.var_scale.set(int(ov.get("scale", 20)))
        self.var_opacity.set(int(ov.get("opacity", 30)))
        self.var_fill.set(ov.get("fill", "#000000"))
        self.var_stroke.set(ov.get("stroke", "#FFFFFF"))
        self.var_stroke_w.set(int(ov.get("stroke_w", 2)))
        self._sync_enabled()

    # 내부
    def _sync_enabled(self):
        state = "normal" if self.var_enabled.get() else "disabled"
        for w in self.winfo_children():
            if isinstance(w, ttk.Checkbutton):
                continue
            try: w.configure(state=state)
            except Exception: pass

    def _emit(self):
        self._sync_enabled()
        if not self._post_key or not self.on_change:
            return
        ov = {}
        if self.var_enabled.get():
            ov = {
                "text": self.var_text.get(),
                "font_path": self.var_font.get(),
                "scale": int(self.var_scale.get()),
                "opacity": int(self.var_opacity.get()),
                "fill": self.var_fill.get(),
                "stroke": self.var_stroke.get(),
                "stroke_w": int(self.var_stroke_w.get()),
            }
        self.on_change(self._post_key, ov)

    def _apply_all(self):
        if self._post_key and self.on_apply_all:
            self.on_apply_all(self._post_key)

    def _reset(self):
        self.var_enabled.set(False)
        self._emit()

    # 슬라이더 연동
    def _on_scale(self, v): self.var_scale.set(int(float(v))); self._emit()
    def _on_opacity(self, v): self.var_opacity.set(int(float(v))); self._emit()
    def _on_stroke_w(self, v): self.var_stroke_w.set(int(float(v))); self._emit()

    # 폰트 선택
    def _pick_font(self):
        path = filedialog.askopenfilename(
            title="폰트 파일 선택",
            filetypes=[("Font files", "*.ttf *.otf"), ("All files", "*.*")]
        )
        if path:
            self.var_font.set(path); self._emit()
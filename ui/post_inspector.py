from __future__ import annotations
import tkinter as tk
from tkinter import ttk, filedialog
from typing import Callable, Optional
from tkinter import colorchooser

# 콜백 시그니처
OnPostApply = Callable[[str, dict], None]                 # 게시물 오버라이드 저장
OnApplyToAllImages = Callable[[str, str], None]           # (post_key, mode: 'default'|'force')
OnPostReset = Callable[[str], None]                       # 게시물 오버라이드 제거

class PostInspector(ttk.LabelFrame):
    """
    게시물 단위 워터마크 옵션:
    - 선택된 게시물에 현재 '효과 중인' 설정값을 폼에 표시
    - 사용자가 수정 후 '적용/강제 적용'일 때만 게시물 오버라이드를 저장하고,
      그 값을 하위 이미지로 내려보냄
    - '초기화(상위값 따르기)'는 게시물 오버라이드를 제거하여 상위(루트/전역)를 따르게 함
    """
    def __init__(self, master,
                 on_apply: Optional[OnPostApply] = None,
                 on_apply_all: Optional[OnApplyToAllImages] = None,
                 on_reset: Optional[OnPostReset] = None,
                 default_font_path: str | None = None):
        super().__init__(master, text="📂 게시물 워터마크", padding=(8, 6))
        self.on_apply = on_apply
        self.on_apply_all = on_apply_all
        self.on_reset = on_reset
        self._post_key: str | None = None

        # UI 상태 (폼 버퍼)
        self.var_text = tk.StringVar(master=self, value="")
        self.var_font = tk.StringVar(master=self, value=default_font_path or "")
        self.var_scale = tk.IntVar(master=self, value=20)            # %
        self.var_opacity = tk.IntVar(master=self, value=30)          # %
        self.var_fill = tk.StringVar(master=self, value="#000000")   # HEX
        self.var_stroke = tk.StringVar(master=self, value="#FFFFFF") # HEX
        self.var_stroke_w = tk.IntVar(master=self, value=2)

        row = 0
        ttk.Label(self, text="텍스트").grid(row=row, column=0, sticky="w")
        ttk.Entry(self, textvariable=self.var_text)\
            .grid(row=row, column=1, columnspan=2, sticky="we", padx=(6, 0)); row += 1

        ttk.Label(self, text="폰트").grid(row=row, column=0, sticky="w")
        ttk.Entry(self, textvariable=self.var_font)\
            .grid(row=row, column=1, sticky="we", padx=(6, 4))
        ttk.Button(self, text="찾기…", command=self._pick_font)\
            .grid(row=row, column=2, sticky="we"); row += 1

        ttk.Label(self, text="스케일(%)").grid(row=row, column=0, sticky="w")
        s_scale = ttk.Scale(self, from_=8, to=60, orient="horizontal",
                            command=lambda v: self.var_scale.set(int(float(v))))
        s_scale.set(self.var_scale.get())
        s_scale.grid(row=row, column=1, columnspan=2, sticky="we", padx=(6, 0)); row += 1

        ttk.Label(self, text="불투명(%)").grid(row=row, column=0, sticky="w")
        s_opacity = ttk.Scale(self, from_=10, to=100, orient="horizontal",
                              command=lambda v: self.var_opacity.set(int(float(v))))
        s_opacity.set(self.var_opacity.get())
        s_opacity.grid(row=row, column=1, columnspan=2, sticky="we", padx=(6, 0)); row += 1

        ttk.Label(self, text="글자색").grid(row=row, column=0, sticky="w")
        frm_fill = ttk.Frame(self)
        frm_fill.grid(row=row, column=1, columnspan=2, sticky="we", padx=(6, 0))
        ttk.Entry(frm_fill, textvariable=self.var_fill, width=12).pack(side="left", fill="x", expand=True)
        self._make_swatch(frm_fill, self.var_fill).pack(side="left", padx=4)
        ttk.Button(frm_fill, text="선택…",
                   command=lambda: self._pick_color(self.var_fill)).pack(side="left")
        row += 1

        ttk.Label(self, text="외곽선").grid(row=row, column=0, sticky="w")
        frm_st = ttk.Frame(self)
        frm_st.grid(row=row, column=1, columnspan=2, sticky="we", padx=(6, 0))
        ttk.Entry(frm_st, textvariable=self.var_stroke, width=12).pack(side="left", fill="x", expand=True)
        self._make_swatch(frm_st, self.var_stroke).pack(side="left", padx=4)
        ttk.Button(frm_st, text="선택…",
                   command=lambda: self._pick_color(self.var_stroke)).pack(side="left")
        row += 1

        ttk.Label(self, text="외곽선 굵기").grid(row=row, column=0, sticky="w")
        s_stw = ttk.Scale(self, from_=0, to=8, orient="horizontal",
                          command=lambda v: self.var_stroke_w.set(int(float(v))))
        s_stw.set(self.var_stroke_w.get())
        s_stw.grid(row=row, column=1, columnspan=2, sticky="we", padx=(6, 0)); row += 1

        # ⬇ 버튼: 적용(비덮어쓰기) / 강제 적용(모두 덮기) / 초기화
        ttk.Button(self, text="적용", command=lambda: self._apply('default'))\
            .grid(row=row, column=0, sticky="we", pady=(8, 0))
        ttk.Button(self, text="강제 적용", command=lambda: self._apply('force'))\
            .grid(row=row, column=1, sticky="we", pady=(8, 0))
        ttk.Button(self, text="초기화(상위값 따르기)", command=self._reset_clicked)\
            .grid(row=row, column=2, sticky="we", pady=(8, 0)); row += 1

        for c in range(3):
            self.columnconfigure(c, weight=1)

    # 외부에서: 선택 게시물이 바뀔 때 '효과 중인' 설정을 그대로 넣어준다.
    # cfg 예: {"text": "...", "font_path":"...", "scale_pct":18, "opacity":60,
    #          "fill":(r,g,b), "stroke":(r,g,b), "stroke_w":2} 또는 None(텍스트 없음)
    def bind_post(self, post_key: str, cfg: dict | None):
        self._post_key = post_key

        def _rgb_to_hex(t):
            try: return "#%02X%02X%02X" % (int(t[0]), int(t[1]), int(t[2]))
            except Exception: return "#000000"

        if cfg:
            self.var_text.set(cfg.get("text", "") or "")
            self.var_font.set(cfg.get("font_path", "") or self.var_font.get())
            self.var_scale.set(int(cfg.get("scale_pct", self.var_scale.get())))
            self.var_opacity.set(int(cfg.get("opacity", self.var_opacity.get())))
            self.var_fill.set(_rgb_to_hex(cfg.get("fill", (0,0,0))))
            self.var_stroke.set(_rgb_to_hex(cfg.get("stroke", (255,255,255))))
            self.var_stroke_w.set(int(cfg.get("stroke_w", self.var_stroke_w.get())))
        else:
            # 워터마크 없음(텍스트 공백) 상태
            self.var_text.set("")

    def _apply(self, mode: str):
        # 1) 게시물 오버라이드 저장 (저장만!)
        if not self._post_key or not self.on_apply:
            return
        ov = {
            "text": self.var_text.get(),
            "font_path": self.var_font.get(),
            "scale": int(self.var_scale.get()),
            "opacity": int(self.var_opacity.get()),
            "fill": self.var_fill.get(),
            "stroke": self.var_stroke.get(),
            "stroke_w": int(self.var_stroke_w.get()),
        }
        self.on_apply(self._post_key, ov)

        # 2) 강제 적용에서만 하위 이미지로 전파
        if mode == 'force' and self.on_apply_all:
            self.on_apply_all(self._post_key, 'force')

    def _reset_clicked(self):
        if not self._post_key:
            return
        if self.on_reset:
            self.on_reset(self._post_key)

    # --- 유틸 ---
    def _pick_color(self, var: tk.StringVar):
        initial = var.get() or "#000000"
        _, hx = colorchooser.askcolor(color=initial, title="색상 선택")
        if hx:
            var.set(hx.upper())

    def _make_swatch(self, parent, var: tk.StringVar):
        sw = tk.Label(parent, text="   ", relief="groove", bd=1, width=3)
        def _update(*_):
            try: sw.configure(bg=var.get())
            except Exception: sw.configure(bg="#FFFFFF")
        var.trace_add("write", _update)
        _update()
        return sw

    def _pick_font(self):
        path = filedialog.askopenfilename(
            title="폰트 파일 선택",
            filetypes=[("Font files", "*.ttf *.otf"), ("All files", "*.*")]
        )
        if path:
            self.var_font.set(path)

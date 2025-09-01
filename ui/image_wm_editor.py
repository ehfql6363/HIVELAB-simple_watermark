# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, colorchooser, filedialog
from pathlib import Path
from typing import Optional, Tuple, Callable


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _rgb_from_hex(hx: str) -> Tuple[int, int, int]:
    hx = (hx or "").strip()
    if not hx.startswith("#"):
        return (0, 0, 0)
    if len(hx) == 4:
        r = int(hx[1] * 2, 16)
        g = int(hx[2] * 2, 16)
        b = int(hx[3] * 2, 16)
        return (r, g, b)
    if len(hx) >= 7:
        return (int(hx[1:3], 16), int(hx[3:5], 16), int(hx[5:7], 16))
    return (0, 0, 0)


def _hex_from_rgb(rgb: Tuple[int, int, int]) -> str:
    try:
        r, g, b = rgb
        return f"#{r:02X}{g:02X}{b:02X}"
    except Exception:
        return "#000000"


# ──────────────────────────────────────────────────────────────────────────────
# Editor
# ──────────────────────────────────────────────────────────────────────────────

class ImageWMEditor(ttk.Frame):
    """
    개별 이미지 워터마크 에디터(분리형)
      - set_active_image_and_defaults(path, cfg) 로 대상/기본값 주입
      - on_apply(path, override_dict) / on_clear(path)
    반응형 레이아웃:
      - 넓을 때: [글자색 | 불투명 | 스케일 | 외곽선색 | 외곽선 굵기] 한 줄
      - 좁을 때: 1행 [글자색 | 불투명 | 스케일], 2행 [외곽선색 | 외곽선 굵기]
    """
    def __init__(
        self,
        master,
        on_apply: Optional[Callable[[Path, dict], None]] = None,
        on_clear: Optional[Callable[[Path], None]] = None,
        wide_breakpoint: int = 920,   # 이 폭 이상이면 1줄, 미만이면 2줄로
    ):
        super().__init__(master)
        self._on_apply = on_apply
        self._on_clear = on_clear
        self._active_path: Optional[Path] = None
        self._wide_breakpoint = int(wide_breakpoint)
        self._is_wide = True  # 최초는 넓게 가정

        # ── 상수: 간격/패딩(모든 셀에서 동일하게 사용)
        self.PADX_L = 10
        self.PADX_M = 6
        self.PADY = 6

        # ── 컨테이너
        self.box = ttk.LabelFrame(self, text="개별 이미지 워터마크", padding=0)
        self.box.pack(fill="x", expand=False)

        # 상태 변수들
        self.var_wm_text = tk.StringVar(value="")
        self.var_opacity = tk.IntVar(value=30)
        self.var_scale = tk.IntVar(value=20)
        self.var_fill = tk.StringVar(value="#000000")    # 글자색
        self.var_stroke = tk.StringVar(value="#FFFFFF")  # 외곽선색
        self.var_stroke_w = tk.IntVar(value=2)
        self.var_font = tk.StringVar(value="")

        # 열 구성: 0~5열 (0=좌측 라벨, 1~4=입력부, 5=오른쪽 버튼)
        for c in (1, 2, 3, 4):
            self.box.grid_columnconfigure(c, weight=1, uniform="wmcols")
        self.box.grid_columnconfigure(5, weight=0)

        # ── 0행: 텍스트
        ttk.Label(self.box, text="텍스트").grid(
            row=0, column=0, sticky="e",
            padx=(self.PADX_L, self.PADX_M), pady=(self.PADY, 2)
        )
        self.ent_text = ttk.Entry(self.box, textvariable=self.var_wm_text)
        self.ent_text.grid(
            row=0, column=1, columnspan=4, sticky="we",
            padx=(0, self.PADX_L), pady=(self.PADY, 2)
        )

        # ── 1~2행: 반응형 그룹(글자색/불투명/스케일/외곽선색/외곽선 굵기)
        # 각 그룹은 프레임 내부 padding=0, 내부 pack도 최소 여백만
        self._build_groups()

        # ── 3행: 폰트 + 버튼(찾기/적용/해제)
        ttk.Label(self.box, text="폰트").grid(
            row=3, column=0, sticky="e",
            padx=(self.PADX_L, self.PADX_M), pady=(2, self.PADY)
        )
        self.ent_font = ttk.Entry(self.box, textvariable=self.var_font)
        self.ent_font.grid(
            row=3, column=1, columnspan=3, sticky="we",
            padx=(0, self.PADX_M), pady=(2, self.PADY)
        )
        self.btn_font = ttk.Button(self.box, text="찾기…", command=self._browse_font)
        self.btn_font.grid(
            row=3, column=4, sticky="w",
            padx=(0, self.PADX_M), pady=(2, self.PADY)
        )
        self.btns_trailing = ttk.Frame(self.box, padding=0)
        self.btns_trailing.grid(
            row=3, column=5, sticky="e",
            padx=(0, self.PADX_L), pady=(2, self.PADY)
        )
        ttk.Button(self.btns_trailing, text="적용", command=self._apply_clicked).pack(side="left", padx=(0, 6))
        ttk.Button(self.btns_trailing, text="해제", command=self._clear_clicked).pack(side="left")

        # 스와치 실시간 반영
        self.var_fill.trace_add("write", lambda *_: self._update_swatch(self.sw_fill, self.var_fill.get()))
        self.var_stroke.trace_add("write", lambda *_: self._update_swatch(self.sw_stroke, self.var_stroke.get()))

        # 최초 레이아웃
        self.after(0, self._relayout)

        # 리사이즈 감지 → 반응형 재배치
        self.bind("<Configure>", self._on_configure)

    # ──────────────────────────────────────────────────────────────────
    # 그룹 생성(글자색/외곽선색/불투명/스케일/외곽선 굵기)
    # ──────────────────────────────────────────────────────────────────
    def _build_groups(self):
        # 글자색
        self.grp_fill = ttk.Frame(self.box, padding=0)
        self.lbl_fill = ttk.Label(self.grp_fill, text="글자색")
        self.ent_fill = ttk.Entry(self.grp_fill, textvariable=self.var_fill, width=10)
        self.sw_fill = tk.Canvas(self.grp_fill, width=28, height=16, highlightthickness=1, highlightbackground="#AAA")
        self.btn_fill = ttk.Button(self.grp_fill, text="선택", command=lambda: self._pick_color(self.var_fill, self.sw_fill))
        self._pack_color_group(self.grp_fill, self.lbl_fill, self.ent_fill, self.sw_fill, self.btn_fill)
        self._update_swatch(self.sw_fill, self.var_fill.get())

        # 외곽선색
        self.grp_stroke = ttk.Frame(self.box, padding=0)
        self.lbl_stroke = ttk.Label(self.grp_stroke, text="외곽선색")
        self.ent_stroke = ttk.Entry(self.grp_stroke, textvariable=self.var_stroke, width=10)
        self.sw_stroke = tk.Canvas(self.grp_stroke, width=28, height=16, highlightthickness=1, highlightbackground="#AAA")
        self.btn_stroke = ttk.Button(self.grp_stroke, text="선택", command=lambda: self._pick_color(self.var_stroke, self.sw_stroke))
        self._pack_color_group(self.grp_stroke, self.lbl_stroke, self.ent_stroke, self.sw_stroke, self.btn_stroke)
        self._update_swatch(self.sw_stroke, self.var_stroke.get())

        # 불투명
        self.grp_opacity = ttk.Frame(self.box, padding=0)
        ttk.Label(self.grp_opacity, text="불투명(%)").pack(side="left", padx=(0, 6))
        self.spin_opacity = ttk.Spinbox(self.grp_opacity, from_=0, to=100, textvariable=self.var_opacity, width=6)
        self.spin_opacity.pack(side="left")

        # 스케일
        self.grp_scale = ttk.Frame(self.box, padding=0)
        ttk.Label(self.grp_scale, text="스케일(%)").pack(side="left", padx=(0, 6))
        self.spin_scale = ttk.Spinbox(self.grp_scale, from_=1, to=50, textvariable=self.var_scale, width=6)
        self.spin_scale.pack(side="left")

        # 외곽선 굵기
        self.grp_stroke_w = ttk.Frame(self.box, padding=0)
        ttk.Label(self.grp_stroke_w, text="외곽선 굵기").pack(side="left", padx=(0, 6))
        self.spin_stroke_w = ttk.Spinbox(self.grp_stroke_w, from_=0, to=20, textvariable=self.var_stroke_w, width=6)
        self.spin_stroke_w.pack(side="left")

    def _pack_color_group(self, frame: ttk.Frame, lbl: ttk.Label, ent: ttk.Entry, sw: tk.Canvas, btn: ttk.Button):
        # 그룹 내부 패딩은 최소화(정렬 깨짐 방지)
        lbl.pack(side="left", padx=(0, 6))
        ent.pack(side="left")
        sw.pack(side="left", padx=6)
        btn.pack(side="left", padx=(6, 0))

    # ──────────────────────────────────────────────────────────────────
    # 반응형 재배치
    # ──────────────────────────────────────────────────────────────────
    def _on_configure(self, _):
        # 너무 자주 재배치하지 않도록 간단한 가드
        self.after_idle(self._relayout)

    def _relayout(self):
        # 현재 폭 기준으로 single-row / two-rows 결정
        w = max(1, self.winfo_width())
        is_wide_now = (w >= self._wide_breakpoint)
        if is_wide_now == self._is_wide and getattr(self, "_layout_inited", False):
            return
        self._is_wide = is_wide_now
        self._layout_inited = True

        # 먼저 기존 위치 해제
        for grp in (self.grp_fill, self.grp_opacity, self.grp_scale, self.grp_stroke, self.grp_stroke_w):
            grp.grid_forget()

        # 행 간격
        pady_mid = (2, 2)

        if self._is_wide:
            # 1줄: [글자색 | 불투명 | 스케일 | 외곽선색 | 외곽선 굵기]
            # 1행을 모두 같은 row=1에 배치
            # 각 칼럼 사이 간격은 동일 PADX_M로 통일
            c = 0
            self.grp_fill.grid     (row=1, column=0, sticky="w", padx=(self.PADX_L, self.PADX_M), pady=pady_mid, columnspan=2)
            self.grp_opacity.grid  (row=1, column=2, sticky="w", padx=(0, self.PADX_M), pady=pady_mid)
            self.grp_scale.grid    (row=1, column=3, sticky="w", padx=(0, self.PADX_M), pady=pady_mid)
            self.grp_stroke.grid   (row=1, column=4, sticky="w", padx=(0, self.PADX_M), pady=pady_mid, columnspan=1)
            self.grp_stroke_w.grid (row=1, column=5, sticky="e", padx=(0, self.PADX_L), pady=pady_mid)

        else:
            # 2줄:
            # 1행 [글자색 | 불투명 | 스케일]
            self.grp_fill.grid     (row=1, column=0, sticky="w", padx=(self.PADX_L, self.PADX_M), pady=pady_mid, columnspan=2)
            self.grp_opacity.grid  (row=1, column=2, sticky="w", padx=(0, self.PADX_M),    pady=pady_mid)
            self.grp_scale.grid    (row=1, column=3, sticky="w", padx=(0, self.PADX_L),    pady=pady_mid, columnspan=3)

            # 2행 [외곽선색 | 외곽선 굵기]
            self.grp_stroke.grid   (row=2, column=0, sticky="w", padx=(self.PADX_L, self.PADX_M), pady=pady_mid, columnspan=3)
            self.grp_stroke_w.grid (row=2, column=3, sticky="w", padx=(0, self.PADX_L),     pady=pady_mid, columnspan=3)

    # ──────────────────────────────────────────────────────────────────
    # Swatch / Pickers
    # ──────────────────────────────────────────────────────────────────
    def _pick_color(self, var: tk.StringVar, sw: tk.Canvas):
        initial = var.get() or "#000000"
        _, hx = colorchooser.askcolor(color=initial, title="색상 선택")
        if hx:
            var.set(hx)
            self._update_swatch(sw, hx)

    def _update_swatch(self, sw: tk.Canvas, hx: str):
        try:
            sw.delete("all")
            sw.create_rectangle(0, 0, 28, 16, outline="", fill=hx)
        except Exception:
            sw.delete("all")
            sw.create_rectangle(0, 0, 28, 16, outline="", fill="#FFFFFF")

    def _browse_font(self):
        path = filedialog.askopenfilename(
            title="폰트 파일 선택 (TTF/OTF/TTC)",
            filetypes=[("Font files", "*.ttf *.otf *.ttc"), ("All files", "*.*")],
        )
        if path:
            self.var_font.set(path)

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────
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
        self.var_fill.set(_hex_from_rgb(tuple(cfg.get("fill", (0, 0, 0)))))
        self.var_stroke.set(_hex_from_rgb(tuple(cfg.get("stroke", (255, 255, 255)))))
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

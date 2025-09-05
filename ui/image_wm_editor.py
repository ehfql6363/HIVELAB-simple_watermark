# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, colorchooser, filedialog
from pathlib import Path
from typing import Optional, Tuple, Callable

# 자동완성
from services.autocomplete import AutocompleteIndex
from util.ac_popup import ACPopup


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
        self.box = ttk.LabelFrame(self, text="개별 이미지 워터마크", padding=(10, 8))
        self.box.pack(fill="x", expand=False, padx=0, pady=(0, 0))

        # 상태 변수들
        self.var_wm_text = tk.StringVar(value="")
        self.var_opacity = tk.IntVar(value=30)
        self.var_scale = tk.IntVar(value=20)
        self.var_fill = tk.StringVar(value="#000000")    # 글자색
        self.var_stroke = tk.StringVar(value="#FFFFFF")  # 외곽선색
        self.var_stroke_w = tk.IntVar(value=2)
        self.var_font = tk.StringVar(value="")

        # 열 구성: 0~5열
        self.box.grid_columnconfigure(0, weight=0)
        for c in (1, 2, 3, 4):
            self.box.grid_columnconfigure(c, weight=1, uniform="wmcols")
        self.box.grid_columnconfigure(5, weight=1)

        # ── 0행: 텍스트
        ttk.Label(self.box, text="텍스트").grid(
            row=0, column=0, sticky="e",
            padx=(self.PADX_L, self.PADX_M), pady=(self.PADY, 4)
        )
        self.ent_text = ttk.Entry(self.box, textvariable=self.var_wm_text)
        self.ent_text.grid(
            row=0, column=1, columnspan=4, sticky="we",
            padx=(0, self.PADX_L), pady=(self.PADY, 4)
        )

        # 자동완성 연결 + 전역 클릭으로 팝업 닫기
        try:
            self._wire_autocomplete(self.ent_text)
            self.winfo_toplevel().bind_all("<Button-1>", self._on_global_click_hide_ac, add="+")
        except Exception:
            pass

        # ── 1~2행: 반응형 그룹(글자색/불투명/스케일/외곽선색/외곽선 굵기)
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
        self.btn_font.grid(row=3, column=4, sticky="w", padx=(0, self.PADX_M), pady=(2, self.PADY))

        self.btns_trailing = ttk.Frame(self.box, padding=0)
        self.btns_trailing.grid(row=3, column=5, sticky="e", padx=(6, self.PADX_L), pady=(2, self.PADY))

        self.btn_apply = ttk.Button(self.btns_trailing, text="적용", command=self._apply_clicked)
        self.btn_apply.pack(side="left", padx=(0, 6))
        self.btn_clear = ttk.Button(self.btns_trailing, text="해제", command=self._clear_clicked)
        self.btn_clear.pack(side="left")

        # 스와치 실시간 반영
        self.var_fill.trace_add("write", lambda *_: self._update_swatch(self.sw_fill, self.var_fill.get()))
        self.var_stroke.trace_add("write", lambda *_: self._update_swatch(self.sw_stroke, self.var_stroke.get()))

        # 최초 레이아웃
        self.after(0, self._relayout)

        # 리사이즈 감지 → 반응형 재배치
        self.bind("<Configure>", self._on_configure)
        self.box.bind("<Configure>", self._on_configure)
        try:
            self.master.bind("<Configure>", self._on_configure)
        except Exception:
            pass

        self.bind("<Configure>", lambda e: self._apply_responsive_labels())
        self.after(0, self._apply_responsive_labels)

    # ──────────────────────────────────────────────────────────────────
    # 그룹 생성(글자색/외곽선색/불투명/스케일/외곽선 굵기)
    # ──────────────────────────────────────────────────────────────────
    def _build_groups(self):
        # 글자색
        self.grp_fill = ttk.Frame(self.box, padding=0)
        self.lbl_fill = ttk.Label(self.grp_fill, text="글자색")
        self.ent_fill = ttk.Entry(self.grp_fill, textvariable=self.var_fill, width=7)
        self.sw_fill = tk.Canvas(self.grp_fill, width=28, height=16, highlightthickness=1, highlightbackground="#AAA", borderwidth=1)
        self.btn_fill = ttk.Button(self.grp_fill, text="선택", command=lambda: self._pick_color(self.var_fill, self.sw_fill), width=5)
        self._pack_color_group(self.grp_fill, self.lbl_fill, self.ent_fill, self.sw_fill, self.btn_fill)
        self._update_swatch(self.sw_fill, self.var_fill.get())

        # 외곽선색
        self.grp_stroke = ttk.Frame(self.box, padding=0)
        self.lbl_stroke = ttk.Label(self.grp_stroke, text="외곽선색")
        self.ent_stroke = ttk.Entry(self.grp_stroke, textvariable=self.var_stroke, width=7)
        self.sw_stroke = tk.Canvas(self.grp_stroke, width=28, height=16, highlightthickness=1, highlightbackground="#AAA", borderwidth=1)
        self.btn_stroke = ttk.Button(self.grp_stroke, text="선택", command=lambda: self._pick_color(self.var_stroke, self.sw_stroke), width=5)
        self._pack_color_group(self.grp_stroke, self.lbl_stroke, self.ent_stroke, self.sw_stroke, self.btn_stroke)
        self._update_swatch(self.sw_stroke, self.var_stroke.get())

        # 불투명
        self.grp_opacity = ttk.Frame(self.box, padding=0)
        ttk.Label(self.grp_opacity, text="불투명(%)").pack(side="left", padx=(0, 6))
        self.spin_opacity = ttk.Spinbox(self.grp_opacity, from_=0, to=100, textvariable=self.var_opacity, width=4)
        self.spin_opacity.pack(side="left")

        # 스케일
        self.grp_scale = ttk.Frame(self.box, padding=0)
        ttk.Label(self.grp_scale, text="스케일(%)").pack(side="left", padx=(0, 6))
        self.spin_scale = ttk.Spinbox(self.grp_scale, from_=1, to=30, textvariable=self.var_scale, width=4)
        self.spin_scale.pack(side="left")

        # 외곽선 굵기
        self.grp_stroke_w = ttk.Frame(self.box, padding=(0, 0))
        ttk.Label(self.grp_stroke_w, text="외곽선 굵기").pack(side="left", padx=(0, 6))
        self.spin_stroke_w = ttk.Spinbox(self.grp_stroke_w, from_=0, to=20, textvariable=self.var_stroke_w, width=3)
        self.spin_stroke_w.pack(side="left")

    def _pack_color_group(self, frame: ttk.Frame, lbl: ttk.Label, ent: ttk.Entry, sw: tk.Canvas, btn: ttk.Button):
        lbl.pack(side="left", padx=(0, 6))
        ent.pack(side="left", padx=(0, 2))
        sw.pack(side="left", padx=8)
        btn.pack(side="left", padx=(8, 0))

    # ──────────────────────────────────────────────────────────────────
    # 반응형 재배치
    # ──────────────────────────────────────────────────────────────────
    def _on_configure(self, _):
        self.after_idle(self._relayout)

    def _relayout(self):
        w_box = self.box.winfo_width()
        w_self = self.winfo_width()
        w = max(1, w_box if w_box > 1 else w_self)
        is_wide_now = (w >= self._wide_breakpoint)
        if is_wide_now == self._is_wide and getattr(self, "_layout_inited", False):
            return
        self._is_wide = is_wide_now
        self._layout_inited = True

        for grp in (self.grp_fill, self.grp_opacity, self.grp_scale, self.grp_stroke, self.grp_stroke_w):
            grp.grid_forget()

        pady_mid = (2, 2)

        if self._is_wide:
            self.grp_fill.grid     (row=1, column=0, sticky="w", padx=(self.PADX_L, self.PADX_M), pady=pady_mid, columnspan=2)
            self.grp_opacity.grid  (row=1, column=2, sticky="w", padx=(0, self.PADX_M), pady=pady_mid)
            self.grp_scale.grid    (row=1, column=3, sticky="w", padx=(0, self.PADX_M), pady=pady_mid)
            self.grp_stroke.grid   (row=1, column=4, sticky="w", padx=(0, self.PADX_M), pady=pady_mid, columnspan=1)
            self.grp_stroke_w.grid (row=1, column=5, sticky="we", padx=(0, self.PADX_L), pady=pady_mid)

            try:
                self.btns_trailing.grid_configure(row=3, column=5, sticky="e",
                                                  padx=(0, self.PADX_L), pady=(2, self.PADY))
            except Exception:
                pass
        else:
            self.grp_fill.grid     (row=1, column=0, sticky="w", padx=(self.PADX_L, self.PADX_M), pady=pady_mid, columnspan=2)
            self.grp_opacity.grid  (row=1, column=2, sticky="w", padx=(0, self.PADX_M),    pady=pady_mid)
            self.grp_scale.grid    (row=1, column=3, sticky="w", padx=(0, self.PADX_L),    pady=pady_mid, columnspan=3)

            self.grp_stroke.grid   (row=2, column=0, sticky="w", padx=(self.PADX_L, self.PADX_M), pady=pady_mid, columnspan=3)
            self.grp_stroke_w.grid (row=2, column=3, sticky="w", padx=(0, self.PADX_L),     pady=pady_mid, columnspan=3)

            try:
                self.btns_trailing.grid_configure(row=4, column=0, columnspan=6, sticky="e",
                                                  padx=(self.PADX_L, self.PADX_L), pady=(2, self.PADY))
            except Exception:
                pass

    def _apply_responsive_labels(self):
        w = max(1, self.winfo_width())
        try:
            if w < 700:
                self.btn_font.configure(text="폰트")
                self.btn_fill.configure(text="색상")
                self.btn_stroke.configure(text="색상")
                self.btn_apply.configure(text="적용")
                self.btn_clear.configure(text="해제")
            elif w < 920:
                self.btn_font.configure(text="찾기")
                self.btn_fill.configure(text="선택")
                self.btn_stroke.configure(text="선택")
                self.btn_apply.configure(text="적용")
                self.btn_clear.configure(text="해제")
            else:
                self.btn_font.configure(text="찾기…")
                self.btn_fill.configure(text="선택")
                self.btn_stroke.configure(text="선택")
                self.btn_apply.configure(text="적용")
                self.btn_clear.configure(text="해제")
        except Exception:
            pass

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

    # ──────────────────────────────────────────────────────────────────
    # 자동완성(루트 패널과 동일 로직)
    # ──────────────────────────────────────────────────────────────────
    def _ensure_ac_objects(self):
        if not hasattr(self, "_ac"):
            try:
                self._ac = AutocompleteIndex(n=3)
            except Exception:
                self._ac = None
        if not hasattr(self, "_ac_popup"):
            try:
                self._ac_popup = ACPopup(self, on_pick=self._on_ac_pick)
            except Exception:
                self._ac_popup = None
        if not hasattr(self, "_ac_target_entry"):
            self._ac_target_entry = None
        if not hasattr(self, "_ac_pending_job"):
            self._ac_pending_job = None
        if not hasattr(self, "_ac_suppressed"):
            self._ac_suppressed = False

    def _cancel_ac_job(self):
        jid = getattr(self, "_ac_pending_job", None)
        if jid:
            try:
                self.after_cancel(jid)
            except Exception:
                pass
            self._ac_pending_job = None

    def _force_hide_ac(self):
        self._ac_suppressed = True
        self._cancel_ac_job()
        try:
            if getattr(self, "_ac_popup", None):
                self._ac_popup.hide()
        except Exception:
            pass

    def _widget_is_descendant_of(self, w: tk.Widget | None, anc: tk.Widget | None) -> bool:
        if not w or not anc:
            return False
        try:
            cur = w
            while cur is not None:
                if cur is anc:
                    return True
                cur = cur.master
        except Exception:
            pass
        return False

    def _on_global_click_hide_ac(self, e):
        self._ensure_ac_objects()
        popup = getattr(self, "_ac_popup", None)
        target = getattr(self, "_ac_target_entry", None)
        try:
            if not popup or not popup.winfo_exists() or not popup.winfo_viewable():
                return
        except Exception:
            return
        w = e.widget
        if self._widget_is_descendant_of(w, popup):
            return
        if self._widget_is_descendant_of(w, target):
            return
        self._force_hide_ac()

    def _update_ac_from_text(self, widget: tk.Entry, text: str, *, reason: str | None = None):
        self._ensure_ac_objects()
        if not getattr(self, "_ac", None) or not getattr(self, "_ac_popup", None):
            return

        self._cancel_ac_job()
        if self._ac_suppressed:
            try:
                self._ac_popup.hide()
            except Exception:
                pass
            return

        try:
            from settings import AppSettings
            pool = AppSettings.load().autocomplete_texts or []
            self._ac.rebuild(pool)
        except Exception:
            pass

        try:
            results = self._ac.query(text or "", top_k=10)
        except Exception:
            results = []

        choices = [t for (t, _s) in results]
        if not choices:
            try:
                self._ac_popup.hide()
            except Exception:
                pass
            return

        def _do_show():
            self._ac_pending_job = None
            if self._ac_suppressed:
                try:
                    self._ac_popup.hide()
                except Exception:
                    pass
                return
            try:
                self._ac_popup.show_below(widget, choices)
            except Exception:
                pass

        self._ac_pending_job = self.after_idle(_do_show)

    def _wire_autocomplete(self, entry_widget: tk.Entry):
        self._ensure_ac_objects()
        if not getattr(self, "_ac_popup", None):
            return

        def _on_focus_in(_e=None, w=entry_widget):
            self._ac_suppressed = False
            self._ac_target_entry = w
            self._update_ac_from_text(w, w.get(), reason="focusin")

        def _on_focus_out(_e=None, _w=entry_widget):
            self._cancel_ac_job()
            self._ac_pending_job = self.after(1, self._force_hide_ac)

        def _on_key_release(e, w=entry_widget):
            ks = getattr(e, "keysym", "")
            if ks in ("Escape", "Return", "Up", "Down"):
                return
            self._ac_suppressed = False
            self._update_ac_from_text(w, w.get(), reason="typing")

        def _on_escape(_e=None):
            self._force_hide_ac()
            return "break"

        def _on_return(_e=None):
            try:
                if self._ac_popup and self._ac_popup.is_visible():
                    self._ac_popup._confirm(None)
                    return "break"
            except Exception:
                pass
            return None

        def _on_mouse_press(_e=None, w=entry_widget):
            self._ac_target_entry = w
            self._ac_suppressed = False
            self._cancel_ac_job()
            self._update_ac_from_text(w, w.get(), reason="mouse")

        entry_widget.bind("<Button-1>", _on_mouse_press, add="+")
        entry_widget.bind("<FocusIn>", _on_focus_in, add="+")
        entry_widget.bind("<FocusOut>", _on_focus_out, add="+")
        entry_widget.bind("<KeyRelease>", _on_key_release, add="+")
        entry_widget.bind("<Escape>", _on_escape, add="+")
        entry_widget.bind("<Return>", _on_return, add="+")
        entry_widget.bind("<Down>", lambda _e: (self._ac_popup.move_selection(+1), "break"), add="+")
        entry_widget.bind("<Up>",   lambda _e: (self._ac_popup.move_selection(-1), "break"), add="+")

    def _on_ac_pick(self, text: str):
        try:
            w = getattr(self, "_ac_target_entry", None)
            if w and w.winfo_exists():
                w.delete(0, "end")
                w.insert(0, text)
                try:
                    w.event_generate("<KeyRelease>")
                except Exception:
                    pass
        except Exception:
            pass
        self._force_hide_ac()

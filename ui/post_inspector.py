from __future__ import annotations
import tkinter as tk
from tkinter import ttk, filedialog
from typing import Callable, Optional
from tkinter import colorchooser

# 자동완성
from services.autocomplete import AutocompleteIndex
from util.ac_popup import ACPopup

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
        self.var_scale = tk.IntVar(master=self, value=5)            # %
        self.var_opacity = tk.IntVar(master=self, value=30)          # %
        self.var_fill = tk.StringVar(master=self, value="#000000")   # HEX
        self.var_stroke = tk.StringVar(master=self, value="#FFFFFF") # HEX
        self.var_stroke_w = tk.IntVar(master=self, value=2)

        row = 0
        ttk.Label(self, text="텍스트").grid(row=row, column=0, sticky="w")
        self.ent_text = ttk.Entry(self, textvariable=self.var_text)
        self.ent_text.grid(row=row, column=1, columnspan=2, sticky="we", padx=(6, 0)); row += 1

        ttk.Label(self, text="폰트").grid(row=row, column=0, sticky="w")
        ttk.Entry(self, textvariable=self.var_font)\
            .grid(row=row, column=1, sticky="we", padx=(6, 4))
        ttk.Button(self, text="찾기…", command=self._pick_font)\
            .grid(row=row, column=2, sticky="we"); row += 1

        ttk.Label(self, text="스케일(%)").grid(row=row, column=0, sticky="w")
        s_scale = ttk.Scale(self, from_=1, to=30, orient="horizontal",
                            variable=self.var_scale)  # ★ 변수에 바인딩
        s_scale.set(self.var_scale.get())
        s_scale.grid(row=row, column=1, columnspan=2, sticky="we", padx=(6, 0)); row += 1

        ttk.Label(self, text="불투명(%)").grid(row=row, column=0, sticky="w")
        s_opacity = ttk.Scale(self, from_=10, to=100, orient="horizontal",
                              variable=self.var_opacity)  # ★ 변수에 바인딩
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
                          variable=self.var_stroke_w)  # ★ 변수에 바인딩
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

        # ── 자동완성: 루트 패널과 동일 UX
        try:
            self._wire_autocomplete(self.ent_text)
            self.winfo_toplevel().bind_all("<Button-1>", self._on_global_click_hide_ac, add="+")
        except Exception:
            pass

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
        # 1) 게시물 오버라이드 저장
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

        # 2) 하위 이미지에 적용 (기본/강제)
        if self.on_apply_all:
            self.on_apply_all(self._post_key, mode)

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

    # ───────────────────────────────────────────────────────────────
    # 자동완성(루트 패널과 동일 로직)
    # ───────────────────────────────────────────────────────────────
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

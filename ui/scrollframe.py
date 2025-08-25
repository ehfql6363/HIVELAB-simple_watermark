# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk

class ScrollFrame(ttk.Frame):
    """세로 스크롤 가능한 프레임. self.inner 에 위젯들을 붙이면 됨."""
    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vbar.set)

        self.inner = ttk.Frame(self.canvas)
        self._win_id = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")

        self.canvas.pack(side="left", fill="both", expand=True)
        self.vbar.pack(side="right", fill="y")

        # 사이즈/스크롤 영역 갱신
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # 마우스 휠 스크롤
        self._bind_mousewheel(self.canvas)

    def _on_inner_configure(self, _):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, e):
        # 캔버스 너비에 맞게 inner 폭 고정
        self.canvas.itemconfigure(self._win_id, width=e.width)

    def _bind_mousewheel(self, widget):
        # Windows / Mac / X11 호환
        widget.bind_all("<MouseWheel>", lambda e: self._on_wheel(e))
        widget.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-3, "units"))
        widget.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(+3, "units"))

    def _on_wheel(self, e):
        delta = e.delta
        if delta == 0:
            return
        # Windows(+120/-120), macOS(±1~±10) 보정
        step = -1 * int(delta / 120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
        self.canvas.yview_scroll(step, "units")

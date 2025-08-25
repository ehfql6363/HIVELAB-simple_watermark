# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk

class ScrollFrame(ttk.Frame):
    def __init__(self, master, *, height: int | None = None, **kw):
        super().__init__(master, **kw)

        self.canvas = tk.Canvas(self, highlightthickness=0)
        if height:
            self.canvas.configure(height=int(height))  # 표시 높이가 있으면 스크롤 여유가 생김
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vbar.set)

        self.inner = ttk.Frame(self.canvas)
        self.win_id = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")

        self.canvas.pack(side="left", fill="x", expand=True)
        self.vbar.pack(side="right", fill="y")

        # scrollregion/width 동기화
        self.inner.bind("<Configure>", self._on_inner_config)
        self.canvas.bind("<Configure>", self._on_canvas_config)

        # ✅ 휠 이벤트: 영역에 마우스가 들어오면 전역 바인딩, 나가면 해제
        self._wheel_bound = False
        for w in (self, self.canvas, self.inner, self.vbar):
            w.bind("<Enter>", self._bind_all_wheel, add="+")
            w.bind("<Leave>", self._maybe_unbind_all_wheel, add="+")
        # (주의) bind_all은 꼭 들어온 프레임에서만 켜고, 나가면 꺼야 다른 영역 스크롤과 충돌 안 납니다.

    # ---- geometry sync ----
    def _on_inner_config(self, _):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.canvas.itemconfigure(self.win_id, width=self.canvas.winfo_width())

    def _on_canvas_config(self, e):
        self.canvas.itemconfigure(self.win_id, width=e.width)

    # ---- wheel routing ----
    def _owns(self, w: tk.Widget | None) -> bool:
        """주어진 위젯이 이 ScrollFrame의 자손인지 검사"""
        while w is not None:
            if w is self:
                return True
            w = w.master
        return False

    def _bind_all_wheel(self, _=None):
        if self._wheel_bound:
            return
        self._wheel_bound = True
        # Windows/macOS
        self.canvas.bind_all("<MouseWheel>", self._on_wheel, add="+")
        # Linux
        self.canvas.bind_all("<Button-4>", self._on_btn4, add="+")
        self.canvas.bind_all("<Button-5>", self._on_btn5, add="+")

    def _maybe_unbind_all_wheel(self, _=None):
        # 자식으로 이동할 때도 Leave가 들어오므로, 포인터가 정말 밖으로 나갔는지 약간 지연 확인
        self.after(10, self._check_pointer_out)

    def _check_pointer_out(self):
        x, y = self.winfo_pointerxy()
        w = self.winfo_containing(x, y)
        if not self._owns(w):
            self._unbind_all_wheel()

    def _unbind_all_wheel(self):
        if not self._wheel_bound:
            return
        try:
            self.canvas.unbind_all("<MouseWheel>")
            self.canvas.unbind_all("<Button-4>")
            self.canvas.unbind_all("<Button-5>")
        finally:
            self._wheel_bound = False

    def _on_wheel(self, e):
        # 포인터가 지금도 내 영역 위인지 확인 (다른 영역이면 무시)
        x, y = self.winfo_pointerxy()
        w = self.winfo_containing(x, y)
        if not self._owns(w):
            return
        # delta는 환경마다 다르니 방향만 사용
        step = -1 if e.delta > 0 else +1
        self.canvas.yview_scroll(step, "units")
        return "break"

    def _on_btn4(self, e):
        # Linux wheel up
        x, y = self.winfo_pointerxy()
        if self._owns(self.winfo_containing(x, y)):
            self.canvas.yview_scroll(-3, "units")
            return "break"

    def _on_btn5(self, e):
        # Linux wheel down
        x, y = self.winfo_pointerxy()
        if self._owns(self.winfo_containing(x, y)):
            self.canvas.yview_scroll(+3, "units")
            return "break"

# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Optional

class ScrollFrame(ttk.Frame):
    """상단 옵션처럼 '세로 스크롤'이 필요한 얕은 컨테이너.
    - Canvas + inner Frame 구조
    - 스크롤바는 물론, '마우스가 위에 있을 때' 휠 스크롤 동작
    - height 지정 시 고정 높이(없으면 자연 높이)
    """
    def __init__(self, master, height: Optional[int] = None):
        super().__init__(master)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        if height:
            self.canvas.configure(height=int(height))

        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vbar.set)

        self.inner = ttk.Frame(self.canvas)
        self._win_id = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")

        self.canvas.pack(side="left", fill="both", expand=True)
        self.vbar.pack(side="right", fill="y")

        # 레이아웃 동기
        self.inner.bind("<Configure>", self._on_inner_config)
        self.canvas.bind("<Configure>", self._on_canvas_config)

        # 휠 스크롤: bind_all(+포인터 가드)로 헤더 위에서 자연 동작
        self._activate_wheel_on_hover(self)

    # --- wheel helpers ---
    def _activate_wheel_on_hover(self, widget):
        widget.bind("<Enter>", self._bind_all_wheel, add="+")
        widget.bind("<Leave>", self._unbind_all_wheel, add="+")
        # inner에도 진입/이탈 걸어두면 자식 위에서도 잘 동작
        self.inner.bind("<Enter>", self._bind_all_wheel, add="+")
        self.inner.bind("<Leave>", self._unbind_all_wheel, add="+")
        self.canvas.bind("<Enter>", self._bind_all_wheel, add="+")
        self.canvas.bind("<Leave>", self._unbind_all_wheel, add="+")

    def _bind_all_wheel(self, _=None):
        # add="+"로 여러 곳에서 공존 가능
        self.bind_all("<MouseWheel>", self._on_wheel, add="+")
        self.bind_all("<Button-4>", self._on_btn4, add="+")  # Linux up
        self.bind_all("<Button-5>", self._on_btn5, add="+")  # Linux down

    def _unbind_all_wheel(self, _=None):
        # 전역 바인딩 해제는 다른 위젯의 바인딩까지 지우므로 생략
        # (여러 바인딩 공존 + 포인터 가드로 충돌 방지)
        pass

    def _pointer_inside_me(self, e) -> bool:
        try:
            w = self.winfo_containing(e.x_root, e.y_root)
            # self 또는 자손이면 True
            while w is not None:
                if w is self:
                    return True
                w = w.master
        except Exception:
            pass
        return False

    def _on_wheel(self, e):
        if not self._pointer_inside_me(e):
            return  # 다른 ScrollFrame/위젯에게 양보
        delta = e.delta
        # Windows/macOS: 120 단위, macOS는 더 작을 수 있음 → 부호 기준
        step = -1 if delta > 0 else 1
        # 고해상도 휠에서 과도 스크롤 방지
        if abs(delta) >= 120:
            step *= int(abs(delta) / 120)
        self.canvas.yview_scroll(step, "units")
        return "break"

    def _on_btn4(self, e):
        if not self._pointer_inside_me(e):
            return
        self.canvas.yview_scroll(-3, "units")
        return "break"

    def _on_btn5(self, e):
        if not self._pointer_inside_me(e):
            return
        self.canvas.yview_scroll(+3, "units")
        return "break"

    # --- layout sync ---
    def _on_inner_config(self, _):
        bbox = self.canvas.bbox("all")
        if bbox:
            self.canvas.configure(scrollregion=bbox)

    def _on_canvas_config(self, e):
        # inner 폭을 캔버스 폭에 맞춤
        self.canvas.itemconfigure(self._win_id, width=e.width)

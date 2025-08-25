# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk

class PostList(ttk.Frame):
    def __init__(self, master, on_select=None):
        super().__init__(master)
        self._on_select = on_select
        self._posts = {}

        ttk.Label(self, text="Posts").pack(anchor="w")

        self.lb = tk.Listbox(self, height=20)
        self.lb.pack(fill="both", expand=True, pady=4)
        self.lb.bind("<<ListboxSelect>>", self._handle_select)
        # Delete 키로 빠른 삭제
        self.lb.bind("<Delete>", lambda e: self.remove_selected())

        # 하단 정보/버튼
        bottom = ttk.Frame(self); bottom.pack(fill="x")
        self.lbl_info = ttk.Label(bottom, text="0 posts")
        self.lbl_info.pack(side="left")

        btns = ttk.Frame(self); btns.pack(fill="x", pady=(4,0))
        ttk.Button(btns, text="Remove", command=self.remove_selected).pack(side="left")
        ttk.Button(btns, text="Remove All", command=self.remove_all).pack(side="left", padx=6)

    # ----- Public API -----
    def set_posts(self, posts: dict):
        """posts: dict[key -> meta]. key 형식: 'RootName/PostName'"""
        self._posts = posts
        self.lb.delete(0, tk.END)
        for name in self._posts.keys():
            self.lb.insert(tk.END, name)
        self._update_count()

    def get_selected_post(self) -> str | None:
        sel = self.lb.curselection()
        if not sel:
            return None
        return self.lb.get(sel[0])

    def get_all_keys(self) -> list[str]:
        """현재 리스트에 남아있는 key들(배치 실행 시 이 목록만 처리)."""
        return [self.lb.get(i) for i in range(self.lb.size())]

    # ----- Actions -----
    def remove_selected(self):
        sel = self.lb.curselection()
        if not sel:
            return
        # 여러 개 선택돼 있을 수 있으니 뒤에서 앞으로 지움
        for i in reversed(sel):
            self.lb.delete(i)
        self._update_count()
        # 선택 변경 콜백
        if self._on_select:
            self._on_select(self.get_selected_post())

    def remove_all(self):
        self.lb.delete(0, tk.END)
        self._update_count()
        if self._on_select:
            self._on_select(None)

    # ----- Internal -----
    def _handle_select(self, _evt):
        if self._on_select:
            self._on_select(self.get_selected_post())

    def _update_count(self):
        self.lbl_info.configure(text=f"{self.lb.size()} posts")

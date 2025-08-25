# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Dict

class PostList(ttk.Frame):
    def __init__(self, master, on_select: Callable[[str | None], None] | None = None):
        super().__init__(master)
        self.on_select = on_select

        box = ttk.LabelFrame(self, text="게시물")
        box.pack(fill="both", expand=True)

        cols = ("key", "count")
        self.tree = ttk.Treeview(box, columns=cols, show="headings", height=16)
        self.tree.heading("key", text="게시물 이름")
        self.tree.heading("count", text="이미지 수")
        self.tree.column("key", width=320); self.tree.column("count", width=80, anchor="e")
        self.tree.pack(side="left", fill="both", expand=True, padx=(6,0), pady=6)

        sb = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=sb.set); sb.pack(side="right", fill="y")

        # 하단 버튼
        btns = ttk.Frame(self); btns.pack(fill="x", pady=(0,6))
        ttk.Button(btns, text="선택 삭제", command=self.remove_selected).pack(side="left")
        ttk.Button(btns, text="모두 삭제", command=self.remove_all).pack(side="left", padx=6)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)

    def set_posts(self, posts: Dict[str, dict]):
        self.tree.delete(*self.tree.get_children())
        # key: "rootname/postname"
        for key, meta in sorted(posts.items()):
            cnt = len(meta.get("files", []))
            self.tree.insert("", "end", values=(key, cnt))

    def get_selected_post(self) -> str | None:
        sel = self.tree.selection()
        if not sel: return None
        return self.tree.set(sel[0], "key")

    def clear(self):
        self.tree.delete(*self.tree.get_children())

    def remove_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("삭제", "삭제할 게시물을 선택하세요."); return
        for iid in sel:
            self.tree.delete(iid)
        # 선택 삭제는 UI만 지우는 동작. 실제 posts dict는 MainWindow에서 관리.

    def remove_all(self):
        if not self.tree.get_children(): return
        if messagebox.askyesno("모두 삭제", "게시물 목록을 모두 삭제할까요?"):
            self.clear()

    def _on_select(self, _):
        if self.on_select:
            self.on_select(self.get_selected_post())

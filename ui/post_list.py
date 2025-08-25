# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Dict, Optional

class PostList(ttk.Frame):
    def __init__(
        self,
        master,
        on_select: Optional[Callable[[str | None], None]] = None,
        on_activate: Optional[Callable[[str | None], None]] = None,  # 🔹 더블클릭 콜백
    ):
        super().__init__(master)
        self.on_select = on_select
        self.on_activate = on_activate

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

        btns = ttk.Frame(self); btns.pack(fill="x", pady=(0,6))
        ttk.Button(btns, text="선택 삭제", command=self.remove_selected).pack(side="left")
        ttk.Button(btns, text="모두 삭제", command=self.remove_all).pack(side="left", padx=6)

        # 이벤트 바인딩
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", self._on_double_click)  # 🔹 더블클릭으로 활성화

    def set_posts(self, posts: Dict[str, dict]):
        self.tree.delete(*self.tree.get_children())
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

    def remove_all(self):
        if not self.tree.get_children(): return
        if messagebox.askyesno("모두 삭제", "게시물 목록을 모두 삭제할까요?"):
            self.clear()

    # ---- 핸들러 ----
    def _on_select(self, _):
        if self.on_select:
            self.on_select(self.get_selected_post())

    def _on_double_click(self, event):
        # 클릭 위치가 실제 행인지 확인
        rowid = self.tree.identify_row(event.y)
        if not rowid:
            return
        # 해당 행을 선택 상태로 만들고 콜백 호출
        self.tree.selection_set(rowid)
        key = self.tree.set(rowid, "key")
        if self.on_activate:
            self.on_activate(key)

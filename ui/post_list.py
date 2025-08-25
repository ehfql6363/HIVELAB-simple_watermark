# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from typing import Dict, List

class PostList(ttk.Frame):
    def __init__(self, master, on_select=None):
        super().__init__(master)
        self._on_select = on_select
        self._posts: Dict[str, List[Path]] = {}

        ttk.Label(self, text="Posts").pack(anchor="w")
        self.lb = tk.Listbox(self, height=20)
        self.lb.pack(fill="both", expand=True, pady=4)
        self.lb.bind("<<ListboxSelect>>", self._handle_select)

        self.lbl_info = ttk.Label(self, text="0 posts")
        self.lbl_info.pack(anchor="w")

    def set_posts(self, posts: Dict[str, List[Path]]):
        self._posts = posts
        self.lb.delete(0, tk.END)
        for name in self._posts.keys():
            self.lb.insert(tk.END, name)
        self.lbl_info.configure(text=f"{len(self._posts)} posts found.")

    def get_selected_post(self) -> str | None:
        sel = self.lb.curselection()
        if not sel:
            return None
        return self.lb.get(sel[0])

    def _handle_select(self, _evt):
        if self._on_select:
            self._on_select(self.get_selected_post())

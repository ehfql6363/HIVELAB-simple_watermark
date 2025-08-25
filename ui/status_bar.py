# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk

class StatusBar(ttk.Frame):
    def __init__(self, master, on_start):
        super().__init__(master)
        self._on_start = on_start
        self._total = 100

        self.progress = ttk.Progressbar(self, mode="determinate", maximum=self._total, value=0)
        self.progress.pack(fill="x", expand=True, side="left", padx=4)
        ttk.Button(self, text="Start Batch", command=self._on_start).pack(side="left", padx=6)

    def reset(self, total: int):
        self._total = max(1, total)
        self.progress.configure(maximum=self._total, value=0)

    def set_progress(self, value: int):
        self.progress.configure(value=value)

    def finish(self):
        self.progress.configure(value=self._total)

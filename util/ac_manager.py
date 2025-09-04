from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import List, Callable

class ACManager(tk.Toplevel):
    def __init__(self, master, get_texts: Callable[[], List[str]], set_texts: Callable[[List[str]], None], on_changed: Callable[[], None]):
        super().__init__(master)
        self.title("자동완성 텍스트 관리")
        self.resizable(True, True)
        self.transient(master)
        self.grab_set()

        self._get_texts = get_texts
        self._set_texts = set_texts
        self._on_changed = on_changed

        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)

        # 상단: 단일 추가
        top = ttk.Frame(frm)
        top.pack(fill="x")
        ttk.Label(top, text="텍스트").pack(side="left")
        self.ent = ttk.Entry(top)
        self.ent.pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(top, text="추가", command=self._add_one).pack(side="left")
        self.bind("<Return>", lambda _e: self._add_one())
        self.ent.focus_set()

        # 리스트
        self.lb = tk.Listbox(frm, height=12, selectmode="extended")
        self.lb.pack(fill="both", expand=True, pady=8)

        # 하단 버튼들
        btns = ttk.Frame(frm)
        btns.pack(fill="x")
        ttk.Button(btns, text="삭제", command=self._delete_sel).pack(side="left")
        ttk.Button(btns, text="중복제거", command=self._dedup).pack(side="left", padx=6)
        ttk.Button(btns, text="정렬(가나다)", command=self._sort).pack(side="left")
        ttk.Button(btns, text="일괄추가", command=self._bulk_add).pack(side="left", padx=6)
        ttk.Button(btns, text="닫기", command=self.destroy).pack(side="right")

        self._refresh()

    def _refresh(self):
        self.lb.delete(0, "end")
        for t in self._get_texts():
            self.lb.insert("end", t)

    def _add_one(self):
        t = (self.ent.get() or "").strip()
        if not t:
            return
        texts = self._get_texts()
        if t not in texts:
            texts.append(t)
            self._set_texts(texts); self._on_changed(); self._refresh()
        self.ent.delete(0, "end")

    def _bulk_add(self):
        win = tk.Toplevel(self)
        win.title("일괄 추가 (줄바꿈 구분)")
        win.transient(self)
        txt = tk.Text(win, width=60, height=12)
        txt.pack(fill="both", expand=True, padx=8, pady=8)
        def apply():
            raw = txt.get("1.0", "end")
            items = [s.strip() for s in raw.splitlines() if s.strip()]
            if not items:
                win.destroy(); return
            texts = self._get_texts()
            for it in items:
                if it not in texts:
                    texts.append(it)
            self._set_texts(texts); self._on_changed(); self._refresh(); win.destroy()
        ttk.Button(win, text="추가", command=apply).pack(pady=6)

    def _delete_sel(self):
        sel = list(self.lb.curselection())
        if not sel:
            return
        texts = self._get_texts()
        for i in reversed(sel):
            if 0 <= i < len(texts):
                del texts[i]
        self._set_texts(texts); self._on_changed(); self._refresh()

    def _dedup(self):
        texts = list(dict.fromkeys([t.strip() for t in self._get_texts() if t.strip()]))
        self._set_texts(texts); self._on_changed(); self._refresh()

    def _sort(self):
        texts = sorted(self._get_texts(), key=lambda s: s.lower())
        self._set_texts(texts); self._on_changed(); self._refresh()
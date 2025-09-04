from __future__ import annotations
import tkinter as tk
from typing import List, Callable

class ACPopup(tk.Toplevel):
    def __init__(self, master, on_pick):
        super().__init__(master)
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self._on_pick = on_pick

        self.lb = tk.Listbox(self, height=8)
        self.lb.pack(fill="both", expand=True)
        self.lb.bind("<Return>", self._confirm)
        self.lb.bind("<Escape>", lambda _e: self.hide())
        self.lb.bind("<Double-Button-1>", self._confirm)

        self.lb.bind("<ButtonRelease-1>", self._confirm)  # 마우스로 항목 클릭 시 확정
        self.bind("<FocusOut>", lambda _e: self.after(50, self.hide))  # 50ms 지연 후 숨김

    def show_below(self, widget, choices, height_px: int = 180, min_width: int = 240):
        if not choices:
            self.hide()
            return
        self.lb.delete(0, "end")
        for s in choices:
            self.lb.insert("end", s)

        try:
            x = widget.winfo_rootx()
            y = widget.winfo_rooty() + widget.winfo_height()
            w = max(widget.winfo_width(), min_width)
            # ✅ 부모 윈도우를 transient로 지정 (포커스 이동 감지 잘 되게)
            self.transient(widget.winfo_toplevel())
        except Exception:
            x, y, w = 100, 100, min_width

        self.geometry(f"{w}x{height_px}+{x}+{y}")
        self.deiconify()
        self.lift()
        if self.lb.size() > 0:
            self.lb.selection_clear(0, "end")
            self.lb.selection_set(0)
            self.lb.activate(0)

    def hide(self):
        self.withdraw()

    def move_selection(self, delta: int):
        if not self.winfo_viewable():
            return
        cur = self.lb.curselection()
        idx = 0 if not cur else cur[0] + delta
        idx = max(0, min(self.lb.size() - 1, idx))
        self.lb.selection_clear(0, "end")
        self.lb.selection_set(idx)
        self.lb.activate(idx)

    def _confirm(self, _e=None):
        sel = self.lb.curselection()
        if not sel:
            self.hide()
            return
        val = self.lb.get(sel[0])
        self._on_pick(val)
        self.hide()

    # ac_popup.py (클래스 내부)
    def is_visible(self) -> bool:
        try:
            return str(self.state()) == "normal"
        except Exception:
            return False

    def confirm_current(self):
        # 외부에서 호출 시 현재 선택을 확정
        self._confirm(None)

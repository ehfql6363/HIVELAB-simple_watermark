# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from typing import Optional, Callable

class StatusBar(ttk.Frame):
    """
    진행 표시 + 로그 + '출력 폴더 열기' 버튼
    외부에서 호출하는 API:
      - reset(total: int) -> None
      - update_progress(n: int) -> None
      - finish(n: int) -> None
      - log_error(msg: str) -> None
      - log_info(msg: str) -> None   (신규)
      - set_output_root(path: Path) -> None  (신규)
      - enable_open_button(flag: bool) -> None (선택)
    """
    def __init__(self, master, on_start: Optional[Callable[[], None]] = None):
        super().__init__(master)
        self._on_start = on_start
        self._total = 0
        self._output_root: Optional[Path] = None

        # 상단: 컨트롤 + 진행바
        top = ttk.Frame(self); top.pack(fill="x")
        self.btn_start = ttk.Button(top, text="시작", command=self._handle_start)
        self.btn_start.pack(side="left")

        self.btn_open = ttk.Button(top, text="출력 폴더 열기", command=self._open_output_root)
        self.btn_open.pack(side="left", padx=6)
        self.btn_open.state(["disabled"])

        self.pbar = ttk.Progressbar(top, mode="determinate", maximum=100, value=0)
        self.pbar.pack(side="left", fill="x", expand=True, padx=(10, 6))
        self.lbl = ttk.Label(top, text="0 / 0")
        self.lbl.pack(side="left")

        # 하단: 로그
        bottom = ttk.Frame(self); bottom.pack(fill="both", expand=True, pady=(6,0))
        self.txt = tk.Text(bottom, height=4, wrap="none", state="disabled")
        ybar = ttk.Scrollbar(bottom, orient="vertical", command=self.txt.yview)
        self.txt.configure(yscrollcommand=ybar.set)
        self.txt.pack(side="left", fill="both", expand=True)
        ybar.pack(side="right", fill="y")

        # 태그 스타일
        self.txt.tag_configure("INFO", foreground="#008000")
        self.txt.tag_configure("ERR", foreground="#B00020")

    # ---------- public API ----------
    def reset(self, total: int):
        self._total = max(0, int(total))
        self.pbar.configure(maximum=max(1, self._total), value=0)
        self.lbl.configure(text=f"0 / {self._total}")
        self._clear_log()
        # 완료 이전에도 폴더 열 수 있게 하려면 enable 유지, 없으면 비활성
        if not self._output_root:
            self.btn_open.state(["disabled"])

    def update_progress(self, n: int):
        n = max(0, int(n))
        self.pbar.configure(value=min(n, max(1, self._total)))
        self.lbl.configure(text=f"{n} / {self._total}")
        self.txt.see("end")

    def finish(self, n: int):
        self.update_progress(self._total or n)
        self.log_info(f"작업 완료: 총 {n}개 항목 처리됨.")
        # 작업 완료 시 폴더 열기 버튼 보장
        self.enable_open_button(True)

    def log_error(self, msg: str):
        self._append_line(f"[ERROR] {msg}\n", "ERR")

    def log_info(self, msg: str):
        self._append_line(f"[INFO] {msg}\n", "INFO")

    def set_output_root(self, path: Path | str):
        try:
            p = Path(path)
        except Exception:
            p = None
        self._output_root = p
        # 경로가 진짜면 버튼 활성화
        self.enable_open_button(bool(p))

    def enable_open_button(self, flag: bool):
        if flag and self._output_root:
            self.btn_open.state(["!disabled"])
        else:
            self.btn_open.state(["disabled"])

    # ---------- internal ----------
    def _handle_start(self):
        if callable(self._on_start):
            self._on_start()

    def _append_line(self, text: str, tag: str):
        self.txt.configure(state="normal")
        self.txt.insert("end", text, (tag,))
        self.txt.configure(state="disabled")
        self.txt.see("end")

    def _clear_log(self):
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.configure(state="disabled")

    def _open_output_root(self):
        p = self._output_root
        if not p:
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(p))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(p)])
            else:
                subprocess.Popen(["xdg-open", str(p)])
        except Exception as e:
            self.log_error(f"출력 폴더 열기 실패: {e}")

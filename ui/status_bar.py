# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
import time

class StatusBar(ttk.Frame):
    def __init__(self, master, on_start):
        super().__init__(master)
        self.on_start = on_start
        self._total = 0
        self._start_ts = None
        self._paused = False

        # 좌: 버튼들
        left = ttk.Frame(self); left.pack(side="left", padx=(0,8))
        self.btn_start = ttk.Button(left, text="시작", command=self._on_start_click)
        self.btn_pause = ttk.Button(left, text="일시정지", command=self._on_pause_click, state="disabled")
        self.btn_resume = ttk.Button(left, text="재개", command=self._on_resume_click, state="disabled")
        self.btn_cancel = ttk.Button(left, text="취소", command=self._on_cancel_click, state="disabled")
        self.btn_start.pack(side="left"); self.btn_pause.pack(side="left", padx=4)
        self.btn_resume.pack(side="left"); self.btn_cancel.pack(side="left", padx=4)

        # 우: 진행바/라벨
        right = ttk.Frame(self); right.pack(side="right", fill="x", expand=True)
        self.prog = ttk.Progressbar(right, orient="horizontal", mode="determinate")
        self.prog.pack(fill="x", expand=True)
        self.lbl = ttk.Label(right, text="진행률: 0 / 0   경과: 00:00   예상: --:--")
        self.lbl.pack(anchor="e", pady=(2,0))

    # ---- public API ----
    def reset(self, total: int):
        self._total = max(0, int(total))
        self._start_ts = time.time()
        self._paused = False
        self.prog.configure(maximum=self._total, value=0)
        self._update_label(0)
        # 버튼 상태
        self.btn_start.configure(state="disabled")
        self.btn_pause.configure(state="normal")
        self.btn_resume.configure(state="disabled")
        self.btn_cancel.configure(state="normal")

    def update_progress(self, n: int):
        n = max(0, min(n, self._total))
        self.prog.configure(value=n)
        self._update_label(n)
        self.update_idletasks()

    def finish(self, n: int):
        self.prog.configure(value=n)
        self._update_label(n, done=True)
        self.btn_start.configure(state="normal")
        self.btn_pause.configure(state="disabled")
        self.btn_resume.configure(state="disabled")
        self.btn_cancel.configure(state="disabled")

    def log_error(self, msg: str):
        # 필요시 확장: 상태 라벨에 에러 카운트 반영 등
        print("[ERROR]", msg)

    # ---- buttons ----
    def _on_start_click(self):
        if callable(self.on_start):
            self.on_start()

    def _on_pause_click(self):
        # 현재 컨트롤러에서 일시정지/취소 기능을 아직 제공하지 않는다면 버튼만 비활성화 처리
        self._paused = True
        self.btn_pause.configure(state="disabled")
        self.btn_resume.configure(state="normal")

    def _on_resume_click(self):
        self._paused = False
        self.btn_pause.configure(state="normal")
        self.btn_resume.configure(state="disabled")

    def _on_cancel_click(self):
        # 컨트롤러 취소 연동 필요 시 콜백 추가 가능. 지금은 UI 리셋.
        self.finish(int(self.prog["value"]))

    # ---- helpers ----
    def _update_label(self, n: int, done: bool=False):
        elapsed = 0 if self._start_ts is None else int(time.time() - self._start_ts)
        if n > 0 and self._total > 0 and not done:
            # 단순 선형 ETA 추정
            rate = elapsed / n if n else 0
            eta = int(rate * (self._total - n))
        else:
            eta = 0 if done else -1
        def fmt(sec):
            m, s = divmod(max(0, sec), 60)
            return f"{m:02d}:{s:02d}"
        eta_str = fmt(eta) if eta >= 0 else "--:--"
        self.lbl.configure(text=f"진행률: {n} / {self._total}   경과: {fmt(elapsed)}   예상: {eta_str}")

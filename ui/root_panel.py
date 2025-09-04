# -*- coding: utf-8 -*-
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from typing import Callable, List, Optional, Dict

from settings import RootConfig, DEFAULT_WM_TEXT, IMAGES_VROOT
from ui.scrollframe import ScrollFrame
from services.autocomplete import AutocompleteIndex
from util.ac_popup import ACPopup

IMAGES_DISPLAY = "이미지"  # 가상 루트의 표시 라벨

class RootPanel(ttk.LabelFrame):
    """
    A 패널: 루트 추가/삭제/모두 삭제 + 루트 목록(비-트리뷰)
    각 행: [경로(readonly Entry)] [워터마크 입력 Entry] [선택 토글/삭제 단추]
    삭제는 '선택된 행들' 기준으로 이루어짐.
    """
    def __init__(self, master,
                 on_change: Optional[Callable[[], None]] = None,
                 title: str = "루트 목록 (루트별 워터마크 텍스트)"):
        super().__init__(master, text=title, padding=(8, 6))
        self._on_change = on_change

        # 상단 버튼바
        topbar = ttk.Frame(self)
        topbar.pack(fill="x", pady=(0, 6))
        ttk.Label(topbar, text="루트").pack(side="left")
        ttk.Frame(topbar).pack(side="left", padx=6)
        self.btn_add = ttk.Button(topbar, text="루트 추가…", style="primary.TButton",
                                  command=self._add_root_dialog)
        self.btn_del = ttk.Button(topbar, text="삭제", style="danger.Outline.TButton",
                                  command=self.remove_selected)
        self.btn_clear = ttk.Button(topbar, text="모두 삭제", style="danger.TButton",
                                    command=self.remove_all)
        # 오른쪽 정렬
        ttk.Frame(topbar).pack(side="left", fill="x", expand=True)
        self.btn_clear.pack(side="right", padx=(6, 0))
        self.btn_del.pack(side="right", padx=(6, 0))
        self.btn_add.pack(side="right", padx=(6, 0))

        # 데이터
        self._rows: List[Dict] = []  # [{frame, path_var, wm_var, sel_var}, ...]
        self._recent_dir: Optional[Path] = None

        # 컬럼 헤더(간단 라벨)
        header = ttk.Frame(self)
        header.pack(fill="x", pady=(0, 4))

        # 열: [체크박스 빈칸][루트 경로][워터마크 텍스트][삭제 빈칸]
        ttk.Label(header, text="").grid(row=0, column=0, padx=(2, 6))
        ttk.Label(header, text="루트 경로").grid(row=0, column=1, sticky="w")
        ttk.Label(header, text="워터마크 텍스트").grid(row=0, column=2, sticky="w")
        ttk.Label(header, text="").grid(row=0, column=3)

        # 헤더와 행 모두 동일한 열 비율로 맞춥니다.
        header.grid_columnconfigure(1, weight=2, uniform="roots")
        header.grid_columnconfigure(2, weight=1, uniform="roots")

        # 2) 스크롤러 + 내부 컨테이너 (행 전용)
        self.scroll = ScrollFrame(self)
        self.scroll.pack(fill="both", expand=True)
        self.rows_container = self.scroll.inner

    # ───────── Public API ─────────
    def _ensure_ac_objects(self):
        """필요 시 자동완성 객체를 지연 생성."""
        if not hasattr(self, "_ac"):
            try:
                self._ac = AutocompleteIndex(n=3)
            except Exception:
                self._ac = None
        if not hasattr(self, "_ac_popup"):
            try:
                self._ac_popup = ACPopup(self, on_pick=self._on_ac_pick)
            except Exception:
                self._ac_popup = None
        if not hasattr(self, "_ac_target_entry"):
            self._ac_target_entry = None

    def _update_ac_from_text(self, widget: tk.Entry, text: str):
        """현재 텍스트로 추천 리스트 갱신."""
        self._ensure_ac_objects()
        if not self._ac or not self._ac_popup:
            return
        # 후보 풀은 AppSettings에서 가져오되 예외시 빈 리스트
        try:
            from settings import AppSettings
            pool = AppSettings.load().autocomplete_texts or []
            self._ac.rebuild(pool)
        except Exception:
            pool = []
        try:
            results = self._ac.query(text or "", top_k=10)
        except Exception:
            results = []
        choices = [t for (t, _s) in results]
        if choices:
            self.after_idle(lambda: self._ac_popup.show_below(widget, choices))
        else:
            self._ac_popup.hide()

    def _wire_autocomplete(self, entry_widget: tk.Entry):
        """Entry 하나에 자동완성 바인딩을 붙인다."""
        self._ensure_ac_objects()
        if not self._ac_popup:
            return  # 팝업 생성 실패 시 조용히 무시

        def _accept_if_visible(_e=None):
            try:
                if self._ac_popup and self._ac_popup.is_visible():
                    self._ac_popup._confirm(None)
                    return "break"
            except Exception:
                pass
            return None

        entry_widget.bind("<FocusIn>",
                          lambda _e, w=entry_widget: (setattr(self, "_ac_target_entry", w),
                                                      self._update_ac_from_text(w, w.get())),
                          add="+")
        entry_widget.bind("<KeyRelease>",
                          lambda _e, w=entry_widget: self._update_ac_from_text(w, w.get()),
                          add="+")
        entry_widget.bind("<Down>", lambda _e: (self._ac_popup.move_selection(+1), "break"), add="+")
        entry_widget.bind("<Up>", lambda _e: (self._ac_popup.move_selection(-1), "break"), add="+")
        entry_widget.bind("<Return>", _accept_if_visible, add="+")
        entry_widget.bind("<Escape>", lambda _e: (self._ac_popup.hide(), "break"), add="+")
        entry_widget.bind("<FocusOut>", lambda _e: self._ac_popup.hide(), add="+")

    def _on_ac_pick(self, text: str):
        """팝업에서 항목 선택 시 Entry에 바로 반영."""
        try:
            w = getattr(self, "_ac_target_entry", None)
            if w and w.winfo_exists():
                w.delete(0, "end")
                w.insert(0, text)
                # 바뀐 내용 즉시 반영되도록 KeyRelease 한 번 쏴줌
                try:
                    w.event_generate("<KeyRelease>")
                except Exception:
                    pass
        except Exception:
            pass

    def set_max_height(self, h: int):
        """헤더 줄 높이를 억지로 키우지 않도록, 내부 스크롤 높이를 제한한다."""
        try:
            # ScrollFrame 자체 높이 제한
            self.scroll.configure(height=h)
            # LabelFrame의 내용 높이 전파 억제
            self.pack_propagate(False)
        except Exception:
            pass

    def _refresh_scroll(self):
        # ScrollFrame이 내부적으로 <Configure>에 맞춰 scrollregion을 업데이트한다면
        # 이 정도로 충분합니다. (캔버스 기반 ScrollFrame의 전형적인 패턴)
        try:
            self.scroll.update_idletasks()
        except Exception:
            pass

    def set_recent_dir(self, p: Optional[Path]):
        self._recent_dir = p

    def insert_or_update_root(self, path_str: str, wm_text: str = DEFAULT_WM_TEXT):
        """경로가 이미 있으면 텍스트만 업데이트, 없으면 새 행 추가"""
        for row in self._rows:
            if row["path_var"].get() == path_str:
                row["wm_var"].set(wm_text)
                self._notify_change()
                return
        self._add_row(path_str, wm_text)
        self._notify_change()
        self._refresh_scroll()

    def ensure_images_row(self):
        """가상 루트 '이미지' 행이 없으면 추가"""
        for row in getattr(self, "_rows", []):
            if row["path_var"].get() == "이미지":
                return
        self._add_row("이미지", DEFAULT_WM_TEXT)
        self._notify_change()
        # 오타 없이 정상 호출
        self._refresh_scroll()

    def get_roots(self) -> List[RootConfig]:
        out: List[RootConfig] = []
        for row in self._rows:
            root_disp = row["path_var"].get()
            wm = row["wm_var"].get()
            # 표시 라벨 "이미지" → 가상 루트 키로 변환
            if root_disp == "이미지":
                out.append(RootConfig(path=Path(IMAGES_VROOT), wm_text=wm))
            else:
                out.append(RootConfig(path=Path(root_disp), wm_text=wm))
        return out

    def remove_selected(self):
        to_remove = [row for row in self._rows if row["sel_var"].get()]
        if not to_remove:
            messagebox.showinfo("삭제", "삭제할 루트를 선택하세요.")
            return
        for row in to_remove:
            try:
                row["frame"].destroy()
            except Exception:
                pass
            self._rows.remove(row)
        self._notify_change()
        self._refresh_scroll()

    def remove_all(self):
        if not self._rows:
            return
        if not messagebox.askyesno("모두 삭제", "루트 목록을 모두 삭제할까요? (드롭 이미지 포함)"):
            return
        for row in list(self._rows):
            try:
                row["frame"].destroy()
            except Exception:
                pass
            self._rows.remove(row)
        self._notify_change()
        self._refresh_scroll()

    # ───────── Internal helpers ─────────

    def _add_root_dialog(self):
        base = self._recent_dir or Path.home()
        path = filedialog.askdirectory(title="입력 루트 선택 (게시물 폴더 포함)", initialdir=str(base))
        if not path:
            return
        self.insert_or_update_root(path, DEFAULT_WM_TEXT)
        try:
            self._recent_dir = Path(path)
        except Exception:
            pass

    def _add_row(self, path_str: str, wm_text: str):
        rowf = ttk.Frame(self.rows_container)
        rowf.pack(fill="x", pady=2)

        sel_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(rowf, variable=sel_var).grid(row=0, column=0, sticky="w", padx=(0, 6))

        path_var = tk.StringVar(value=path_str)
        ent_path = ttk.Entry(rowf, textvariable=path_var, state="readonly")
        ent_path.grid(row=0, column=1, sticky="we", padx=(0, 8))

        wm_var = tk.StringVar(value=wm_text)
        ent_wm = ttk.Entry(rowf, textvariable=wm_var)
        ent_wm.grid(row=0, column=2, sticky="we")

        self._wire_autocomplete(ent_wm)

        def _del_this():
            try:
                rowf.destroy()
            finally:
                try:
                    self._rows.remove(row)
                except Exception:
                    pass
                self._refresh_scroll()  # ★ 삭제 후 스크롤영역 갱신
                self._notify_change()

        ttk.Button(rowf, text="삭제", style="danger.Outline.TButton",
                   command=_del_this).grid(row=0, column=3, sticky="e", padx=(6, 0))

        # 헤더와 동일한 비율(경로:워터마크 = 2:1)
        rowf.grid_columnconfigure(1, weight=2, uniform="roots")
        rowf.grid_columnconfigure(2, weight=1, uniform="roots")

        # 입력 변화 감지 → on_change 호출
        wm_var.trace_add("write", lambda *_: self._notify_change())

        row = dict(frame=rowf, path_var=path_var, wm_var=wm_var, sel_var=sel_var)
        self._rows.append(row)

        self._refresh_scroll()  # ★ 행 추가 후 스크롤영역 갱신

    def _notify_change(self):
        if callable(self._on_change):
            self._on_change()

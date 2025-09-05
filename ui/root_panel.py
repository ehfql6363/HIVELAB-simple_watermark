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

        try:
            self.winfo_toplevel().bind_all("<Button-1>", self._on_global_click_hide_ac, add="+")
        except Exception:
            pass

    # ───────── Public API ─────────
    def get_selected_root_keys(self) -> List[Path]:
        """체크된 루트들의 내부 키(Path or IMAGES_VROOT)를 Path로 반환.
           가상 루트 '이미지'는 IMAGES_VROOT 문자열을 Path(...)로 감싸 동일하게 처리."""
        keys: List[Path] = []
        for row in self._rows:
            try:
                if not row["sel_var"].get():
                    continue
                disp = row["path_var"].get()
                if disp == IMAGES_DISPLAY:
                    keys.append(Path(IMAGES_VROOT))
                else:
                    keys.append(Path(disp))
            except Exception:
                pass
        return keys

    def _on_global_click_hide_ac(self, e):
        # 자동완성 객체/팝업 확보
        self._ensure_ac_objects()
        popup = getattr(self, "_ac_popup", None)
        target = getattr(self, "_ac_target_entry", None)

        # 팝업이 없거나 안 떠 있으면 무시
        try:
            if not popup or not popup.winfo_exists() or not popup.winfo_viewable():
                return
        except Exception:
            return

        w = e.widget
        # 팝업 내부 클릭이면 유지
        if self._widget_is_descendant_of(w, popup):
            return
        # 현재 타겟 Entry 내부 클릭이면 유지
        if self._widget_is_descendant_of(w, target):
            return

        # 그 외(빈 공간/다른 위젯 클릭) → 팝업 완전 닫기 + 재표시 억제(다음 FocusIn 전까지)
        self._force_hide_ac()

    def _widget_is_descendant_of(self, w: tk.Widget | None, ancestor: tk.Widget | None) -> bool:
        if not w or not ancestor:
            return False
        try:
            cur = w
            while cur is not None:
                if cur is ancestor:
                    return True
                cur = cur.master
        except Exception:
            pass
        return False

    def _ensure_ac_objects(self):
        """필요 시 자동완성 객체/팝업/상태 플래그를 지연 생성."""
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
        if not hasattr(self, "_ac_pending_job"):
            self._ac_pending_job = None  # after/after_idle 예약 ID
        if not hasattr(self, "_ac_suppressed"):
            self._ac_suppressed = False  # True면 다음 FocusIn 전까지 팝업 표시 금지

    def _cancel_ac_job(self):
        """예약된 팝업 표시 작업이 있으면 취소."""
        jid = getattr(self, "_ac_pending_job", None)
        if jid:
            try:
                self.after_cancel(jid)
            except Exception:
                pass
            self._ac_pending_job = None

    def _force_hide_ac(self):
        """팝업을 즉시 숨기고, 다음 FocusIn 전까지 재표시를 막는다."""
        self._ac_suppressed = True
        self._cancel_ac_job()
        try:
            if self._ac_popup:
                self._ac_popup.hide()
        except Exception:
            pass

    def _update_ac_from_text(self, widget: tk.Entry, text: str, *, reason: str | None = None):
        """현재 텍스트로 추천 리스트 갱신. Esc/FocusOut 뒤에는 재표시 억제."""
        self._ensure_ac_objects()
        if not self._ac or not self._ac_popup:
            return

        # Esc/FocusOut 이후엔 다음 FocusIn 전까지 표시 금지
        self._cancel_ac_job()
        if self._ac_suppressed:
            self._ac_popup.hide()
            return

        # 후보 풀 로드
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
        if not choices:
            self._ac_popup.hide()
            return

        def _do_show():
            self._ac_pending_job = None
            if self._ac_suppressed:
                try:
                    self._ac_popup.hide()
                except Exception:
                    pass
                return
            try:
                self._ac_popup.show_below(widget, choices)
            except Exception:
                pass

        # idle에 예약(다른 핸들러가 먼저 끝난 뒤 표시)
        self._ac_pending_job = self.after_idle(_do_show)

    def _wire_autocomplete(self, entry_widget: tk.Entry):
        """Entry 하나에 자동완성 바인딩을 붙인다."""
        self._ensure_ac_objects()
        if not self._ac_popup:
            return

        def _on_focus_in(_e=None, w=entry_widget):
            # FocusIn 되면 다시 표시 가능 상태로 전환
            self._ac_suppressed = False
            self._ac_target_entry = w
            self._update_ac_from_text(w, w.get(), reason="focusin")

        def _on_focus_out(_e=None, w=entry_widget):
            # 팝업 클릭(확정)과의 경합을 피하려고 1ms 뒤에 닫기
            self._cancel_ac_job()

            def _hide_later():
                self._force_hide_ac()

            self._ac_pending_job = self.after(1, _hide_later)

        def _on_key_release(e, w=entry_widget):
            ks = getattr(e, "keysym", "")
            # 방향키/엔터/ESC는 여기서 갱신하지 않음
            if ks in ("Escape", "Return", "Up", "Down"):
                return
            self._ac_suppressed = False
            self._update_ac_from_text(w, w.get(), reason="typing")

        def _on_escape(_e=None):
            self._force_hide_ac()
            return "break"

        def _on_return(_e=None):
            try:
                if self._ac_popup and self._ac_popup.is_visible():
                    self._ac_popup._confirm(None)
                    return "break"
            except Exception:
                pass
            return None

        def _on_mouse_press(_e=None, w=entry_widget):
            """
            같은 Entry가 이미 포커스를 가진 상태에서 다시 클릭해도
            팝업이 즉시 뜨도록 마우스 클릭에도 트리거를 건다.
            """
            self._ac_target_entry = w
            # 빈 공간 클릭으로 닫을 때 suppression이 켜져 있을 수 있으니 해제
            self._ac_suppressed = False
            self._cancel_ac_job()
            self._update_ac_from_text(w, w.get(), reason="mouse")

        # 바인딩들
        entry_widget.bind("<Button-1>", _on_mouse_press, add="+")  # ★ 추가
        entry_widget.bind("<FocusIn>", _on_focus_in, add="+")
        entry_widget.bind("<FocusOut>", _on_focus_out, add="+")
        entry_widget.bind("<KeyRelease>", _on_key_release, add="+")
        entry_widget.bind("<Escape>", _on_escape, add="+")
        entry_widget.bind("<Return>", _on_return, add="+")
        entry_widget.bind("<Down>", lambda _e: (self._ac_popup.move_selection(+1), "break"), add="+")
        entry_widget.bind("<Up>", lambda _e: (self._ac_popup.move_selection(-1), "break"), add="+")

    def _on_ac_pick(self, text: str):
        """팝업에서 항목 선택 시 Entry에 반영하고 자연스럽게 닫기."""
        try:
            w = getattr(self, "_ac_target_entry", None)
            if w and w.winfo_exists():
                w.delete(0, "end")
                w.insert(0, text)
                try:
                    w.event_generate("<KeyRelease>")
                except Exception:
                    pass
        except Exception:
            pass
        # 선택 후에는 팝업을 닫고 재표시 억제
        self._force_hide_ac()

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

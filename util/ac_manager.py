from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import List, Callable, Optional


class ACManager(tk.Toplevel):
    def __init__(self, master,
                 get_texts: Callable[[], List[str]],
                 set_texts: Callable[[List[str]], None],
                 on_changed: Callable[[], None],
                 on_pick: Optional[Callable[[str], None]] = None):
        super().__init__(master)
        self.title("자동완성 텍스트 관리")
        self.resizable(True, True)
        self.transient(master)
        self.grab_set()

        self._get_texts = get_texts
        self._set_texts = set_texts
        self._on_changed = on_changed
        self._on_pick = on_pick

        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)

        # 상단: 단일 추가
        top = ttk.Frame(frm)
        top.pack(fill="x")
        ttk.Label(top, text="텍스트").pack(side="left")
        self.ent = ttk.Entry(top)
        self.ent.pack(side="left", fill="x", expand=True, padx=6)

        # '텍스트 추가' 버튼(이 옆에 팝업이 뜨도록 좌표 사용)
        self.btn_add = ttk.Button(top, text="추가", command=self._add_one)
        self.btn_add.pack(side="left")

        # ⛔ 전역 <Return> 바인딩 제거 → 충돌 방지
        # self.bind("<Return>", ...)  # 삭제
        # ✅ 엔트리에서만 Enter=추가
        self.ent.bind("<Return>", lambda e: (self._add_one(), "break"))
        self.ent.focus_set()

        # 리스트
        self.lb = tk.Listbox(frm, height=12, selectmode="extended")
        self.lb.pack(fill="both", expand=True, pady=8)

        # 키 바인딩
        # 1) 목록에서 Enter=선택 확정
        self.lb.bind("<Return>", lambda e: (self._confirm_pick(), "break"))
        # 2) Delete=삭제  (원래 버그: 함수 참조만 하고 호출 안 했던 부분)
        self.lb.bind("<Delete>", lambda e: (self._delete_sel(), "break"))
        # 3) 더블클릭으로도 선택 가능
        self.lb.bind("<Double-Button-1>", lambda e: self._confirm_pick())

        # 하단 버튼들
        btns = ttk.Frame(frm)
        btns.pack(fill="x")
        ttk.Button(btns, text="삭제", command=self._delete_sel).pack(side="left")
        ttk.Button(btns, text="중복제거", command=self._dedup).pack(side="left", padx=6)
        ttk.Button(btns, text="정렬(가나다)", command=self._sort).pack(side="left")
        self.btn_bulk = ttk.Button(btns, text="일괄추가", command=self._bulk_add)  # 위치 계산에 씀
        self.btn_bulk.pack(side="left", padx=6)
        ttk.Button(btns, text="닫기", command=self.destroy).pack(side="right")

        self._refresh()

    def _refresh(self):
        self.lb.delete(0, "end")
        for t in self._get_texts():
            self.lb.insert("end", t)

    def _confirm_pick(self, _e=None):
        if not self._on_pick:
            return
        sel = self.lb.curselection()
        if not sel:
            return
        val = self.lb.get(sel[0])
        try:
            self._on_pick(val)  # ★ 워터마크 Entry에 적용
        except Exception:
            pass

    def _add_one(self):
        """엔트리 내용 1개 추가 (+중복 제거/트림/즉시 영속)."""
        t = (self.ent.get() or "").strip()
        if not t:
            return
        # 중복 제거 규칙: 공백 트림 후, 케이스 민감도는 그대로 두되 완전 일치만 제외
        texts = [s for s in self._get_texts() if s.strip()]
        if t not in texts:
            texts.append(t)
            # ✅ 여기서 바로 저장(프로그램 종료 후에도 유지)
            #    set_texts + on_changed 콜백만 호출하면, 컨트롤러/세팅 쪽에서 디스크로 영속화하게 설계
            self._set_texts(texts)
            try:
                self._on_changed()  # 예: settings.save() 같은 영속 로직이 여기에 연결되어 있어야 함
            except Exception:
                pass
            self._refresh()
        self.ent.delete(0, "end")

    def _bulk_add(self):
        win = tk.Toplevel(self)
        win.title("일괄 추가 (줄바꿈 구분)")
        win.transient(self)

        # ✅ 팝업 시작 위치를 '텍스트 추가' 버튼 옆으로
        try:
            win.update_idletasks()
            bx = self.btn_add.winfo_rootx()
            by = self.btn_add.winfo_rooty()
            bw = self.btn_add.winfo_width()
            # 버튼 오른쪽, 같은 높이
            x = bx + bw + 8
            y = by
            win.geometry(f"+{x}+{y}")
        except Exception:
            pass

        txt = tk.Text(win, width=60, height=12)
        txt.pack(fill="both", expand=True, padx=8, pady=8)

        def apply():
            raw = txt.get("1.0", "end")
            items = [s.strip() for s in raw.splitlines() if s.strip()]
            if not items:
                win.destroy(); return
            texts = [s for s in self._get_texts() if s.strip()]
            for it in items:
                if it not in texts:
                    texts.append(it)
            # ✅ 일괄추가도 즉시 영속
            self._set_texts(texts)
            try:
                self._on_changed()
            except Exception:
                pass
            self._refresh(); win.destroy()

        ttk.Button(win, text="추가", command=apply).pack(pady=6)

    def _delete_sel(self):
        sel = list(self.lb.curselection())
        if not sel:
            return
        texts = self._get_texts()
        for i in reversed(sel):
            if 0 <= i < len(texts):
                del texts[i]
        # ✅ 삭제도 즉시 영속
        self._set_texts(texts)
        try:
            self._on_changed()
        except Exception:
            pass
        self._refresh()

    def _dedup(self):
        texts = list(dict.fromkeys([t.strip() for t in self._get_texts() if t.strip()]))
        self._set_texts(texts)
        try:
            self._on_changed()
        except Exception:
            pass
        self._refresh()

    def _sort(self):
        texts = sorted(self._get_texts(), key=lambda s: s.lower())
        self._set_texts(texts)
        try:
            self._on_changed()
        except Exception:
            pass
        self._refresh()

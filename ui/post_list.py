# ui/post_list.py

# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from settings import IMAGES_VROOT  # 가상 루트 라벨링에 사용

class PostList(ttk.Frame):
    def __init__(
        self,
        master,
        on_select: Optional[Callable[[str | None], None]] = None,
        on_activate: Optional[Callable[[str | None], None]] = None,
        resolve_wm: Optional[Callable[[dict], str]] = None,           # ★ 추가: 실제 표시 텍스트 산출기
        on_wmtext_change: Optional[Callable[[str, str], None]] = None # ★ 추가: 인라인 편집 콜백
    ):
        super().__init__(master)
        self.on_select = on_select
        self.on_activate = on_activate
        self.resolve_wm = resolve_wm or (lambda meta: "")
        self.on_wmtext_change = on_wmtext_change

        self._posts_ref: Dict[str, dict] = {}
        self._root_nodes: Dict[str, str] = {}   # root_key -> iid
        self._iid_to_key: Dict[str, str] = {}   # leaf iid -> post key
        self._edit_entry: Optional[ttk.Entry] = None
        self._edit_iid: Optional[str] = None
        self._edit_col: Optional[str] = None

        box = ttk.LabelFrame(self, text="게시물")
        box.pack(fill="both", expand=True)

        cols = ("wm_text",)
        self.tree = ttk.Treeview(
            box,
            columns=cols,
            show="tree headings",
            height=16
        )
        # #0 열 (트리 전용) 활성화
        self.tree.heading("#0", text="이름")
        self.tree.column("#0", width=340)
        # 워터마크 텍스트 열
        self.tree.heading("wm_text", text="워터마크 텍스트")
        self.tree.column("wm_text", width=260)

        self.tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)

        sb = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=sb.set); sb.pack(side="right", fill="y")

        btns = ttk.Frame(self); btns.pack(fill="x", pady=(0,6))
        ttk.Button(btns, text="선택 삭제", command=self.remove_selected).pack(side="left")
        ttk.Button(btns, text="모두 삭제", command=self.remove_all).pack(side="left", padx=6)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", self._on_double_click)

    # ---------- 데이터 채우기 ----------

    def set_posts(self, posts: Dict[str, dict]):
        """posts dict를 폴더트리로 렌더링 (루트별 그룹핑)"""
        self._posts_ref = posts
        self.tree.delete(*self.tree.get_children())
        self._root_nodes.clear()
        self._iid_to_key.clear()

        # 루트별 그룹핑
        groups: Dict[str, list[Tuple[str, dict]]] = {}
        for key, meta in posts.items():
            rc = meta["root"]
            root_key = str(rc.path)  # IMAGES_VROOT 포함
            groups.setdefault(root_key, []).append((key, meta))

        # 루트 노드 → 게시물(leaf) 노드
        for root_key in sorted(groups.keys(), key=lambda s: Path(s).name.lower()):
            root_disp = "이미지" if root_key == IMAGES_VROOT else Path(root_key).name
            rid = self.tree.insert(
                "",
                "end",
                text="📂 " + root_disp,  # 트리 전용열(#0)에 표시
                values=("",),
                open=True
            )
            self._root_nodes[root_key] = rid

            # 루트 바로 아래 게시물들
            for i, (key, meta) in enumerate(sorted(groups[root_key], key=lambda kv: kv[0].lower())):
                post_name = meta.get("post_name") or Path(key).name
                wm_text = self.resolve_wm(meta)
                # ├/└ 접두사 추가 (마지막이면 └, 아니면 ├)
                prefix = "└ " if i == len(groups[root_key]) - 1 else "├ "
                iid = self.tree.insert(
                    rid,
                    "end",
                    text=prefix + post_name,
                    values=(wm_text,)
                )
                self._iid_to_key[iid] = key

    def select_key(self, key: str):
        for iid, k in self._iid_to_key.items():
            if k == key:
                self.tree.selection_set(iid)
                self.tree.see(iid)
                self.event_generate("<<TreeviewSelect>>")
                break

    def get_selected_post(self) -> str | None:
        sel = self.tree.selection()
        if not sel: return None
        iid = sel[0]
        return self._iid_to_key.get(iid)

    def clear(self):
        self.tree.delete(*self.tree.get_children())
        self._iid_to_key.clear()
        self._root_nodes.clear()

    def remove_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("삭제", "삭제할 게시물을 선택하세요."); return
        for iid in sel:
            # leaf만 삭제
            if iid in self._iid_to_key:
                self.tree.delete(iid)
                self._iid_to_key.pop(iid, None)

    def remove_all(self):
        if not self.tree.get_children(): return
        if messagebox.askyesno("모두 삭제", "게시물 목록을 모두 삭제할까요?"):
            self.clear()

    # ---------- 이벤트 ----------

    def _on_select(self, _):
        if self.on_select:
            self.on_select(self.get_selected_post())

    def _on_double_click(self, event):
        rowid = self.tree.identify_row(event.y)
        colid = self.tree.identify_column(event.x)
        # leaf + wm_text 컬럼(#2)에서만 편집
        if not rowid or (rowid not in self._iid_to_key) or colid != "#2":
            return
        self._end_edit(commit=False)
        x, y, w, h = self.tree.bbox(rowid, colid)
        cur = self.tree.set(rowid, "wm_text")
        self._edit_iid, self._edit_col = rowid, colid
        self._edit_entry = ttk.Entry(self.tree)
        self._edit_entry.insert(0, cur)
        self._edit_entry.select_range(0, tk.END)
        self._edit_entry.focus()
        self._edit_entry.place(x=x, y=y, width=w, height=h)
        self._edit_entry.bind("<Return>", lambda e: self._end_edit(True))
        self._edit_entry.bind("<Escape>", lambda e: self._end_edit(False))
        self._edit_entry.bind("<FocusOut>", lambda e: self._end_edit(True))

    def _end_edit(self, commit: bool):
        if not self._edit_entry:
            return
        if commit and self._edit_iid and self._edit_col == "#2":
            val = self._edit_entry.get()
            self.tree.set(self._edit_iid, "wm_text", val)
            key = self._iid_to_key.get(self._edit_iid)
            if key and key in self._posts_ref:
                # 게시물 단위 오버라이드 저장 (빈 문자열도 허용: 워터마크 없음)
                self._posts_ref[key]["wm_text_edit"] = val
                if callable(self.on_wmtext_change):
                    self.on_wmtext_change(key, val)
        self._edit_entry.destroy()
        self._edit_entry = None
        self._edit_iid = None
        self._edit_col = None

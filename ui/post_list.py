from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple, Union

from settings import IMAGES_VROOT  # 가상 루트 라벨링에 사용

ItemKey = Union[str, Tuple[str, Path]]  # 'post'면 key(str), 'image'면 (key, path)

class PostList(ttk.Frame):
    def __init__(
        self,
        master,
        on_select: Optional[Callable[[str | None], None]] = None,
        on_activate: Optional[Callable[[str | None], None]] = None,
        resolve_wm: Optional[Callable[[dict, Optional[Path]], str]] = None,                 # 게시물용 표시 텍스트
        resolve_img_wm: Optional[Callable[[dict, Path], str]] = None,       # 이미지용 표시 텍스트
        on_wmtext_change: Optional[Callable[[str, str], None]] = None,      # 게시물 편집 반영
        on_image_wmtext_change: Optional[Callable[[str, Path, str], None]] = None,  # 이미지 편집 반영
        on_image_select: Optional[Callable[[str, Path], None]] = None,      # 이미지 행 선택 시 알림(선택)
    ):
        super().__init__(master)
        self.on_select = on_select
        self.on_activate = on_activate
        self.resolve_wm = resolve_wm or (lambda meta: "")
        self.resolve_img_wm = resolve_img_wm or (lambda meta, p: "")
        self.on_wmtext_change = on_wmtext_change
        self.on_image_wmtext_change = on_image_wmtext_change
        self.on_image_select = on_image_select

        self._posts_ref: Dict[str, dict] = {}
        self._root_nodes: Dict[str, str] = {}   # root_key -> iid
        self._iid_to_item: Dict[str, Tuple[str, ItemKey]] = {}  # iid -> ('post', key) | ('image', (key, path))
        self._edit_entry: Optional[ttk.Entry] = None
        self._edit_iid: Optional[str] = None
        self._edit_col: Optional[str] = None

        # 스타일 약간 정리
        style = ttk.Style(self)
        style.configure("Treeview", rowheight=26, padding=(2, 2))
        style.configure("Treeview.Heading", padding=(6, 4))

        box = ttk.LabelFrame(self, text="게시물", padding=(8, 6))
        box.pack(fill="both", expand=True, padx=2, pady=2)

        # 트리 + 워터마크 텍스트 열
        cols = ("wm_text",)
        self.tree = ttk.Treeview(
            box,
            columns=cols,
            show="tree headings",
            height=10,
            selectmode="browse"
        )
        self.tree.heading("#0", text="이름")
        self.tree.column("#0", width=260, stretch=True)

        self.tree.heading("wm_text", text="워터마크 텍스트")
        self.tree.column("wm_text", width=240, anchor="w", stretch=True)

        self.tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=(6, 6))

        sb = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        sb.pack(side="right", fill="y")

        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=2, pady=(6, 8))
        ttk.Button(btns, text="선택 삭제", command=self.remove_selected).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="모두 삭제", command=self.remove_all).pack(side="left")

        # 이벤트
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", self._on_double_click)

        self._iid_to_type = {}  # "post" / "image"
        self._iid_to_postkey = {}  # 게시물 iid -> post_key
        self._iid_to_imginfo = {}  # 이미지 iid -> (post_key, Path)

    # ---------- 데이터 채우기 ----------

    def set_posts(self, posts: Dict[str, dict]):
        self._posts_ref = posts
        self.tree.delete(*self.tree.get_children())
        self._root_nodes.clear()
        self._iid_to_item.clear()

        # 루트별 그룹핑
        groups: Dict[str, list[Tuple[str, dict]]] = {}
        for key, meta in posts.items():
            rc = meta["root"]
            root_key = str(rc.path)
            groups.setdefault(root_key, []).append((key, meta))

        # 루트 → (게시물 or 바로 이미지) → 이미지
        for root_key in sorted(groups.keys(), key=lambda s: Path(s).name.lower()):
            root_disp = "이미지" if root_key == IMAGES_VROOT else Path(root_key).name
            rid = self.tree.insert("", "end", text="📂 " + root_disp, values=("",), open=False)
            self._root_nodes[root_key] = rid
            self._iid_to_item[rid] = ("root", root_key)

            posts_in_root = sorted(groups[root_key], key=lambda kv: kv[0].lower())
            for pi, (post_key, meta) in enumerate(posts_in_root):
                rc = meta["root"]
                # __SELF__ 추정: post_dir == rc.path 이고, post_name == rc 폴더명
                is_self_post = False
                try:
                    is_self_post = (meta.get("post_dir") == rc.path) and \
                                   ((meta.get("post_name") or "") == Path(rc.path).name)
                except Exception:
                    pass

                files_sorted = sorted(list(meta.get("files") or []), key=lambda p: p.name.lower())

                if is_self_post:
                    # ▶ 루트 바로 아래에 이미지 넣기
                    for fi, path in enumerate(files_sorted):
                        img_prefix = "└ " if fi == len(files_sorted) - 1 else "├ "
                        disp_name = f"🖼 {img_prefix}{path.name}"
                        wm_img = self.resolve_img_wm(meta, path)
                        iid = self.tree.insert(rid, "end", text=disp_name, values=(wm_img,))
                        self._iid_to_item[iid] = ("image", (post_key, path))
                else:
                    # ▶ 일반: 게시물 노드 만들고 그 아래 이미지
                    post_name = meta.get("post_name") or Path(post_key).name
                    wm_post = self.resolve_wm(meta)
                    p_prefix = "└ " if pi == len(posts_in_root) - 1 else "├ "
                    pid = self.tree.insert(rid, "end", text=p_prefix + post_name, values=(wm_post,), open=False)
                    self._iid_to_item[pid] = ("post", post_key)

                    for fi, path in enumerate(files_sorted):
                        img_prefix = "└ " if fi == len(files_sorted) - 1 else "├ "
                        disp_name = f"🖼 {img_prefix}{path.name}"
                        wm_img = self.resolve_img_wm(meta, path)
                        iid = self.tree.insert(pid, "end", text=disp_name, values=(wm_img,))
                        self._iid_to_item[iid] = ("image", (post_key, path))

    # ---------- 유틸 ----------

    # post_list.py

    def refresh_wm_for_post(self, post_key: str):
        """post_key와 관련된 트리의 워터마크 텍스트 표시를 강제 재계산/갱신한다.
        - 게시물(폴더) 행 1개(있을 때)
        - 그 하위의 모든 이미지 행(부모가 누구든 pk가 일치하면 모두)
        """
        meta = self._posts_ref.get(post_key)
        if not meta:
            return

        # 1) 게시물(폴더) 행 갱신 (있으면)
        try:
            for iid, (typ, item) in self._iid_to_item.items():
                if typ == "post" and item == post_key:
                    # 폴더 행의 데이터 컬럼(#1/"wm_text") 갱신
                    try:
                        self.tree.set(iid, "wm_text", self.resolve_wm(meta))
                    except Exception:
                        pass
                    break
        except Exception:
            pass

        # 2) 이 post_key에 속한 '모든' 이미지 행을 전역 매핑에서 찾아 갱신
        try:
            for iid, (typ, item) in list(self._iid_to_item.items()):
                if typ != "image":
                    continue
                pk, path = item  # (post_key, Path)
                if pk != post_key:
                    continue
                try:
                    self.tree.set(iid, "wm_text", self.resolve_img_wm(meta, path))
                except Exception:
                    pass
        except Exception:
            pass

        # 3) 즉시 리프레시(지연반영/포커스 전환 기다리지 않도록)
        try:
            self.tree.update_idletasks()
        except Exception:
            pass

    def _get_item(self, iid: str) -> Tuple[str, ItemKey] | None:
        return self._iid_to_item.get(iid)

    def _set_row_wm_text(self, iid: str, text: str):
        self.tree.set(iid, "wm_text", text)

    def select_key(self, key: str):
        for iid, (typ, item) in self._iid_to_item.items():
            if typ == "post" and item == key:
                self.tree.selection_set(iid)
                self.tree.see(iid)
                self.event_generate("<<TreeviewSelect>>")
                break

    def get_selected_post(self) -> str | None:
        sel = self.tree.selection()
        if not sel:
            return None
        iid = sel[0]
        item = self._get_item(iid)
        if not item:
            return None

        typ, key = item
        if typ == "post":
            return key  # str
        elif typ == "image":
            post_key, _path = key  # (post_key, Path)
            return post_key
        elif typ == "root":
            # 루트를 선택한 상태에서는 특정 게시물을 반환하지 않음
            # (원하면 이 자리에서 첫 게시물을 골라 반환하는 로직을 넣을 수도 있음)
            return None
        else:
            return None

    def clear(self):
        self.tree.delete(*self.tree.get_children())
        self._iid_to_item.clear()
        self._root_nodes.clear()

    def remove_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("삭제", "삭제할 항목을 선택하세요.")
            return
        for iid in sel:
            if iid in self._iid_to_item:
                self.tree.delete(iid)
                self._iid_to_item.pop(iid, None)

    def remove_all(self):
        if not self.tree.get_children():
            return
        if messagebox.askyesno("모두 삭제", "게시물 목록을 모두 삭제할까요?"):
            self.clear()

    # ---------- 이벤트 ----------

    def _get_root_iid(self, iid: str) -> str:
        """iid가 속한 최상위(루트) iid 반환."""
        cur = iid
        while True:
            parent = self.tree.parent(cur)
            if not parent:
                return cur
            cur = parent

    def _collapse_other_roots(self, keep_root_iid: Optional[str]):
        """keep_root_iid만 열어두고 다른 루트들은 닫기."""
        for top_iid in self.tree.get_children(""):
            if top_iid != keep_root_iid:
                try:
                    self.tree.item(top_iid, open=False)
                except Exception:
                    pass

    def _collapse_other_posts(self, keep_iid: Optional[str]):
        """keep_iid(유지할 게시물 iid)만 열어두고 나머지 게시물은 닫는다."""
        for iid, (typ, _item) in self._iid_to_item.items():
            if typ == "post" and iid != keep_iid:
                try:
                    self.tree.item(iid, open=False)
                except Exception:
                    pass

    def _on_select(self, _):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        item = self._get_item(iid)
        if not item:
            return

        typ, key = item

        # 루트만 열어두고 나머지 루트 닫기
        root_iid = self._get_root_iid(iid)
        try:
            self.tree.item(root_iid, open=True)
        except Exception:
            pass
        self._collapse_other_roots(root_iid)

        if typ == "post":
            post_iid = iid
            try:
                self.tree.item(post_iid, open=True)
            except Exception:
                pass
            self._collapse_other_posts(post_iid)

        elif typ == "image":
            post_iid = self.tree.parent(iid)
            if post_iid:
                try:
                    self.tree.item(post_iid, open=True)
                except Exception:
                    pass
                self._collapse_other_posts(post_iid)

        elif typ == "root":
            # 루트 클릭 시 → 첫 번째 자식(post)이 있으면 자동 선택
            children = self.tree.get_children(iid)
            if children:
                first_child = children[0]
                self.tree.selection_set(first_child)
                self.tree.see(first_child)
                self.event_generate("<<TreeviewSelect>>")
                return  # 여기서 빠져나가면 post/image 분기로 안 들어감

        # ▼ 루트 제외하고 콜백 호출
        if typ != "root" and self.on_select:
            self.on_select(self.get_selected_post())

        if typ == "image" and self.on_image_select:
            post_key, path = key
            self.on_image_select(post_key, path)

    def select_first_post(self):
        """트리 최상단에서 '게시물 노드가 있으면 그 게시물',
        없고 이미지만 있으면 '첫 이미지'를 선택해 준다."""
        roots = self.tree.get_children("")
        if not roots:
            return
        rid = roots[0]
        # 루트는 펼치기만 하고, 실제 선택은 첫 자식에게
        try:
            self.tree.item(rid, open=True)
        except Exception:
            pass

        children = self.tree.get_children(rid)
        if not children:
            return

        # 첫 자식을 선택 (게시물이든 이미지든)
        first = children[0]
        self.tree.selection_set(first)
        self.tree.see(first)
        # 선택 이벤트 트리거 → _on_select가 알아서 콜백 호출/미리보기 갱신
        self.event_generate("<<TreeviewSelect>>")

    def _on_double_click(self, event):
        rowid = self.tree.identify_row(event.y)
        colid = self.tree.identify_column(event.x)
        # 데이터 컬럼(#1)에서만 편집
        if not rowid or (rowid not in self._iid_to_item) or colid != "#1":
            return

        # 기존 에디터 종료
        self._end_edit(commit=False)

        bbox = self.tree.bbox(rowid, colid)
        if not bbox:
            return
        x, y, w, h = bbox
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

        return "break"

    def _end_edit(self, commit: bool):
        if not self._edit_entry:
            return
        if commit and self._edit_iid and self._edit_col == "#1":
            val = self._edit_entry.get()
            self._set_row_wm_text(self._edit_iid, val)

            # 어디에 써야 하는지 판별
            item = self._get_item(self._edit_iid)
            if item:
                typ, key = item
                if typ == "post":
                    post_key = key  # str
                    # 모델에 저장
                    if post_key in self._posts_ref:
                        meta = self._posts_ref[post_key]
                        meta["wm_text_edit"] = val  # 빈 문자열 포함 그대로 저장

                        # ⬇⬇ 추가: 폴더 텍스트가 바뀌면 하위 이미지 개별 텍스트 초기화
                        # 1) 인라인 텍스트 편집 맵 제거
                        imgs_map = meta.get("img_wm_text_edits")
                        if imgs_map:
                            imgs_map.clear()
                            meta["img_wm_text_edits"] = {}

                        # 2) 오버라이드에 들어있던 'text' 키 제거(다른 옵션은 보존)
                        ov_map = meta.get("img_overrides") or {}
                        for p, ov in list(ov_map.items()):
                            if isinstance(ov, dict) and "text" in ov:
                                ov.pop("text", None)

                    if callable(self.on_wmtext_change):
                        self.on_wmtext_change(post_key, val)

                    # 트리뷰 즉시 리프레시
                    try:
                        self.refresh_wm_for_post(post_key)
                    except Exception:
                        pass
                else:
                    post_key, path = key
                    meta = self._posts_ref.get(post_key)
                    if meta is not None:
                        imgs_map = meta.get("img_wm_text_edits")
                        if imgs_map is None:
                            imgs_map = meta["img_wm_text_edits"] = {}
                        imgs_map[path] = val
                    if callable(self.on_image_wmtext_change):
                        self.on_image_wmtext_change(post_key, path, val)

        self._edit_entry.destroy()
        self._edit_entry = None
        self._edit_iid = None
        self._edit_col = None
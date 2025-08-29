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
        resolve_wm: Optional[Callable[[dict], str]] = None,                 # 게시물용 표시 텍스트
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

        box = ttk.LabelFrame(self, text="게시물")
        box.pack(fill="both", expand=True)

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

        self.tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)

        sb = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        sb.pack(side="right", fill="y")

        btns = ttk.Frame(self)
        btns.pack(fill="x", pady=(0, 6))
        ttk.Button(btns, text="선택 삭제", command=self.remove_selected).pack(side="left")
        ttk.Button(btns, text="모두 삭제", command=self.remove_all).pack(side="left", padx=6)

        # 이벤트
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", self._on_double_click)

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
            rid = self.tree.insert("", "end", text="📂 " + root_disp, values=("",), open=True)
            self._root_nodes[root_key] = rid

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
        else:
            # 이미지 선택 시에도 "소속 게시물 key" 반환
            k, _ = key  # (post_key, path)
            return k

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

    def _on_select(self, _):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        item = self._get_item(iid)
        if not item:
            return

        typ, key = item
        # (1) 부모 쪽 콜백 유지: post 선택(또는 이미지 선택) → 해당 게시물 키 알림
        if self.on_select:
            self.on_select(self.get_selected_post())

        # (2) 이미지 행 선택이면 별도 콜백(선택사항)
        if typ == "image" and self.on_image_select:
            post_key, path = key
            self.on_image_select(post_key, path)

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
                    # 모델에 저장 (호출 측에서 settings/메모리 반영 추천)
                    if post_key in self._posts_ref:
                        self._posts_ref[post_key]["wm_text_edit"] = val
                    if callable(self.on_wmtext_change):
                        self.on_wmtext_change(post_key, val)
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
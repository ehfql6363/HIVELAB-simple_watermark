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

        self._wm_entry_overlays: dict[str, ttk.Entry] = {}  # iid -> Entry
        self._wm_entry_vars: dict[str, tk.StringVar] = {}  # iid -> textvariable
        self._wm_col_id = "wm_text"
        self._wm_col_index = "#1"  # Treeview column index for wm_text

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

        try:
            style.map("Treeview", background=[("selected", "#2563EB")], foreground=[("selected", "#FFFFFF")])
            # 행 높이 약간 키워서 여백감 주기
            style.configure("Treeview", rowheight=28, padding=(2, 4))
        except Exception:
            pass

        try:
            self.tree.tag_configure("row.even", background="#F8FAFC")  # 아주 옅은 회색/블루톤
            self.tree.tag_configure("row.odd", background="#FFFFFF")
        except Exception:
            pass

        self.tree.heading("#0", text="이름")
        self.tree.column("#0", width=380, stretch=True, anchor="w")

        self.tree.heading("wm_text", text="워터마크 텍스트")
        self.tree.column("wm_text", width=100, anchor="w", stretch=True)

        self.tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=(6, 6))

        sb = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        sb.pack(side="right", fill="y")

        # yscrollcommand 래핑: 스크롤 시 오버레이 갱신
        def _yscroll(first, last, _orig=sb.set):
            _orig(first, last)
            try:
                self._refresh_wm_entries()
            except Exception:
                pass

        self.tree.configure(yscrollcommand=_yscroll)

        # 트리/컨테이너 리사이즈·열기/닫기·선택 등에도 갱신
        for seq in ("<Configure>",):
            self.tree.bind(seq, lambda e: self._refresh_wm_entries(), add="+")
        for seq in ("<<TreeviewOpen>>", "<<TreeviewClose>>", "<<TreeviewSelect>>"):
            self.tree.bind(seq, lambda e: self._refresh_wm_entries(), add="+")
        # 마우스 휠 스크롤(플랫폼별 이벤트도 커버)
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.tree.bind(seq, lambda e: (self.after_idle(self._refresh_wm_entries)), add="+")

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

        # Undo
        root = self.winfo_toplevel()
        root.bind_all("<Control-z>", lambda e: (self._do_undo(e) if self._focus_in_me() else None), add="+")
        root.bind_all("<Command-z>", lambda e: (self._do_undo(e) if self._focus_in_me() else None), add="+")

    # ---------- 데이터 채우기 ----------
    def _focus_in_me(self) -> bool:
        try:
            w = self.focus_get()
            while w is not None:
                if w is self or w is self.tree:
                    return True
                # 오버레이 Entry도 허용
                if hasattr(self, "_wm_entry_overlays") and any(
                        w is ent for ent in self._wm_entry_overlays.values()):
                    return True
                w = w.master
        except Exception:
            pass
        return False

    def _get_raw_wm_for_iid(self, iid: str) -> str:
        """현재 iid의 원문 워터마크 텍스트를 계산(장식 X)."""
        item = self._get_item(iid)
        if not item:
            return ""
        typ, key = item
        try:
            if typ == "post":
                post_key = key  # str
                meta = self._posts_ref.get(post_key) or {}
                return (self.resolve_wm(meta) or "").strip()
            elif typ == "image":
                post_key, path = key
                meta = self._posts_ref.get(post_key) or {}
                return (self.resolve_img_wm(meta, path) or "").strip()
            else:
                return ""
        except Exception:
            return ""

    def _apply_wm_edit(self, iid: str, new_val: str):
        """Entry에서 편집 확정 시 메타/콜백 반영."""
        item = self._get_item(iid)
        if not item:
            return
        typ, key = item
        if typ == "post":
            post_key = key  # str
            if post_key in self._posts_ref:
                meta = self._posts_ref[post_key]
                meta["wm_text_edit"] = new_val
            if callable(self.on_wmtext_change):
                try:
                    self.on_wmtext_change(post_key, new_val)
                except Exception:
                    pass
            # 동일 post의 자식 이미지 표시 재계산
            try:
                self.refresh_wm_for_post(post_key)
            except Exception:
                pass

        elif typ == "image":
            post_key, path = key
            meta = self._posts_ref.get(post_key)
            if meta is not None:
                imgs_map = meta.get("img_wm_text_edits") or {}
                imgs_map[path] = new_val
                meta["img_wm_text_edits"] = imgs_map
            if callable(self.on_image_wmtext_change):
                try:
                    self.on_image_wmtext_change(post_key, path, new_val)
                except Exception:
                    pass

    def _ensure_overlay_for_iid(self, iid: str):
        """해당 iid의 wm_text 셀 위에 Entry를 오버레이(보이기/배치)."""
        # 루트 행은 편집 제외: 텍스트 박스 표시하지 않음
        item = self._get_item(iid)
        if not item:
            return
        typ, _ = item
        if typ == "root":
            self._destroy_overlay_for_iid(iid)
            return

        try:
            bbox = self.tree.bbox(iid, self._wm_col_index)  # (x, y, w, h)
        except Exception:
            bbox = None
        if not bbox or bbox[2] <= 4 or bbox[3] <= 6:
            # 화면에 안 보이면 제거
            self._destroy_overlay_for_iid(iid)
            return

        x, y, w, h = bbox

        # 없으면 생성
        if iid not in self._wm_entry_overlays:
            var = tk.StringVar(value=self._get_raw_wm_for_iid(iid))
            ent = ttk.Entry(self.tree, textvariable=var)
            ent.place(x=x + 1, y=y + 1, width=w - 2, height=h - 2)
            ent._orig_value = var.get()  # type: ignore[attr-defined]

            def _on_focus_in(_=None, _ent=ent, _var=var):
                _ent._orig_value = _var.get()  # 편집 시작값 저장

            def _commit(_=None, _iid=iid, _var=var, _ent=ent):
                new_val = _var.get()
                old_val = getattr(_ent, "_orig_value", new_val)
                if new_val == old_val:
                    return
                # 실제 적용
                self._apply_wm_edit(_iid, new_val)

                # 🔴 Undo 레코드: (라벨, 되돌림 함수, 포커스 iid)
                def _undo():
                    self._apply_wm_edit(_iid, old_val)
                    try:
                        _var.set(old_val)
                    except Exception:
                        pass
                    return _iid  # 되돌린 대상 iid 반환(선택)

                self._push_undo("WM edit", _undo, _iid)

            ent.bind("<FocusIn>", _on_focus_in)
            ent.bind("<Return>", _commit)
            ent.bind("<FocusOut>", _commit)

            self._wm_entry_overlays[iid] = ent
            self._wm_entry_vars[iid] = var
        else:
            # 위치/크기 조정 + 값 싱크
            ent = self._wm_entry_overlays[iid]
            var = self._wm_entry_vars[iid]
            ent.place(x=x + 1, y=y + 1, width=w - 2, height=h - 2)
            cur_raw = self._get_raw_wm_for_iid(iid)
            if var.get() != cur_raw:
                var.set(cur_raw)

    def _destroy_overlay_for_iid(self, iid: str):
        ent = self._wm_entry_overlays.pop(iid, None)
        if ent is not None:
            try:
                ent.destroy()
            except Exception:
                pass
        self._wm_entry_vars.pop(iid, None)

    def _refresh_wm_entries(self):
        """현재 보이는 모든 행에 대해 wm_text 오버레이를 갱신하고, 보이지 않는 건 제거."""
        # 1) 현재 visible 행들 추출
        visible_iids = set()
        try:
            # Treeview는 가시 행을 직접 주지 않으므로, 루트부터 펼쳐진 자식들을 순회하며
            # bbox가 유효한 항목만 '보이는 행'으로 간주
            stack = list(self.tree.get_children(""))
            while stack:
                iid = stack.pop(0)
                visible_iids.add(iid)
                # 펼쳐진 경우만 자식 체크
                try:
                    if self.tree.item(iid, "open"):
                        stack[0:0] = list(self.tree.get_children(iid))
                except Exception:
                    pass
        except Exception:
            pass

        # 2) visible인 것들만 보장
        for iid in list(visible_iids):
            self._ensure_overlay_for_iid(iid)

        # 3) 더 이상 안 보이는 오버레이 정리
        for iid in list(self._wm_entry_overlays.keys()):
            try:
                # bbox가 없거나, 열이 숨김 상태면 제거
                bbox = self.tree.bbox(iid, self._wm_col_index)
                if not bbox or bbox[2] <= 4 or bbox[3] <= 6:
                    self._destroy_overlay_for_iid(iid)
            except Exception:
                self._destroy_overlay_for_iid(iid)

    def set_posts(self, posts: Dict[str, dict]):
        self._posts_ref = posts
        self.tree.delete(*self.tree.get_children())
        self._root_nodes.clear()
        self._iid_to_item.clear()

        row_index = 0

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
                        iid = self.tree.insert(rid, "end", text=disp_name, values=(wm_img,),
                                               tags=[("row.even" if (row_index % 2 == 0) else "row.odd")])
                        row_index += 1
                        self._iid_to_item[iid] = ("image", (post_key, path))
                else:
                    # ▶ 일반: 게시물 노드 만들고 그 아래 이미지
                    post_name = meta.get("post_name") or Path(post_key).name
                    wm_post = self.resolve_wm(meta)
                    p_prefix = "└ " if pi == len(posts_in_root) - 1 else "├ "
                    pid = self.tree.insert(rid, "end", text=p_prefix + post_name, values=(wm_post,), open=False,
                                           tags=[("row.even" if (row_index % 2 == 0) else "row.odd")])
                    row_index += 1
                    self._iid_to_item[pid] = ("post", post_key)

                    for fi, path in enumerate(files_sorted):
                        img_prefix = "└ " if fi == len(files_sorted) - 1 else "├ "
                        disp_name = f"🖼️ {img_prefix}{path.name}"
                        wm_img = self.resolve_img_wm(meta, path)
                        iid = self.tree.insert(pid, "end", text=disp_name, values=(wm_img,),
                                               tags=[("row.even" if (row_index % 2 == 0) else "row.odd")])
                        row_index += 1
                        self._iid_to_item[iid] = ("image", (post_key, path))

        try:
            self._refresh_wm_entries()
        except Exception:
            pass

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
            self._refresh_wm_entries()
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

        try:
            self._refresh_wm_entries()
        except Exception:
            pass

    def remove_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("삭제", "삭제할 항목을 선택하세요.")
            return
        for iid in sel:
            if iid in self._iid_to_item:
                self.tree.delete(iid)
                self._iid_to_item.pop(iid, None)

        try:
            self._refresh_wm_entries()
        except Exception:
            pass

    def remove_all(self):
        if not self.tree.get_children():
            return
        if messagebox.askyesno("모두 삭제", "게시물 목록을 모두 삭제할까요?"):
            self.clear()

        try:
            self._refresh_wm_entries()
        except Exception:
            pass

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

        try:
            self._refresh_wm_entries()
        except Exception:
            pass

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

        if colid == self._wm_col_index:
            return

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

        # ★ 편집 전 스냅샷 저장(Undo용)
        self._pre_edit_snapshot = None
        item = self._get_item(rowid)
        if item:
            typ, key = item
            if typ == "post":
                post_key = key  # str
                meta = self._posts_ref.get(post_key) or {}
                # 이미지 인라인/오버라이드까지 되돌리려면 깊은 복사
                import copy
                self._pre_edit_snapshot = {
                    "typ": "post",
                    "iid": rowid,
                    "post_key": post_key,
                    "prev_cell": cur,
                    "meta_before": {
                        "had_wm_key": ("wm_text_edit" in meta),
                        "wm_text_edit": meta.get("wm_text_edit", None),
                        "img_wm_text_edits": copy.deepcopy(meta.get("img_wm_text_edits") or {}),
                        "img_overrides": copy.deepcopy(meta.get("img_overrides") or {}),
                    }
                }
            elif typ == "image":
                post_key, path = key
                meta = self._posts_ref.get(post_key) or {}
                img_edits = meta.get("img_wm_text_edits") or {}
                self._pre_edit_snapshot = {
                    "typ": "image",
                    "iid": rowid,
                    "post_key": post_key,
                    "path": path,
                    "prev_cell": cur,
                    "meta_before": {
                        "had_img_key": (path in img_edits),
                        "prev_text": (img_edits.get(path) if path in img_edits else None),
                    }
                }

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
            new_val = self._edit_entry.get()
            row_iid = self._edit_iid  # 🔴 포커스 대상 iid
            old_cell_text = self.tree.set(row_iid, "wm_text")  # 커밋 전 셀 표시값

            self._set_row_wm_text(row_iid, new_val)

            item = self._get_item(row_iid)
            if item:
                typ, key = item

                if typ == "post":
                    post_key = key  # str
                    meta = self._posts_ref.get(post_key) or {}

                    # 🔹 모델 갱신
                    meta["wm_text_edit"] = new_val

                    # 🔹 UNDO 함수 정의 (모델/표시 복구)
                    def _undo():
                        # 이전 값 계산: _pre_edit_snapshot가 있으면 우선 사용
                        prev = ""
                        if self._pre_edit_snapshot and self._pre_edit_snapshot.get("typ") == "post":
                            before = self._pre_edit_snapshot.get("meta_before") or {}
                            if before.get("had_wm_key", False):
                                prev = before.get("wm_text_edit", "") or ""
                            else:
                                prev = ""  # 키 없던 상태
                            # 딥 필드 복구
                            import copy
                            meta["img_wm_text_edits"] = copy.deepcopy(before.get("img_wm_text_edits") or {})
                            if not meta["img_wm_text_edits"]:
                                meta.pop("img_wm_text_edits", None)
                            meta["img_overrides"] = copy.deepcopy(before.get("img_overrides") or {})
                            if not meta["img_overrides"]:
                                meta.pop("img_overrides", None)
                        else:
                            # 스냅샷이 없으면 셀의 old_cell_text로 최소 복구
                            prev = old_cell_text

                        # wm_text_edit 복구
                        if prev == "" and "wm_text_edit" in meta:
                            del meta["wm_text_edit"]
                        else:
                            meta["wm_text_edit"] = prev

                        # 트리 표시 재계산
                        try:
                            self.refresh_wm_for_post(post_key)
                        except Exception:
                            pass

                        # 오버레이/트리 표시도 최소 보정
                        try:
                            self.tree.set(row_iid, "wm_text", prev)
                        except Exception:
                            pass

                        return row_iid  # 🔴 Undo가 되돌린 대상 iid를 반환

                    # 🔹 통합 Undo 스택 푸시 (포커스 대상 포함)
                    self._push_undo("WM edit", _undo, row_iid)

                    # 외부 알림
                    if callable(self.on_wmtext_change):
                        self.on_wmtext_change(post_key, new_val)

                    # 표시 재계산
                    try:
                        self.refresh_wm_for_post(post_key)
                    except Exception:
                        pass

                elif typ == "image":
                    post_key, path = key
                    meta = self._posts_ref.get(post_key)
                    if meta is not None:
                        imgs_map = meta.get("img_wm_text_edits") or {}
                        prev_text = imgs_map.get(path, None)
                        imgs_map[path] = new_val
                        meta["img_wm_text_edits"] = imgs_map

                        def _undo():
                            # 이전 상태로 복원
                            imgs_map2 = meta.get("img_wm_text_edits") or {}
                            if prev_text is None:
                                # 키 없던 상태
                                if path in imgs_map2:
                                    del imgs_map2[path]
                                if not imgs_map2 and "img_wm_text_edits" in meta:
                                    del meta["img_wm_text_edits"]
                            else:
                                imgs_map2[path] = prev_text
                                meta["img_wm_text_edits"] = imgs_map2

                            # 트리 셀 표시 복원
                            try:
                                prev_show = prev_text or ""
                                self.tree.set(row_iid, "wm_text", prev_show)
                            except Exception:
                                pass

                            # 외부 알림
                            if callable(self.on_image_wmtext_change):
                                try:
                                    self.on_image_wmtext_change(post_key, path, prev_text or "")
                                except Exception:
                                    pass

                            return row_iid  # 🔴 포커스 대상 iid 반환

                        self._push_undo("WM edit", _undo, row_iid)

                        if callable(self.on_image_wmtext_change):
                            self.on_image_wmtext_change(post_key, path, new_val)

        # 에디터 정리 (공통)
        self._edit_entry.destroy()
        self._edit_entry = None
        self._edit_iid = None
        self._edit_col = None
        self._pre_edit_snapshot = None

    # def _focus_row(self, iid: str | None):
    #     if not iid:
    #         return
    #     try:
    #         # 선택/포커스/가시영역 보장
    #         self.tree.selection_set(iid)
    #         self.tree.focus(iid)
    #         self.tree.see(iid)
    #         self.update_idletasks()
    #     except Exception:
    #         pass
    #
    #     # (선택) 워터마크 칸이 오버레이 Entry 형태라면 그 엔트리로 커서 주기
    #     try:
    #         ent = getattr(self, "_wm_entry_overlays", {}).get(iid)
    #         if ent:
    #             ent.focus_set()
    #             ent.icursor("end")
    #     except Exception:
    #         pass
    #
    #     try:
    #         bbox = self.tree.bbox(iid, "#1")
    #         if bbox:
    #             # _on_double_click과 동일하게 Entry 오픈
    #             x, y, w, h = bbox
    #             cur = self.tree.set(iid, "wm_text")
    #             self._edit_iid, self._edit_col = iid, "#1"
    #             self._edit_entry = ttk.Entry(self.tree)
    #             self._edit_entry.insert(0, cur)
    #             self._edit_entry.select_range(0, tk.END)
    #             self._edit_entry.focus()
    #             self._edit_entry.place(x=x, y=y, width=w, height=h)
    #             self._edit_entry.bind("<Return>", lambda e: self._end_edit(True))
    #             self._edit_entry.bind("<Escape>", lambda e: self._end_edit(False))
    #             self._edit_entry.bind("<FocusOut>", lambda e: self._end_edit(True))
    #     except Exception:
    #         pass

    def _ancestors(self, iid: str):
        chain = []
        cur = iid
        while True:
            try:
                p = self.tree.parent(cur)
            except Exception:
                p = ""
            if not p:
                break
            chain.append(p)
            cur = p
        return chain

    def _ensure_visible(self, iid: str | None):
        if not iid:
            return
        # 조상 노드 모두 펼치기
        try:
            for pid in reversed(self._ancestors(iid)):
                self.tree.item(pid, open=True)
        except Exception:
            pass
        try:
            self.tree.see(iid)
        except Exception:
            pass

    def _focus_row(self, iid: str | None):
        if not iid:
            return
        # 펼치고 스크롤/선택/포커스
        self._ensure_visible(iid)
        try:
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.tree.see(iid)
            self.update_idletasks()
        except Exception:
            pass
        # 오버레이 Entry 쓰는 경우, 실제 엔트리에 커서도 주기(있으면)
        try:
            ent = getattr(self, "_wm_entry_overlays", {}).get(iid)
            if ent:
                ent.focus_set()
                ent.icursor("end")
        except Exception:
            pass

    def _ensure_undo_stack(self):
        if not hasattr(self, "_undo_stack"):
            self._undo_stack: list[tuple[str, callable, str | None]] = []

    def _push_undo(self, label: str, undo_fn, focus_iid: str | None):
        self._ensure_undo_stack()
        self._undo_stack.append((label, undo_fn, focus_iid))

    def _do_undo(self, _=None):
        self._ensure_undo_stack()
        if not self._undo_stack:
            return "break"
        label, fn, focus_iid = self._undo_stack.pop()
        try:
            # undo_fn이 iid를 리턴하면 그걸 우선 사용 (선택)
            ret = fn()
            target_iid = ret if isinstance(ret, str) and ret else focus_iid
        except Exception:
            target_iid = focus_iid
        # UI 갱신 후 해당 행으로 이동
        try:
            self._refresh_wm_entries()
        except Exception:
            pass
        self.after_idle(lambda: self._focus_row(target_iid))
        return "break"

    def _select_post_or_first_image(self, post_key: str):
        """post_key의 게시물 노드를 선택하되, 게시물 노드가 없으면
        해당 post_key의 첫 번째 이미지 행을 선택한다."""
        # 1) 게시물 노드 찾기
        for iid, (typ, item) in self._iid_to_item.items():
            if typ == "post" and item == post_key:
                try:
                    self.tree.selection_set(iid)
                    self.tree.see(iid)
                    # 선택 이벤트 트리거 → 우측 프리뷰/에디터 싱크
                    self.event_generate("<<TreeviewSelect>>")
                except Exception:
                    pass
                return

        # 2) 게시물 노드가 없다면(자기자신 게시물 등) 첫 이미지 선택
        for iid, (typ, item) in self._iid_to_item.items():
            if typ == "image":
                pk, _p = item
                if pk == post_key:
                    try:
                        self.tree.selection_set(iid)
                        self.tree.see(iid)
                        self.event_generate("<<TreeviewSelect>>")
                    except Exception:
                        pass
                    return

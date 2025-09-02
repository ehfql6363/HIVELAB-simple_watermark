# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox
from typing import Dict, Optional, Tuple

from controller import AppController
from settings import AppSettings, DEFAULT_WM_TEXT, hex_to_rgb, RootConfig
from ui.image_wm_editor import ImageWMEditor
from ui.post_list import PostList
from ui.preview_pane import PreviewPane
from ui.thumb_gallery import ThumbGallery
import ttkbootstrap as tb
from ui.scrollframe import ScrollFrame

from ui.root_panel import RootPanel
from ui.wm_panel import WmPanel
from ui.post_inspector import PostInspector

# DnD 지원 루트
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES  # ★ DND_FILES 같이 가져오기
    class BaseTk(TkinterDnD.Tk): ...
    DND_AVAILABLE = True
except Exception:
    class BaseTk(tk.Tk): ...
    DND_AVAILABLE = False
    DND_FILES = None  # type: ignore

class MainWindow(BaseTk):
    def __init__(self, controller: AppController):
        super().__init__()
        self.title("게시물 워터마크 & 리사이즈")
        self.geometry("1180x960")
        # 창 너무 작아질 때 하단 상태바가 가려지지 않도록 최소 크기
        try: self.minsize(1180, 720)
        except Exception: pass

        self.controller = controller
        self.posts: Dict[str, dict] = {}

        try:
            self._style = tb.Style()  # 혹은 ttk.Style()
            # 테마를 강제로 바꾸고 싶다면: tb.Style("flatly") 등
            self._style.configure("TButton", padding=(10, 6))
            self._style.configure("Treeview.Heading", font=("", 10, "bold"))
        except Exception:
            pass

        self.app_settings = AppSettings.load()
        self._wm_anchor: Tuple[float, float] = tuple(self.app_settings.wm_anchor)
        self._active_src: Optional[Path] = None

        # 루트 시그니처(루트 목록이 바뀌면 자동 스캔 대체 등록)
        self._roots_sig: Tuple[Tuple[str, str], ...] = tuple()

        # ── 상단 옵션(출력/워터마크/루트 목록) ───────────────────────────────
        self.header = ttk.Frame(self)
        self.header.pack(side="top", fill="x", padx=8, pady=(12, 4))
        self._build_header(self.header)

        # ── 중간: 좌(게시물+에디터) / 우(프리뷰+썸네일) ─────────────────────
        self._build_middle(self)

        # 옵션 패널 초기값 채우기
        self.wm_panel.set_initial_options(self.app_settings)
        self.root_panel.set_recent_dir(self.app_settings.last_dir_output_dialog)

        if self.app_settings.output_root and not self.wm_panel.var_output.get().strip():
            self.wm_panel.var_output.set(str(self.app_settings.output_root))

        if self.app_settings.wm_font_path and not self.wm_panel.var_font.get().strip():
            self.wm_panel.var_font.set(str(self.app_settings.wm_font_path))

        # 최초 옵션 반영 → 루트 변경 감지로 게시물 등록
        self._on_options_changed()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _collect_ui_options(self):
        """
        A/B 패널로부터 현재 UI 상태를 한 번에 수집해
        기존 (_collect_settings)에서 기대하던 튜플 형태로 반환.
        """
        # B패널에서 출력/워터마크/배경/폰트/타겟크기 수집
        (sizes,
         bg_hex,
         wm_opacity,
         wm_scale,
         out_root_str,
         wm_fill_hex,
         wm_stroke_hex,
         wm_stroke_w,
         wm_font_path_str) = self.wm_panel.collect_options()

        # A패널에서 루트 목록
        roots = self.root_panel.get_roots()

        return (sizes, bg_hex, wm_opacity, wm_scale, out_root_str, roots,
                wm_fill_hex, wm_stroke_hex, wm_stroke_w, wm_font_path_str)

    def _on_global_drop(self, event):
        # 1) 드롭 항목 파싱
        try:
            items = self.tk.splitlist(event.data)
        except Exception:
            items = [event.data]

        from services.discovery import IMG_EXTS  # 이미지 확장자 집합
        paths = []
        for p in items:
            p = (p or "").strip()
            if p:
                paths.append(Path(p))

        dirs = [p for p in paths if p.is_dir()]
        files = [p for p in paths if p.is_file() and p.suffix.lower() in IMG_EXTS]

        # 2) 폴더 → A 패널(루트)로
        for d in dirs:
            try:
                self.root_panel.insert_or_update_root(str(d), DEFAULT_WM_TEXT)
            except Exception:
                pass

        # 3) 파일(이미지) → B 패널(WmPanel)로
        if files:
            try:
                self.wm_panel.add_dropped_images(files)
            except Exception:
                pass
            # 가상 루트 행 보장
            try:
                self.root_panel.ensure_images_row()
            except Exception:
                pass

        # 4) 무언가 반영됐다면 옵션 변경 반영
        if dirs or files:
            try:
                self._on_options_changed()
            except Exception:
                pass

    def _open_output_folder(self):
        # 우선순위: 현재 옵션창 값 → 앱 저장값
        out_root_str = (self.wm_panel.get_output_root_str() or "").strip()
        path = Path(out_root_str) if out_root_str else (self.app_settings.output_root or None)
        if not path:
            messagebox.showinfo("출력 폴더", "출력 루트 폴더를 먼저 지정하세요.")
            return
        try:
            path.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as e:
            messagebox.showerror("열기 오류", str(e))

    def _on_post_wmtext_change(self, post_key: str, value: str):
        """
        폴더(B) 인라인 편집 시:
        - '가장 최근 수정 우선' 규칙에 따라 게시물 텍스트만 최신 rev로 저장
        - 하위 이미지의 기존 값은 건드리지 않음(삭제 금지)
        - 리스트/프리뷰 즉시 갱신
        """
        meta = self.posts.get(post_key)
        if not meta:
            return

        # 1) 게시물 텍스트를 최신 rev로 기록 (빈 문자열도 '의도된 최신값'으로 인정)
        self.controller.set_post_overrides(post_key, {"text": value})

        # 2) 트리 표시 즉시 갱신
        try:
            self.post_list.refresh_wm_for_post(post_key)
        except Exception:
            pass

        # 3) 현재 보고 있던 이미지가 있으면 해당 이미지의 최신 병합 cfg로 에디터/프리뷰 동기화
        try:
            if getattr(self, "_active_src", None):
                cfg = self._effective_wm_cfg_for(meta, self._active_src)
                if getattr(self, "wm_editor", None):
                    try:
                        self.wm_editor.set_active_image_and_defaults(self._active_src, cfg)
                    except Exception:
                        pass
                if getattr(self, "preview", None):
                    try:
                        self.preview.set_wm_preview_config(cfg)
                    except Exception:
                        pass
        except Exception:
            pass

        # 4) 전체 프리뷰 재생성
        try:
            self.on_preview()
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────────────
    # 빌드
    # ──────────────────────────────────────────────────────────────────────
    def _build_header(self, parent: ttk.Frame):
        # 헤더 한 줄 컨테이너: 세로로는 확장하지 않게(expand=False)
        header_row = ttk.Frame(parent)
        header_row.pack(side="top", fill="x", expand=False)

        # A/B 두 패널을 가로 grid로 배치 (동일 가로 비율)
        header_row.grid_columnconfigure(0, weight=1, uniform="ab")
        header_row.grid_columnconfigure(1, weight=1, uniform="ab")

        # ── A: 루트 패널 ─────────────────────────
        self.root_panel = RootPanel(header_row, on_change=self._on_options_changed)
        self.root_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 6))

        # ── B: 워터마크/배경 패널 ────────────────
        self.wm_panel = WmPanel(header_row, on_change=self._on_options_changed)
        self.wm_panel.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 6))

        if DND_AVAILABLE:
            try:
                self.drop_target_register(DND_FILES)  # 최상위 윈도우에 등록
                self.dnd_bind("<<Drop>>", self._on_global_drop)
            except Exception:
                pass

        # 둘 다 같은 최대 높이로 클램프 (원하는 값으로 조절)
        MAX_HEADER_H = 180
        try:
            self.root_panel.set_max_height(MAX_HEADER_H)
        except Exception:
            pass
        try:
            self.wm_panel.set_max_height(MAX_HEADER_H)
        except Exception:
            pass

        # 단축키 바인딩 (기존 유지)
        self.bind_all("<F5>", lambda e: self.on_start_batch())
        self.bind_all("<F6>", lambda e: self._open_output_folder())

    def _on_list_toggle_wm_mode(self, items: list[tuple[str, object]], mode: str):
        """
        mode: 'empty' | 'restore'
        - empty  : 선택 항목의 텍스트를 강제로 ""로 설정
        - restore: 선택 항목의 텍스트를 루트/글로벌 기본값으로 설정
        (스타일은 건드리지 않음)
        """
        affected_posts: set[str] = set()

        # 루트 → 그 루트의 모든 게시물로 확장
        expanded: list[tuple[str, object]] = []
        for typ, key in items:
            if typ == "root":
                root_key = str(key)
                for pk, meta in (self.posts or {}).items():
                    try:
                        rc = meta.get("root")
                        if rc and str(rc.path) == root_key:
                            expanded.append(("post", pk))
                    except Exception:
                        pass
            else:
                expanded.append((typ, key))

        for typ, key in expanded:
            if typ == "post":
                post_key = key  # str
                meta = (self.posts or {}).get(post_key)
                if not meta:
                    continue
                if mode == "empty":
                    self.controller.set_post_overrides(post_key, {"text": ""})
                else:
                    base = self._base_text_from_root_global(meta)
                    self.controller.set_post_overrides(post_key, {"text": base})
                affected_posts.add(post_key)

            elif typ == "image":
                post_key, path = key
                meta = (self.posts or {}).get(post_key)
                if not meta:
                    continue
                if mode == "empty":
                    self.controller.set_image_override(post_key, path, "text", "")
                else:
                    base = self._base_text_from_root_global(meta)
                    self.controller.set_image_override(post_key, path, "text", base)
                affected_posts.add(post_key)

        for pk in affected_posts:
            try:
                self.post_list.refresh_wm_for_post(pk)
            except Exception:
                pass
        try:
            self.on_preview()
        except Exception:
            pass

    def _build_middle(self, parent):
        # 좌우 분할
        mid = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        mid.pack(fill="both", expand=True, padx=8, pady=(8, 8))

        # ── 왼쪽: 게시물 트리 ─────────────────────
        left_frame = ttk.Frame(mid)
        mid.add(left_frame, weight=1)

        # 왼쪽을 세로 분할: 위(PostList) / 아래(PostInspector)
        left_split = ttk.PanedWindow(left_frame, orient=tk.VERTICAL)
        left_split.pack(fill="both", expand=True)

        # (위) PostList
        postlist_holder = ttk.Frame(left_split)
        self.post_list = PostList(
            postlist_holder,
            on_select=self.on_select_post,
            resolve_wm=self._resolve_wm_text_for_list,
            resolve_img_wm=self._resolve_img_wm_text_for_list,
            on_wmtext_change=self._on_post_wmtext_change,
            on_image_wmtext_change=self._on_image_wmtext_change,
            on_image_select=self._on_postlist_image_select,
            on_toggle_wm=self._on_list_toggle_wm,
            on_toggle_wm_mode=self._on_list_toggle_wm_mode
        )

        self.post_list.pack(fill="both", expand=True)
        left_split.add(postlist_holder, weight=3)

        # (아래) PostInspector
        def _on_post_overrides_change(post_key: str, overrides: dict):
            if overrides:
                self.controller.set_post_overrides(post_key, overrides)
            else:
                # ⬇ settings 전달
                self.controller.reset_post_scope(post_key, self.app_settings)

            try:
                self.post_list.refresh_wm_for_post(post_key)
            except Exception:
                pass
            try:
                self.on_preview()
            except Exception:
                pass

        def _on_apply_all_images(post_key: str):
            meta = self.posts.get(post_key)
            if not meta:
                return
            # 현재 '최신 병합 텍스트'를 각 이미지 text로 복사(이미지마다 새 rev 발행)
            for p in (meta.get("files") or []):
                cfg = self.controller.resolve_wm_config(meta, self.app_settings, p)
                txt = "" if not cfg else (cfg.get("text", "") or "")
                self.controller.set_image_override(post_key, p, "text", txt)

            self.controller.apply_post_text_to_all_images(post_key)
            try:
                self.post_list.refresh_wm_for_post(post_key)
            except Exception:
                pass
            try:
                self.on_preview()
            except Exception:
                pass

        inspector_holder = ttk.Frame(left_split)
        self.post_inspector = PostInspector(
            inspector_holder,
            on_change=_on_post_overrides_change,
            on_apply_all=_on_apply_all_images,
            default_font_path=str(self.app_settings.wm_font_path or "")
        )
        self.post_inspector.pack(fill="x", expand=False)
        left_split.add(inspector_holder, weight=2)

        # ── 오른쪽: 스크롤 가능한 컬럼 ──
        right_scroll = ScrollFrame(mid)
        mid.add(right_scroll, weight=8)
        right_col = right_scroll.inner

        # (1) 개별 이미지 워터마크 에디터
        editor_frame = ttk.Frame(right_col)
        self.wm_editor = ImageWMEditor(
            editor_frame,
            on_apply=self._on_image_wm_override,
            on_clear=self._on_image_wm_clear
        )
        self.wm_editor.pack(fill="x", expand=False)
        editor_frame.pack(fill="x", side="top", padx=0, pady=(0, 8))

        # (2) 프리뷰/썸네일 Paned(V)  → tk.PanedWindow 사용
        MIN_PREVIEW, MIN_GALLERY = 500, 200

        stack = tk.PanedWindow(right_col, orient="vertical")  # ★ tk.PanedWindow
        stack.pack(fill="both", expand=True, side="top")

        # 프리뷰 pane
        pre_frame = ttk.Frame(stack)
        self.preview = PreviewPane(
            pre_frame,
            on_anchor_change=self._on_anchor_change,
            on_apply_all=self._on_apply_all,
            on_clear_individual=self._on_clear_individual
        )
        self.preview.pack(fill="both", expand=True)
        stack.add(pre_frame, minsize=MIN_PREVIEW)  # ★ minsize 적용

        # 썸네일 pane
        gal_frame = ttk.Frame(stack)
        self.gallery = ThumbGallery(
            gal_frame,
            on_activate=self._on_activate_image,
            thumb_size=168, cols=6, height=MIN_GALLERY
        )
        self.gallery.pack(fill="x", expand=False)
        stack.add(gal_frame, minsize=MIN_GALLERY)  # ★ minsize 적용

        # 초기 sash 위치: 썸네일이 최소 높이 확보되도록
        def _init_sash():
            try:
                stack.update_idletasks()
                total = stack.winfo_height()
                if total > (MIN_PREVIEW + MIN_GALLERY):
                    stack.sashpos(0, total - MIN_GALLERY)
                else:
                    stack.sashpos(0, MIN_PREVIEW)
            except Exception:
                pass

        self.after_idle(_init_sash)

        # 리사이즈 시에도 최소 높이 유지 (단일 보정만)
        def _enforce_mins(_=None):
            try:
                total = stack.winfo_height()
                if total <= 0:
                    return
                pos = stack.sashpos(0)
                lo = MIN_PREVIEW
                hi = max(MIN_PREVIEW, total - MIN_GALLERY)
                new_pos = min(max(pos, lo), hi)
                if new_pos != pos:
                    stack.sashpos(0, new_pos)
            except Exception:
                pass

        stack.bind("<Configure>", lambda e: self.after(40, _enforce_mins))

        # (3) 우측 하단 버튼바 — 썸네일 아래, 오른쪽 정렬
        btnbar = ttk.Frame(right_col)
        btnbar.pack(fill="x", side="top", pady=(8, 0))
        ttk.Frame(btnbar).pack(side="left", fill="x", expand=True)  # 오른쪽 정렬 스페이서
        self.btn_start = ttk.Button(btnbar, text="시작 (F5)", command=self.on_start_batch)
        self.btn_start.pack(side="right", padx=(6, 0))
        self.btn_open = ttk.Button(btnbar, text="출력 폴더 열기 (F6)", command=self._open_output_folder)
        self.btn_open.pack(side="right")

    def _base_text_from_root_global(self, meta: dict) -> str:
        """루트 wm_text가 있으면 그것, 없으면 글로벌 default_wm_text."""
        try:
            root = meta.get("root")
            rtxt = getattr(root, "wm_text", None) if root is not None else None
            base = (rtxt if rtxt is not None else self.app_settings.default_wm_text) or ""
            return str(base).strip()
        except Exception:
            return ""

    def _on_list_toggle_wm(self, items: list[tuple[str, object]]):
        """
        멀티 선택된 루트/게시물/이미지의 워터마크 텍스트를
        - 현재 보이는 값이 비어있지 않으면 => '비우기'
        - 현재 보이는 값이 비어있으면     => '복원(루트/글로벌 기본 텍스트)'
        로 토글한다. (스타일은 건드리지 않음)
        """
        if not items:
            return

        affected_posts: set[str] = set()

        # 1) 루트 선택은 내부의 게시물들로 확장
        expanded: list[tuple[str, object]] = []
        for typ, key in items:
            if typ == "root":
                root_key = str(key)  # root_key is a path string
                # 이 루트에 속한 게시물 모두 수집
                for pk, meta in (self.posts or {}).items():
                    try:
                        rc = meta.get("root")
                        if rc and str(rc.path) == root_key:
                            expanded.append(("post", pk))
                    except Exception:
                        pass
            else:
                expanded.append((typ, key))

        # 2) 실제 토글 처리
        for typ, key in expanded:
            if typ == "post":
                post_key = key  # str
                meta = (self.posts or {}).get(post_key)
                if not meta:
                    continue
                # 현재 게시물의 '효과 텍스트'(이미지 아님)
                cfg = self.controller.resolve_wm_config(meta, self.app_settings, None)
                cur_text = "" if cfg is None else (cfg.get("text", "") or "")
                if cur_text.strip() != "":
                    # 비우기: 게시물 오버라이드 text를 ""로
                    self.controller.set_post_overrides(post_key, {"text": ""})
                else:
                    # 복원: 루트/글로벌 기본 텍스트를 게시물 오버라이드로 설정(최신 rev로 승리)
                    base_text = self._base_text_from_root_global(meta)
                    self.controller.set_post_overrides(post_key, {"text": base_text})
                affected_posts.add(post_key)

            elif typ == "image":
                post_key, path = key  # (str, Path)
                meta = (self.posts or {}).get(post_key)
                if not meta:
                    continue
                cfg = self.controller.resolve_wm_config(meta, self.app_settings, path)
                cur_text = "" if cfg is None else (cfg.get("text", "") or "")
                if cur_text.strip() != "":
                    # 비우기: 이미지 오버라이드 text=""
                    self.controller.set_image_override(post_key, path, "text", "")
                else:
                    # 복원: 루트/글로벌 기본 텍스트로 이미지 text를 설정 (최신 rev)
                    base_text = self._base_text_from_root_global(meta)
                    self.controller.set_image_override(post_key, path, "text", base_text)
                affected_posts.add(post_key)

        # 3) UI 갱신
        for pk in affected_posts:
            try:
                self.post_list.refresh_wm_for_post(pk)
            except Exception:
                pass
        try:
            self.on_preview()
        except Exception:
            pass

    def _effective_wm_text_for(self, meta: dict, path: Path | None) -> str:
        cfg = self.controller.resolve_wm_config(meta, self.app_settings, path)
        return "" if cfg is None else (cfg.get("text", "") or "")

    def _effective_wm_cfg_for(self, meta: dict, path: Path | None) -> dict | None:
        return self.controller.resolve_wm_config(meta, self.app_settings, path)

    def _resolve_img_wm_text_for_list(self, meta: dict, path: Path) -> str:
        cfg = self.controller.resolve_wm_config(meta, self.app_settings, path)
        return "" if cfg is None else (cfg.get("text", "") or "")

    def _on_image_wmtext_change(self, post_key: str, path: Path, value: str):
        """
        이미지 인라인 편집 반영:
        - 해당 이미지의 text를 최신 rev로 저장
        - 에디터/리스트/프리뷰 즉시 갱신
        """
        meta = self.posts.get(post_key)
        if not meta:
            return

        # 1) 이미지 텍스트를 최신 rev로 기록 (빈 문자열도 '없앰' 의도로 최신 처리)
        self.controller.set_image_override(post_key, path, "text", value)

        # 2) 현재 이 이미지를 보고 있으면 최신 병합 cfg로 에디터/프리뷰 동기화
        try:
            if getattr(self, "_active_src", None) == path:
                cfg = self._effective_wm_cfg_for(meta, path)
                if getattr(self, "wm_editor", None):
                    try:
                        self.wm_editor.set_active_image_and_defaults(path, cfg)
                    except Exception:
                        pass
                if getattr(self, "preview", None):
                    try:
                        self.preview.set_wm_preview_config(cfg)
                    except Exception:
                        pass
        except Exception:
            pass

        # 3) 트리 표시 갱신 (해당 게시물의 이미지 텍스트들)
        try:
            self.post_list.refresh_wm_for_post(post_key)
        except Exception:
            pass

        # 4) 프리뷰 갱신
        try:
            self.on_preview()
        except Exception:
            pass

    def _on_postlist_image_select(self, post_key: str, path: Path):
        # 활성 이미지 업데이트
        self._active_src = path
        self.gallery.set_active(path, fire=False)

        # 에디터 값 채우기(개별 오버라이드 or 상속값)
        meta = self.posts.get(post_key) or {}
        cfg = self._effective_wm_cfg_for(meta, path)
        if hasattr(self, "wm_editor"):  # 에디터 Frame/위젯 인스턴스
            try:
                self.wm_editor.set_active_image_and_defaults(path, cfg)
            except Exception:
                pass

        # 프리뷰 갱신
        self.on_preview()

    # ──────────────────────────────────────────────────────────────────────
    # 옵션/루트 변경 → 게시물 등록(스캔 버튼 삭제를 대체)
    # ──────────────────────────────────────────────────────────────────────
    def _roots_signature(self, roots: list[RootConfig]) -> Tuple[Tuple[str, str], ...]:
        sig = []
        for rc in roots:
            path_str = str(rc.path)
            wm = (rc.wm_text or "").strip()
            sig.append((path_str, wm))
        return tuple(sig)

    def _rebuild_posts_from_roots(self):
        roots = self.root_panel.get_roots()
        dropped = self.wm_panel.get_dropped_images()
        self.posts = self.controller.scan_posts_multi(roots, dropped_images=dropped)
        self.controller.attach_posts(self.posts)

        # 트리 갱신
        self.post_list.set_posts(self.posts)

        # 갤러리/프리뷰 초기화
        self._active_src = None
        self.gallery.clear()
        self.preview.clear()
        self.preview.set_anchor(tuple(self.app_settings.wm_anchor))
        self.wm_editor.set_active_image_and_defaults(None, None)

        # ✅ 첫 항목 자동 선택 (이 안에서 <<TreeviewSelect>>를 발생시킴)
        try:
            self.post_list.select_first_post()
        except Exception:
            pass

    def _on_options_changed(self):
        (sizes, bg_hex, wm_opacity, wm_scale, out_root_str, roots,
         wm_fill_hex, wm_stroke_hex, wm_stroke_w, wm_font_path_str) = self._collect_ui_options()

        # 최근 디렉터리(선택) – WmPanel이 관리한다면 가져와 저장
        recent_out, recent_font = self.wm_panel.get_recent_dirs()

        s = self.app_settings
        s.output_root = Path(out_root_str) if out_root_str else s.output_root
        s.sizes = sizes
        s.bg_color = hex_to_rgb(bg_hex or "#FFFFFF")
        s.wm_opacity = int(wm_opacity)
        s.wm_scale_pct = int(wm_scale)
        s.wm_fill_color = hex_to_rgb(wm_fill_hex or "#000000")
        s.wm_stroke_color = hex_to_rgb(wm_stroke_hex or "#FFFFFF")
        s.wm_stroke_width = int(wm_stroke_w)
        s.wm_font_path = Path(wm_font_path_str) if wm_font_path_str else None
        if recent_out:  s.last_dir_output_dialog = recent_out
        if recent_font: s.last_dir_font_dialog = recent_font
        try:
            s.save()
        except Exception:
            pass

        # 루트 변경 감지 → 게시물 즉시 반영
        sig = self._roots_signature(roots)
        if sig != self._roots_sig:
            self._roots_sig = sig
            self._rebuild_posts_from_roots()

    # ──────────────────────────────────────────────────────────────────────
    # 좌측: 게시물 선택/이미지 선택
    # ──────────────────────────────────────────────────────────────────────
    def on_select_post(self, key: Optional[str]):
        self._active_src = None
        if not key or key not in self.posts:
            self.gallery.clear()
            self.preview.clear()
            self.wm_editor.set_active_image_and_defaults(None, None)
            return

        meta = self.posts[key]
        files = meta.get("files", [])
        default_anchor = tuple(meta.get("anchor") or self.app_settings.wm_anchor)
        img_map = meta.get("img_anchors") or {}

        try:
            self.post_inspector.bind_post(key, (self.posts.get(key) or {}).get("post_overrides"))
        except Exception:
            pass

        self.gallery.set_files(files, default_anchor=default_anchor, img_anchor_map=img_map)
        self.gallery.set_active(None)
        self._wm_anchor = default_anchor

        # 새 게시물 선택 시, 에디터는 비움
        self.wm_editor.set_active_image_and_defaults(None, None)
        self.on_preview()

    def _on_activate_image(self, path: Path):
        self._active_src = path
        self.gallery.set_active(path)

        key = self.post_list.get_selected_post()
        if not key or key not in self.posts:
            return
        meta = self.posts[key]
        overrides = meta.get("img_overrides") or {}
        cfg = overrides.get(path)

        # 에디터에 현재 이미지/기본값 반영
        self.wm_editor.set_active_image_and_defaults(path, cfg)
        self.on_preview()

    # ──────────────────────────────────────────────────────────────────────
    # 프리뷰 (개별 오버라이드 지원)
    # ──────────────────────────────────────────────────────────────────────
    def on_preview(self):
        # 1) 선택/유효성 체크
        key = self.post_list.get_selected_post()
        if not key or key not in self.posts:
            return

        meta = self.posts[key]
        files = meta.get("files") or []
        if not files:
            from tkinter import messagebox
            messagebox.showinfo("미리보기", "이 항목에는 이미지가 없습니다.")
            return

        # 2) 현재 활성 이미지가 없으면 첫 번째 이미지로
        if self._active_src is None or self._active_src not in files:
            self._active_src = files[0]

        # 3) 앵커 계산(개별 → 게시물 기본 → 앱 기본)
        img_anchor_map = meta.get("img_anchors") or {}
        if self._active_src in img_anchor_map:
            anchor = tuple(img_anchor_map[self._active_src])
        elif meta.get("anchor"):
            anchor = tuple(meta["anchor"])
        else:
            anchor = tuple(self.app_settings.wm_anchor)
        self._wm_anchor = (float(anchor[0]), float(anchor[1]))

        # 4) 현재 UI 설정 수집
        settings = self._collect_settings()

        # 5) 프리뷰/에디터에서 실제로 쓸 워터마크 텍스트/옵션 계산
        #    (이미지 개별 → 게시물 인라인 → 루트 → 앱 기본 순서)
        effective_txt = self._effective_wm_text_for(meta, self._active_src)
        cfg_for_preview = self._effective_wm_cfg_for(meta, self._active_src)  # dict 또는 None

        # 6) 프리뷰 전용 섀도우 posts: root.wm_text 를 effective_txt로 교체
        #    (컨트롤러는 root.wm_text만 보기 때문에 여기서만 임시로 바꿔줌)
        from settings import RootConfig
        shadow_posts = dict(self.posts)
        shadow_meta = dict(meta)
        rc = meta["root"]
        shadow_meta["root"] = RootConfig(path=rc.path, wm_text=effective_txt)  # ""도 허용(워터마크 없음)
        shadow_posts[key] = shadow_meta

        # 7) 컨트롤러로부터 Before/After 생성
        try:
            before_img, after_img = self.controller.preview_by_key(
                key,
                shadow_posts,
                settings,
                selected_src=self._active_src
            )
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("미리보기 오류", str(e))
            return

        # 8) 프리뷰 반영
        self.preview.show(before_img, after_img)
        self.preview.set_anchor(self._wm_anchor)
        # 유령 워터마크(미리보기 오버레이) 설정
        self.preview.set_wm_preview_config(cfg_for_preview)

        # 9) 하단 “개별 이미지 워터마크” 에디터에도 동일 값 반영
        if hasattr(self, "wm_editor") and self.wm_editor:
            try:
                self.wm_editor.set_active_image_and_defaults(self._active_src, cfg_for_preview)
            except Exception:
                pass

        # 10) 썸네일 활성 표시 싱크(있으면)
        if hasattr(self, "gallery") and self.gallery:
            try:
                self.gallery.set_active(self._active_src, fire=False)
            except Exception:
                pass

    def _collect_settings(self) -> AppSettings:
        (sizes, bg_hex, wm_opacity, wm_scale, out_root_str, _roots,
         wm_fill_hex, wm_stroke_hex, wm_stroke_w, wm_font_path_str) = self._collect_ui_options()

        # 출력 루트 폴백
        if not out_root_str and self.app_settings.output_root:
            out_root = self.app_settings.output_root
        else:
            out_root = Path(out_root_str) if out_root_str else Path("")

        # 폰트 폴백
        if not wm_font_path_str and self.app_settings.wm_font_path:
            wm_font_path = self.app_settings.wm_font_path
        else:
            wm_font_path = Path(wm_font_path_str) if wm_font_path_str else None

        return AppSettings(
            output_root=out_root,
            sizes=sizes,
            bg_color=hex_to_rgb(bg_hex or "#FFFFFF"),
            wm_opacity=int(wm_opacity),
            wm_scale_pct=int(wm_scale),
            default_wm_text=DEFAULT_WM_TEXT,
            wm_fill_color=hex_to_rgb(wm_fill_hex or "#000000"),
            wm_stroke_color=hex_to_rgb(wm_stroke_hex or "#FFFFFF"),
            wm_stroke_width=int(wm_stroke_w),
            wm_anchor=self.app_settings.wm_anchor,
            wm_font_path=wm_font_path,
        )

    def _resolve_wm_text_for_list(self, meta: dict) -> str:
        cfg = self.controller.resolve_wm_config(meta, self.app_settings, None)
        return "" if cfg is None else (cfg.get("text", "") or "")

    # ──────────────────────────────────────────────────────────────────────
    # 앵커 변경/적용/해제
    # ──────────────────────────────────────────────────────────────────────
    def _on_anchor_change(self, norm_xy):
        key = self.post_list.get_selected_post()
        if not key or key not in self.posts:
            return
        meta = self.posts[key]
        if self._active_src:
            img_map = meta.get("img_anchors")
            if img_map is None:
                img_map = meta["img_anchors"] = {}
            img_map[self._active_src] = (float(norm_xy[0]), float(norm_xy[1]))
        else:
            meta["anchor"] = (float(norm_xy[0]), float(norm_xy[1]))

        self._wm_anchor = (float(norm_xy[0]), float(norm_xy[1]))
        self._refresh_gallery_overlay(key)
        self.on_preview()

    def _on_apply_all(self, anchor):
        key = self.post_list.get_selected_post()
        if not key or key not in self.posts:
            return

        meta = self.posts[key]
        files = meta.get("files") or []
        img_map = meta.get("img_overrides") or {}  # 개별 오버라이드와 충돌 없음

        meta["anchor"] = (float(anchor[0]), float(anchor[1]))
        # 개별 지정 앵커는 손대지 않음
        self._refresh_gallery_overlay(key)
        self._wm_anchor = meta["anchor"]
        self.on_preview()

        messagebox.showinfo("모든 이미지에 적용", "기본 위치를 업데이트했습니다.")

    def _on_clear_individual(self):
        key = self.post_list.get_selected_post()
        if not key or key not in self.posts or not self._active_src:
            messagebox.showinfo("개별 지정 해제", "해제할 이미지를 먼저 선택하세요.")
            return
        meta = self.posts[key]
        img_map = meta.get("img_anchors") or {}
        if self._active_src in img_map:
            del img_map[self._active_src]
            if not img_map:
                meta["img_anchors"] = {}
            self._refresh_gallery_overlay(key)
            self.on_preview()
            messagebox.showinfo("개별 지정 해제", "현재 이미지가 게시물 기본 위치를 따르도록 복구되었습니다.")
        else:
            messagebox.showinfo("개별 지정 해제", "이 이미지에는 개별 지정이 없습니다.")

    def _refresh_gallery_overlay(self, key: str):
        meta = self.posts.get(key) or {}
        default_anchor = tuple(meta.get("anchor") or self.app_settings.wm_anchor)
        img_map = meta.get("img_anchors") or {}
        style_override_set = set((meta.get("img_overrides") or {}).keys())
        self.gallery.update_anchor_overlay(default_anchor, img_map, style_override_set=style_override_set)

    # ──────────────────────────────────────────────────────────────────────
    # 에디터 콜백(저장/해제)
    # ──────────────────────────────────────────────────────────────────────
    def _on_image_wm_override(self, path: Path, ov: dict):
        key = self.post_list.get_selected_post()
        if not key or key not in self.posts:
            return

        for k, v in (ov or {}).items():
            self.controller.set_image_override(key, path, k, v)
        self._refresh_gallery_overlay(key)
        try:
            self.post_list.refresh_wm_for_post(key)
        except Exception:
            pass
        self.on_preview()

    def _on_image_wm_clear(self, path: Path):
        key = self.post_list.get_selected_post()
        if not key or key not in self.posts:
            return

        self.controller.clear_image_overrides(key, path)
        self._refresh_gallery_overlay(key)
        try:
            self.post_list.refresh_wm_for_post(key)
        except Exception:
            pass
        self.on_preview()

    # ──────────────────────────────────────────────────────────────────────
    # 배치 시작
    # ──────────────────────────────────────────────────────────────────────
    def on_start_batch(self):
        if not self.posts:
            messagebox.showinfo("시작", "등록된 게시물이 없습니다.")
            return

        out_root_str = (self.wm_panel.get_output_root_str() or "").strip()
        if not out_root_str and self.app_settings.output_root:
            out_root_str = str(self.app_settings.output_root)
        if not out_root_str:
            messagebox.showinfo("출력 폴더", "출력 루트 폴더를 먼저 지정하세요.")
            return

        settings = self._collect_settings()
        out_root = Path(out_root_str)
        try:
            out_root.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror("출력 폴더", f"출력 루트를 만들 수 없습니다:\n{e}")
            return

        # 진행바 초기화
        total = sum(len(meta["files"]) for meta in self.posts.values()) * len(settings.sizes)

        # 버튼 상태
        self.btn_start.configure(state="disabled")
        self.btn_open.configure(state="disabled")

        def on_prog(n):
            return

        def on_done(n, _out=out_root):
            # 버튼 복구
            self.btn_start.configure(state="normal")
            self.btn_open.configure(state="normal")
            messagebox.showinfo("완료", f"총 {n}개 처리 완료.\n저장 위치: {_out}")

        def on_err(msg):
            # 오류는 알림만 (진행은 계속)
            messagebox.showerror("오류", str(msg))

        self.controller.start_batch(settings, self.posts, on_prog, on_done, on_err)

    def _on_close(self):
        try:
            self._on_options_changed()
        except Exception:
            pass
        self.destroy()

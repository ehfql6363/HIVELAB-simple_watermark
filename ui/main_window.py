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
from ui.options_panel import OptionsPanel
from ui.post_list import PostList
from ui.preview_pane import PreviewPane
from ui.thumb_gallery import ThumbGallery
import ttkbootstrap as tb

# DnD 지원 루트
try:
    from tkinterdnd2 import TkinterDnD  # type: ignore
    class BaseTk(TkinterDnD.Tk): ...
except Exception:
    class BaseTk(tk.Tk): ...

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

        # ttkbootstrap 테마 주입
        try:
            self._style.configure("TButton", padding=(10,6))
            self._style.configure("Treeview.Heading", font=("", 10, "bold"))
        except Exception: pass


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

        # ── 하단 상태바 ───────────────────────────────────────────────────
        # self.status = StatusBar(self, on_start=self.on_start_batch)
        # self.status.pack(side="bottom", fill="x", padx=8, pady=8)

        # 옵션 패널 초기값 채우기
        self.opt.set_initial_options(self.app_settings)

        if self.app_settings.output_root and not self.opt.var_output.get().strip():
            self.opt.var_output.set(str(self.app_settings.output_root))

        if self.app_settings.wm_font_path and not self.opt.var_font.get().strip():
            self.opt.var_font.set(str(self.app_settings.wm_font_path))

        # 최초 옵션 반영 → 루트 변경 감지로 게시물 등록
        self._on_options_changed()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _open_output_folder(self):
        # 우선순위: 현재 옵션창 값 → 앱 저장값
        out_root_str = (self.opt.get_output_root_str() or "").strip()
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
        게시물 인라인 편집 반영:
        - 트리뷰(부모/하위 이미지) 즉시 갱신
        - 현재 보던 항목이면 프리뷰/에디터도 재계산
        """
        # 모델에도 반영(안전차원)
        if post_key in self.posts:
            self.posts[post_key]["wm_text_edit"] = value

        # 트리뷰 표시 즉시 갱신 (부모/하위 이미지 모두)
        try:
            self.post_list.refresh_wm_for_post(post_key)
        except Exception:
            pass

        # 프리뷰/에디터 갱신
        try:
            if self._active_src:
                meta = self.posts.get(post_key) or {}
                cfg = self._effective_wm_cfg_for(meta, self._active_src)
                if hasattr(self, "wm_editor") and self.wm_editor:
                    self.wm_editor.set_active_image_and_defaults(self._active_src, cfg)
            self.on_preview()
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────────────
    # 빌드
    # ──────────────────────────────────────────────────────────────────────
    def _build_header(self, parent: ttk.Frame):
        # 버튼바(스캔/미리보기) 제거 요구사항 반영 → 오직 옵션 패널만
        self.opt = OptionsPanel(parent, on_change=self._on_options_changed)
        self.opt.pack(fill="x")

        actions = ttk.Frame(parent)
        actions.pack(fill="x", padx=2, pady=(8, 2))  # 한 줄 아래, 오른쪽 정렬용 컨테이너

        right = ttk.Frame(actions)
        right.pack(side="right")  # 오른쪽 붙이기

        self.header_prog = ttk.Progressbar(right, length=360, mode="determinate",
                                           style="info.Horizontal.TProgressbar")
        self.header_prog.pack(side="left", padx=(0, 10))

        self.btn_start = ttk.Button(right, text="시작 (F5)", command=self.on_start_batch,
                                    style = "primary.TButton")
        self.btn_start.pack(side="left", padx=(0, 8))

        self.btn_open = ttk.Button(right, text="출력 폴더 열기 (F6)", command=self._open_output_folder,
                                   style = "secondary.TButton")
        self.btn_open.pack(side="left", padx=(0, 2))

        # 단축키 바인딩
        self.bind_all("<F5>", lambda e: self.on_start_batch())
        self.bind_all("<F6>", lambda e: self._open_output_folder())

    def _build_middle(self, parent):
        # 전체 가로 분할: 좌(게시물), 우(에디터 + [프리뷰/썸네일])
        mid = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        mid.pack(fill="both", expand=True, padx=12, pady=(6, 12))

        # ── 왼쪽: 게시물(트리)만 ─────────────────────────
        left_frame = ttk.Frame(mid)
        mid.add(left_frame, weight=3)

        self.post_list = PostList(
            left_frame,
            on_select=self.on_select_post,
            resolve_wm=self._resolve_wm_text_for_list,
            resolve_img_wm=self._resolve_img_wm_text_for_list,
            on_wmtext_change=self._on_post_wmtext_change,
            on_image_wmtext_change=self._on_image_wmtext_change,
            on_image_select=self._on_postlist_image_select,
        )
        self.post_list.pack(fill="both", expand=True)

        # ── 오른쪽: 일반 프레임 + (프리뷰/썸네일) 전용 PanedWindow ──────────
        right_col = ttk.Frame(mid)
        mid.add(right_col, weight=5)

        # (1) 개별 이미지 워터마크 에디터: 맨 위, 여백 최소
        editor_frame = ttk.Frame(right_col)
        self.wm_editor = ImageWMEditor(
            editor_frame,
            on_apply=self._on_image_wm_override,
            on_clear=self._on_image_wm_clear
        )
        self.wm_editor.pack(fill="x", expand=False)
        editor_frame.pack(fill="x", side="top", padx=0, pady=(0, 10))  # ← 딱 붙게, 아래만 약간

        # (2) 프리뷰/썸네일만 세로 리사이즈: 여기만 PanedWindow 사용
        stack = ttk.PanedWindow(right_col, orient=tk.VERTICAL)
        stack.pack(fill="both", expand=True, side="top", padx=2, pady=(0, 2))

        # 프리뷰
        pre_frame = ttk.Frame(stack)
        self.preview = PreviewPane(
            pre_frame,
            on_anchor_change=self._on_anchor_change,
            on_apply_all=self._on_apply_all,
            on_clear_individual=self._on_clear_individual
        )
        self.preview.pack(fill="both", expand=True)
        stack.add(pre_frame, weight=6)

        # 썸네일
        gal_frame = ttk.Frame(stack)
        self.gallery = ThumbGallery(
            gal_frame,
            on_activate=self._on_activate_image,
            thumb_size=168, cols=6, height=200
        )
        self.gallery.pack(fill="x", expand=False)
        stack.add(gal_frame, weight=1)

        # 프리뷰/썸네일 최소 높이 유지(옵션)
        MIN_PREVIEW, MIN_GALLERY = 360, 180
        self._stack_sash_job = None

        def _apply_stack_sash():
            self._stack_sash_job = None
            try:
                total = stack.winfo_height()
                if total <= 0:
                    return
                pos = stack.sashpos(0)
                lo = MIN_PREVIEW
                hi = max(MIN_PREVIEW, total - MIN_GALLERY)
                pos = min(max(pos, lo), hi)
                if pos != stack.sashpos(0):
                    stack.sashpos(0, pos)
            except Exception:
                pass

        def _debounced_enforce(_=None):
            if self._stack_sash_job:
                try:
                    self.after_cancel(self._stack_sash_job)
                except Exception:
                    pass
            self._stack_sash_job = self.after(60, _apply_stack_sash)

        stack.bind("<Configure>", _debounced_enforce)
        self.after(0, _apply_stack_sash)

    def _effective_wm_text_for(self, meta: dict, path: Path | None) -> str:
        """이미지/게시물/루트/앱설정 순으로 워터마크 텍스트 결정."""
        # 1) 이미지 개별 텍스트
        if path is not None:
            img_edits = meta.get("img_wm_text_edits") or {}
            if path in img_edits:
                return (img_edits[path] or "").strip()

        # 2) 게시물 인라인 편집 텍스트
        edited = (meta.get("wm_text_edit") or "").strip()
        if edited != "":
            return edited  # 빈문자면 '없음' 취지로 그대로 빈값 유지

        # 3) 루트 설정 (""이면 '없음')
        root = meta["root"]
        raw = getattr(root, "wm_text", None)
        if raw is None:
            # None → 앱 기본
            return (self.app_settings.default_wm_text or "").strip()
        return raw.strip()  # "" 허용(없음)

    def _effective_wm_cfg_for(self, meta: dict, path: Path | None) -> dict | None:
        """프리뷰/에디터에 내려줄 풀 옵션 딕셔너리(없음이면 None)."""
        txt = self._effective_wm_text_for(meta, path)
        s = self._collect_settings()  # 현재 UI 값

        base = {
            "text": (txt or "").strip(),
            "opacity": int(s.wm_opacity),
            "scale_pct": int(s.wm_scale_pct),
            "fill": tuple(s.wm_fill_color),
            "stroke": tuple(s.wm_stroke_color),
            "stroke_w": int(s.wm_stroke_width),
            "font_path": str(s.wm_font_path) if s.wm_font_path else "",
        }

        # ★ 이미지 개별 오버라이드 반영
        if path is not None:
            img_ov = (meta.get("img_overrides") or {}).get(path) or {}
            if img_ov:
                base.update(img_ov)

        # 최종 텍스트가 ""이면 '워터마크 없음'
        if (base.get("text") or "").strip() == "":
            return None
        return base

    def _resolve_img_wm_text_for_list(self, meta: dict, path: Path) -> str:
        """
        이미지 레벨 표시 텍스트:
        - 개별 오버라이드(text)가 있으면 최우선
        - 그다음 인라인 편집(meta["img_wm_text_edits"][path])
        - 없으면 게시물/루트/앱 기본
        """
        # 1순위: 오버라이드의 text
        ov_map = meta.get("img_overrides") or {}
        ov = ov_map.get(path) or {}
        if "text" in ov:
            return (ov.get("text") or "").strip()

        # 2순위: 이미지 인라인 편집 텍스트
        img_edits = meta.get("img_wm_text_edits") or {}
        if path in img_edits:
            return (img_edits[path] or "").strip()

        # 기본
        return self._resolve_wm_text_for_list(meta)

    def _on_image_wmtext_change(self, post_key: str, path: Path, value: str):
        """
        이미지 인라인 편집 반영:
        - 현재 그 이미지를 보고 있으면, 에디터/프리뷰 즉시 갱신
        """
        if not self.posts:
            return
        meta = self.posts.get(post_key)
        if not meta:
            return

        if self._active_src == path:
            cfg = self._effective_wm_cfg_for(meta, path)
            if hasattr(self, "wm_editor"):
                try:
                    self.wm_editor.set_active_image_and_defaults(path, cfg)
                except Exception:
                    pass
        # 프리뷰 갱신
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
        roots = self.opt.get_roots()
        dropped = self.opt.get_dropped_images()
        self.posts = self.controller.scan_posts_multi(roots, dropped_images=dropped)

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
         wm_fill_hex, wm_stroke_hex, wm_stroke_w, wm_font_path_str) = self.opt.collect_options()
        recent_out, recent_font = self.opt.get_recent_dirs()

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
        if recent_out: s.last_dir_output_dialog = recent_out
        if recent_font: s.last_dir_font_dialog = recent_font
        try: s.save()
        except Exception: pass

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
         wm_fill_hex, wm_stroke_hex, wm_stroke_w, wm_font_path_str) = self.opt.collect_options()

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
        """
        게시물 레벨 표시 텍스트:
        - meta["wm_text_edit"]가 있으면 우선
        - 없으면 root.wm_text (빈문자 ""면 '없음' 취지로 빈 처리)
        - 둘 다 없으면 settings.default_wm_text
        """
        root = meta["root"]
        edited = (meta.get("wm_text_edit") or "").strip()
        if edited != "":
            return edited
        raw = root.wm_text
        if raw is None:
            # None → 기본 텍스트 사용
            return (self.app_settings.default_wm_text or "").strip()
        raw = raw.strip()
        if raw == "":
            # 빈 문자열 → “워터마크 없음”
            return ""
        return raw

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
        meta = self.posts[key]
        overrides = meta.setdefault("img_overrides", {})
        overrides[path] = ov

        # 썸네일 배지/앵커 오버레이 즉시 갱신
        self._refresh_gallery_overlay(key)

        # 리스트의 표시 텍스트 갱신(함수가 있다면 호출)
        if hasattr(self.post_list, "refresh_wm_for_post"):
            try:
                self.post_list.refresh_wm_for_post(key)
            except Exception:
                pass

        # 프리뷰 재생성
        self.on_preview()

    def _on_image_wm_clear(self, path: Path):
        key = self.post_list.get_selected_post()
        if not key or key not in self.posts:
            return
        meta = self.posts[key]
        overrides = meta.get("img_overrides") or {}
        try:
            del overrides[path]
        except Exception:
            pass

        # 동기화 갱신
        self._refresh_gallery_overlay(key)
        if hasattr(self.post_list, "refresh_wm_for_post"):
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

        out_root_str = (self.opt.get_output_root_str() or "").strip()
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
        try:
            self.header_prog.configure(maximum=total, value=0)
        except Exception:
            pass

        # 버튼 상태
        self.btn_start.configure(state="disabled")
        self.btn_open.configure(state="disabled")

        def on_prog(n):
            try:
                self.header_prog.configure(value=n)
                self.header_prog.update_idletasks()
            except Exception:
                pass

        def on_done(n, _out=out_root):
            try:
                self.header_prog.configure(value=total)
            except Exception:
                pass
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

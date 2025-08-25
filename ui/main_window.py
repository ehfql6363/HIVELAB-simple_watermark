# -*- coding: utf-8 -*-
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox
from typing import Dict, Optional

from controller import AppController
from settings import AppSettings, DEFAULT_SIZES, DEFAULT_WM_TEXT, hex_to_rgb
from ui.options_panel import OptionsPanel
from ui.post_list import PostList
from ui.preview_pane import PreviewPane
from ui.scrollframe import ScrollFrame
from ui.status_bar import StatusBar
from ui.thumb_gallery import ThumbGallery

# DnD 지원 루트
try:
    from tkinterdnd2 import TkinterDnD  # type: ignore
    class BaseTk(TkinterDnD.Tk): pass
except Exception:
    class BaseTk(tk.Tk): pass

class MainWindow(BaseTk):
    def __init__(self, controller: AppController):
        super().__init__()
        self.title("게시물 워터마크 & 리사이즈")
        self.geometry("1180x860")

        self.controller = controller
        self.posts: Dict[str, dict] = {}

        # 설정 로드(앵커는 세션 한정이므로 파일에는 post_anchors 저장 안함)
        self.app_settings = AppSettings.load()
        self._wm_anchor = tuple(self.app_settings.wm_anchor)  # 기본 앵커
        self._active_src: Optional[Path] = None  # 현재 편집 중 이미지(없으면 게시물 앵커 편집)

        # 1) 헤더(옵션+툴바)만 스크롤 가능
        self.header = ScrollFrame(self, height=300)
        self.header.pack(side="top", fill="x", padx=8, pady=(6, 0))
        self._build_header(self.header.inner)

        # 2) 가운데 PanedWindow는 스크롤 밖 (부모: self)
        self._build_middle(self)

        # 3) 상태바는 그대로
        self.status = StatusBar(self, on_start=self.on_start_batch)
        self.status.pack(side="bottom", fill="x", padx=8, pady=8)

        # UI 초기값 주입
        self.opt.set_initial_options(self.app_settings)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_header(self, parent):
        self.opt = OptionsPanel(parent, on_change=self._on_options_changed)
        self.opt.pack(fill="x", pady=(0, 6))
        tbar = ttk.Frame(parent);
        tbar.pack(fill="x", pady=(0, 6))
        ttk.Button(tbar, text="게시물 스캔", command=self.on_scan).pack(side="left")
        ttk.Button(tbar, text="미리보기", command=self.on_preview).pack(side="left", padx=6)

    def _build_middle(self, parent):
        mid = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        mid.pack(fill="both", expand=True)

        # 좌: 리스트 (자체 스크롤)
        self.post_list = PostList(mid, on_select=self.on_select_post,
                                  on_activate=lambda key: self.on_preview())
        mid.add(self.post_list, weight=1)

        # 우: 세로 PanedWindow (미리보기/갤러리)
        right = ttk.PanedWindow(mid, orient=tk.VERTICAL)
        mid.add(right, weight=4)

        pre_frame = ttk.Frame(right)
        self.preview = PreviewPane(pre_frame, on_anchor_change=self._on_anchor_change)
        self.preview.pack(fill="both", expand=True)
        right.add(pre_frame, weight=5)

        gal_frame = ttk.Frame(right)
        gal_frame.pack_propagate(False)
        self.gallery = ThumbGallery(gal_frame, on_activate=self._on_activate_image,
                                    thumb_size=168, cols=6, height=240)
        self.gallery.pack(fill="x", expand=False)
        right.add(gal_frame, weight=1)

        # sash 최소 높이(디바운스) 그대로 유지
        MIN_PREVIEW, MIN_GALLERY = 360, 140
        self._sash_job = None

        def _apply_minsize():
            self._sash_job = None
            try:
                total = right.winfo_height()
                if total <= 0: return
                pos = right.sashpos(0)
                if pos < MIN_PREVIEW: pos = MIN_PREVIEW
                if (total - pos) < MIN_GALLERY:
                    pos = max(total - MIN_GALLERY, MIN_PREVIEW)
                if pos != right.sashpos(0):
                    right.sashpos(0, pos)
            except:
                pass

        def _enforce(_=None):
            if self._sash_job: self.after_cancel(self._sash_job)
            self._sash_job = self.after(30, _apply_minsize)

        right.bind("<Configure>", _enforce)
        self.after(0, _apply_minsize)

    # ---- 콜백/로직 ----
    def _on_options_changed(self):
        # UI 즉시 저장(출력/사이즈/폰트 등)
        (sizes, bg_hex, wm_opacity, wm_scale, out_root_str, roots,
         wm_fill_hex, wm_stroke_hex, wm_stroke_w, wm_font_path_str) = self.opt.collect_options()
        recent_out, recent_font = self.opt.get_recent_dirs()

        s = self.app_settings
        s.output_root = Path(out_root_str) if out_root_str else s.output_root
        s.sizes = sizes if sizes else list(DEFAULT_SIZES)
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

    def _collect_settings(self) -> AppSettings:
        (sizes, bg_hex, wm_opacity, wm_scale, out_root_str, roots,
         wm_fill_hex, wm_stroke_hex, wm_stroke_w, wm_font_path_str) = self.opt.collect_options()

        if not out_root_str and roots:
            messagebox.showinfo("출력 폴더", "출력 폴더가 비어 있습니다. 첫 번째 루트의 export로 저장합니다.")
        default_out = (Path(roots[0].path) / "export") if roots else Path("export")

        return AppSettings(
            output_root=Path(out_root_str) if out_root_str else default_out,
            sizes=sizes if sizes else list(DEFAULT_SIZES),
            bg_color=hex_to_rgb(bg_hex or "#FFFFFF"),
            wm_opacity=int(wm_opacity),
            wm_scale_pct=int(wm_scale),
            default_wm_text=DEFAULT_WM_TEXT,
            wm_fill_color=hex_to_rgb(wm_fill_hex or "#000000"),
            wm_stroke_color=hex_to_rgb(wm_stroke_hex or "#FFFFFF"),
            wm_stroke_width=int(wm_stroke_w),
            wm_anchor=self.app_settings.wm_anchor,  # 기본 앵커(중앙 등)
            wm_font_path=Path(wm_font_path_str) if wm_font_path_str else None,
        )

    def on_scan(self):
        roots = self.opt.get_roots()
        if not roots:
            messagebox.showinfo("루트 폴더", "먼저 루트 폴더를 추가하세요.")
            return
        self.posts = self.controller.scan_posts_multi(roots)
        self.post_list.set_posts(self.posts)
        # 새 스캔 → 갤러리/선택 초기화
        self._active_src = None
        self.gallery.clear()
        self.gallery.set_badged(set())

    def on_select_post(self, key: str | None):
        # 선택이 바뀌면: 갤러리 구성, 활성 이미지 초기화
        self._active_src = None
        if key and key in self.posts:
            files = self.posts[key].get("files", [])
            self.gallery.set_files(files)
            self.gallery.set_active(None)
            # 커서용 앵커는 '이 게시물 앵커 or 기본값'
            self._wm_anchor = tuple(self.posts[key].get("anchor") or self.app_settings.wm_anchor)

            # ✅ 이 게시물의 per-image 앵커들을 배지로 표시
            img_map = self.posts[key].get("img_anchors") or {}
            self.gallery.set_badged(set(img_map.keys()))

    def _on_activate_image(self, path: Path):
        # 썸네일 더블클릭 → 해당 이미지 편집 모드
        self._active_src = path
        self.gallery.set_active(path)
        self.on_preview()

    def on_preview(self):
        key = self.post_list.get_selected_post()
        if not key:
            messagebox.showinfo("미리보기", "게시물을 하나 선택하세요."); return
        if key not in self.posts or not self.posts[key]["files"]:
            messagebox.showinfo("미리보기", "이 게시물에는 이미지가 없습니다."); return

        settings = self._collect_settings()
        meta = self.posts[key]
        wm_text = (meta["root"].wm_text or "").strip() or settings.default_wm_text

        # 유령 워터마크 프리뷰 설정 전달
        wm_cfg = {
            "text": wm_text,
            "opacity": settings.wm_opacity,
            "scale_pct": settings.wm_scale_pct,
            "fill": settings.wm_fill_color,
            "stroke": settings.wm_stroke_color,
            "stroke_w": settings.wm_stroke_width,
            "font_path": str(settings.wm_font_path) if settings.wm_font_path else "",
        }
        self.preview.set_wm_preview_config(wm_cfg)

        # 이 미리보기에서 사용할 앵커: 이미지 > 게시물 > 기본
        img_anchor_map = meta.get("img_anchors") or {}
        if self._active_src and self._active_src in img_anchor_map:
            anchor = tuple(img_anchor_map[self._active_src])
        elif meta.get("anchor"):
            anchor = tuple(meta["anchor"])
        else:
            anchor = tuple(self.app_settings.wm_anchor)

        self._wm_anchor = anchor  # 드래그 유령 위치

        try:
            before_img, after_img = self.controller.preview_by_key(
                key, self.posts, settings, selected_src=self._active_src
            )
        except Exception as e:
            messagebox.showerror("미리보기 오류", str(e)); return

        self.preview.show(before_img, after_img)
        self.preview.set_anchor(anchor)

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

        # ✅ 갤러리 배지 갱신 (이미지별 앵커 상태 반영)
        img_map = meta.get("img_anchors") or {}
        self.gallery.set_badged(set(img_map.keys()))

        # 미리보기 갱신
        self.on_preview()

    def on_start_batch(self):
        if not self.posts:
            messagebox.showinfo("시작", "스캔된 게시물이 없습니다.")
            return
        settings = self._collect_settings()

        total = sum(len(meta["files"]) for meta in self.posts.values()) * len(settings.sizes)
        self.status.reset(total)

        def on_prog(n): self.status.update_progress(n)
        def on_done(n): self.status.finish(n)
        def on_err(msg): self.status.log_error(msg)

        self.controller.start_batch(settings, self.posts, on_prog, on_done, on_err)

    def _on_close(self):
        try:
            self._on_options_changed()  # 옵션 저장
            # 앵커(게시물/이미지)는 세션 한정 → 저장하지 않음
        except Exception:
            pass
        self.destroy()

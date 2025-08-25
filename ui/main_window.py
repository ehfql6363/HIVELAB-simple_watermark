# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Dict

from settings import AppSettings, DEFAULT_SIZES, DEFAULT_WM_TEXT, hex_to_rgb
from controller import AppController
from ui.options_panel import OptionsPanel
from ui.preview_pane import PreviewPane
from ui.post_list import PostList
from ui.status_bar import StatusBar
from ui.scrollframe import ScrollFrame

class BaseTk(tk.Tk):
    pass

try:
    from tkinterdnd2 import TkinterDnD
    class BaseTk(TkinterDnD.Tk):
        pass
except Exception:
    class BaseTk(tk.Tk):
        pass

class MainWindow(BaseTk):
    def __init__(self, controller: AppController):
        super().__init__()
        self.title("게시물 워터마크 & 리사이즈")
        self.geometry("1180x820")

        self.controller = controller
        self.posts: Dict[str, dict] = {}
        self._wm_anchor = (0.5, 0.5)

        # 상단(스크롤) + 하단(고정) 레이아웃
        self.scroll = ScrollFrame(self)
        self.scroll.pack(side="top", fill="both", expand=True, padx=8, pady=(6, 0))

        self._build_scroll_content(self.scroll.inner)

        # 하단 고정 상태바(시작/진행바 항상 보임)
        self.status = StatusBar(self, on_start=self.on_start_batch)
        self.status.pack(side="bottom", fill="x", padx=8, pady=8)

    def _build_scroll_content(self, parent):
        # 옵션 패널
        self.opt = OptionsPanel(parent)
        self.opt.pack(fill="x", pady=(0, 6))

        # 중간 툴바 (한글화)
        tbar = ttk.Frame(parent); tbar.pack(fill="x", pady=(0, 6))
        ttk.Button(tbar, text="게시물 스캔", command=self.on_scan).pack(side="left")
        ttk.Button(tbar, text="미리보기", command=self.on_preview).pack(side="left", padx=6)

        # 좌/우(게시물 리스트 / 미리보기)
        mid = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        mid.pack(fill="both", expand=True)

        self.post_list = PostList(mid, on_select=self.on_select_post)
        mid.add(self.post_list, weight=1)

        self.preview = PreviewPane(mid, on_anchor_change=self._on_anchor_change)
        mid.add(self.preview, weight=3)

    # ---- 콜백/로직 ----
    def _on_anchor_change(self, norm_xy):
        self._wm_anchor = norm_xy
        key = self.post_list.get_selected_post()
        if key and key in self.posts:
            self.on_preview()  # 위치 반영 즉시 미리보기

    def _collect_settings(self) -> AppSettings:
        (sizes, bg_hex, wm_opacity, wm_scale, out_root_str, roots,
         wm_fill_hex, wm_stroke_hex, wm_stroke_w, wm_font_path_str) = self.opt.collect_options()

        if not out_root_str and roots:
            messagebox.showinfo("출력 폴더", "출력 폴더가 비어 있습니다. 첫 번째 루트의 export로 저장합니다.")
        default_out = (Path(roots[0].path) / "export") if roots else Path("export")

        from settings import DEFAULT_SIZES as DS
        return AppSettings(
            output_root=Path(out_root_str) if out_root_str else default_out,
            sizes=sizes if sizes else list(DS),
            bg_color=hex_to_rgb(bg_hex or "#FFFFFF"),
            wm_opacity=int(wm_opacity),
            wm_scale_pct=int(wm_scale),
            default_wm_text=DEFAULT_WM_TEXT,
            wm_fill_color=hex_to_rgb(wm_fill_hex or "#000000"),
            wm_stroke_color=hex_to_rgb(wm_stroke_hex or "#FFFFFF"),
            wm_stroke_width=int(wm_stroke_w),
            wm_anchor=self._wm_anchor,
            wm_font_path=Path(wm_font_path_str) if wm_font_path_str else None,
        )

    def on_scan(self):
        roots = self.opt.get_roots()
        if not roots:
            messagebox.showinfo("루트 폴더", "먼저 루트 폴더를 추가하세요.")
            return
        self.posts = self.controller.scan_posts_multi(roots)
        self.post_list.set_posts(self.posts)

    def on_select_post(self, key: str | None):
        # 선택만 바뀌면 즉시 미리보기까지 자동으로 하지 않고, 버튼으로 제어
        pass

    def on_preview(self):
        key = self.post_list.get_selected_post()
        if not key:
            messagebox.showinfo("미리보기", "게시물을 하나 선택하세요.")
            return
        if key not in self.posts or not self.posts[key]["files"]:
            messagebox.showinfo("미리보기", "이 게시물에는 이미지가 없습니다.")
            return

        settings = self._collect_settings()

        # 유령 워터마크 프리뷰 설정 전달
        meta = self.posts[key]
        wm_text = (meta["root"].wm_text or "").strip() or settings.default_wm_text
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

        try:
            before_img, after_img = self.controller.preview_by_key(key, self.posts, settings)
        except Exception as e:
            messagebox.showerror("미리보기 오류", str(e))
            return

        self.preview.show(before_img, after_img)
        self.preview.set_anchor(self._wm_anchor)

    def on_start_batch(self):
        if not self.posts:
            messagebox.showinfo("시작", "스캔된 게시물이 없습니다.")
            return
        settings = self._collect_settings()
        # 전체 작업량
        total = sum(len(meta["files"]) for meta in self.posts.values()) * len(settings.sizes)
        self.status.reset(total)

        def on_prog(n): self.status.update_progress(n)
        def on_done(n): self.status.finish(n)
        def on_err(msg): self.status.log_error(msg)

        self.controller.start_batch(settings, self.posts, on_prog, on_done, on_err)

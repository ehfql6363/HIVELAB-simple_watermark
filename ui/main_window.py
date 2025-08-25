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
        self.geometry("1180x820")

        self.controller = controller
        self.posts: Dict[str, dict] = {}

        # 설정 로드
        self.app_settings = AppSettings.load()
        self._wm_anchor = tuple(self.app_settings.wm_anchor)

        # 레이아웃
        self.scroll = ScrollFrame(self)
        self.scroll.pack(side="top", fill="both", expand=True, padx=8, pady=(6, 0))
        self._build_scroll_content(self.scroll.inner)

        self.status = StatusBar(self, on_start=self.on_start_batch)
        self.status.pack(side="bottom", fill="x", padx=8, pady=8)

        # UI 초기값 주입
        self.opt.set_initial_options(self.app_settings)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_scroll_content(self, parent):
        self.opt = OptionsPanel(parent, on_change=self._on_options_changed)
        self.opt.pack(fill="x", pady=(0, 6))

        tbar = ttk.Frame(parent);
        tbar.pack(fill="x", pady=(0, 6))
        ttk.Button(tbar, text="게시물 스캔", command=self.on_scan).pack(side="left")
        ttk.Button(tbar, text="미리보기", command=self.on_preview).pack(side="left", padx=6)

        mid = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        mid.pack(fill="both", expand=True)

        # 🔹 더블 클릭 시 미리보기 실행
        self.post_list = PostList(
            mid,
            on_select=self.on_select_post,
            on_activate=lambda key: self.on_preview(),
        )
        mid.add(self.post_list, weight=1)

        self.preview = PreviewPane(mid, on_anchor_change=self._on_anchor_change)
        mid.add(self.preview, weight=3)

    def _on_options_changed(self):
        # UI → settings 동기화
        (sizes, bg_hex, wm_opacity, wm_scale, out_root_str, roots,
         wm_fill_hex, wm_stroke_hex, wm_stroke_w, wm_font_path_str) = self.opt.collect_options()

        # 최근 폴더도 반영
        recent_out, recent_font = self.opt.get_recent_dirs()

        s = self.app_settings
        from settings import hex_to_rgb, DEFAULT_SIZES
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

        try:
            s.save()  # 🔸 즉시 저장
        except Exception:
            pass

    # ---- 콜백/로직 ----
    def _on_anchor_change(self, norm_xy):
        key = self.post_list.get_selected_post()
        if not key or key not in self.posts:
            return
        # ✅ 세션 메모리만 갱신
        self.posts[key]["anchor"] = (float(norm_xy[0]), float(norm_xy[1]))
        self._wm_anchor = self.posts[key]["anchor"]
        # 미리보기만 갱신 (디스크 저장/설정 저장 없음)
        self.on_preview()

    def _collect_settings(self) -> AppSettings:
        (sizes, bg_hex, wm_opacity, wm_scale, out_root_str, roots,
         wm_fill_hex, wm_stroke_hex, wm_stroke_w, wm_font_path_str) = self.opt.collect_options()

        default_out = (Path(roots[0].path) / "export") if roots else Path("export")

        s = AppSettings(
            output_root=Path(out_root_str) if out_root_str else default_out,
            sizes=sizes if sizes else list(DEFAULT_SIZES),
            bg_color=hex_to_rgb(bg_hex or "#FFFFFF"),
            wm_opacity=int(wm_opacity),
            wm_scale_pct=int(wm_scale),
            default_wm_text=DEFAULT_WM_TEXT,
            wm_fill_color=hex_to_rgb(wm_fill_hex or "#000000"),
            wm_stroke_color=hex_to_rgb(wm_stroke_hex or "#FFFFFF"),
            wm_stroke_width=int(wm_stroke_w),
            wm_anchor=self.app_settings.wm_anchor,
            wm_font_path=Path(wm_font_path_str) if wm_font_path_str else None,
            # post_anchors는 세션 한정이므로 건들지 않음
        )
        return s

    def on_scan(self):
        roots = self.opt.get_roots()
        if not roots:
            messagebox.showinfo("루트 폴더", "먼저 루트 폴더를 추가하세요.")
            return
        self.posts = self.controller.scan_posts_multi(roots)
        # ✅ 설정 파일로부터 앵커 주입 없음 (세션 새로 시작)
        self.post_list.set_posts(self.posts)

    def on_select_post(self, key: str | None):
        if key and key in self.posts:
            self._wm_anchor = tuple(self.posts[key].get("anchor") or self.app_settings.wm_anchor)

    def on_preview(self):
        key = self.post_list.get_selected_post()
        if not key:
            messagebox.showinfo("미리보기", "게시물을 하나 선택하세요."); return
        if key not in self.posts or not self.posts[key]["files"]:
            messagebox.showinfo("미리보기", "이 게시물에는 이미지가 없습니다."); return

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

        # 🔹 이 게시물의 앵커 사용
        anchor = tuple(meta.get("anchor") or self.app_settings.wm_anchor)  # ✅ 세션 > 기본
        self._wm_anchor = anchor

        try:
            before_img, after_img = self.controller.preview_by_key(key, self.posts, settings)
        except Exception as e:
            messagebox.showerror("미리보기 오류", str(e)); return

        self.preview.show(before_img, after_img)
        self.preview.set_anchor(anchor)

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

    # 종료 시에도 보수적으로 저장(최근 폴더 포함)
    def _on_close(self):
        try:
            self._on_options_changed()  # UI 옵션만 저장
            # ✅ 앵커는 저장하지 않음 (세션 한정)
        except Exception:
            pass
        self.destroy()

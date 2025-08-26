# -*- coding: utf-8 -*-
from __future__ import annotations
import os
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from typing import Callable, List, Optional, Dict, Tuple
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

from PIL import Image, ImageTk

class ThumbGallery(ttk.Frame):
    """썸네일 그리드 (클릭으로 활성화). 썸네일 생성은 병렬, UI 업데이트는 메인 스레드."""
    def __init__(self, master,
                 on_activate: Optional[Callable[[Path], None]] = None,
                 thumb_size: int = 160, cols: int = 5, height: int = 220):
        super().__init__(master)
        self.on_activate = on_activate
        self.thumb_size = int(thumb_size)
        self.cols = int(cols)
        self.fixed_height = int(height)

        # 스크롤 컨테이너
        self.canvas = tk.Canvas(self, highlightthickness=0, height=self.fixed_height)
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vbar.set)
        self.inner = tk.Frame(self.canvas)
        self.win_id = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vbar.pack(side="right", fill="y")

        self.inner.bind("<Configure>", self._on_inner_config)
        self.canvas.bind("<Configure>", self._on_canvas_config)

        # 마우스 휠(호버 시)
        self._enable_wheel_for(self.canvas)
        self._enable_wheel_for(self.inner)

        # 상태
        self._tiles: Dict[Path, tk.Frame] = {}
        self._imgs: Dict[Path, ImageTk.PhotoImage] = {}  # PhotoImage 강참조
        self._active: Optional[Path] = None

        # --- 병렬 썸네일 준비 ---
        self._executor = ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 4))
        self._gen_token = 0  # 세대 토큰(새 목록 로드시 증가)
        # PIL 썸네일 LRU 캐시 (PhotoImage는 Tk 객체라 캐시에 넣지 않음)
        self._pil_cache: "OrderedDict[Tuple[str,int,int], Image.Image]" = OrderedDict()
        self._pil_cache_limit = 256

        self.bind("<Destroy>", self._on_destroy, add="+")

    # ----- 외부 API -----
    def clear(self):
        for w in self.inner.winfo_children():
            w.destroy()
        self._tiles.clear()
        self._imgs.clear()
        self._active = None
        self._update_scroll()

    def set_files(self, files: List[Path],
                  default_anchor: Tuple[float, float] | None = None,
                  img_anchor_map: Optional[Dict[Path, Tuple[float, float]]] = None):
        """files만 사용. (default_anchor/img_anchor_map은 호환용 인자)"""
        self.clear()
        self._gen_token += 1
        token = self._gen_token

        if not files:
            return

        size = self.thumb_size
        pad = 8

        # 플레이스홀더 하나 만들어 재사용(회색)
        placeholder = ImageTk.PhotoImage(Image.new("RGB", (size, size), (240, 240, 240)))

        for i, p in enumerate(files):
            r, c = divmod(i, self.cols)
            tile = tk.Frame(self.inner, bd=1, relief="groove")
            tile.grid(row=r, column=c, padx=pad, pady=pad, sticky="nsew")

            # 이미지 라벨(플레이스홀더)
            lbl_img = tk.Label(tile, image=placeholder)
            lbl_img.image = placeholder
            lbl_img.pack(padx=4, pady=(4, 0))

            # 파일명 라벨
            lbl_txt = tk.Label(tile, text=p.name, wraplength=size, justify="center")
            lbl_txt.pack(padx=4, pady=(2, 6))

            # 클릭 한 번으로 활성화
            def _activate(ev=None, path=p):
                self.set_active(path)
                if callable(self.on_activate):
                    self.on_activate(path)
            tile.bind("<Button-1>", _activate)
            lbl_img.bind("<Button-1>", _activate)
            lbl_txt.bind("<Button-1>", _activate)

            self._tiles[p] = tile

        # 컬럼 확장
        for c in range(self.cols):
            self.inner.grid_columnconfigure(c, weight=1)
        self._update_scroll()

        # 백그라운드로 썸네일 생성 & UI 반영
        for p in files:
            self._submit_thumb_job(p, size, token)

    def set_active(self, path: Optional[Path]):
        if self._active and self._active in self._tiles:
            self._tiles[self._active].configure(bd=1, relief="groove")
        self._active = path
        if path and path in self._tiles:
            self._tiles[path].configure(bd=2, relief="solid")

    # 호환용(오버레이 안 씀)
    def update_anchor_overlay(self, default_anchor, img_anchor_map):
        pass

    # ----- 내부: 병렬 썸네일 파이프라인 -----
    def _submit_thumb_job(self, path: Path, size: int, token: int):
        """캐시 있으면 즉시, 없으면 스레드에서 PIL 썸네일 생성 후 메인 스레드 반영."""
        key = self._cache_key(path, size)
        pil = self._pil_cache_get(key)
        if pil is not None:
            # 메인 스레드에서 즉시 반영
            self.after(0, self._apply_thumb, token, path, pil)
            return

        def _worker():
            pil_img = self._make_pil_thumb(path, size)
            return pil_img

        fut = self._executor.submit(_worker)
        def _done(_fut):
            try:
                pil_img = _fut.result()
            except Exception:
                pil_img = Image.new("RGB", (size, size), (200, 200, 200))
            # 캐시에 넣고 UI 반영 예약
            self._pil_cache_put(key, pil_img)
            self.after(0, self._apply_thumb, token, path, pil_img)
        fut.add_done_callback(_done)

    def _apply_thumb(self, token: int, path: Path, pil: Image.Image):
        """메인 스레드: PhotoImage 생성 → 해당 타일에 적용(세대 불일치/타일없음은 무시)."""
        if token != self._gen_token:
            return  # 오래된 작업
        tile = self._tiles.get(path)
        if not tile or not tile.winfo_exists():
            return
        # PhotoImage는 메인 스레드에서 생성해야 안전
        tkim = ImageTk.PhotoImage(pil)
        self._imgs[path] = tkim
        # 타일의 첫 Label(image) 찾아 교체
        for w in tile.winfo_children():
            if isinstance(w, tk.Label) and getattr(w, "image", None) is not None:
                w.configure(image=tkim)
                w.image = tkim
                break

    def _make_pil_thumb(self, p: Path, size: int) -> Image.Image:
        try:
            with Image.open(p) as im:
                im.load()
                im.thumbnail((size, size), Image.Resampling.LANCZOS)
                bg = Image.new("RGB", (size, size), (245, 245, 245))
                ox = (size - im.width) // 2
                oy = (size - im.height) // 2
                bg.paste(im, (ox, oy))
                return bg
        except Exception:
            return Image.new("RGB", (size, size), (200, 200, 200))

    def _cache_key(self, p: Path, size: int) -> Tuple[str, int, int]:
        try:
            mt = p.stat().st_mtime_ns
        except Exception:
            mt = 0
        return (str(p), mt, size)

    def _pil_cache_get(self, key) -> Optional[Image.Image]:
        pil = self._pil_cache.get(key)
        if pil is not None:
            # LRU 갱신
            self._pil_cache.move_to_end(key)
        return pil

    def _pil_cache_put(self, key, pil: Image.Image):
        self._pil_cache[key] = pil
        self._pil_cache.move_to_end(key)
        if len(self._pil_cache) > self._pil_cache_limit:
            self._pil_cache.popitem(last=False)

    # ----- 스크롤/휠 -----
    def _on_inner_config(self, _):
        self._update_scroll()

    def _on_canvas_config(self, e):
        self.canvas.itemconfigure(self.win_id, width=e.width)

    def _update_scroll(self):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _enable_wheel_for(self, widget):
        widget.bind("<Enter>", lambda e: self._bind_wheel(), add="+")
        widget.bind("<Leave>", lambda e: self._unbind_wheel(), add="+")
    def _bind_wheel(self):
        self.canvas.bind("<MouseWheel>", self._on_wheel, add="+")
        self.canvas.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-3, "units"), add="+")
        self.canvas.bind("<Button-5>", lambda e: self.canvas.yview_scroll(+3, "units"), add="+")
    def _unbind_wheel(self):
        self.canvas.unbind("<MouseWheel>")
        self.canvas.unbind("<Button-4>")
        self.canvas.unbind("<Button-5>")
    def _on_wheel(self, e):
        delta = e.delta
        if delta == 0:
            return "break"
        step = -1 * int(delta / 120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
        self.canvas.yview_scroll(step, "units")
        return "break"

    # ----- 종료 처리 -----
    def _on_destroy(self, _):
        try:
            self._executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

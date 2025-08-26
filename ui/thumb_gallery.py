# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from typing import Callable, List, Optional, Dict, Set
from PIL import Image, ImageTk, ImageOps
from concurrent.futures import ThreadPoolExecutor, Future

class ThumbGallery(ttk.Frame):
    """썸네일 그리드. 더블클릭으로 활성화 콜백 호출."""
    def __init__(self, master, on_activate: Optional[Callable[[Path], None]] = None,
                 thumb_size: int = 160, cols: int = 5, height: int = 220):
        super().__init__(master)
        self.on_activate = on_activate
        self.thumb_size = int(thumb_size)
        self.cols = int(cols)
        self.fixed_height = int(height)

        self.canvas = tk.Canvas(self, highlightthickness=0, height=self.fixed_height)
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vbar.set)

        self.inner = tk.Frame(self.canvas)
        self.win_id = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vbar.pack(side="right", fill="y")

        # 크기 동기화
        self.inner.bind("<Configure>", self._on_inner_config)
        self.canvas.bind("<Configure>", self._on_canvas_config)

        # 배지 상태
        self._badges: Dict[Path, tk.Canvas] = {}
        self._badge_paths: Set[Path] = set()

        # ✅ 휠: 갤러리 영역에 마우스가 올라오면 전역 바인딩, 벗어나면 해제
        self._wheel_bound = False
        for w in (self, self.canvas, self.inner, self.vbar):
            w.bind("<Enter>", self._bind_all_wheel, add="+")
            w.bind("<Leave>", self._maybe_unbind_all_wheel, add="+")

        self._tiles: Dict[Path, tk.Frame] = {}
        self._imgs: Dict[Path, ImageTk.PhotoImage] = {}
        self._active: Optional[Path] = None

        self._executor = ThreadPoolExecutor(max_workers=3)
        self._futures: Dict[Path, Future] = {}

    # ---------- Public ----------
    def clear(self):
        for f in self._futures.values():
            f.cancel()
        self._futures.clear()

        for w in self.inner.winfo_children():
            w.destroy()
        self._tiles.clear()
        self._imgs.clear()
        self._active = None
        self._badge_paths.clear()
        self._badges.clear()
        self._update_scroll()

    def set_files(self, files: List[Path]):
        self.clear()
        if not files:
            return
        size = self.thumb_size
        pad = 8

        def _make_tile(p: Path, r: int, c: int):
            tile = tk.Frame(self.inner, bd=1, relief="groove")
            tile.grid(row=r, column=c, padx=pad, pady=pad, sticky="nsew")
            # placeholder
            ph = Image.new("RGB", (size, size), (235, 235, 235))
            tkim = ImageTk.PhotoImage(ph)
            lbl_img = tk.Label(tile, image=tkim);
            lbl_img.image = tkim
            lbl_img.pack(padx=4, pady=(4, 0))
            lbl_txt = tk.Label(tile, text=p.name, wraplength=size, justify="center")
            lbl_txt.pack(padx=4, pady=(2, 6))
            self._tiles[p] = tile

            # 더블클릭 핸들러는 미리 바인딩
            def _activate(ev=None, path=p):
                self.set_active(path)
                if callable(self.on_activate): self.on_activate(path)

            for w in (tile, lbl_img, lbl_txt):
                w.bind("<Double-Button-1>", _activate)

        for i, p in enumerate(files):
            r, c = divmod(i, self.cols)
            _make_tile(p, r, c)
            self._futures[p] = self._executor.submit(self._build_thumb_pil, p, size)

        def _drain():
            done = []
            for p, fut in list(self._futures.items()):
                if fut.done():
                    done.append(p)
                    pil_img = fut.result() if not fut.cancelled() else None
                    if pil_img is not None and p in self._tiles:
                        # PhotoImage는 메인스레드에서
                        tkim = ImageTk.PhotoImage(pil_img)
                        self._imgs[p] = tkim
                        # 타일 첫 번째 child가 이미지 라벨
                        lbl_img = self._tiles[p].winfo_children()[0]
                        lbl_img.configure(image=tkim);
                        lbl_img.image = tkim
            for p in done: self._futures.pop(p, None)
            if self._futures:
                self.after(16, _drain)  # 60fps 수준으로 폴링

        _drain()

        for c in range(self.cols):
            self.inner.grid_columnconfigure(c, weight=1)
        self._update_scroll()

    @staticmethod
    def _build_thumb_pil(p: Path, size: int) -> Image.Image:
        from PIL import ImageOps
        try:
            with Image.open(p) as im:
                im = ImageOps.exif_transpose(im)
                im.thumbnail((size, size), Image.Resampling.LANCZOS)
                bg = Image.new("RGB", (size, size), (245, 245, 245))
                ox = (size - im.width) // 2;
                oy = (size - im.height) // 2
                bg.paste(im, (ox, oy))
            return bg
        except Exception:
            return Image.new("RGB", (size, size), (200, 200, 200))

    # ✅ 공개 API: 앵커가 있는 이미지들을 배지로 표시
    def set_badged(self, paths: Set[Path]):
        self._badge_paths = set(paths)
        # 이미 있는 타일 기준으로 표시/제거
        for p, tile in self._tiles.items():
            has = p in self._badge_paths
            exists = p in self._badges
            if has and not exists:
                self._show_badge_for(p)
            elif not has and exists:
                self._hide_badge_for(p)

    # ----- 내부: 배지 그리기/지우기 -----
    def _show_badge_for(self, p: Path):
        tile = self._tiles.get(p)
        if not tile or p in self._badges:
            return
        # 작은 원형 점(초록) 캔버스
        badge = tk.Canvas(tile, width=14, height=14, highlightthickness=0,
                          bd=0, bg=tile.cget("background"))
        badge.place(relx=1.0, x=-6, y=6, anchor="ne")
        badge.create_oval(2, 2, 12, 12, fill="#22c55e", outline="white", width=1)
        self._badges[p] = badge

    def _hide_badge_for(self, p: Path):
        w = self._badges.pop(p, None)
        if w:
            try:
                w.destroy()
            except:
                pass

    def set_active(self, path: Optional[Path]):
        if self._active and self._active in self._tiles:
            self._tiles[self._active].configure(bd=1, relief="groove")
        self._active = path
        if path and path in self._tiles:
            self._tiles[path].configure(bd=2, relief="solid")

    # ---------- Geometry / Scroll ----------
    def _on_inner_config(self, _):
        self._update_scroll()
        # inner 폭을 canvas 폭에 맞춤
        self.canvas.itemconfigure(self.win_id, width=self.canvas.winfo_width())

    def _on_canvas_config(self, e):
        self.canvas.itemconfigure(self.win_id, width=e.width)

    def _update_scroll(self):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    # ---------- Wheel routing (global bind while hovered) ----------
    def _owns(self, w: tk.Widget | None) -> bool:
        """주어진 위젯이 이 갤러리의 자손인지 검사."""
        while w is not None:
            if w is self:
                return True
            w = w.master
        return False

    def _bind_all_wheel(self, _=None):
        if self._wheel_bound:
            return
        self._wheel_bound = True
        # Windows / macOS
        self.canvas.bind_all("<MouseWheel>", self._on_wheel, add="+")
        # Linux
        self.canvas.bind_all("<Button-4>", self._on_btn4, add="+")
        self.canvas.bind_all("<Button-5>", self._on_btn5, add="+")

    def _maybe_unbind_all_wheel(self, _=None):
        # 자식으로 이동해도 Leave가 오므로, 포인터가 진짜로 갤러리 밖인지 확인
        self.after(10, self._check_pointer_out)

    def _check_pointer_out(self):
        x, y = self.winfo_pointerxy()
        w = self.winfo_containing(x, y)
        if not self._owns(w):
            self._unbind_all_wheel()

    def _unbind_all_wheel(self):
        if not self._wheel_bound:
            return
        try:
            self.canvas.unbind_all("<MouseWheel>")
            self.canvas.unbind_all("<Button-4>")
            self.canvas.unbind_all("<Button-5>")
        finally:
            self._wheel_bound = False

    def _on_wheel(self, e):
        # 현재 포인터가 갤러리 영역 위인지 확인 (다른 영역이면 무시)
        x, y = self.winfo_pointerxy()
        if not self._owns(self.winfo_containing(x, y)):
            return
        # delta 방향만 사용
        step = -1 if e.delta > 0 else +1
        self.canvas.yview_scroll(step, "units")
        return "break"

    def _on_btn4(self, e):
        x, y = self.winfo_pointerxy()
        if self._owns(self.winfo_containing(x, y)):
            self.canvas.yview_scroll(-3, "units")
            return "break"

    def _on_btn5(self, e):
        x, y = self.winfo_pointerxy()
        if self._owns(self.winfo_containing(x, y)):
            self.canvas.yview_scroll(+3, "units")
            return "break"

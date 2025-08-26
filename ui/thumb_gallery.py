# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from typing import Callable, List, Optional, Dict, Tuple
from PIL import Image, ImageTk, ImageDraw, ImageFont

def _draw_anchor_marker(square_img: Image.Image, content_box: Tuple[int,int,int,int],
                        anchor: Tuple[float,float], color=(30,144,255), radius=6):
    """정사각형 썸네일 이미지(square_img) 위에 '콘텐츠 내' 정규 앵커 위치에 점 표시.
       content_box: (x0,y0,x1,y1) — 실제 이미지가 그려진 영역(패딩 제외)
       anchor: (nx, ny) 0..1
    """
    x0, y0, x1, y1 = content_box
    iw, ih = max(1, x1 - x0), max(1, y1 - y0)
    nx = min(1.0, max(0.0, float(anchor[0])))
    ny = min(1.0, max(0.0, float(anchor[1])))
    cx = int(x0 + nx * iw)
    cy = int(y0 + ny * ih)
    d = ImageDraw.Draw(square_img, "RGBA")
    # 테두리 흰색 + 내부 파랑
    r = max(2, int(radius))
    d.ellipse((cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1), fill=(255, 255, 255, 230))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(*color, 230))

def _draw_badge(square_img: Image.Image, text="•", bg=(76,175,80), fg=(255,255,255)):
    """우상단에 작은 배지(개별 앵커가 있음을 표시)."""
    W, H = square_img.size
    r = 9
    cx, cy = W - r - 6, r + 6
    d = ImageDraw.Draw(square_img, "RGBA")
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(*bg, 255))
    # 글자
    try:
        font = ImageFont.truetype("arial.ttf", 12)
    except Exception:
        font = ImageFont.load_default()
    tw, th = d.textsize(text, font=font)
    d.text((cx - tw // 2, cy - th // 2 - 1), text, font=font, fill=fg)

class ThumbGallery(ttk.Frame):
    """썸네일 그리드. 더블클릭으로 활성화 콜백 호출 + 앵커 오버레이/배지."""
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

        self.inner.bind("<Configure>", self._on_inner_config)
        self.canvas.bind("<Configure>", self._on_canvas_config)

        # 휠 스크롤: bind_all(+포인터 가드)
        self._activate_wheel_on_hover(self)

        self._tiles: Dict[Path, tk.Frame] = {}
        self._imgs: Dict[Path, ImageTk.PhotoImage] = {}
        self._active: Optional[Path] = None

        # 앵커 오버레이 상태
        self._default_anchor: Tuple[float, float] = (0.5, 0.5)
        self._img_anchor_map: Dict[Path, Tuple[float, float]] = {}

    # --- public API ---
    def clear(self):
        for w in self.inner.winfo_children():
            w.destroy()
        self._tiles.clear()
        self._imgs.clear()
        self._active = None
        self._update_scroll()

    def set_files(self, files: List[Path],
                  default_anchor: Tuple[float, float] = (0.5, 0.5),
                  img_anchor_map: Optional[Dict[Path, Tuple[float, float]]] = None):
        self.clear()
        self._default_anchor = tuple(default_anchor)
        self._img_anchor_map = dict(img_anchor_map or {})

        if not files:
            return
        size = self.thumb_size
        pad = 8
        for i, p in enumerate(files):
            r, c = divmod(i, self.cols)
            tile = tk.Frame(self.inner, bd=1, relief="groove")
            tile.grid(row=r, column=c, padx=pad, pady=pad, sticky="nsew")

            # 썸네일 만들기 (정사각형 캔버스 안에 contain) + 앵커 오버레이
            tkim = self._make_thumb_with_overlay(p, size)
            lbl_img = tk.Label(tile, image=tkim)
            lbl_img.image = tkim  # 강참조
            self._imgs[p] = tkim
            lbl_img.pack(padx=4, pady=(4, 0))

            lbl_txt = tk.Label(tile, text=p.name, wraplength=size, justify="center")
            lbl_txt.pack(padx=4, pady=(2, 6))

            # 더블클릭 활성화
            def _activate(ev=None, path=p):
                self.set_active(path)
                if callable(self.on_activate):
                    self.on_activate(path)
            tile.bind("<Double-Button-1>", _activate)
            lbl_img.bind("<Double-Button-1>", _activate)
            lbl_txt.bind("<Double-Button-1>", _activate)

            self._tiles[p] = tile

        # 그리드 확장성
        for c in range(self.cols):
            self.inner.grid_columnconfigure(c, weight=1)
        self._update_scroll()

    def set_active(self, path: Optional[Path]):
        # 기존 강조 해제
        if self._active and self._active in self._tiles:
            self._tiles[self._active].configure(bd=1, relief="groove")
        self._active = path
        if path and path in self._tiles:
            self._tiles[path].configure(bd=2, relief="solid")

    def set_badged(self, paths: set[Path]):
        """(옵션) 별도 배지 제어용 — 현재는 개별 앵커가 있으면 자동 배지이므로 사용 안 해도 됨."""
        pass

    def update_anchor_overlay(self, default_anchor: Tuple[float, float],
                              img_anchor_map: Dict[Path, Tuple[float, float]]):
        """기본/개별 앵커 변경 시 썸네일 전량 오버레이 갱신."""
        self._default_anchor = tuple(default_anchor)
        self._img_anchor_map = dict(img_anchor_map or {})
        for p, tile in self._tiles.items():
            if p in self._imgs:
                self._imgs[p] = self._make_thumb_with_overlay(p, self.thumb_size)
                # 이미지 교체
                for w in tile.winfo_children():
                    if isinstance(w, tk.Label) and getattr(w, "image", None) is not None:
                        w.configure(image=self._imgs[p])
                        w.image = self._imgs[p]  # 강참조 유지
                        break

    # --- internal: rendering ---
    def _make_thumb_with_overlay(self, path: Path, size: int) -> ImageTk.PhotoImage:
        # 기본 썸네일
        try:
            im = Image.open(path)
            im.thumbnail((size, size), Image.Resampling.LANCZOS)
            bg = Image.new("RGBA", (size, size), (245, 245, 245, 255))
            ox = (size - im.width) // 2
            oy = (size - im.height) // 2
            bg.paste(im, (ox, oy))
            content_box = (ox, oy, ox + im.width, oy + im.height)
        except Exception:
            bg = Image.new("RGBA", (size, size), (200, 200, 200, 255))
            content_box = (4, 4, size - 4, size - 4)

        # 앵커(개별 > 기본)
        anchor = self._img_anchor_map.get(path, self._default_anchor)
        _draw_anchor_marker(bg, content_box, anchor, color=(30, 144, 255), radius=6)

        # 배지: 개별 앵커 가진 경우
        if path in self._img_anchor_map:
            _draw_badge(bg, text="•", bg=(76, 175, 80), fg=(255, 255, 255))

        return ImageTk.PhotoImage(bg.convert("RGB"))

    # --- scroll helpers ---
    def _on_inner_config(self, _):
        self._update_scroll()

    def _on_canvas_config(self, e):
        self.canvas.itemconfigure(self.win_id, width=e.width)

    def _update_scroll(self):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    # --- wheel helpers (bind_all + 포인터 가드) ---
    def _activate_wheel_on_hover(self, widget):
        widget.bind("<Enter>", self._bind_all_wheel, add="+")
        widget.bind("<Leave>", self._unbind_all_wheel, add="+")
        self.inner.bind("<Enter>", self._bind_all_wheel, add="+")
        self.inner.bind("<Leave>", self._unbind_all_wheel, add="+")
        self.canvas.bind("<Enter>", self._bind_all_wheel, add="+")
        self.canvas.bind("<Leave>", self._unbind_all_wheel, add="+")

    def _bind_all_wheel(self, _=None):
        self.bind_all("<MouseWheel>", self._on_wheel, add="+")
        self.bind_all("<Button-4>", self._on_btn4, add="+")
        self.bind_all("<Button-5>", self._on_btn5, add="+")

    def _unbind_all_wheel(self, _=None):
        # 전역 바인딩 해제는 다른 위젯에 영향 → 생략(포인터 가드로 충돌 방지)
        pass

    def _pointer_inside_me(self, e) -> bool:
        try:
            w = self.winfo_containing(e.x_root, e.y_root)
            while w is not None:
                if w is self:
                    return True
                w = w.master
        except Exception:
            pass
        return False

    def _on_wheel(self, e):
        if not self._pointer_inside_me(e):
            return
        delta = e.delta
        step = -1 if delta > 0 else 1
        if abs(delta) >= 120:
            step *= int(abs(delta) / 120)
        self.canvas.yview_scroll(step, "units")
        return "break"

    def _on_btn4(self, e):
        if not self._pointer_inside_me(e):
            return
        self.canvas.yview_scroll(-3, "units")
        return "break"

    def _on_btn5(self, e):
        if not self._pointer_inside_me(e):
            return
        self.canvas.yview_scroll(+3, "units")
        return "break"

# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
from typing import Callable, Tuple

class _CheckerCanvas(tk.Canvas):
    """체크보드 배경 + 중앙 정렬 이미지 + 오버레이(그리드/마커)."""
    def __init__(self, master, tile=12, c1="#E6E6E6", c2="#C8C8C8", **kw):
        super().__init__(master, highlightthickness=0, background="white", **kw)
        self.tile = tile; self.c1, self.c2 = c1, c2
        self._pil_img: Image.Image | None = None
        self._tk_img: ImageTk.PhotoImage | None = None
        self._img_id = None
        self._last = {"w":1,"h":1,"x0":0,"y0":0,"iw":1,"ih":1}  # canvas W/H, image bbox x0/y0/iw/ih
        self._grid_visible = False
        self._marker_norm: Tuple[float,float] | None = None
        self.bind("<Configure>", self._on_resize)

    # --- public ---
    def set_image(self, pil_img: Image.Image | None):
        self._pil_img = pil_img
        self._render()

    def set_grid_visible(self, visible: bool):
        self._grid_visible = visible
        self._render_grid()

    def set_marker_norm(self, norm: Tuple[float,float] | None):
        self._marker_norm = norm
        self._render_marker()

    def event_to_norm(self, ex: int, ey: int) -> Tuple[float,float] | None:
        """캔버스 좌표 -> 이미지 기준 정규화(0..1). 이미지 밖이면 가장자리로 클램프."""
        x0, y0, iw, ih = self._last["x0"], self._last["y0"], self._last["iw"], self._last["ih"]
        if iw <= 1 or ih <= 1:
            return None
        x = min(max(ex, x0), x0 + iw)
        y = min(max(ey, y0), y0 + ih)
        nx = (x - x0) / iw
        ny = (y - y0) / ih
        nx = min(1.0, max(0.0, nx))
        ny = min(1.0, max(0.0, ny))
        return (nx, ny)

    # --- internal render ---
    def _on_resize(self, _):
        self._render()

    def _draw_checker(self, w: int, h: int):
        self.delete("checker")
        t = self.tile
        cols = (w + t - 1) // t; rows = (h + t - 1) // t
        for r in range(rows):
            for c in range(cols):
                x0 = c * t; y0 = r * t
                x1 = min(x0 + t, w); y1 = min(y0 + t, h)
                color = self.c1 if (r + c) % 2 == 0 else self.c2
                self.create_rectangle(x0, y0, x1, y1, fill=color, width=0, tags="checker")

    def _render(self):
        w = max(1, self.winfo_width()); h = max(1, self.winfo_height())
        self._draw_checker(w, h)
        if self._pil_img is None:
            self.delete("content"); self.delete("grid"); self.delete("marker")
            self._last.update({"w":w,"h":h,"x0":0,"y0":0,"iw":1,"ih":1})
            return

        W, H = self._pil_img.size
        scale = min(w / W, h / H, 1.0)
        iw, ih = max(1,int(W*scale)), max(1,int(H*scale))
        x0, y0 = (w - iw)//2, (h - ih)//2

        disp = self._pil_img.resize((iw, ih), Image.Resampling.LANCZOS)
        self._tk_img = ImageTk.PhotoImage(disp)
        if self._img_id is None:
            self._img_id = self.create_image(w//2, h//2, image=self._tk_img, anchor="center", tags="content")
        else:
            self.itemconfigure(self._img_id, image=self._tk_img)
            self.coords(self._img_id, w//2, h//2)

        self._last.update({"w":w,"h":h,"x0":x0,"y0":y0,"iw":iw,"ih":ih})
        self._render_grid()
        self._render_marker()

    def _render_grid(self):
        self.delete("grid")
        if not self._grid_visible: return
        x0, y0, iw, ih = self._last["x0"], self._last["y0"], self._last["iw"], self._last["ih"]
        # 수직 2개, 수평 2개
        for i in (1,2):
            x = x0 + int(i * iw / 3)
            self.create_line(x, y0, x, y0+ih, fill="#000000", width=1, stipple="gray50", tags="grid")
        for i in (1,2):
            y = y0 + int(i * ih / 3)
            self.create_line(x0, y, x0+iw, y, fill="#000000", width=1, stipple="gray50", tags="grid")

    def _render_marker(self):
        self.delete("marker")
        if not self._marker_norm:
            return
        x0, y0, iw, ih = self._last["x0"], self._last["y0"], self._last["iw"], self._last["ih"]
        nx, ny = self._marker_norm
        cx = x0 + nx * iw; cy = y0 + ny * ih
        # 십자 + 원
        self.create_line(cx-10, cy, cx+10, cy, fill="#000000", width=2, tags="marker")
        self.create_line(cx, cy-10, cx, cy+10, fill="#000000", width=2, tags="marker")
        self.create_oval(cx-6, cy-6, cx+6, cy+6, outline="#FFFFFF", width=2, tags="marker")
        self.tag_raise("marker")
        self.tag_raise("grid")

class PreviewPane(ttk.Frame):
    """Before/After + Swap + (그리드/드래그) 위치 지정."""
    def __init__(self, master, on_anchor_change: Callable[[Tuple[float,float]], None] | None = None):
        super().__init__(master)
        self._on_anchor_change = on_anchor_change
        self._placement_mode = tk.StringVar(value="grid")  # "grid" | "drag"

        # 상단 툴바
        top = ttk.Frame(self); top.pack(fill="x", pady=(2, 0))
        self.lbl_before_cap = ttk.Label(top, text="Before", font=("", 10, "bold"))
        self.lbl_after_cap = ttk.Label(top, text="After", font=("", 10, "bold"))
        self.btn_swap = ttk.Button(top, text="Swap ◀▶", command=self._on_swap)
        self.lbl_before_cap.pack(side="left", padx=4)
        self.btn_swap.pack(side="left", padx=8)
        self.lbl_after_cap.pack(side="left", padx=4)

        # 배치 모드 선택
        ttk.Label(top, text="Placement:").pack(side="left", padx=(16,2))
        ttk.Radiobutton(top, text="3×3 Grid", variable=self._placement_mode, value="grid", command=self._on_mode_change).pack(side="left")
        ttk.Radiobutton(top, text="Drag", variable=self._placement_mode, value="drag", command=self._on_mode_change).pack(side="left", padx=(4,0))

        # 본문
        grid = ttk.Frame(self); grid.pack(fill="both", expand=True, pady=4)
        self.box_before = tk.Frame(grid, bd=1, relief="solid")
        self.box_after  = tk.Frame(grid, bd=2, relief="solid")
        self.box_before.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.box_after.grid(row=0, column=1, sticky="nsew", padx=4, pady=4)

        self.canvas_before = _CheckerCanvas(self.box_before)
        self.canvas_after  = _CheckerCanvas(self.box_after)
        self.canvas_before.pack(fill="both", expand=True)
        self.canvas_after.pack(fill="both", expand=True)

        grid.columnconfigure(0, weight=1); grid.columnconfigure(1, weight=1); grid.rowconfigure(0, weight=1)

        self._pil_before: Image.Image | None = None
        self._pil_after: Image.Image | None = None
        self._swapped = False
        self._anchor_norm: Tuple[float,float] = (0.5, 0.5)
        self._dragging = False

        # 이벤트: 두 캔버스 모두 바인딩(활성 캔버스만 처리)
        for cv in (self.canvas_before, self.canvas_after):
            cv.bind("<Button-1>", self._on_click)
            cv.bind("<B1-Motion>", self._on_drag)
            cv.bind("<ButtonRelease-1>", self._on_release)

        # 초기 모드 설정(그리드 표시)
        self._apply_grid_visibility()

    # ---- 외부 API ----
    def show(self, before_img: Image.Image, after_img: Image.Image):
        self._pil_before = before_img
        self._pil_after = after_img
        left, right = (self._pil_after, self._pil_before) if self._swapped else (self._pil_before, self._pil_after)
        self.canvas_before.set_image(left)
        self.canvas_after.set_image(right)
        # 마커 다시 그림(After가 보이는 캔버스에)
        self._update_marker()

    def clear(self):
        self._pil_before = None; self._pil_after = None; self._swapped = False; self._dragging = False
        self.canvas_before.set_image(None); self.canvas_after.set_image(None)
        self.canvas_before.set_marker_norm(None); self.canvas_after.set_marker_norm(None)
        self.lbl_before_cap.configure(text="Before"); self.lbl_after_cap.configure(text="After")

    def set_anchor(self, norm: Tuple[float,float]):
        self._anchor_norm = (float(norm[0]), float(norm[1]))
        self._update_marker()

    # ---- 내부 ----
    def _get_active_canvas(self) -> _CheckerCanvas:
        # 현재 After가 보이는 캔버스
        return self.canvas_before if self._swapped else self.canvas_after

    def _update_marker(self):
        # After 캔버스에만 마커 표시
        act = self._get_active_canvas()
        oth = self.canvas_after if act is self.canvas_before else self.canvas_before
        act.set_marker_norm(self._anchor_norm)
        oth.set_marker_norm(None)
        self._apply_grid_visibility()

    def _on_swap(self):
        self._swapped = not self._swapped
        # 캡션 갱신
        if self._swapped:
            self.lbl_before_cap.configure(text="After (swapped)")
            self.lbl_after_cap.configure(text="Before (swapped)")
        else:
            self.lbl_before_cap.configure(text="Before")
            self.lbl_after_cap.configure(text="After")
        # 이미지/마커 재렌더
        if self._pil_before and self._pil_after:
            self.show(self._pil_before, self._pil_after)

    def _on_mode_change(self):
        self._apply_grid_visibility()

    def _apply_grid_visibility(self):
        show_grid = (self._placement_mode.get() == "grid")
        # After가 보이는 캔버스에만 그리드
        self._get_active_canvas().set_grid_visible(show_grid)
        # 반대쪽은 감춤
        (self.canvas_after if self._get_active_canvas() is self.canvas_before else self.canvas_before).set_grid_visible(False)

    def _on_click(self, e):
        # 활성 캔버스만 처리
        if e.widget is not self._get_active_canvas():
            return
        if self._placement_mode.get() == "grid":
            # 클릭한 칸의 중앙
            cv = self._get_active_canvas()
            norm = cv.event_to_norm(e.x, e.y)
            if not norm: return
            nx, ny = norm
            # 3x3 스냅
            cx = (int(nx * 3) + 0.5) / 3.0
            cy = (int(ny * 3) + 0.5) / 3.0
            self._commit_anchor((cx, cy))
        else:
            # 드래그 시작
            self._dragging = True
            self._on_drag(e)

    def _on_drag(self, e):
        if not self._dragging and self._placement_mode.get() != "drag":
            return
        if e.widget is not self._get_active_canvas():
            return
        cv = self._get_active_canvas()
        norm = cv.event_to_norm(e.x, e.y)
        if not norm: return
        # 드래그 중 마커만 즉시 갱신(렌더 비용 최소)
        self._anchor_norm = norm
        self._update_marker()

    def _on_release(self, e):
        if self._dragging and self._placement_mode.get() == "drag":
            self._dragging = False
            # 드래그 종료 시 커밋
            self._commit_anchor(self._anchor_norm)

    def _commit_anchor(self, norm: Tuple[float,float]):
        self._anchor_norm = (float(norm[0]), float(norm[1]))
        self._update_marker()
        # 콜백으로 부모(MainWindow)에게 알리고, 그쪽에서 미리보기 재렌더
        if self._on_anchor_change:
            self._on_anchor_change(self._anchor_norm)

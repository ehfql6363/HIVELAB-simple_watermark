# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from collections import deque
from PIL import Image, ImageTk, ImageDraw, ImageFont
from typing import Callable, Tuple, Optional, Dict

# ---- 폰트 헬퍼(미리보기 전용, services/watermark와 동일 아이디어) ----
_DEFAULT_FONTS = [
    "arial.ttf", "tahoma.ttf", "segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

def _pick_font(size: int):
    for cand in _DEFAULT_FONTS:
        try:
            return ImageFont.truetype(cand, size=size)
        except Exception:
            pass
    return ImageFont.load_default()

def _measure_text(font, text, stroke_width=0):
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    bbox = d.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]

def _fit_font_by_width(text: str, target_w: int, low=8, high=512, stroke_width=2):
    best = low
    while low <= high:
        mid = (low + high) // 2
        w, _ = _measure_text(_pick_font(mid), text, stroke_width=stroke_width)
        if w <= target_w:
            best = mid; low = mid + 1
        else:
            high = mid - 1
    return best


class _CheckerCanvas(tk.Canvas):
    """체크보드 + 이미지 + 오버레이(그리드/셀하이라이트/유령 워터마크).
    - after_idle로 배경/이미지 렌더
    - 드래그/그리드 선택은 오버레이만 변경(초경량)
    - PhotoImage 강참조 유지
    """
    def __init__(self, master, tile=12, c1="#E6E6E6", c2="#C8C8C8", **kw):
        super().__init__(master, highlightthickness=0, background="white", **kw)
        self.tile = tile; self.c1, self.c2 = c1, c2
        self._pil_img: Image.Image | None = None
        self._img_id: int | None = None
        self._img_refs = deque(maxlen=4)  # 본문 이미지 강참조

        # 레이아웃(캔버스/이미지 박스)
        self._last = {"w":1,"h":1,"x0":0,"y0":0,"iw":1,"ih":1}

        # 오버레이 상태
        self._grid_visible = False
        self._grid_sel: Optional[Tuple[int,int]] = None
        self._marker_norm: Optional[Tuple[float,float]] = None

        # 오버레이 item ids
        self._grid_line_ids: list[int] = []
        self._cell_sel_id: Optional[int] = None
        self._wmghost_id: Optional[int] = None

        # 워터마크 유령 스프라이트 캐시
        self._wm_cfg: Optional[Dict] = None
        self._wm_sprite_key: Optional[Tuple] = None
        self._wm_sprite_tk: Optional[ImageTk.PhotoImage] = None
        self._wm_sprite_refs = deque(maxlen=2)  # 유령 스프라이트 강참조

        # 렌더 큐
        self._pending = False
        self.bind("<Configure>", self._on_resize)

    # ---------- Public API ----------
    def set_image(self, pil_img: Image.Image | None):
        self._pil_img = pil_img
        self._queue_render()

    def set_grid_visible(self, visible: bool):
        self._grid_visible = visible
        self._draw_grid_overlay(); self._draw_cell_highlight()
        # 그리드 모드에선 유령 숨김(헷갈리지 않도록)
        if visible:
            self._clear_wmghost()

    def select_grid_cell(self, ix_iy: Optional[Tuple[int,int]]):
        self._grid_sel = ix_iy
        self._draw_cell_highlight()

    def set_marker_norm(self, norm: Optional[Tuple[float,float]]):
        # 드래그 모드에서만 호출됨(PreviewPane이 제어). 유령 워터마크를 옮긴다.
        self._marker_norm = norm
        self._draw_wmghost()

    def set_wm_config(self, cfg: Optional[Dict]):
        """cfg keys: text, opacity(int0-100), scale_pct(int), fill(tuple RGB), stroke(tuple RGB), stroke_w(int)"""
        self._wm_cfg = cfg
        # 설정 바뀌면 스프라이트 재생성 필요 → 다음 풀렌더에서 맞춰 생성
        self._wm_sprite_key = None
        self._queue_render()

    def event_to_norm(self, ex: int, ey: int) -> Optional[Tuple[float,float]]:
        x0, y0, iw, ih = self._last["x0"], self._last["y0"], self._last["iw"], self._last["ih"]
        if iw <= 1 or ih <= 1: return None
        x = min(max(ex, x0), x0 + iw); y = min(max(ey, y0), y0 + ih)
        nx = (x - x0) / iw; ny = (y - y0) / ih
        return (min(1.0, max(0.0, nx)), min(1.0, max(0.0, ny)))

    # ---------- Internal ----------
    def _queue_render(self):
        if not self._pending:
            self._pending = True
            self.after_idle(self._render_full)

    def _on_resize(self, _):
        self._queue_render()

    # ---- 풀 렌더 ----
    def _render_full(self):
        self._pending = False
        w = max(1, self.winfo_width()); h = max(1, self.winfo_height())
        if w < 4 or h < 4:
            self.after(16, self._render_full); return

        # 체크보드
        self.delete("checker")
        t = self.tile
        cols = (w + t - 1) // t; rows = (h + t - 1) // t
        for r in range(rows):
            for c in range(cols):
                x0 = c * t; y0 = r * t
                x1 = min(x0 + t, w); y1 = min(y0 + t, h)
                color = self.c1 if (r + c) % 2 == 0 else self.c2
                self.create_rectangle(x0, y0, x1, y1, fill=color, width=0, tags="checker")
        self.tag_lower("checker")

        # 이미지
        if self._pil_img is None:
            self.delete("content"); self._img_id = None
            self._last.update({"w":w,"h":h,"x0":0,"y0":0,"iw":1,"ih":1})
            self._clear_overlay()
            return

        W, H = self._pil_img.size
        scale = min(w / W, h / H, 1.0)
        iw, ih = max(1, int(W*scale)), max(1, int(H*scale))
        x0, y0 = (w - iw)//2, (h - ih)//2

        disp = self._pil_img.resize((iw, ih), Image.Resampling.LANCZOS)
        tkimg = ImageTk.PhotoImage(disp)
        self._img_refs.append(tkimg)

        if self._img_id is None:
            self._img_id = self.create_image(x0, y0, image=tkimg, anchor="nw", tags="content")
        else:
            self.itemconfigure(self._img_id, image=tkimg)
            self.coords(self._img_id, x0, y0)

        self.tag_lower("checker"); self.tag_raise("content")

        # 기하 저장
        self._last.update({"w":w,"h":h,"x0":x0,"y0":y0,"iw":iw,"ih":ih})

        # 유령 스프라이트 준비(이미지 크기가 바뀌었으면 다시 만든다)
        self._ensure_wm_sprite()

        # 오버레이(그리드/셀/유령) 갱신
        self._draw_grid_overlay(); self._draw_cell_highlight(); self._draw_wmghost()

    def _clear_overlay(self):
        for tag in ("grid", "cellsel", "wmghost"):
            self.delete(tag)
        self._grid_line_ids.clear()
        self._cell_sel_id = None
        self._wmghost_id = None

    # ---- Grid/Cell overlay ----
    def _draw_grid_overlay(self):
        self.delete("grid")
        self._grid_line_ids.clear()
        if not self._grid_visible: return
        x0, y0, iw, ih = self._last["x0"], self._last["y0"], self._last["iw"], self._last["ih"]
        if iw <= 1 or ih <= 1: return
        for i in (1,2):
            x = x0 + int(i * iw / 3)
            self._grid_line_ids.append(self.create_line(x, y0, x, y0+ih, fill="#000000", width=1, stipple="gray50", tags="grid"))
        for i in (1,2):
            y = y0 + int(i * ih / 3)
            self._grid_line_ids.append(self.create_line(x0, y, x0+iw, y, fill="#000000", width=1, stipple="gray50", tags="grid"))
        self.tag_raise("grid")

    def _draw_cell_highlight(self):
        self.delete("cellsel"); self._cell_sel_id = None
        if self._grid_sel is None or not self._grid_visible: return
        x0, y0, iw, ih = self._last["x0"], self._last["y0"], self._last["iw"], self._last["ih"]
        if iw <= 1 or ih <= 1: return
        ix, iy = self._grid_sel
        ix = min(2, max(0, int(ix))); iy = min(2, max(0, int(iy)))
        cw = iw / 3.0; ch = ih / 3.0
        rx0 = int(x0 + ix * cw); ry0 = int(y0 + iy * ch)
        rx1 = int(x0 + (ix + 1) * cw); ry1 = int(y0 + (iy + 1) * ch)
        self._cell_sel_id = self.create_rectangle(
            rx0, ry0, rx1, ry1,
            fill="#66CCFF", outline="#1E90FF", width=1,
            stipple="gray25", tags="cellsel"
        )
        self.tag_raise("cellsel"); self.tag_raise("grid")

    # ---- Ghost watermark ----
    def _ensure_wm_sprite(self):
        """캔버스 내 'After 이미지'의 짧은 변 기준으로 scale_pct에 맞춘 텍스트 스프라이트를 생성/캐시."""
        if not self._wm_cfg:
            self._wm_sprite_key = None
            self._wm_sprite_tk = None
            self._clear_wmghost()
            return

        x0, y0, iw, ih = self._last["x0"], self._last["y0"], self._last["iw"], self._last["ih"]
        if iw <= 1 or ih <= 1:
            return

        txt = self._wm_cfg.get("text", "") or ""
        op = int(self._wm_cfg.get("opacity", 30))
        scale_pct = int(self._wm_cfg.get("scale_pct", 5))
        fill = tuple(self._wm_cfg.get("fill", (0,0,0)))
        stroke = tuple(self._wm_cfg.get("stroke", (255,255,255)))
        sw = int(self._wm_cfg.get("stroke_w", 2))

        target_w = max(1, int(min(iw, ih) * (scale_pct / 100.0)))
        key = (txt, op, scale_pct, fill, stroke, sw, target_w)

        if key == self._wm_sprite_key and self._wm_sprite_tk is not None:
            return  # 캐시 재사용

        # 새 스프라이트 생성
        font = _pick_font(_fit_font_by_width(txt, target_w, stroke_width=sw))
        tw, th = _measure_text(font, txt, stroke_width=sw)
        alpha = int(255 * (op / 100.0))
        fill_rgba = (fill[0], fill[1], fill[2], alpha)
        stroke_rgba = (stroke[0], stroke[1], stroke[2], alpha)

        over = Image.new("RGBA", (tw, th), (0,0,0,0))
        d = ImageDraw.Draw(over)
        d.text((0, 0), txt, font=font, fill=fill_rgba, stroke_width=max(0, sw), stroke_fill=stroke_rgba)

        tkimg = ImageTk.PhotoImage(over)
        self._wm_sprite_tk = tkimg
        self._wm_sprite_refs.append(tkimg)  # 강참조
        self._wm_sprite_key = key

        # 기존 유령은 새 스프라이트로 교체
        if self._wmghost_id is not None:
            self.itemconfigure(self._wmghost_id, image=self._wm_sprite_tk)

    def _draw_wmghost(self):
        """드래그 모드에서 마우스 위치(정규화)에 유령 워터마크를 표시/이동."""
        # 그리드 모드거나 설정/스프라이트 없음 → 숨김
        if self._grid_visible or not self._wm_cfg or not self._wm_sprite_tk or self._marker_norm is None:
            self._clear_wmghost()
            return

        x0, y0, iw, ih = self._last["x0"], self._last["y0"], self._last["iw"], self._last["ih"]
        if iw <= 1 or ih <= 1:
            self._clear_wmghost(); return

        nx = min(1.0, max(0.0, float(self._marker_norm[0])))
        ny = min(1.0, max(0.0, float(self._marker_norm[1])))
        cx = x0 + nx * iw; cy = y0 + ny * ih

        if self._wmghost_id is None:
            self._wmghost_id = self.create_image(cx, cy, image=self._wm_sprite_tk, anchor="center", tags="wmghost")
        else:
            self.coords(self._wmghost_id, cx, cy)

        self.tag_raise("wmghost")  # 이미지 위로

    def _clear_wmghost(self):
        if self._wmghost_id is not None:
            self.delete(self._wmghost_id)
            self._wmghost_id = None


class PreviewPane(ttk.Frame):
    """Before/After + Swap + (그리드/드래그) 위치 지정 + 드래그 유령 워터마크."""
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

        ttk.Label(top, text="Placement:").pack(side="left", padx=(16,2))
        ttk.Radiobutton(top, text="3×3 Grid", variable=self._placement_mode, value="grid", command=self._on_mode_change).pack(side="left")
        ttk.Radiobutton(top, text="Drag", variable=self._placement_mode, value="drag", command=self._on_mode_change).pack(side="left", padx=(4,0))

        # 본문
        container = ttk.Frame(self); container.pack(fill="both", expand=True, pady=4)
        self.box_before = tk.Frame(container, bd=1, relief="solid")
        self.box_after  = tk.Frame(container, bd=2, relief="solid")
        self.box_before.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.box_after.grid(row=0, column=1, sticky="nsew", padx=4, pady=4)

        self.canvas_before = _CheckerCanvas(self.box_before)
        self.canvas_after  = _CheckerCanvas(self.box_after)
        self.canvas_before.pack(fill="both", expand=True)
        self.canvas_after.pack(fill="both", expand=True)

        container.columnconfigure(0, weight=1); container.columnconfigure(1, weight=1); container.rowconfigure(0, weight=1)

        self._pil_before: Image.Image | None = None
        self._pil_after: Image.Image | None = None
        self._swapped = False
        self._anchor_norm: Tuple[float,float] = (0.5, 0.5)
        self._dragging = False

        for cv in (self.canvas_before, self.canvas_after):
            cv.bind("<Button-1>", self._on_click)
            cv.bind("<B1-Motion>", self._on_drag)
            cv.bind("<ButtonRelease-1>", self._on_release)

        self._apply_grid_and_visuals()

    # ---- 외부 API ----
    def set_wm_preview_config(self, cfg: Optional[Dict]):
        """After 이미지 기준 유령 워터마크용 설정 전달."""
        # 두 캔버스 모두 같은 설정을 갖지만, 실제로는 After가 보이는 쪽만 사용
        self.canvas_before.set_wm_config(cfg)
        self.canvas_after.set_wm_config(cfg)

    def show(self, before_img: Image.Image, after_img: Image.Image):
        self._pil_before = before_img
        self._pil_after = after_img
        left, right = (self._pil_after, self._pil_before) if self._swapped else (self._pil_before, self._pil_after)
        self.canvas_before.set_image(left)
        self.canvas_after.set_image(right)
        self._refresh_visuals()

    def clear(self):
        self._pil_before = None; self._pil_after = None; self._swapped = False; self._dragging = False
        self.canvas_before.set_image(None); self.canvas_after.set_image(None)
        self.canvas_before.select_grid_cell(None); self.canvas_after.select_grid_cell(None)
        self.canvas_before.set_marker_norm(None); self.canvas_after.set_marker_norm(None)
        self.lbl_before_cap.configure(text="Before"); self.lbl_after_cap.configure(text="After")

    def set_anchor(self, norm: Tuple[float,float]):
        self._anchor_norm = (float(norm[0]), float(norm[1]))
        self._refresh_visuals()

    # ---- 내부 도우미 ----
    def _get_active_canvas(self) -> _CheckerCanvas:
        return self.canvas_before if self._swapped else self.canvas_after  # 현재 After가 보이는 캔버스

    def _refresh_visuals(self):
        act = self._get_active_canvas()
        oth = self.canvas_after if act is self.canvas_before else self.canvas_before

        if self._placement_mode.get() == "grid":
            ix = min(2, max(0, int(self._anchor_norm[0] * 3)))
            iy = min(2, max(0, int(self._anchor_norm[1] * 3)))
            act.select_grid_cell((ix, iy))
            act.set_marker_norm(None)          # 유령 숨김
            oth.select_grid_cell(None); oth.set_marker_norm(None)
        else:
            act.select_grid_cell(None)
            act.set_marker_norm(self._anchor_norm)  # 유령 표시
            oth.select_grid_cell(None); oth.set_marker_norm(None)

        self._apply_grid_and_visuals()

    def _apply_grid_and_visuals(self):
        show_grid = (self._placement_mode.get() == "grid")
        self._get_active_canvas().set_grid_visible(show_grid)
        (self.canvas_after if self._get_active_canvas() is self.canvas_before else self.canvas_before).set_grid_visible(False)

    # ---- 이벤트 ----
    def _on_swap(self):
        self._swapped = not self._swapped
        if self._swapped:
            self.lbl_before_cap.configure(text="After (swapped)")
            self.lbl_after_cap.configure(text="Before (swapped)")
        else:
            self.lbl_before_cap.configure(text="Before")
            self.lbl_after_cap.configure(text="After")
        if self._pil_before and self._pil_after:
            self.show(self._pil_before, self._pil_after)

    def _on_mode_change(self):
        self._refresh_visuals()

    def _on_click(self, e):
        if e.widget is not self._get_active_canvas():
            return
        if self._placement_mode.get() == "grid":
            cv = self._get_active_canvas()
            norm = cv.event_to_norm(e.x, e.y)
            if not norm: return
            nx, ny = norm
            ix = min(2, max(0, int(nx * 3)))
            iy = min(2, max(0, int(ny * 3)))
            cx = (ix + 0.5) / 3.0; cy = (iy + 0.5) / 3.0
            self._anchor_norm = (cx, cy)
            cv.select_grid_cell((ix, iy))
            cv.set_marker_norm(None)
            if self._on_anchor_change:
                self._on_anchor_change(self._anchor_norm)
        else:
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
        # 유령만 즉시 이동(초경량)
        self._anchor_norm = norm
        cv.set_marker_norm(norm)

    def _on_release(self, e):
        if self._dragging and self._placement_mode.get() == "drag":
            self._dragging = False
            # 최종 확정 시 실제 미리보기 이미지 재계산
            if self._on_anchor_change:
                self._on_anchor_change(self._anchor_norm)
            # 중복 표시 방지: 유령은 잠시 숨김(새 After가 도착하면 필요시 다시 그림)
            self.canvas_before.set_marker_norm(None)
            self.canvas_after.set_marker_norm(None)

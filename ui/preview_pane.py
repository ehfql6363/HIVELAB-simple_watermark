# -*- coding: utf-8 -*-
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from collections import deque
from PIL import Image, ImageTk, ImageDraw, ImageFont
from typing import Callable, Tuple, Optional, Dict

_DEFAULT_FONTS = [
    "arial.ttf", "tahoma.ttf", "segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

def _pick_font(size: int, font_path: Optional[str] = None):
    if font_path:
        try:
            return ImageFont.truetype(font_path, size=size)
        except Exception:
            pass
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

def _fit_font_by_width(text: str, target_w: int, low=8, high=512, stroke_width=2, font_path: Optional[str]=None):
    best = low
    while low <= high:
        mid = (low + high) // 2
        w, _ = _measure_text(_pick_font(mid, font_path), text, stroke_width=stroke_width)
        if w <= target_w:
            best = mid; low = mid + 1
        else:
            high = mid - 1
    return best

class _CheckerCanvas(tk.Canvas):
    def __init__(self, master, **kw):
        super().__init__(master, highlightthickness=0, background="#E9E9E9", **kw)
        self._pil_img: Image.Image | None = None
        self._img_id: int | None = None
        self._img_refs = deque(maxlen=4)

        self._last = {"w":1,"h":1,"x0":0,"y0":0,"iw":1,"ih":1,"src_id":None}

        self._grid_visible = False
        self._grid_sel: Optional[Tuple[int,int]] = None
        self._marker_norm: Optional[Tuple[float,float]] = None

        self._grid_line_ids: list[int] = []
        self._cell_sel_id: Optional[int] = None
        self._wmghost_id: Optional[int] = None

        self._wm_cfg: Optional[Dict] = None
        self._wm_sprite_key: Optional[Tuple] = None
        self._wm_sprite_tk: Optional[ImageTk.PhotoImage] = None
        self._wm_sprite_refs = deque(maxlen=2)

        self._pending = False
        self._resample_fast = False
        self._hq_job_id: Optional[str] = None

        self.bind("<Configure>", self._on_resize)

    # ------- 외부 제어 -------
    def set_image(self, pil_img: Image.Image | None):
        self._pil_img = pil_img
        self._queue_render(hq=True)

    def set_grid_visible(self, visible: bool):
        self._grid_visible = visible
        self._draw_grid_overlay(); self._draw_cell_highlight()
        if visible:
            self._clear_wmghost()

    def select_grid_cell(self, ix_iy: Optional[Tuple[int,int]]):
        self._grid_sel = ix_iy
        self._draw_cell_highlight()

    def set_marker_norm(self, norm: Optional[Tuple[float,float]]):
        self._marker_norm = norm
        self._draw_wmghost()

    def set_wm_config(self, cfg: Optional[Dict]):
        self._wm_cfg = cfg
        self._wm_sprite_key = None
        self._queue_render(hq=True)

    def event_to_norm(self, ex: int, ey: int) -> Optional[Tuple[float,float]]:
        x0, y0, iw, ih = self._last["x0"], self._last["y0"], self._last["iw"], self._last["ih"]
        if iw <= 1 or ih <= 1: return None
        x = min(max(ex, x0), x0 + iw); y = min(max(ey, y0), y0 + ih)
        nx = (x - x0) / iw; ny = (y - y0) / ih
        return (min(1.0, max(0.0, nx)), min(1.0, max(0.0, ny)))

    # ------- 렌더 큐 -------
    def _queue_render(self, hq: bool=False):
        if hq:
            self._resample_fast = True
            if self._hq_job_id:
                try: self.after_cancel(self._hq_job_id)
                except Exception: pass
            self._hq_job_id = self.after(120, self._render_hq)
        if not self._pending:
            self._pending = True
            self.after_idle(self._render_full)

    def _render_hq(self):
        self._hq_job_id = None
        self._resample_fast = False
        if not self._pending:
            self._pending = True
            self.after_idle(self._render_full)

    def _on_resize(self, _):
        self._queue_render(hq=True)

    # ------- 내부 렌더 -------
    def _render_full(self):
        self._pending = False
        w = max(1, self.winfo_width()); h = max(1, self.winfo_height())
        if w < 4 or h < 4:
            self.after(16, self._render_full); return

        self.delete("checker")
        self.create_rectangle(0, 0, w, h, fill="#E9E9E9", outline="", width=0, tags="checker")
        self.tag_lower("checker")

        if self._pil_img is None:
            self.delete("content"); self._img_id = None
            self._last.update({"w":w,"h":h,"x0":0,"y0":0,"iw":1,"ih":1})
            self._clear_overlay()
            return

        W, H = self._pil_img.size
        raw_scale = min(w / W, h / H, 1.0)
        step = 1.0 / 64.0
        scale = max(step, round(raw_scale / step) * step)
        iw, ih = max(1, int(W * scale)), max(1, int(H * scale))
        x0, y0 = (w - iw) // 2, (h - ih) // 2

        resample = Image.Resampling.BILINEAR if self._resample_fast else Image.Resampling.LANCZOS

        cur_src_id = id(self._pil_img)
        prev_src_id = self._last.get("src_id")

        reuse_image = (
            self._img_id is not None
            and iw == self._last["iw"]
            and ih == self._last["ih"]
            and cur_src_id == prev_src_id
        )

        if reuse_image:
            self.coords(self._img_id, x0, y0)
        else:
            disp = self._pil_img if (iw == W and ih == H) else self._pil_img.resize((iw, ih), resample)
            tkimg = ImageTk.PhotoImage(disp)
            self._img_refs.append(tkimg)
            if self._img_id is None:
                self._img_id = self.create_image(x0, y0, image=tkimg, anchor="nw", tags="content")
            else:
                self.itemconfigure(self._img_id, image=tkimg)
                self.coords(self._img_id, x0, y0)

        self.tag_lower("checker"); self.tag_raise("content")
        self._last.update({"w": w, "h": h, "x0": x0, "y0": y0, "iw": iw, "ih": ih, "src_id": cur_src_id})

        self._ensure_wm_sprite()
        self._draw_grid_overlay(); self._draw_cell_highlight(); self._draw_wmghost()

    def _clear_overlay(self):
        for tag in ("grid", "cellsel", "wmghost"):
            self.delete(tag)
        self._grid_line_ids.clear()
        self._cell_sel_id = None
        self._wmghost_id = None

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
        self.create_rectangle(rx0, ry0, rx1, ry1, fill="#38f448", outline="#38f448", width=1, tags="cellsel", stipple="gray25")
        self.tag_raise("cellsel"); self.tag_raise("grid")

    def _ensure_wm_sprite(self):
        if not self._wm_cfg:
            self._wm_sprite_key = None; self._wm_sprite_tk = None
            self._clear_wmghost(); return
        txt = (self._wm_cfg.get("text") or "").strip()
        if txt == "":
            self._wm_sprite_key = None; self._wm_sprite_tk = None
            self._clear_wmghost(); return

        x0, y0, iw, ih = self._last["x0"], self._last["y0"], self._last["iw"], self._last["ih"]
        if iw <= 1 or ih <= 1: return

        op = int(self._wm_cfg.get("opacity", 30))
        scale_pct = int(self._wm_cfg.get("scale_pct", 5))
        fill = tuple(self._wm_cfg.get("fill", (0, 0, 0)))
        stroke = tuple(self._wm_cfg.get("stroke", (255, 255, 255)))
        sw = int(self._wm_cfg.get("stroke_w", 2))
        font_path = self._wm_cfg.get("font_path") or None

        target_w_raw = max(1, int(min(iw, ih) * (scale_pct / 100.0)))
        target_w = (target_w_raw + 7) // 8 * 8

        key = (txt, op, scale_pct, fill, stroke, sw, target_w, font_path)
        if key == self._wm_sprite_key and self._wm_sprite_tk is not None:
            return

        font_size = _fit_font_by_width(txt, target_w, stroke_width=sw, font_path=font_path)
        font = _pick_font(font_size, font_path=font_path)

        tmp = Image.new("L", (8, 8))
        d = ImageDraw.Draw(tmp)
        l, t, r, b = d.textbbox((0, 0), txt, font=font, stroke_width=max(0, sw))
        tw, th = max(1, r - l), max(1, b - t)

        alpha = int(255 * (op / 100.0))
        fill_rgba = (fill[0], fill[1], fill[2], alpha)
        stroke_rgba = (stroke[0], stroke[1], stroke[2], alpha)

        over = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        d2 = ImageDraw.Draw(over)
        d2.text((-l, -t), txt, font=font, fill=fill_rgba,
                stroke_width=max(0, sw), stroke_fill=stroke_rgba)

        tkimg = ImageTk.PhotoImage(over)
        self._wm_sprite_tk = tkimg
        self._wm_sprite_refs.append(tkimg)
        self._wm_sprite_key = key
        if self._wmghost_id is not None:
            self.itemconfigure(self._wmghost_id, image=self._wm_sprite_tk)

    def _draw_wmghost(self):
        if self._grid_visible or not self._wm_sprite_tk or self._marker_norm is None:
            self._clear_wmghost(); return
        x0, y0, iw, ih = self._last["x0"], self._last["y0"], self._last["iw"], self._last["ih"]
        if iw <= 1 or ih <= 1: self._clear_wmghost(); return
        nx = min(1.0, max(0.0, float(self._marker_norm[0])))
        ny = min(1.0, max(0.0, float(self._marker_norm[1])))
        cx = x0 + nx * iw; cy = y0 + ny * ih
        if self._wmghost_id is None:
            self._wmghost_id = self.create_image(cx, cy, image=self._wm_sprite_tk, anchor="center", tags="wmghost")
        else:
            self.coords(self._wmghost_id, cx, cy)
        self.tag_raise("wmghost")

    def _clear_wmghost(self):
        if self._wmghost_id is not None:
            self.delete(self._wmghost_id)
            self._wmghost_id = None

class PreviewPane(ttk.Frame):
    """Before/After + Swap + (그리드/드래그) 위치 지정 + 드래그 유령 워터마크."""
    def __init__(self, master,
                 on_anchor_change: Callable[[Tuple[float,float]], None] | None = None,
                 on_apply_all: Callable[[Tuple[float,float]], None] | None = None,
                 on_clear_individual=None):
        super().__init__(master)
        self._on_anchor_change = on_anchor_change
        self._on_clear_individual = on_clear_individual
        self._on_apply_all = on_apply_all
        self._placement_mode = tk.StringVar(value="grid")

        top = ttk.Frame(self); top.pack(fill="x", pady=(2, 0))
        self.lbl_before_cap = ttk.Label(top, text="원본", font=("", 10, "bold"))
        self.lbl_after_cap = ttk.Label(top, text="적용", font=("", 10, "bold"))
        self.btn_swap = ttk.Button(top, text="좌우 교체 ◀▶", command=self._on_swap)
        self.lbl_before_cap.pack(side="left", padx=4)
        self.btn_swap.pack(side="left", padx=8)
        self.lbl_after_cap.pack(side="left", padx=4)

        ttk.Label(top, text="배치:").pack(side="left", padx=(16,2))
        ttk.Radiobutton(top, text="3×3 그리드", variable=self._placement_mode,
                        value="grid", command=self._on_mode_change).pack(side="left")
        ttk.Radiobutton(top, text="드래그", variable=self._placement_mode,
                        value="drag", command=self._on_mode_change).pack(side="left", padx=(4,0))

        ttk.Button(top, text="모든 이미지에 적용",
                   command=lambda: on_apply_all and on_apply_all(self._anchor_norm)
                   ).pack(side="left", padx=(12, 4))
        ttk.Button(top, text="현재 이미지 기본 따르기",
                   command=lambda: self._on_clear_individual and self._on_clear_individual()
                   ).pack(side="left")

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

    # ------- 외부 API -------
    def set_wm_preview_config(self, cfg: Optional[Dict]):
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
        self.lbl_before_cap.configure(text="원본"); self.lbl_after_cap.configure(text="적용")

    def set_anchor(self, norm: Tuple[float,float]):
        self._anchor_norm = (float(norm[0]), float(norm[1]))
        self._refresh_visuals()

    # ------- 내부 동작 -------
    def _get_active_canvas(self) -> _CheckerCanvas:
        return self.canvas_before if self._swapped else self.canvas_after

    def _refresh_visuals(self):
        act = self._get_active_canvas()
        oth = self.canvas_after if act is self.canvas_before else self.canvas_before

        if self._placement_mode.get() == "grid":
            ix = min(2, max(0, int(self._anchor_norm[0] * 3)))
            iy = min(2, max(0, int(self._anchor_norm[1] * 3)))
            act.select_grid_cell((ix, iy))
            act.set_marker_norm(None)
            oth.select_grid_cell(None); oth.set_marker_norm(None)
        else:
            act.select_grid_cell(None)
            act.set_marker_norm(self._anchor_norm)
            oth.select_grid_cell(None); oth.set_marker_norm(None)

        self._apply_grid_and_visuals()

    def _apply_grid_and_visuals(self):
        show_grid = (self._placement_mode.get() == "grid")
        self._get_active_canvas().set_grid_visible(show_grid)
        (self.canvas_after if self._get_active_canvas() is self.canvas_before else self.canvas_before).set_grid_visible(False)

    def _on_swap(self):
        self._swapped = not self._swapped
        if self._swapped:
            self.lbl_before_cap.configure(text="적용 (좌우 교체)")
            self.lbl_after_cap.configure(text="원본 (좌우 교체)")
        else:
            self.lbl_before_cap.configure(text="원본")
            self.lbl_after_cap.configure(text="적용")
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
        self._anchor_norm = norm
        cv.set_marker_norm(norm)

    def _on_release(self, e):
        if self._dragging and self._placement_mode.get() == "drag":
            self._dragging = False
            if self._on_anchor_change:
                self._on_anchor_change(self._anchor_norm)
            self.canvas_before.set_marker_norm(None)
            self.canvas_after.set_marker_norm(None)

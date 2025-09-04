from pathlib import Path
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont
from functools import lru_cache

DEFAULT_FONT_CANDIDATES = [
    "arial.ttf", "tahoma.ttf", "segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

_font_cache = {}

def _get_font(font_path: str | None, size: int):
    key = (font_path or "", int(size))
    f = _font_cache.get(key)
    if f: return f
    try:
        if font_path:
            f = ImageFont.truetype(font_path, size=size)
        else:
            # 후보 우선 시도
            for cand in DEFAULT_FONT_CANDIDATES:
                try:
                    f = ImageFont.truetype(cand, size=size)
                    break
                except Exception:
                    continue
            if not f:
                f = ImageFont.load_default()
    except Exception:
        f = ImageFont.load_default()
    _font_cache[key] = f
    return f

def add_text_watermark(canvas, text, opacity_pct, scale_pct, fill_rgb, stroke_rgb, stroke_width, anchor_norm, font_path):
    if not text or not str(text).strip():
        return canvas

    sprite = get_wm_sprite(
        text, scale_pct, opacity_pct, fill_rgb, stroke_rgb, stroke_width,
        str(font_path) if font_path else "", canvas.size
    )

    cx = int(anchor_norm[0] * canvas.width)
    cy = int(anchor_norm[1] * canvas.height)
    x = cx - sprite.width // 2
    y = cy - sprite.height // 2

    if canvas.mode != "RGBA":
        base = canvas.convert("RGBA")
    else:
        base = canvas.copy()

    base.alpha_composite(sprite, (x, y))
    return base.convert("RGB") if canvas.mode != "RGBA" else base

def make_overlay_sprite(
    text: str,
    canvas_wh: tuple[int, int],
    scale_pct: int,
    opacity_pct: int,
    fill_rgb: tuple[int,int,int],
    stroke_rgb: tuple[int,int,int],
    stroke_width: int,
    font_path: str | None,
):
    W, H = canvas_wh
    short_side = min(W, H)
    return _make_sprite(
        *_sprite_key(text, scale_pct, opacity_pct, tuple(fill_rgb), tuple(stroke_rgb),
                     int(stroke_width), font_path or "", int(short_side))
    )

@lru_cache(maxsize=256)
def _sprite_key(text, scale_pct, opacity, fill, stroke, stroke_w, font_path_str, short_side):
    return (text, int(scale_pct), int(opacity), tuple(fill), tuple(stroke), int(stroke_w),
            font_path_str or "", int(short_side))

def _make_sprite(text, scale_pct, opacity, fill, stroke, stroke_w, font_path_str, short_side):
    # 목표 '높이'를 짧은 변 * 비율로
    target_h = max(1, int(short_side * (scale_pct / 100.0)))

    lo, hi, best = 6, max(12, target_h * 3), 12
    tmp = Image.new("L", (4, 4))
    d = ImageDraw.Draw(tmp)

    # 높이 기준 이분 탐색
    while lo <= hi:
        mid = (lo + hi) // 2
        f = _get_font(font_path_str or None, mid)
        l, t, r, b = d.textbbox((0, 0), text, font=f, stroke_width=max(0, stroke_w))
        h = b - t
        if h <= target_h:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1

    f = _get_font(font_path_str or None, best)
    l, t, r, b = d.textbbox((0, 0), text, font=f, stroke_width=max(0, stroke_w))
    w, h = max(1, r - l), max(1, b - t)

    sprite = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sprite)
    a = int(255 * (opacity / 100.0))
    draw.text(
        (-l, -t), text, font=f,
        fill=(fill[0], fill[1], fill[2], a),
        stroke_width=max(0, stroke_w),
        stroke_fill=(stroke[0], stroke[1], stroke[2], a)
    )
    return sprite


def get_wm_sprite(text, scale_pct, opacity, fill, stroke, stroke_w, font_path, canvas_size):
    short_side = min(canvas_size)
    key = _sprite_key(text, scale_pct, opacity, tuple(fill), tuple(stroke), int(stroke_w),
                      str(font_path) if font_path else "", int(short_side))
    return _make_sprite(*key)

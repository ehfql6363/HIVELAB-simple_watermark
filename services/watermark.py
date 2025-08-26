from pathlib import Path
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont
from functools import lru_cache

DEFAULT_FONT_CANDIDATES = [
    "arial.ttf", "tahoma.ttf", "segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

_font_cache = {}

def pick_font(size: int, font_path: Optional[Path] = None):
    # 우선 사용자가 선택한 폰트 시도
    if font_path:
        try:
            return ImageFont.truetype(str(font_path), size=size)
        except Exception:
            pass
    # 후보 폰트 시도
    for cand in DEFAULT_FONT_CANDIDATES:
        try:
            return ImageFont.truetype(cand, size=size)
        except Exception:
            pass
    return ImageFont.load_default()

def _measure_text(font, text, stroke_width=0):
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    bbox = d.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]

def _fit_font_by_width(text: str, target_w: int, low=8, high=512, stroke_width=2, font_path: Optional[Path]=None):
    best = low
    while low <= high:
        mid = (low + high) // 2
        w, _ = _measure_text(pick_font(mid, font_path), text, stroke_width=stroke_width)
        if w <= target_w:
            best = mid; low = mid + 1
        else:
            high = mid - 1
    return best

def add_text_watermark(canvas, text, opacity_pct, scale_pct, fill_rgb, stroke_rgb, stroke_width, anchor_norm, font_path):
    if not text:
        return canvas
    sprite = get_wm_sprite(text, scale_pct, opacity_pct, fill_rgb, stroke_rgb, stroke_width, font_path, canvas.size)
    cx = int(anchor_norm[0] * canvas.width)
    cy = int(anchor_norm[1] * canvas.height)
    x = cx - sprite.width//2
    y = cy - sprite.height//2
    out = canvas.copy()
    out.alpha_composite(sprite, (x, y)) if out.mode == "RGBA" else out.convert("RGBA").alpha_composite(sprite, (x,y)).convert("RGB")
    return out

def add_center_watermark(*args, **kwargs):
    kwargs.pop("anchor_norm", None)
    return add_text_watermark(*args, **kwargs, anchor_norm=(0.5, 0.5))

def _get_font(font_path: str | None, size: int):
    key = (font_path or "", int(size))
    f = _font_cache.get(key)
    if f: return f
    from PIL import ImageFont
    try: f = ImageFont.truetype(font_path, size=size) if font_path else ImageFont.load_default()
    except: f = ImageFont.load_default()
    _font_cache[key] = f
    return f

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
    from PIL import Image, ImageDraw
    W, H = canvas_wh
    target_w = max(1, int(min(W, H) * (scale_pct / 100.0)))

    # 이진탐색으로 폰트 크기 맞추기
    lo, hi, best = 8, 512, 8
    while lo <= hi:
        mid = (lo + hi) // 2
        font = _get_font(font_path, mid)
        d = ImageDraw.Draw(Image.new("RGB", (8, 8)))
        w, h = d.textbbox((0,0), text, font=font, stroke_width=max(0, stroke_width))[2:]
        if w <= target_w:
            best = mid; lo = mid + 1
        else:
            hi = mid - 1

    font = _get_font(font_path, best)
    d = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    tw, th = d.textbbox((0,0), text, font=font, stroke_width=max(0, stroke_width))[2:]

    alpha = int(255 * (opacity_pct / 100.0))
    over = Image.new("RGBA", (tw, th), (0,0,0,0))
    d = ImageDraw.Draw(over)
    d.text((0,0), text, font=font, fill=(*fill_rgb, alpha),
           stroke_width=max(0, stroke_width), stroke_fill=(*stroke_rgb, alpha))
    return over

def paste_overlay(canvas: Image.Image, overlay: "Image.Image", anchor_norm: tuple[float,float]) -> Image.Image:
    x = int(anchor_norm[0] * canvas.width  - overlay.width  / 2)
    y = int(anchor_norm[1] * canvas.height - overlay.height / 2)
    canvas.paste(overlay, (x, y), overlay)
    return canvas

def _pick_font(path, size):
    return ImageFont.truetype(str(path), size=size) if path else ImageFont.load_default()

def _measure(d, text, font, stroke_w):
    bbox = d.textbbox((0,0), text, font=font, stroke_width=stroke_w)
    return bbox[2]-bbox[0], bbox[3]-bbox[1]

@lru_cache(maxsize=256)
def _sprite_key(text, scale_pct, opacity, fill, stroke, stroke_w, font_path_str, short_side):
    # short_side: 대상 이미지의 짧은 변
    return (text, int(scale_pct), int(opacity), fill, stroke, int(stroke_w), font_path_str or "", int(short_side))

def _make_sprite(text, scale_pct, opacity, fill, stroke, stroke_w, font_path, short_side):
    # 텍스트 폭이 짧은 변 * scale_pct% 에 맞도록 폰트 찾기(이진 탐색)
    target_w = max(1, int(short_side * (scale_pct/100.0)))
    lo, hi, best = 6, 512, 12
    d = ImageDraw.Draw(Image.new("L", (4,4)))
    while lo <= hi:
        mid = (lo+hi)//2
        f = _pick_font(font_path, mid)
        w,_ = _measure(d, text, f, stroke_w)
        if w <= target_w:
            best = mid; lo = mid+1
        else:
            hi = mid-1
    f = _pick_font(font_path, best)
    w,h = _measure(d, text, f, stroke_w)
    sprite = Image.new("RGBA", (max(1,w), max(1,h)), (0,0,0,0))
    draw = ImageDraw.Draw(sprite)
    a = int(255 * (opacity/100.0))
    draw.text((0,0), text, font=f,
              fill=(fill[0], fill[1], fill[2], a),
              stroke_width=max(0, stroke_w),
              stroke_fill=(stroke[0], stroke[1], stroke[2], a))
    return sprite

def get_wm_sprite(text, scale_pct, opacity, fill, stroke, stroke_w, font_path, canvas_size):
    short_side = min(canvas_size)
    key = _sprite_key(text, scale_pct, opacity, tuple(fill), tuple(stroke), stroke_w,
                      str(font_path) if font_path else "", short_side)
    # lru_cache는 “결과”를 캐시하므로, 키로 다시 만들어 사용
    return _make_sprite(*key)

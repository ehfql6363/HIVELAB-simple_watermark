from pathlib import Path
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

DEFAULT_FONT_CANDIDATES = [
    "arial.ttf", "tahoma.ttf", "segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

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

def add_text_watermark(
    img: Image.Image,
    text: str,
    opacity_pct: int,
    scale_pct: int,
    fill_rgb: Tuple[int,int,int] = (0, 0, 0),
    stroke_rgb: Tuple[int,int,int] = (255, 255, 255),
    stroke_width: int = 2,
    anchor_norm=(0.5, 0.5),
    font_path: Optional[Path] = None,
) -> Image.Image:
    """텍스트 워터마크를 임의 위치에 배치."""
    if not text:
        return img

    W, H = img.size
    short = min(W, H)
    target_w = max(1, int(short * (scale_pct / 100.0)))

    font = pick_font(_fit_font_by_width(text, target_w, stroke_width=stroke_width, font_path=font_path), font_path)
    tw, th = _measure_text(font, text, stroke_width=stroke_width)

    ax = min(1.0, max(0.0, float(anchor_norm[0])))
    ay = min(1.0, max(0.0, float(anchor_norm[1])))
    cx = ax * W; cy = ay * H
    x = int(round(cx - tw / 2)); y = int(round(cy - th / 2))
    x = max(0, min(x, W - tw)); y = max(0, min(y, H - th))

    alpha = int(255 * (opacity_pct / 100.0))
    fill_rgba = (*fill_rgb, alpha)
    stroke_rgba = (*stroke_rgb, alpha)

    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    d.text((x, y), text, font=font, fill=fill_rgba,
           stroke_width=max(0, int(stroke_width)), stroke_fill=stroke_rgba)
    base = img.convert("RGBA")
    return Image.alpha_composite(base, over).convert("RGB")

def add_center_watermark(*args, **kwargs):
    kwargs.pop("anchor_norm", None)
    return add_text_watermark(*args, **kwargs, anchor_norm=(0.5, 0.5))

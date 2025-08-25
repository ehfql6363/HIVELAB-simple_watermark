from PIL import Image, ImageDraw, ImageFont

DEFAULT_FONT_CANDIDATES = [
    "arial.ttf", "tahoma.ttf", "segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

def pick_font(size: int):
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

def _fit_font_by_width(text: str, target_w: int, low=8, high=512, stroke_width=2):
    best = low
    while low <= high:
        mid = (low + high) // 2
        w, _ = _measure_text(pick_font(mid), text, stroke_width=stroke_width)
        if w <= target_w:
            best = mid; low = mid + 1
        else:
            high = mid - 1
    return best

def add_center_watermark(
    img: Image.Image,
    text: str,
    opacity_pct: int,
    scale_pct: int,
    fill_rgb=(0, 0, 0),
    stroke_rgb=(255, 255, 255),
    stroke_width: int = 2,
) -> Image.Image:
    """중앙 워터마크(텍스트) — 색/외곽선/두께 설정 가능."""
    if not text:
        return img

    W, H = img.size
    short = min(W, H)
    target_w = max(1, int(short * (scale_pct / 100.0)))

    font = pick_font(_fit_font_by_width(text, target_w, stroke_width=stroke_width))
    tw, th = _measure_text(font, text, stroke_width=stroke_width)
    x, y = (W - tw) // 2, (H - th) // 2

    alpha = int(255 * (opacity_pct / 100.0))
    fill_rgba = (fill_rgb[0], fill_rgb[1], fill_rgb[2], alpha)
    stroke_rgba = (stroke_rgb[0], stroke_rgb[1], stroke_rgb[2], alpha)

    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    d.text(
        (x, y),
        text,
        font=font,
        fill=fill_rgba,
        stroke_width=max(0, int(stroke_width)),
        stroke_fill=stroke_rgba,
    )
    base = img.convert("RGBA")
    return Image.alpha_composite(base, over).convert("RGB")

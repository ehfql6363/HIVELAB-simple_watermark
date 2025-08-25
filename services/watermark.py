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

def add_text_watermark(
    img: Image.Image,
    text: str,
    opacity_pct: int,
    scale_pct: int,
    fill_rgb=(0, 0, 0),
    stroke_rgb=(255, 255, 255),
    stroke_width: int = 2,
    anchor_norm=(0.5, 0.5),  # 🔹 (x,y) in 0..1
) -> Image.Image:
    """텍스트 워터마크를 임의 위치에 배치. anchor_norm은 최종 이미지 기준 정규화 좌표(0..1)."""
    if not text:
        return img

    W, H = img.size
    short = min(W, H)
    target_w = max(1, int(short * (scale_pct / 100.0)))

    font = pick_font(_fit_font_by_width(text, target_w, stroke_width=stroke_width))
    tw, th = _measure_text(font, text, stroke_width=stroke_width)

    # 정규화 앵커 → 픽셀 좌표(텍스트 박스 중심)
    ax = min(1.0, max(0.0, float(anchor_norm[0])))
    ay = min(1.0, max(0.0, float(anchor_norm[1])))
    cx = ax * W
    cy = ay * H
    x = int(round(cx - tw / 2))
    y = int(round(cy - th / 2))

    # 화면 밖으로 나가지 않게 살짝 클램프
    x = max(0, min(x, W - tw))
    y = max(0, min(y, H - th))

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

# 하위호환(중앙 배치)
def add_center_watermark(*args, **kwargs):
    kwargs.pop("anchor_norm", None)
    return add_text_watermark(*args, **kwargs, anchor_norm=(0.5, 0.5))

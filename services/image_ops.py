from PIL import Image, ImageOps
from pathlib import Path

def exif_transpose(image: Image.Image) -> Image.Image:
    try:
        return ImageOps.exif_transpose(image)
    except Exception:
        return image

def load_image(path: Path) -> Image.Image:
    im = Image.open(str(path))
    im = exif_transpose(im)
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if im.mode == "LA" else "RGB")
    return im

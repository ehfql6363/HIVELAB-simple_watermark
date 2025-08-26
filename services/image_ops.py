# services/image_ops.py
from PIL import Image, ImageOps
from pathlib import Path
from functools import lru_cache

@lru_cache(maxsize=32)
def _load_image_cached(path_str: str) -> Image.Image:
    p = Path(path_str)
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"이미지 파일이 없습니다: {path_str}")
    with Image.open(path_str) as im:
        im = ImageOps.exif_transpose(im)
        return im.convert("RGB").copy()

def load_image(path: Path) -> Image.Image:
    # 절대 None을 반환하지 않음
    return _load_image_cached(str(path))

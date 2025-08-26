from PIL import Image, ImageOps
from pathlib import Path
from functools import lru_cache

@lru_cache(maxsize=32)
def _load_image_cached(path_str: str):
    with Image.open(path_str) as im:
        im = ImageOps.exif_transpose(im)   # 회전 보정
        return im.convert("RGB").copy()    # 파일 핸들 해제 + 캐시에 안전 복제본

def load_image(path: Path) -> Image.Image:
    try:
        return _load_image_cached(str(path))
    except Exception:
        # 실패하면 캐시 우회(에러 이미지 등)
        with Image.open(path) as im:
            return im.convert("RGB").copy()

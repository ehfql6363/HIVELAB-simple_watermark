# services/image_ops.py
from PIL import Image, ImageOps
from pathlib import Path
from functools import lru_cache


def _stat_mtime_ns(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except Exception:
        return 0

@lru_cache(maxsize=64)
def _load_image_cached_with_mtime(path_str: str, mtime_ns: int) -> Image.Image:
    p = Path(path_str)
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"이미지 파일이 없습니다: {path_str}")
    with Image.open(path_str) as im:
        im = ImageOps.exif_transpose(im)
        return im.convert("RGB").copy()

def load_image(path: Path) -> Image.Image:
    # 파일이 변경되면 mtime_ns가 바뀌어 캐시 자동 무효화
    return _load_image_cached_with_mtime(str(path), _stat_mtime_ns(path))

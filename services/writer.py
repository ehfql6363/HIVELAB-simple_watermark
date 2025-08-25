from pathlib import Path

def save_jpeg(img, dst: Path, quality: int = 92):
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(dst), format="JPEG", quality=quality, subsampling=1, optimize=True)

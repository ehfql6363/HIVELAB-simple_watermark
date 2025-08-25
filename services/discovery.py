from pathlib import Path

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

def is_image(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() in SUPPORTED_EXTS

def numeric_key(p: Path):
    # Prefer numeric stem ordering if possible (1,2,10)
    try:
        return (0, int(p.stem))
    except Exception:
        return (1, p.name.lower())

def scan_posts(input_root: Path):
    posts = {}
    if not input_root or not input_root.exists():
        return posts
    for child in sorted(input_root.iterdir(), key=lambda p: p.name.lower()):
        if child.is_dir():
            imgs = [p for p in sorted(child.iterdir(), key=numeric_key) if is_image(p)]
            if imgs:
                posts[child.name] = imgs
    return posts

from __future__ import annotations
from pathlib import Path
from typing import Dict, List
import re

IMG_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}

def _is_image(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() in IMG_EXTS

def _natural_key(p: Path):
    s = p.stem
    parts = re.split(r'(\d+)', s)
    return [int(t) if t.isdigit() else t.lower() for t in parts]

def scan_posts(root: Path) -> Dict[str, List[Path]]:
    """
    - root 바로 아래에 이미지가 있으면: 단일 게시물로 간주하여 {"__SELF__": [이미지들]} 반환
    - 아니면: 하위 폴더를 게시물로 스캔하여 {post_name: [이미지들]} 반환
    """
    root = Path(root)
    if not root.exists():
        return {}

    # 1) 이 폴더 자체가 '게시물 폴더' 인가?
    direct_imgs = sorted([p for p in root.iterdir() if _is_image(p)], key=_natural_key)
    if direct_imgs:
        return {"__SELF__": direct_imgs}

    # 2) 아니면 하위 폴더들을 게시물로 스캔
    posts: Dict[str, List[Path]] = {}
    for sub in sorted([d for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")],
                      key=lambda d: d.name.lower()):
        imgs = sorted([p for p in sub.iterdir() if _is_image(p)], key=_natural_key)
        if imgs:
            posts[sub.name] = imgs
    return posts

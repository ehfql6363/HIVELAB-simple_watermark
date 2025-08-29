# discovery.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, List
import os, re

IMG_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}
_num_re = re.compile(r'(\d+)')

def _natural_key_name(name: str):
    stem = os.path.splitext(name)[0]
    return [int(t) if t.isdigit() else t.lower() for t in _num_re.split(stem)]

def scan_posts(root: Path) -> Dict[str, List[Path]]:
    root = Path(root)
    if not root.exists():
        return {}

    # 1) 루트 바로 아래를 한 번만 스캔
    direct_imgs: List[Path] = []
    subdirs: List[Path] = []
    with os.scandir(root) as it:
        for e in it:
            if not e.name or e.name.startswith('.'):
                continue
            try:
                if e.is_file():
                    if os.path.splitext(e.name)[1].lower() in IMG_EXTS:
                        direct_imgs.append(Path(e.path))
                elif e.is_dir():
                    subdirs.append(Path(e.path))
            except Exception:
                continue

    if direct_imgs:
        direct_imgs.sort(key=lambda p: _natural_key_name(p.name))
        return {"__SELF__": direct_imgs}

    posts: Dict[str, List[Path]] = {}
    for d in sorted(subdirs, key=lambda p: p.name.lower()):
        imgs: List[Path] = []
        try:
            with os.scandir(d) as it2:
                for e2 in it2:
                    if e2.is_file():
                        if os.path.splitext(e2.name)[1].lower() in IMG_EXTS:
                            imgs.append(Path(e2.path))
        except Exception:
            continue
        if imgs:
            imgs.sort(key=lambda p: _natural_key_name(p.name))
            posts[d.name] = imgs
    return posts

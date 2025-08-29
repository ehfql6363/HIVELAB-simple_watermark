# discovery.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, List
import os, re

IMG_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}
_num_re = re.compile(r'(\d+)')

def _natural_key_name(name: str):
    # "img12_a" -> ['img', 12, '_a'] 형태로 변환
    stem = os.path.splitext(name)[0]
    parts = _num_re.split(stem)
    return [int(t) if t.isdigit() else t.lower() for t in parts]

def _iter_images_in(dirpath: Path):
    try:
        with os.scandir(dirpath) as it:
            for e in it:
                # 숨김 파일/디렉터리 스킵(리눅스/맥 기준; 윈도우 Hidden 속성은 별도)
                if e.name.startswith('.'):
                    continue
                if not e.is_file():
                    continue
                # 확장자 빠르게 체크 (Path 만들기 전에)
                _, ext = os.path.splitext(e.name)
                if ext.lower() in IMG_EXTS:
                    yield Path(e.path)
    except (FileNotFoundError, PermissionError):
        return  # 조용히 무시

def scan_posts(root: Path) -> Dict[str, List[Path]]:
    root = Path(root)
    if not root.exists():
        return {}

    # 1) 루트 바로 아래에 이미지가 있으면 단일 게시물
    direct_imgs = sorted(
        _iter_images_in(root),
        key=lambda p: _natural_key_name(p.name)  # ★ 파일명 기준 자연 정렬
    )
    if direct_imgs:
        return {"__SELF__": direct_imgs}

    # 2) 하위 폴더들을 게시물로 스캔
    posts: Dict[str, List[Path]] = {}
    subs: List[Path] = []
    try:
        with os.scandir(root) as it:
            for e in it:
                if e.name.startswith('.'):
                    continue
                if e.is_dir():
                    subs.append(Path(e.path))
    except (FileNotFoundError, PermissionError):
        return posts

    # 폴더 이름 알파벳 정렬(기존 로직 유지)
    for sub in sorted(subs, key=lambda d: d.name.lower()):
        imgs = sorted(
            _iter_images_in(sub),
            key=lambda p: _natural_key_name(p.name)  # ★ 파일명 기준 자연 정렬
        )
        if imgs:
            posts[sub.name] = imgs
    return posts

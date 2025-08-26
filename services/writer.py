# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True

def _safe_name(name: str) -> str:
    # Windows 금지문자 치환
    return "".join(c if c not in '\\/:*?"<>|' else "_" for c in str(name)).strip()

def build_out_dir(output_root: Path, root_dir: Path, post_key: str) -> Path:
    """
    평탄화된 출력 경로의 디렉터리만 생성: export/<루트명>/<게시물명>
    """
    return output_root / root_dir.name / _safe_name(post_key)

def build_out_path(
    output_root: Path,
    root_dir: Path,
    post_key: str,
    size_label: Optional[str],     # ✅ 호환성: 받아도 무시
    src_file: Path,
    fmt_ext: str
) -> Path:
    """
    최종 파일 경로(사이즈 폴더 없음):
      export/<루트명>/<게시물명>/<원본파일명>.<확장자>
    """
    out_dir = build_out_dir(output_root, root_dir, post_key)
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = fmt_ext.lstrip(".")
    return out_dir / f"{src_file.stem}.{ext}"

def save_image(
    img: Image.Image,
    path: Path,
    quality: int = 90,
    icc: bytes | None = None,
    exif: bytes | None = None,
    fmt: Optional[str] = None
):
    """
    JPEG/WEBP 저장 유틸. 경로 폴더가 없으면 생성.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    params = {}
    if icc: params["icc_profile"] = icc
    if exif: params["exif"] = exif

    if fmt is None:
        suf = path.suffix.lower()
        if suf in (".jpg", ".jpeg"): fmt = "JPEG"
        elif suf == ".webp": fmt = "WEBP"
        else: fmt = "PNG"

    if fmt.upper() == "JPEG":
        params.update(optimize=True, quality=quality, subsampling="4:4:4")
    elif fmt.upper() == "WEBP":
        params.update(quality=quality, method=6)

    img.save(path, format=fmt, **params)

def save_jpeg(
    img: Image.Image,
    path: Path,
    quality: int = 90,
    icc: bytes | None = None,
    exif: bytes | None = None
):
    """
    컨트롤러에서 사용 중인 이름과 호환되도록 제공.
    확장자가 .jpg/.jpeg가 아니어도 JPEG로 저장하도록 강제.
    """
    if path.suffix.lower() not in (".jpg", ".jpeg"):
        path = path.with_suffix(".jpg")
    save_image(img, path, quality=quality, icc=icc, exif=exif, fmt="JPEG")

# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
from typing import Optional, Dict, Any
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
    dst: Path,
    *,
    quality: int = 90,
    optimize: bool = False,
    progressive: bool = False,
    exif: Optional[bytes] = None,
    extra_params: Optional[Dict[str, Any]] = None,
) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    fmt = (dst.suffix or "").lower().lstrip(".")
    params: Dict[str, Any] = dict(extra_params or {})

    if fmt in ("jpg", "jpeg"):
        params.setdefault("quality", int(quality))
        params.setdefault("optimize", bool(optimize))
        params.setdefault("progressive", bool(progressive))
        if exif:
            params["exif"] = exif
        if img.mode in ("RGBA", "LA"):
            img = img.convert("RGB")
        img.save(str(dst), format="JPEG", **params)

    elif fmt == "png":
        # PNG는 EXIF를 일반적으로 유지하지 않으므로 별도 처리 안 함
        # (필요 시 PngInfo로 주입해야 하나 대부분 워크플로우에선 불필요)
        img.save(str(dst), format="PNG", **params)

    else:
        # 알 수 없는 확장자 → JPEG 저장
        if img.mode in ("RGBA", "LA"):
            img = img.convert("RGB")
        params.setdefault("quality", int(quality))
        params.setdefault("optimize", bool(optimize))
        params.setdefault("progressive", bool(progressive))
        img.save(str(dst.with_suffix(".jpg")), format="JPEG", **params)

def save_jpeg(
    img: Image.Image,
    path: Path,
    quality: int = 90,
    icc: bytes | None = None,
    exif: bytes | None = None
):
    """
    JPEG 저장 전용 유틸(선택 사용). 확장자 강제 .jpg.
    """
    if path.suffix.lower() not in (".jpg", ".jpeg"):
        path = path.with_suffix(".jpg")
    extra: Dict[str, Any] = {}
    if icc:
        # Pillow는 'icc_profile' 키로 받음
        extra["icc_profile"] = icc
    save_image(img, path, quality=quality, exif=exif, extra_params=extra)

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

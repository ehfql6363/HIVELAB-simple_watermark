# writer.py
from __future__ import annotations
from pathlib import Path
from typing import Optional, Dict, Any
from PIL import Image, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True

def _safe_name(name: str) -> str:
    return "".join(c if c not in '\\/:*?"<>|' else "_" for c in str(name)).strip()

def build_out_dir(output_root: Path, root_dir: Path, post_key: str) -> Path:
    return output_root / root_dir.name / _safe_name(post_key)

def build_out_path(
    output_root: Path,
    root_dir: Path,
    post_key: str,
    size_label: Optional[str],
    src_file: Path,
    fmt_ext: str
) -> Path:
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
        # 🔸 속도 우선: subsampling=2(4:2:0), optimize/progressive 꺼두기
        params.setdefault("quality", int(quality))
        params.setdefault("subsampling", 2)
        params.setdefault("optimize", bool(optimize))        # 기본 False
        params.setdefault("progressive", bool(progressive))  # 기본 False
        if exif:
            params["exif"] = exif
        if img.mode in ("RGBA", "LA"):
            img = img.convert("RGB")
        img.save(str(dst), format="JPEG", **params)

    elif fmt == "png":
        # 🔸 속도 우선: 압축 레벨 낮추기
        params.setdefault("compress_level", 3)
        img.save(str(dst), format="PNG", **params)

    else:
        # 미지 확장자 → JPEG로 강제
        if img.mode in ("RGBA", "LA"):
            img = img.convert("RGB")
        params.setdefault("quality", int(quality))
        params.setdefault("subsampling", 2)
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
    """JPEG 저장 전용 (확장자 강제 .jpg)."""
    if path.suffix.lower() not in (".jpg", ".jpeg"):
        path = path.with_suffix(".jpg")
    extra: Dict[str, Any] = {}
    if icc:
        extra["icc_profile"] = icc
    save_image(img, path, quality=quality, exif=exif, extra_params=extra)

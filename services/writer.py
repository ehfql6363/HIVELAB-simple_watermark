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
    """
    고속 저장 함수.
    - JPEG: quality(기본 90), optimize=False, progressive=False 로 속도↑
    - PNG 등 다른 확장자는 Pillow 기본 저장
    - 저장 전 폴더 자동 생성
    - RGBA → JPEG 시 RGB로 자동 변환

    Parameters
    ----------
    img : PIL.Image.Image
    dst : Path
        저장 경로(확장자로 포맷 결정)
    quality : int
        JPEG 품질(속도/용량 균형)
    optimize : bool
        JPEG 최적화(느려서 기본 False 권장)
    progressive : bool
        프로그레시브 JPEG(느려서 기본 False 권장)
    exif : bytes | None
        원본 EXIF 유지 시 전달
    extra_params : dict | None
        포맷별 세부 옵션 추가(필요시)
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    fmt = (dst.suffix or "").lower().lstrip(".")
    params: Dict[str, Any] = dict(extra_params or {})

    if fmt in ("jpg", "jpeg"):
        # JPEG 파라미터
        params.setdefault("quality", int(quality))
        params.setdefault("optimize", bool(optimize))
        params.setdefault("progressive", bool(progressive))
        # 속도 위해 subsampling은 Pillow 기본(대개 4:2:0)을 그대로 사용
        if exif:
            params["exif"] = exif
        if img.mode in ("RGBA", "LA"):
            img = img.convert("RGB")
        img.save(str(dst), format="JPEG", **params)
    elif fmt == "png":
        # PNG는 기본 저장(필요하면 compress_level 등 조정 가능)
        if exif:
            try:
                params["pnginfo"] = exif  # PNG EXIF는 제한적(무시될 수 있음)
            except Exception:
                pass
        img.save(str(dst), format="PNG", **params)
    else:
        # 확장자 인식 불가 → JPEG로 강제 저장
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
    컨트롤러에서 사용 중인 이름과 호환되도록 제공.
    확장자가 .jpg/.jpeg가 아니어도 JPEG로 저장하도록 강제.
    """
    if path.suffix.lower() not in (".jpg", ".jpeg"):
        path = path.with_suffix(".jpg")
    save_image(img, path, quality=quality, icc=icc, exif=exif, fmt="JPEG")

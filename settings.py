from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional

DEFAULT_SIZES = [(1080, 1080), (1080, 1350), (1080, 1920)]
DEFAULT_BG = (255, 255, 255)
DEFAULT_WM_TEXT = "㈜하이브랩"

DEFAULT_WM_FILL = (0, 0, 0)
DEFAULT_WM_STROKE = (255, 255, 255)
DEFAULT_WM_STROKE_W = 2

@dataclass
class RootConfig:
    path: Path
    wm_text: str = DEFAULT_WM_TEXT

@dataclass
class AppSettings:
    output_root: Path = Path("")
    sizes: List[Tuple[int, int]] = None
    bg_color: Tuple[int, int, int] = DEFAULT_BG
    wm_opacity: int = 30
    wm_scale_pct: int = 5
    default_wm_text: str = DEFAULT_WM_TEXT

    wm_fill_color: Tuple[int, int, int] = DEFAULT_WM_FILL
    wm_stroke_color: Tuple[int, int, int] = DEFAULT_WM_STROKE
    wm_stroke_width: int = DEFAULT_WM_STROKE_W

    wm_anchor: Tuple[float, float] = (0.5, 0.5)

    # 🔹 새 옵션: TrueType/OpenType 폰트 파일 경로
    wm_font_path: Optional[Path] = None

    def __post_init__(self):
        if self.sizes is None:
            self.sizes = list(DEFAULT_SIZES)

def hex_to_rgb(hexstr: str) -> Tuple[int, int, int]:
    hs = hexstr.lstrip("#")
    if len(hs) == 3:
        hs = "".join([c * 2 for c in hs])
    try:
        r = int(hs[0:2], 16); g = int(hs[2:4], 16); b = int(hs[4:6], 16)
        return (r, g, b)
    except Exception:
        return DEFAULT_BG

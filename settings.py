from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

DEFAULT_SIZES = [(1080, 1080), (1080, 1350), (1080, 1920)]
DEFAULT_BG = (255, 255, 255)
DEFAULT_WM_TEXT = "© YourBrand"

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
    default_wm_text: str = DEFAULT_WM_TEXT  # 루트에 비어있으면 이 값으로 대체

    def __post_init__(self):
        if self.sizes is None:
            self.sizes = list(DEFAULT_SIZES)

def hex_to_rgb(hexstr: str) -> Tuple[int, int, int]:
    hs = hexstr.lstrip("#")
    if len(hs) == 3:
        hs = "".join([c * 2 for c in hs])
    try:
        r = int(hs[0:2], 16)
        g = int(hs[2:4], 16)
        b = int(hs[4:6], 16)
        return (r, g, b)
    except Exception:
        return DEFAULT_BG

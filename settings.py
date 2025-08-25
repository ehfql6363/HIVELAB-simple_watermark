# -*- coding: utf-8 -*-
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
import json

DEFAULT_SIZES = [(1080, 1080), (1080, 1350), (1080, 1920)]
DEFAULT_BG = (255, 255, 255)
DEFAULT_WM_TEXT = "하이브랩"
DEFAULT_WM_FILL = (0, 0, 0)
DEFAULT_WM_STROKE = (255, 255, 255)
DEFAULT_WM_STROKE_W = 2

# 사용자 설정 저장 위치 (~/.post_wm_tool.json)
CONFIG_PATH = Path.home() / ".post_wm_tool.json"

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

    # 선택 폰트 파일 경로
    wm_font_path: Optional[Path] = None

    # 🔹 게시물별 워터마크 위치 (키: "rootname/postname" → (nx, ny))
    post_anchors: Dict[str, Tuple[float, float]] = field(default_factory=dict)

    def __post_init__(self):
        if self.sizes is None:
            self.sizes = list(DEFAULT_SIZES)

    # ----- 직렬화 -----
    def to_dict(self) -> Dict[str, Any]:
        def p(v): return str(v) if isinstance(v, Path) else v
        return {
            "output_root": p(self.output_root),
            "sizes": self.sizes,
            "bg_color": list(self.bg_color),
            "wm_opacity": self.wm_opacity,
            "wm_scale_pct": self.wm_scale_pct,
            "default_wm_text": self.default_wm_text,
            "wm_fill_color": list(self.wm_fill_color),
            "wm_stroke_color": list(self.wm_stroke_color),
            "wm_stroke_width": self.wm_stroke_width,
            "wm_anchor": list(self.wm_anchor),
            "wm_font_path": p(self.wm_font_path) if self.wm_font_path else "",
            "post_anchors": {k: list(v) for k, v in self.post_anchors.items()},
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "AppSettings":
        def tup3(x, dflt):
            try:
                t = tuple(int(v) for v in x);
                return (t + dflt)[:3]
            except: return dflt
        def tup2f(x, dflt):
            try:
                t = tuple(float(v) for v in x)
                return (t + dflt)[:2]
            except: return dflt

        sizes = d.get("sizes") or DEFAULT_SIZES
        out = AppSettings(
            output_root=Path(d.get("output_root", "")) if d.get("output_root") else Path(""),
            sizes=[tuple(map(int, s)) for s in sizes],
            bg_color=tup3(d.get("bg_color", DEFAULT_BG), DEFAULT_BG),
            wm_opacity=int(d.get("wm_opacity", 30)),
            wm_scale_pct=int(d.get("wm_scale_pct", 5)),
            default_wm_text=d.get("default_wm_text", DEFAULT_WM_TEXT),
            wm_fill_color=tup3(d.get("wm_fill_color", DEFAULT_WM_FILL), DEFAULT_WM_FILL),
            wm_stroke_color=tup3(d.get("wm_stroke_color", DEFAULT_WM_STROKE), DEFAULT_WM_STROKE),
            wm_stroke_width=int(d.get("wm_stroke_width", DEFAULT_WM_STROKE_W)),
            wm_anchor=tup2f(d.get("wm_anchor", (0.5, 0.5)), (0.5, 0.5)),
            wm_font_path=Path(d["wm_font_path"]) if d.get("wm_font_path") else None,
            post_anchors={k: tuple(map(float, v)) for k, v in (d.get("post_anchors") or {}).items()},
        )
        return out

    # ----- 파일 IO -----
    def save(self, path: Path | None = None):
        path = path or CONFIG_PATH
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def load(path: Path | None = None) -> "AppSettings":
        path = path or CONFIG_PATH
        if not path.exists():
            return AppSettings()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return AppSettings.from_dict(data)
        except Exception:
            # 손상/불일치 시 기본값
            return AppSettings()

# color helpers
def hex_to_rgb(hexstr: str) -> Tuple[int, int, int]:
    hs = hexstr.lstrip("#")
    if len(hs) == 3: hs = "".join([c * 2 for c in hs])
    try:
        return (int(hs[0:2], 16), int(hs[2:4], 16), int(hs[4:6], 16))
    except Exception:
        return DEFAULT_BG

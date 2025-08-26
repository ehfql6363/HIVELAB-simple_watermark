# -*- coding: utf-8 -*-
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
import json

DEFAULT_SIZES = [(1080, 1080), (1080, 1350), (1080, 1920)]
DEFAULT_BG = (255, 255, 255)
DEFAULT_WM_TEXT = "워터마크"
DEFAULT_WM_FILL = (0, 0, 0)
DEFAULT_WM_STROKE = (255, 255, 255)
DEFAULT_WM_STROKE_W = 2

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
    wm_scale_pct: int = 20  # ← 의도적으로 크게 사용 중이면 OK
    default_wm_text: str = DEFAULT_WM_TEXT

    wm_fill_color: Tuple[int, int, int] = DEFAULT_WM_FILL
    wm_stroke_color: Tuple[int, int, int] = DEFAULT_WM_STROKE
    wm_stroke_width: int = DEFAULT_WM_STROKE_W

    wm_anchor: Tuple[float, float] = (0.5, 0.5)
    wm_font_path: Optional[Path] = None

    # 게시물별 앵커(세션 전용 메모리)
    post_anchors: Dict[str, Tuple[float, float]] = field(default_factory=dict)

    # 파일 다이얼로그 최근 폴더 기억(출력/폰트 각각)
    last_dir_output_dialog: Optional[Path] = None
    last_dir_font_dialog: Optional[Path] = None

    def __post_init__(self):
        if self.sizes is None:
            self.sizes = list(DEFAULT_SIZES)

    # -------- serialize --------
    def to_dict(self) -> Dict[str, Any]:
        def p(v): return str(v) if isinstance(v, Path) else v
        return {
            "output_root": p(self.output_root),
            "sizes": self.sizes,  # (0,0) 센티널도 그대로 저장
            "bg_color": list(self.bg_color),
            "wm_opacity": self.wm_opacity,
            "wm_scale_pct": self.wm_scale_pct,
            "default_wm_text": self.default_wm_text,
            "wm_fill_color": list(self.wm_fill_color),
            "wm_stroke_color": list(self.wm_stroke_color),
            "wm_stroke_width": self.wm_stroke_width,
            "wm_anchor": list(self.wm_anchor),
            "wm_font_path": p(self.wm_font_path) if self.wm_font_path else "",
            "last_dir_output_dialog": p(self.last_dir_output_dialog) if self.last_dir_output_dialog else "",
            "last_dir_font_dialog": p(self.last_dir_font_dialog) if self.last_dir_font_dialog else "",
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "AppSettings":
        def tup3(x, dflt):
            try:
                t = tuple(int(v) for v in x)
                return (t + dflt)[:3]
            except:
                return dflt
        def tup2f(x, dflt):
            try:
                t = tuple(float(v) for v in x)
                return (t + dflt)[:2]
            except:
                return dflt

        sizes = d.get("sizes") or DEFAULT_SIZES
        return AppSettings(
            output_root=Path(d.get("output_root", "")) if d.get("output_root") else Path(""),
            sizes=[tuple(map(int, s)) for s in sizes],
            bg_color=tup3(d.get("bg_color", DEFAULT_BG), DEFAULT_BG),
            wm_opacity=int(d.get("wm_opacity", 30)),
            wm_scale_pct=int(d.get("wm_scale_pct", 20)),
            default_wm_text=d.get("default_wm_text", DEFAULT_WM_TEXT),
            wm_fill_color=tup3(d.get("wm_fill_color", DEFAULT_WM_FILL), DEFAULT_WM_FILL),
            wm_stroke_color=tup3(d.get("wm_stroke_color", DEFAULT_WM_STROKE), DEFAULT_WM_STROKE),
            wm_stroke_width=int(d.get("wm_stroke_width", DEFAULT_WM_STROKE_W)),
            wm_anchor=tup2f(d.get("wm_anchor", (0.5, 0.5)), (0.5, 0.5)),
            wm_font_path=Path(d["wm_font_path"]) if d.get("wm_font_path") else None,
            post_anchors=dict(),  # ✅ 항상 빈 dict로 시작(세션 한정)
            last_dir_output_dialog=Path(d["last_dir_output_dialog"]) if d.get("last_dir_output_dialog") else None,
            last_dir_font_dialog=Path(d["last_dir_font_dialog"]) if d.get("last_dir_font_dialog") else None,
        )

    # -------- file IO --------
    def save(self, path: Path | None = None):
        path = path or CONFIG_PATH
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def load(path: Path | None = None) -> "AppSettings":
        path = path or CONFIG_PATH
        if not path.exists():
            return AppSettings()
        try:
            return AppSettings.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return AppSettings()

def hex_to_rgb(hexstr: str) -> Tuple[int, int, int]:
    hs = hexstr.lstrip("#")
    if len(hs) == 3:
        hs = "".join([c*2 for c in hs])
    try:
        return (int(hs[0:2],16), int(hs[2:4],16), int(hs[4:6],16))
    except Exception:
        return DEFAULT_BG

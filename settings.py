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
IMAGES_VROOT = "__DROPPED_IMAGES__"   # 가상 루트 키(드롭 파일 전용)

CONFIG_PATH = Path.home() / ".post_wm_tool.json"

@dataclass
class RootConfig:
    path: Path
    wm_text: str = DEFAULT_WM_TEXT

@dataclass
class AppSettings:
    output_root: Path = Path("")
    sizes: List[Tuple[int, int]] = field(default_factory=lambda: [(1080, 1080)])
    bg_color: Tuple[int, int, int] = (255, 255, 255)
    wm_opacity: int = 30
    wm_scale_pct: int = 20
    default_wm_text: str = "워터마크"
    wm_fill_color: Tuple[int, int, int] = (0, 0, 0)
    wm_stroke_color: Tuple[int, int, int] = (255, 255, 255)
    wm_stroke_width: int = 2
    wm_anchor: Tuple[float, float] = (0.5, 0.5)
    wm_font_path: Optional[Path] = None
    last_dir_output_dialog: Optional[Path] = None
    last_dir_font_dialog: Optional[Path] = None
    autocomplete_texts: List[str] = field(default_factory=list)

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
            "autocomplete_texts": list(dict.fromkeys([t.strip() for t in self.autocomplete_texts if str(t).strip()])), # ✅ 중복 제거
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
        s =  AppSettings(
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
            last_dir_output_dialog=Path(d["last_dir_output_dialog"]) if d.get("last_dir_output_dialog") else None,
            last_dir_font_dialog=Path(d["last_dir_font_dialog"]) if d.get("last_dir_font_dialog") else None,
        )

        s.autocomplete_texts = [str(t).strip() for t in d.get("autocomplete_texts", []) if str(t).strip()]
        return s

    # -------- file IO --------
    def save(self) -> None:
        data = {
            "output_root": str(self.output_root) if self.output_root else "",
            "sizes": [list(map(int, t)) for t in self.sizes],
            "bg_color": list(self.bg_color),
            "wm_opacity": int(self.wm_opacity),
            "wm_scale_pct": int(self.wm_scale_pct),
            "default_wm_text": self.default_wm_text,
            "wm_fill_color": list(self.wm_fill_color),
            "wm_stroke_color": list(self.wm_stroke_color),
            "wm_stroke_width": int(self.wm_stroke_width),
            "wm_anchor": list(self.wm_anchor),
            "wm_font_path": str(self.wm_font_path) if self.wm_font_path else "",
            "last_dir_output_dialog": str(self.last_dir_output_dialog) if self.last_dir_output_dialog else "",
            "last_dir_font_dialog": str(self.last_dir_font_dialog) if self.last_dir_font_dialog else "",
            "autocomplete_texts": list(dict.fromkeys([t.strip() for t in self.autocomplete_texts if str(t).strip()])),
        }
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def load() -> "AppSettings":
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return AppSettings()

        s = AppSettings()
        s.output_root = Path(data.get("output_root", "")) if data.get("output_root") else Path("")
        s.sizes = [tuple(map(int, t)) for t in data.get("sizes", [])] or [(1080, 1080)]
        s.bg_color = tuple(data.get("bg_color", (255, 255, 255)))
        s.wm_opacity = int(data.get("wm_opacity", 30))
        s.wm_scale_pct = int(data.get("wm_scale_pct", 20))
        s.default_wm_text = data.get("default_wm_text", "워터마크")
        s.wm_fill_color = tuple(data.get("wm_fill_color", (0, 0, 0)))
        s.wm_stroke_color = tuple(data.get("wm_stroke_color", (255, 255, 255)))
        s.wm_stroke_width = int(data.get("wm_stroke_width", 2))
        s.wm_anchor = tuple(data.get("wm_anchor", (0.5, 0.5)))
        font_str = data.get("wm_font_path") or ""
        s.wm_font_path = Path(font_str) if font_str else None
        out_dir = data.get("last_dir_output_dialog") or ""
        s.last_dir_output_dialog = Path(out_dir) if out_dir else None
        font_dir = data.get("last_dir_font_dialog") or ""
        s.last_dir_font_dialog = Path(font_dir) if font_dir else None
        return s

def hex_to_rgb(hexstr: str) -> Tuple[int, int, int]:
    hs = hexstr.lstrip("#")
    if len(hs) == 3:
        hs = "".join([c*2 for c in hs])
    try:
        return (int(hs[0:2],16), int(hs[2:4],16), int(hs[4:6],16))
    except Exception:
        return DEFAULT_BG

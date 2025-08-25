from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Dict, Optional

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageOps, ImageDraw, ImageFont, ImageTk

# --------------------------- Config Defaults ---------------------------

DEFAULT_SIZES = [(1080, 1080), (1080, 1350), (1080, 1920)]
DEFAULT_BG = (255, 255, 255)  # white
DEFAULT_WM_TEXT = "© YourBrand"
DEFAULT_WM_OPACITY = 30  # 0..100
DEFAULT_WM_SCALE_PCT = 5  # % of short side
DEFAULT_FONT_CANDIDATES = [
    # Common Windows fonts first
    "arial.ttf", "tahoma.ttf", "segoeui.ttf",
    # DejaVu as a common fallback on many systems
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# --------------------------- Data Model ---------------------------

@dataclass
class AppSettings:
    input_root: Path = Path("")
    output_root: Path = Path("")
    sizes: List[Tuple[int, int]] = None
    bg_color: Tuple[int, int, int] = DEFAULT_BG
    wm_text: str = DEFAULT_WM_TEXT
    wm_opacity: int = DEFAULT_WM_OPACITY
    wm_scale_pct: int = DEFAULT_WM_SCALE_PCT

    def __post_init__(self):
        if self.sizes is None:
            self.sizes = list(DEFAULT_SIZES)

# --------------------------- Helpers & Image Ops ---------------------------

def exif_transpose(image: Image.Image) -> Image.Image:
    try:
        return ImageOps.exif_transpose(image)
    except Exception:
        return image

def load_image(path: Path) -> Image.Image:
    im = Image.open(str(path))
    im = exif_transpose(im)
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if im.mode == "LA" else "RGB")
    return im

def resize_contain(img: Image.Image, target: Tuple[int, int], bg: Tuple[int, int, int]) -> Image.Image:
    """Contain resize: keep aspect, add padding to fill target canvas."""
    Wt, Ht = target
    Ws, Hs = img.size
    scale = min(Wt / Ws, Ht / Hs)
    newW, newH = max(1, int(Ws * scale)), max(1, int(Hs * scale))
    img_resized = img.resize((newW, newH), Image.Resampling.LANCZOS)

    canvas = Image.new("RGB", (Wt, Ht), bg)
    ox = (Wt - newW) // 2
    oy = (Ht - newH) // 2
    if img_resized.mode == "RGBA":
        canvas.paste(img_resized, (ox, oy), img_resized)
    else:
        canvas.paste(img_resized, (ox, oy))
    return canvas

def pick_font(size: int) -> ImageFont.ImageFont:
    for cand in DEFAULT_FONT_CANDIDATES:
        try:
            return ImageFont.truetype(cand, size=size)
        except Exception:
            continue
    return ImageFont.load_default()

def measure_text(font: ImageFont.FreeTypeFont, text: str, stroke_width: int = 0) -> Tuple[int, int]:
    dummy_img = Image.new("RGB", (10, 10))
    d = ImageDraw.Draw(dummy_img)
    bbox = d.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    return w, h

def find_font_size_for_width(text: str, target_width: int, low: int = 8, high: int = 512, stroke_width: int = 2) -> int:
    """Binary search a font size whose rendered width is <= target_width (maximal)."""
    best = low
    while low <= high:
        mid = (low + high) // 2
        font = pick_font(mid)
        w, _ = measure_text(font, text, stroke_width=stroke_width)
        if w <= target_width:
            best = mid
            low = mid + 1
        else:
            high = mid - 1
    return best

def add_center_watermark(img: Image.Image, text: str, opacity_pct: int, scale_pct: int) -> Image.Image:
    if not text:
        return img

    W, H = img.size
    short_side = min(W, H)
    target_w = max(1, int(short_side * (scale_pct / 100.0)))

    stroke_width = 2
    font_size = find_font_size_for_width(text, target_w, stroke_width=stroke_width)
    font = pick_font(font_size)

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    tw, th = measure_text(font, text, stroke_width=stroke_width)
    x = (W - tw) // 2
    y = (H - th) // 2

    alpha = int(255 * (opacity_pct / 100.0))
    d.text(
        (x, y),
        text,
        font=font,
        fill=(0, 0, 0, alpha),  # black fill
        stroke_width=stroke_width,
        stroke_fill=(255, 255, 255, alpha),  # white stroke for contrast
    )

    base = img.convert("RGBA")
    out = Image.alpha_composite(base, overlay)
    return out.convert("RGB")

def process_image(src: Path, target: Tuple[int, int], settings: AppSettings) -> Image.Image:
    im = load_image(src)
    canvas = resize_contain(im, target, settings.bg_color)
    out = add_center_watermark(canvas, settings.wm_text, settings.wm_opacity, settings.wm_scale_pct)
    return out

def save_jpeg(img: Image.Image, dst: Path, quality: int = 92) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(dst), format="JPEG", quality=quality, subsampling=1, optimize=True)

# --------------------------- Scanning ---------------------------

def is_image(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() in SUPPORTED_EXTS

def numeric_key(p: Path):
    # Prefer numeric stem ordering if possible (1,2,10)
    try:
        return (0, int(p.stem))
    except Exception:
        return (1, p.name.lower())

def scan_posts(input_root: Path) -> Dict[str, List[Path]]:
    posts: Dict[str, List[Path]] = {}
    if not input_root or not input_root.exists():
        return posts
    for child in sorted(input_root.iterdir(), key=lambda p: p.name.lower()):
        if child.is_dir():
            imgs = [p for p in sorted(child.iterdir(), key=numeric_key) if is_image(p)]
            if imgs:
                posts[child.name] = imgs
    return posts

# --------------------------- GUI ---------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Post Watermark & Resize (MVP)")
        self.geometry("1100x680")

        self.settings = AppSettings()
        self.posts: Dict[str, List[Path]] = {}
        self.preview_tk_before = None
        self.preview_tk_after = None

        self._build_ui()

    def _build_ui(self):
        # Top controls
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=6)

        # Input root
        ttk.Label(top, text="Input Root:").grid(row=0, column=0, sticky="w")
        self.var_input = tk.StringVar()
        ttk.Entry(top, textvariable=self.var_input, width=50).grid(row=0, column=1, sticky="we", padx=4)
        ttk.Button(top, text="Browse…", command=self.on_browse_input).grid(row=0, column=2, padx=4)

        # Output root
        ttk.Label(top, text="Output Root:").grid(row=1, column=0, sticky="w")
        self.var_output = tk.StringVar()
        ttk.Entry(top, textvariable=self.var_output, width=50).grid(row=1, column=1, sticky="we", padx=4)
        ttk.Button(top, text="Browse…", command=self.on_browse_output).grid(row=1, column=2, padx=4)

        # Sizes
        size_frame = ttk.Frame(top)
        size_frame.grid(row=0, column=3, rowspan=2, padx=8, sticky="w")
        ttk.Label(size_frame, text="Target Sizes:").grid(row=0, column=0, columnspan=3, sticky="w")
        self.size_vars: Dict[Tuple[int, int], tk.BooleanVar] = {}
        for i, (w, h) in enumerate(DEFAULT_SIZES):
            var = tk.BooleanVar(value=True)  # all ON by default
            cb = ttk.Checkbutton(size_frame, text=f"{w}x{h}", variable=var)
            cb.grid(row=1, column=i, padx=4, sticky="w")
            self.size_vars[(w, h)] = var

        # Watermark (center defaults)
        wm_frame = ttk.Frame(top)
        wm_frame.grid(row=0, column=4, rowspan=2, padx=8, sticky="w")
        ttk.Label(wm_frame, text="Watermark (center)").grid(row=0, column=0, columnspan=4, sticky="w")

        ttk.Label(wm_frame, text="Text").grid(row=1, column=0, sticky="e")
        self.var_wm_text = tk.StringVar(value=self.settings.wm_text)
        ttk.Entry(wm_frame, textvariable=self.var_wm_text, width=24).grid(row=1, column=1, sticky="w", padx=4)

        ttk.Label(wm_frame, text="Opacity").grid(row=1, column=2, sticky="e")
        self.var_wm_opacity = tk.IntVar(value=self.settings.wm_opacity)
        ttk.Spinbox(wm_frame, from_=0, to=100, textvariable=self.var_wm_opacity, width=5).grid(row=1, column=3, sticky="w")

        ttk.Label(wm_frame, text="Scale % (short side)").grid(row=2, column=0, sticky="e")
        self.var_wm_scale = tk.IntVar(value=self.settings.wm_scale_pct)
        ttk.Spinbox(wm_frame, from_=1, to=50, textvariable=self.var_wm_scale, width=5).grid(row=2, column=1, sticky="w")

        ttk.Label(wm_frame, text="BG #RRGGBB").grid(row=2, column=2, sticky="e")
        self.var_bg = tk.StringVar(value="#FFFFFF")
        ttk.Entry(wm_frame, textvariable=self.var_bg, width=8).grid(row=2, column=3, sticky="w")

        # Middle: left posts list, right preview
        mid = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        mid.pack(fill="both", expand=True, padx=8, pady=6)

        left = ttk.Frame(mid, width=260)
        right = ttk.Frame(mid)
        mid.add(left, weight=1)
        mid.add(right, weight=3)

        ttk.Label(left, text="Posts").pack(anchor="w")
        self.lb_posts = tk.Listbox(left, height=20)
        self.lb_posts.pack(fill="both", expand=True, pady=4)
        self.lb_posts.bind("<<ListboxSelect>>", self.on_select_post)

        self.lbl_post_info = ttk.Label(left, text="0 posts")
        self.lbl_post_info.pack(anchor="w")

        prev_top = ttk.Frame(right)
        prev_top.pack(fill="x")
        ttk.Button(prev_top, text="Scan Posts", command=self.on_scan).pack(side="left")
        ttk.Button(prev_top, text="Preview Selected", command=self.on_preview).pack(side="left", padx=6)

        prev = ttk.Frame(right)
        prev.pack(fill="both", expand=True, pady=8)

        self.lbl_before = ttk.Label(prev, text="Before")
        self.lbl_after = ttk.Label(prev, text="After")
        self.lbl_before.grid(row=0, column=0, sticky="nsew", padx=4)
        self.lbl_after.grid(row=0, column=1, sticky="nsew", padx=4)
        prev.columnconfigure(0, weight=1)
        prev.columnconfigure(1, weight=1)
        prev.rowconfigure(0, weight=1)

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=8, pady=6)

        self.progress = ttk.Progressbar(bottom, mode="determinate")
        self.progress.pack(fill="x", expand=True, side="left", padx=4)
        ttk.Button(bottom, text="Start Batch", command=self.on_start_batch).pack(side="left", padx=6)

    # ------------------ UI Callbacks ------------------

    def on_browse_input(self):
        path = filedialog.askdirectory(title="Select Input Root (Contains posts as subfolders)")
        if path:
            self.var_input.set(path)

    def on_browse_output(self):
        path = filedialog.askdirectory(title="Select Output Root")
        if path:
            self.var_output.set(path)

    def on_scan(self):
        root = Path(self.var_input.get().strip())
        if not root.exists():
            messagebox.showerror("Error", "Input root does not exist.")
            return
        self.posts = scan_posts(root)
        self.lb_posts.delete(0, tk.END)
        for name in self.posts.keys():
            self.lb_posts.insert(tk.END, name)
        self.lbl_post_info.configure(text=f"{len(self.posts)} posts found.")

    def on_select_post(self, _evt):
        self.preview_clear()

    def preview_clear(self):
        self.lbl_before.configure(image="", text="Before")
        self.lbl_after.configure(image="", text="After")
        self.preview_tk_before = None
        self.preview_tk_after = None

    def collect_settings(self) -> AppSettings:
        sizes = [s for s, var in self.size_vars.items() if var.get()] or list(DEFAULT_SIZES)
        bg_hex = self.var_bg.get().strip() or "#FFFFFF"
        bg = self.hex_to_rgb(bg_hex)
        in_root = Path(self.var_input.get().strip())
        out_root = Path(self.var_output.get().strip()) if self.var_output.get().strip() else in_root / "export"
        return AppSettings(
            input_root=in_root,
            output_root=out_root,
            sizes=sizes,
            bg_color=bg,
            wm_text=self.var_wm_text.get(),
            wm_opacity=int(self.var_wm_opacity.get()),
            wm_scale_pct=int(self.var_wm_scale.get()),
        )

    @staticmethod
    def hex_to_rgb(hexstr: str) -> Tuple[int, int, int]:
        hs = hexstr.lstrip("#")
        if len(hs) == 3:
            hs = "".join([c*2 for c in hs])
        try:
            r = int(hs[0:2], 16)
            g = int(hs[2:4], 16)
            b = int(hs[4:6], 16)
            return (r, g, b)
        except Exception:
            return DEFAULT_BG

    def on_preview(self):
        sel = self.lb_posts.curselection()
        if not sel:
            messagebox.showinfo("Preview", "Select a post from the left list.")
            return
        post_name = self.lb_posts.get(sel[0])
        files = self.posts.get(post_name, [])
        if not files:
            messagebox.showinfo("Preview", "No images in this post.")
            return

        src = files[0]
        settings = self.collect_settings()
        try:
            before = load_image(src).convert("RGB")
            after = process_image(src, settings.sizes[0], settings)  # preview first selected size
        except Exception as e:
            messagebox.showerror("Preview Error", str(e))
            return

        self.preview_tk_before = self.to_tk_image(before, max_w=520, max_h=520)
        self.preview_tk_after = self.to_tk_image(after, max_w=520, max_h=520)

        self.lbl_before.configure(image=self.preview_tk_before, text="")
        self.lbl_after.configure(image=self.preview_tk_after, text="")

    def to_tk_image(self, img: Image.Image, max_w: int, max_h: int):
        W, H = img.size
        scale = min(max_w / W, max_h / H, 1.0)
        newW, newH = int(W * scale), int(H * scale)
        thumb = img.resize((newW, newH), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(thumb)

    def on_start_batch(self):
        if not self.posts:
            messagebox.showinfo("Run", "No posts found. Click 'Scan Posts' first.")
            return
        settings = self.collect_settings()

        total = sum(len(v) for v in self.posts.values()) * len(settings.sizes)
        if total == 0:
            messagebox.showinfo("Run", "Nothing to process.")
            return

        self.progress.configure(maximum=total, value=0)
        t = threading.Thread(target=self._run_batch, args=(settings, total), daemon=True)
        t.start()

    def _run_batch(self, settings: AppSettings, total: int):
        processed = 0
        try:
            for post, files in self.posts.items():
                for src in files:
                    for (w, h) in settings.sizes:
                        try:
                            out_img = process_image(src, (w, h), settings)
                            dst = settings.output_root / post / f"{w}x{h}" / (src.stem + "_wm.jpg")
                            save_jpeg(out_img, dst)
                        except Exception as e:
                            print(f"[ERROR] {src} {w}x{h}: {e}")
                        finally:
                            processed += 1
                            self.progress.after(0, self.progress.configure, {"value": processed})
            self.progress.after(0, lambda: messagebox.showinfo("Done", f"Finished. Processed {processed} items."))
        except Exception as e:
            self.progress.after(0, lambda: messagebox.showerror("Run Error", str(e)))

# --------------------------- Main ---------------------------

if __name__ == "__main__":
    app = App()
    app.mainloop()

from __future__ import annotations

import threading
from pathlib import Path
from typing import Dict, List, Tuple

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk

from settings import AppSettings, DEFAULT_SIZES, DEFAULT_BG, hex_to_rgb
from services.discovery import scan_posts
from services.image_ops import load_image
from services.resize import resize_contain
from services.watermark import add_center_watermark
from services.writer import save_jpeg


def process_image(src: Path, target: Tuple[int, int], settings: AppSettings):
    """Pipeline: load -> contain -> center watermark."""
    im = load_image(src)
    canvas = resize_contain(im, target, settings.bg_color)
    out = add_center_watermark(
        canvas,
        text=settings.wm_text,
        opacity_pct=settings.wm_opacity,
        scale_pct=settings.wm_scale_pct,
    )
    return out


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Post Watermark & Resize (Phase 1)")
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
        bg = hex_to_rgb(bg_hex)
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


if __name__ == "__main__":
    app = App()
    app.mainloop()

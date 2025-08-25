from PIL import Image

def resize_contain(img: Image.Image, target: tuple, bg: tuple) -> Image.Image:
    Wt, Ht = target
    Ws, Hs = img.size
    scale = min(Wt / Ws, Ht / Hs)
    newW, newH = max(1, int(Ws * scale)), max(1, int(Hs * scale))
    r = img.resize((newW, newH), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (Wt, Ht), bg)
    ox, oy = (Wt - newW) // 2, (Ht - newH) // 2
    canvas.paste(r, (ox, oy), r if r.mode == "RGBA" else None)
    return canvas

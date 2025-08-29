from PIL import Image

def resize_contain(img: Image.Image, target: tuple, bg: tuple) -> Image.Image:
    """정확한 품질(LANCZOS) 경로: 배치 저장 등 최종 결과용."""
    Wt, Ht = map(int, target)
    if (Wt, Ht) == (0, 0):
        return img
    Ws, Hs = img.size
    scale = min(Wt / Ws, Ht / Hs)
    newW, newH = max(1, int(Ws * scale)), max(1, int(Hs * scale))
    r = img.resize((newW, newH), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (Wt, Ht), bg)
    ox, oy = (Wt - newW) // 2, (Ht - newH) // 2
    canvas.paste(r, (ox, oy))
    return canvas

def resize_contain_fast(img: Image.Image, target: tuple, bg: tuple) -> Image.Image:
    """
    프리뷰용 빠른 경로:
    - 큰 다운스케일은 먼저 thumbnail(BICUBIC) → 최종 맞춤
    - 미세 스케일은 BICUBIC 한 번
    """
    Wt, Ht = map(int, target)
    if (Wt, Ht) == (0, 0):
        return img
    Ws, Hs = img.size
    if Ws == 0 or Hs == 0:
        return Image.new("RGB", (Wt, Ht), bg)

    scale = min(Wt / Ws, Ht / Hs)
    newW, newH = max(1, int(Ws * scale)), max(1, int(Hs * scale))

    # 큰 축소면 먼저 thumbnail로 러프 다운스케일
    r = img
    if max(Ws, Hs) > max(Wt, Ht) * 1.8:
        r = img.copy()
        r.thumbnail((Wt, Ht), Image.Resampling.BICUBIC)
        Ws2, Hs2 = r.size
        scale2 = min(Wt / Ws2, Ht / Hs2)
        newW, newH = max(1, int(Ws2 * scale2)), max(1, int(Hs2 * scale2))

    if r.size != (newW, newH):
        r = r.resize((newW, newH), Image.Resampling.BICUBIC)

    canvas = Image.new("RGB", (Wt, Ht), bg)
    ox, oy = (Wt - newW) // 2, (Ht - newH) // 2
    canvas.paste(r, (ox, oy))
    return canvas

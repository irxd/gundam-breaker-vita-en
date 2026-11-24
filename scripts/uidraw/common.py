"""Shared drawing helpers for the UI texture redraws (scripts/draw_ui.py runs the jobs)."""
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont  # noqa: F401

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "game", "ui_png")
FONT = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", "bahnschrift.ttf")

ORANGE = dict(top=(255, 236, 170), bottom=(236, 128, 16), glow=(200, 90, 0))


def original(path):
    """The original texture (exported by scripts/export_ui.py) as RGBA."""
    return Image.open(os.path.join(SRC, *path.split("/")) + ".png").convert("RGBA")


def font(size, variation="Bold Condensed"):
    f = ImageFont.truetype(FONT, size)
    try:
        f.set_variation_by_name(variation)
    except (OSError, ValueError):
        pass
    return f


def fit_font(text, box, height, variation="Bold Condensed"):
    """Largest font up to cap height `height` px whose text fits the box width."""
    size = height * 2
    while size > 6:
        f = font(size, variation)
        x0, y0, x1, y1 = f.getbbox(text)
        if y1 - y0 <= height and x1 - x0 <= box[2] - box[0]:
            return f
        size -= 1
    return font(6, variation)


def glow(base, text, colours, height, box, scanline=2):
    w, h = base.size
    f = fit_font(text, box, height)
    x0, y0, x1, y1 = f.getbbox(text)
    ox = (box[0] + box[2] - (x1 - x0)) // 2 - x0
    oy = (box[1] + box[3] - (y1 - y0)) // 2 - y0
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((ox, oy), text, font=f, fill=255)
    # vertical gradient over the glyph rows
    top, bottom = colours["top"], colours["bottom"]
    grad = Image.new("RGB", (w, h))
    gd = ImageDraw.Draw(grad)
    gy0, gy1 = oy + y0, oy + y1
    for y in range(h):
        t = min(1.0, max(0.0, (y - gy0) / max(1, gy1 - gy0)))
        c = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom))
        if scanline and y % scanline == 1:
            c = tuple(v * 3 // 4 for v in c)
        gd.line((0, y, w, y), fill=c)
    halo = Image.new("RGB", (w, h), colours["glow"])
    halo_mask = mask.filter(ImageFilter.GaussianBlur(4)).point(lambda v: min(255, v * 2))
    out = Image.new("RGB", (w, h), (0, 0, 0))
    out = Image.composite(halo, out, halo_mask)
    out = Image.composite(grad, out, mask)
    return out.convert("RGBA")



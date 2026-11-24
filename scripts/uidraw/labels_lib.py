"""Helpers for the stylised label redraws in labels.py: erase the Japanese, render English text masks, colour them
like the original (colours sampled row by row from the original glyphs), glow on black or composite on plates.

Boxes are (x0, y0, x1, y1), x1/y1 exclusive.
"""
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .common import font, original

SS = 4  # supersampling for text masks


def lum(p):
    return (p[0] * 299 + p[1] * 587 + p[2] * 114) // 1000


# ---------------------------------------------------------------- erase

def erase(img, how, boxes, **kw):
    """Erase boxes in place. how: 'black' (opaque black, glow textures), 'clear' (transparent), 'fill' (kw colour),
    'rows' (per row, interpolate between clean columns kw left=(x0,x1), right=(x0,x1); one of them may be None),
    'copy' (kw src=image or path, sx/sy offset: copy the same box from src shifted by (sx, sy))."""
    for box in boxes:
        x0, y0, x1, y1 = box
        if how == "black":
            img.paste((0, 0, 0, 255), box)
        elif how == "clear":
            img.paste((0, 0, 0, 0), box)
        elif how == "fill":
            img.paste(kw["colour"], box)
        elif how == "copy":
            src = kw["src"]
            if isinstance(src, str):
                src = original(src)
            sx, sy = kw.get("sx", 0), kw.get("sy", 0)
            img.paste(src.crop((x0 + sx, y0 + sy, x1 + sx, y1 + sy)), (x0, y0))
        elif how == "rows":
            left, right = kw.get("left"), kw.get("right")
            px = img.load()
            for y in range(y0, y1):
                def avg(r):
                    if not r:
                        return None
                    vals = [px[x, y] for x in range(r[0], r[1])]
                    return tuple(sum(v[i] for v in vals) / len(vals) for i in range(4))
                a, b = avg(left), avg(right)
                a = a or b
                b = b or a
                for x in range(x0, x1):
                    t = (x - x0) / max(1, x1 - x0 - 1)
                    px[x, y] = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(4))
        elif how == "inpaint":
            _inpaint(img, box, kw.get("thr", 90), kw.get("grow", 2))
        else:
            raise ValueError(how)
    return img


def _inpaint(img, box, thr, grow):
    """Replace bright pixels (luminance > thr, grown by `grow` px) inside box by diffusing the surrounding
    pixels inwards (for text over a picture, e.g. the NO IMAGE silhouette). Neighbours are taken from the
    same row parity so 2-px scanlines survive."""
    x0, y0, x1, y1 = box
    region = img.crop(box)
    w, h = region.size
    m = Image.new("L", (w, h), 0)
    rp, mp = region.load(), m.load()
    for y in range(h):
        for x in range(w):
            if lum(rp[x, y]) > thr:
                mp[x, y] = 255
    if grow:
        m = m.filter(ImageFilter.MaxFilter(grow * 2 + 1))
        mp = m.load()
    hole = {(x, y) for y in range(h) for x in range(w) if mp[x, y]}
    while hole:
        done = {}
        for (x, y) in hole:
            acc, n = [0, 0, 0, 0], 0
            for dx, dy in ((1, 0), (-1, 0), (0, 2), (0, -2), (1, 2), (-1, -2), (1, -2), (-1, 2)):  # keep scanlines
                q = (x + dx, y + dy)
                if 0 <= q[0] < w and 0 <= q[1] < h and q not in hole:
                    v = rp[q]
                    for i in range(4):
                        acc[i] += v[i]
                    n += 1
            if n >= 2:
                done[(x, y)] = tuple(a // n for a in acc)
        if not done:
            break
        for q, v in done.items():
            rp[q] = v
        hole -= set(done)
    img.paste(region, (x0, y0))


# ---------------------------------------------------------------- text masks

def _advance_layout(text, f, spacing):
    """x positions (supersampled units) of each char."""
    xs, x = [], 0.0
    for ch in text:
        xs.append(x)
        x += f.getlength(ch) + spacing * SS
    return xs


def text_mask(size, text, box, cap, variation="Bold Condensed", spacing=0.0, min_spacing=None, align="c",
              valign="c", squash_min=0.78, italic=0.0, dy=0, dx=0):
    """L mask of `size` with `text` placed in `box`. cap = cap height (px) of capital letters. If the text is too
    wide: spacing is reduced down to min_spacing, then the text is squashed horizontally down to squash_min, then the
    font shrinks. Vertical placement centres the cap height (valign 'c'), or puts the caps at the box top ('t') or
    the baseline at the box bottom ('b'). `italic` = shear (x shift per px of height)."""
    bw = box[2] - box[0]
    if min_spacing is None:
        min_spacing = min(spacing, max(0.0, spacing * 0.35))
    cur = cap
    while True:
        f = None
        # font size whose 'H' is `cur` px tall (supersampled)
        s = int(cur * SS * 1.45)
        while s > 4:
            f = font(s, variation)
            hb = f.getbbox("H")
            if hb[3] - hb[1] <= cur * SS:
                break
            s -= 1
        sp = spacing
        while True:
            xs = _advance_layout(text, f, sp)
            ink = _ink_width(text, f, xs)
            if ink <= bw * SS or sp <= min_spacing:
                break
            sp = max(min_spacing, sp - 0.25)
        sq = min(1.0, bw * SS / max(1, ink))
        if sq >= squash_min or cur <= 5:
            break
        cur -= 0.5
    hb = f.getbbox("H")
    capt, caph = hb[1], hb[3] - hb[1]
    asc, desc = f.getmetrics()
    W = int(ink + 8 * SS + abs(italic) * (asc + desc))
    H = asc + desc + 4 * SS
    big = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(big)
    for ch, x in zip(text, xs):
        d.text((x + 4 * SS - _ink_left(text, f), 2 * SS), ch, font=f, fill=255)
    if italic:
        big = big.transform(big.size, Image.AFFINE, (1, italic, -italic * (2 * SS + capt + caph), 0, 1, 0),
                            resample=Image.BICUBIC)
    bb = big.getbbox()
    if not bb:
        return Image.new("L", size, 0)
    lx0, lx1 = bb[0], bb[2]
    big = big.crop((lx0, 0, lx1, H))
    neww = max(1, round(big.width * min(1.0, sq) / SS))
    newh = max(1, round(H / SS))
    small = big.resize((neww, newh), Image.LANCZOS)
    small = small.point(lambda v: min(255, v))
    cap_top = (2 * SS + capt) / SS
    cap_h = caph / SS
    if align == "c":
        x = box[0] + (bw - neww) // 2
    elif align == "l":
        x = box[0]
    else:
        x = box[2] - neww
    if valign == "c":
        y = box[1] + ((box[3] - box[1]) - cap_h) / 2 - cap_top
    elif valign == "t":
        y = box[1] - cap_top
    else:
        y = box[3] - (cap_top + cap_h)
    out = Image.new("L", size, 0)
    out.paste(small, (int(x + dx), int(round(y + dy))))
    return out


def _ink_left(text, f):
    return min(0, f.getbbox(text[0])[0])


def _ink_width(text, f, xs):
    x0 = xs[0] + f.getbbox(text[0])[0]
    x1 = max(x + f.getbbox(ch)[2] for ch, x in zip(text, xs) if ch.strip()) if text.strip() else x0
    return x1 - x0


def masks_union(size, *masks):
    out = Image.new("L", size, 0)
    for m in masks:
        out = ImageChops.lighter(out, m)
    return out


# ---------------------------------------------------------------- colours

def sample_rows(img, box, frac=0.12, minlum=60):
    """Glyph colour per row of the original: mean of the brightest `frac` of opaque pixels in each row of box.
    Returns (rows {y: (r,g,b)}, span (y0, y1)) where span = rows whose brightest pixels reach half the maximum."""
    px = img.load()
    rows, peak = {}, {}
    for y in range(box[1], box[3]):
        vals = [px[x, y] for x in range(box[0], box[2]) if px[x, y][3] > 96]
        if not vals:
            continue
        vals.sort(key=lum, reverse=True)
        top = vals[:max(1, int(len(vals) * frac))]
        c = tuple(sum(v[i] for v in top) // len(top) for i in range(3))
        rows[y] = c
        peak[y] = lum(top[0])
    if not peak:
        raise ValueError(f"nothing to sample in {box}")
    m = max(peak.values())
    span = [y for y in peak if peak[y] >= max(minlum, m * 0.5)]
    return rows, (min(span), max(span) + 1)


def mean_colour(img, box, lo, hi):
    """Mean colour of pixels with luminance in [lo, hi) (e.g. the halo)."""
    px = img.load()
    vals = [px[x, y] for y in range(box[1], box[3]) for x in range(box[0], box[2]) if lo <= lum(px[x, y]) < hi]
    if not vals:
        return (0, 0, 0)
    return tuple(sum(v[i] for v in vals) // len(vals) for i in range(3))


def gradient_layer(size, mask, rows, span, scale=1.0):
    """RGB image: each row of the mask's ink coloured like the original row at the same relative height."""
    w, h = size
    bb = mask.getbbox()
    out = Image.new("RGB", size, (0, 0, 0))
    if not bb:
        return out
    d = ImageDraw.Draw(out)
    my0, my1 = bb[1], bb[3]
    sy0, sy1 = span
    keys = sorted(rows)
    for y in range(h):
        t = (y - my0) / max(1, my1 - my0 - 1)
        t = min(1.0, max(0.0, t))
        oy = round(sy0 + t * (sy1 - 1 - sy0))
        oy = min(keys, key=lambda k: abs(k - oy))
        c = tuple(min(255, round(v * scale)) for v in rows[oy])
        d.line((0, y, w, y), fill=c)
    return out


def fixed_gradient(size, mask, top, bottom, scanline=0, dark=0.75):
    w, h = size
    bb = mask.getbbox() or (0, 0, w, h)
    out = Image.new("RGB", size)
    d = ImageDraw.Draw(out)
    for y in range(h):
        t = min(1.0, max(0.0, (y - bb[1]) / max(1, bb[3] - bb[1] - 1)))
        c = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom))
        if scanline and (y - bb[1]) % scanline == scanline - 1:
            c = tuple(round(v * dark) for v in c)
        d.line((0, y, w, y), fill=c)
    return out


# ---------------------------------------------------------------- compositing

def add_glow(base, mask, core, halo_colour, radius=3.0, strength=1.6, smear=0, smear_k=0.35, wide=0, wide_k=0.5):
    """Glow on an opaque black texture (DXT1, drawn additively by the game): base + halo + core."""
    w, h = base.size
    out = base.convert("RGB")
    halo = mask.filter(ImageFilter.GaussianBlur(radius)).point(lambda v: min(255, int(v * strength)))
    if wide:
        wm = mask.filter(ImageFilter.GaussianBlur(wide)).point(lambda v: min(255, int(v * wide_k * 3)))
        halo = ImageChops.lighter(halo, wm)
    if smear:
        # vertical ghost streaks above/below the glyphs (count_head style)
        sm = mask.resize((w, max(1, h // smear)), Image.BOX).resize((w, h), Image.BILINEAR)
        sm = sm.filter(ImageFilter.BoxBlur(1)).point(lambda v: int(v * smear_k))
        halo = ImageChops.lighter(halo, sm)
    hl = Image.composite(Image.new("RGB", (w, h), halo_colour), Image.new("RGB", (w, h), 0), halo)
    out = ImageChops.add(out, hl)
    out = Image.composite(core, out, mask)
    res = out.convert("RGBA")
    res.putalpha(base.getchannel("A"))
    return res


def over(base, mask, core, alpha=255, shadow=None, shadow_alpha=160, shadow_off=(1, 1), outline=None,
         outline_alpha=140, outline_r=1):
    """Composite coloured text (core RGB through mask) over an RGBA base (plates, transparent panels)."""
    out = base.copy()
    if outline is not None:
        om = mask.filter(ImageFilter.MaxFilter(outline_r * 2 + 1)).point(lambda v: v * outline_alpha // 255)
        layer = Image.new("RGBA", base.size, outline + (0,))
        layer.putalpha(om)
        out.alpha_composite(layer)
    if shadow is not None:
        sm = Image.new("L", base.size, 0)
        sm.paste(mask, shadow_off)
        sm = sm.point(lambda v: v * shadow_alpha // 255)
        layer = Image.new("RGBA", base.size, shadow + (0,))
        layer.putalpha(sm)
        out.alpha_composite(layer)
    layer = core.convert("RGBA")
    layer.putalpha(mask.point(lambda v: v * alpha // 255))
    out.alpha_composite(layer)
    return out

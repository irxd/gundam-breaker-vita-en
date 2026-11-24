"""Plain text: button-hint strips (*_key*), help lines, controller diagrams, text-heavy screens
(one agent owns this module).

JOBS: list of (texture path, English, style, options). draw(base, text, style, opt) -> RGBA image of base.size.

Styles
  keys   button-hint strip: white words after button icons on a transparent strip. The strip is cut into items at
         wide empty column gaps; each item's icon (the first solid run of columns) is kept pixel for pixel, the words
         are erased and the English (one entry per item, "|" separated) is drawn after it in the item's own colour
         (greyed items stay greyed). Items are re-flowed with the original gaps, keeping the strip's alignment.
"""
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

FONTS = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")
BAHN = os.path.join(FONTS, "bahnschrift.ttf")

# Plain light sans for hints: Bahnschrift, from wide to narrow; fit() takes the first that fits.
HINT_VARIANTS = ("SemiCondensed", "Condensed", "SemiLight Condensed")


def hfont(size, variation="SemiCondensed"):
    f = ImageFont.truetype(BAHN, size)
    f.set_variation_by_name(variation)
    return f


def text_w(f, s):
    return f.getlength(s)


def fit(s, width, size, variants=HINT_VARIANTS, min_size=None):
    """(font) of the widest variant at `size` whose text fits; then smaller sizes of the narrowest variant."""
    for v in variants:
        f = hfont(size, v)
        if text_w(f, s) <= width:
            return f
    min_size = min_size or size - 4
    for sz in range(size - 1, min_size - 1, -1):
        f = hfont(sz, variants[-1])
        if text_w(f, s) <= width:
            return f
    raise ValueError(f"{s!r} does not fit in {width}px")


# ---------------------------------------------------------------- keys
def _columns(img, thr=40):
    """Columns holding visible light pixels (alpha x brightness, so dark outlines/halos don't count)."""
    w, h = img.size
    px = img.load()
    return [any(px[x, y][3] * max(px[x, y][:3]) > thr * 255 for y in range(h)) for x in range(w)]


def _runs(cols, x0=0, x1=None):
    x1 = len(cols) if x1 is None else x1
    out, start = [], None
    for x in range(x0, x1):
        if cols[x] and start is None:
            start = x
        elif not cols[x] and start is not None:
            out.append([start, x])
            start = None
    if start is not None:
        out.append([start, x1])
    return out


def key_items(img, item_gap=9, icon_min=14):
    """[(item_x0, icon_x1, item_x1)] for a hint strip."""
    cols = _columns(img)
    runs = _runs(cols)
    items = []
    for r in runs:
        if items and r[0] - items[-1][-1][1] < item_gap:
            items[-1].append(r)
        else:
            items.append([r])
    out = []
    for runs_ in items:
        x0 = runs_[0][0]
        icon_end = None
        for r in runs_:
            if r[1] - r[0] >= icon_min:
                icon_end = r[1]
                break
        if icon_end is None:
            raise ValueError("no icon found")
        out.append((x0, icon_end, runs_[-1][1]))
    return out


def _text_colour(img, box):
    best = (0, (255, 255, 255))
    px = img.load()
    for x in range(box[0], box[2]):
        for y in range(box[1], box[3]):
            r, g, b, a = px[x, y]
            if a > best[0]:
                best = (a, (r, g, b))
    return best[1] + (best[0],)


def keys(base, text, size=17, base_y=None, pad=3, gap=None, align=None, variants=HINT_VARIANTS, min_size=None,
         keep=(), outline=False):
    """`keep`: indexes of items whose words are left as they are (already English)."""
    w, h = base.size
    items = key_items(base)
    words = text.split("|")
    if len(words) != len(items):
        raise ValueError(f"{len(items)} items in the strip, {len(words)} given: {items}")
    L, R = items[0][0], items[-1][2]
    if align is None:
        align = "left" if L <= 6 else "right" if R >= w - 6 else "centre"
    if base_y is None and h == 32:
        base_y = 22
    if base_y is None:
        # baseline from the first icon's vertical centre (centre + 6 on the usual 32 px strips: baseline 22)
        bb = base.crop((items[0][0], 0, items[0][1], h)).getchannel("A").point(lambda v: 255 if v > 96 else 0).getbbox()
        base_y = round((bb[1] + bb[3]) / 2) + 6
    gaps = [items[i + 1][0] - items[i][2] for i in range(len(items) - 1)]
    if gap is not None:
        gaps = [gap] * len(gaps)
    parts = []  # (icon image, icon width, text, font, colour, text gap)
    for i, ((x0, ie, x1), s) in enumerate(zip(items, words)):
        m = 3 if outline else 1
        icon = base.crop((x0 - m, 0, ie + m, h))
        if i in keep:
            parts.append((base.crop((x0, 0, x1, h)), x1 - x0, None, None, None, 0))
            continue
        col = _text_colour(base, (ie, 0, x1, h))
        parts.append((icon, ie - x0, s, None, col, pad))

    def layout(fonts):
        total = sum(p[1] + p[5] + (text_w(f, p[2]) if p[2] else 0) for p, f in zip(parts, fonts)) + sum(gaps)
        return total

    # Fit: the same font for all items of a strip, as narrow as needed.
    room = w - 4
    chosen = None
    cands = [(size, v) for v in variants] + [(sz, variants[-1]) for sz in range(size - 1, (min_size or size - 4) - 1,
                                                                                    -1)]
    for sz, v in cands:
        f = hfont(sz, v)
        fonts = [f] * len(parts)
        tot = layout(fonts)
        if tot <= room:
            chosen = (fonts, tot)
            break
    if chosen is None:
        # shrink gaps as a last resort
        f = hfont(cands[-1][0], cands[-1][1])
        fonts = [f] * len(parts)
        tot = layout(fonts)
        over = tot - room
        if over > sum(gaps) - 6 * len(gaps):
            raise ValueError(f"{text!r} does not fit ({tot:.0f} > {room})")
        k = over / max(1, sum(gaps))
        gaps = [g - g * k for g in gaps]
        chosen = (fonts, layout(fonts))
    fonts, tot = chosen
    if align == "left":
        x = L
    elif align == "right":
        x = R - tot
    else:
        x = (L + R - tot) / 2
    x = max(2, min(x, w - 2 - tot))
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    for i, (p, f) in enumerate(zip(parts, fonts)):
        icon, iw, s, _, col, tg = p
        xi = round(x)
        _paste(out, icon, xi - (icon.width - iw) // 2)
        x += iw
        if s:
            x += tg
            _text(out, (x, base_y), s, f, col, outline)
            x += text_w(f, s)
        if i < len(gaps):
            x += gaps[i]
    return out


def _paste(img, part, x):
    """alpha_composite at column x, clipped at the left edge."""
    if x < 0:
        part = part.crop((-x, 0, part.width, part.height))
        x = 0
    img.alpha_composite(part, (x, 0))


def _text(img, xy, s, f, col, outline=False):
    """Draw text on a transparent layer with straight alpha (colour kept, coverage -> alpha); `outline` adds the
    soft black halo some strips (pause menu) have."""
    w, h = img.size
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).text(xy, s, font=f, fill=255, anchor="ls")
    if outline:
        halo = m.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(1)).point(lambda v: min(255, v * 2))
        hl = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        hl.putalpha(halo.point(lambda v: v * 200 // 255))
        img.alpha_composite(hl)
    a = col[3] if len(col) > 3 else 255
    if a < 255:
        m = m.point(lambda v: v * a // 255)
    layer = Image.new("RGBA", (w, h), col[:3] + (0,))
    layer.putalpha(m)
    img.alpha_composite(layer)


# ---------------------------------------------------------------- blue
BLUE = (82, 203, 255)
BLUE_HALO = (0, 70, 140)


def _segments(s):
    """'Hold + {sq}: Attack' -> ['Hold + ', ('sq',), ': Attack']"""
    out = []
    while "{" in s:
        a, rest = s.split("{", 1)
        name, s = rest.split("}", 1)
        if a:
            out.append(a)
        out.append((name,))
    if s:
        out.append(s)
    return out


def glow_line(img, src, x, cy, segs, f, align="left", colour=BLUE, halo=BLUE_HALO, icons=None, cap=None):
    """Blue glowing text on black (additive textures), with icon crops of the original (`src`) inline.
    x: left edge (align left), right edge (right) or centre; cy: vertical centre of the capitals."""
    w, h = img.size
    cap = cap or (f.getbbox("H", anchor="ls")[3] - f.getbbox("H", anchor="ls")[1])
    base_y = round(cy + cap / 2)
    widths = []
    for sg in segs:
        if isinstance(sg, tuple):
            b = icons[sg[0]]
            widths.append(b[2] - b[0])
        else:
            widths.append(f.getlength(sg))
    tot = sum(widths)
    if align == "right":
        x0 = x - tot
    elif align == "centre":
        x0 = x - tot / 2
    else:
        x0 = x
    if x0 < 0 or x0 + tot > w:
        raise ValueError(f"line {segs!r} does not fit ({x0:.0f}..{x0 + tot:.0f} of {w})")
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    xx = x0
    pastes = []
    for sg, sw in zip(segs, widths):
        if isinstance(sg, tuple):
            b = icons[sg[0]]
            # icons keep their own vertical position relative to the text centre given in the box (5th item)
            icy = b[4] if len(b) > 4 else (b[1] + b[3]) / 2
            pastes.append((src.crop(b[:4]), (round(xx), round(cy - (icy - b[1])))))
        else:
            d.text((xx, base_y), sg, font=f, fill=255, anchor="ls")
        xx += sw
    glow_mask = m.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(1.6))
    layer = Image.new("RGB", (w, h), (0, 0, 0))
    layer.paste(Image.new("RGB", (w, h), halo), mask=glow_mask)
    layer.paste(Image.new("RGB", (w, h), colour), mask=m)
    out = ImageChops.lighter(img.convert("RGB"), layer)
    for part, pos in pastes:
        region = out.crop((pos[0], pos[1], pos[0] + part.width, pos[1] + part.height))
        out.paste(ImageChops.lighter(region, part.convert("RGB")), pos)
    return out.convert("RGBA")


def blue(base, text, at, erase="all", icons=None, size=17, variation="SemiBold SemiCondensed", min_size=13,
         widths=None, colour=BLUE, halo=BLUE_HALO):
    """Lines of `text` ('\\n' separated, '{name}' = icon crop) at `at` = [(x, cy, align), ...]. `erase`: 'all' (the
    texture is only text) or a list of boxes to clear to black first. Each line is fitted to its width
    (widths[i], else what is left of the texture) by narrowing, then shrinking the font."""
    w, h = base.size
    src = base
    img = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    if erase != "all":
        img = base.copy()
        d = ImageDraw.Draw(img)
        for b in erase:
            d.rectangle((b[0], b[1], b[2] - 1, b[3] - 1), fill=(0, 0, 0, 255))
    lines = text.split("\n")
    if len(lines) != len(at):
        raise ValueError(f"{len(lines)} lines, {len(at)} positions")
    cap = round(hfont(size, variation).getbbox("H")[3] - hfont(size, variation).getbbox("H")[1])
    for i, (line, (x, cy, align)) in enumerate(zip(lines, at)):
        segs = _segments(line)
        if widths and widths[i]:
            room = widths[i]
        else:
            room = (w - 2 - x) if align == "left" else (x - 2) if align == "right" else w - 4
        iw = sum(icons[s[0]][2] - icons[s[0]][0] for s in segs if isinstance(s, tuple))
        txt = "".join(s for s in segs if not isinstance(s, tuple))
        f = None
        narrow = variation.replace("SemiCondensed", "Condensed")
        for sz, v in [(size, variation), (size, narrow)] + [(s, narrow) for s in range(size - 1, min_size - 1, -1)]:
            f = hfont(sz, v)
            if f.getlength(txt) + iw <= room:
                break
        else:
            raise ValueError(f"{line!r} does not fit in {room}px")
        img = glow_line(img, src, x, cy, segs, f, align, colour=colour, halo=halo, icons=icons,
                        cap=cap if f.size == size else None)
    return img


# ---------------------------------------------------------------- plain labels
def _cap(f):
    b = f.getbbox("H", anchor="ls")
    return b[3] - b[1]


def plain(base, text, box, keep=(), align="left", cy=None, size=15, variation="SemiCondensed", min_size=11,
          colour=None, outline=False, glyph_cy=None):
    """White words in `box` = (x0, x1) on a transparent label; the columns in `keep` (icons) are copied from the
    original, everything else is cleared. Lines ('\\n') are centred on cy (list, one per line; default the middle of
    the texture). `glyph_cy`: per-line centre of the capitals if it differs from cy."""
    w, h = base.size
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for k in keep:
        out.alpha_composite(base.crop((k[0], 0, k[1], h)), (k[0], 0))
    if colour is None:
        colour = _text_colour(base, (box[0], 0, box[1], h))
    lines = text.split("\n")
    if cy is None:
        cy = [h / 2] if len(lines) == 1 else [h * (2 * i + 1) / (2 * len(lines)) for i in range(len(lines))]
    room = box[1] - box[0]
    narrow = variation.replace("SemiCondensed", "Condensed")
    for sz, v in [(size, variation), (size, narrow)] + [(s, narrow) for s in range(size - 1, min_size - 1, -1)]:
        f = hfont(sz, v)
        if all(f.getlength(s) <= room for s in lines):
            break
    else:
        raise ValueError(f"{text!r} does not fit in {room}px")
    cap = _cap(f)
    for s, c in zip(lines, cy):
        tw = f.getlength(s)
        x = box[0] if align == "left" else box[1] - tw if align == "right" else (box[0] + box[1] - tw) / 2
        _text(out, (x, round(c + cap / 2)), s, f, colour, outline)
    return out


# ---------------------------------------------------------------- plates
PLATE_TEXT = dict(top=(236, 242, 248), bottom=(120, 182, 232))


def clear_rows(img, box):
    """Erase text on a striped plate: every row of `box` (x0, y0, x1, y1) is re-drawn as a linear blend between
    the pixels just left and right of the box (the plates' stripes are horizontal, the shading slow along x)."""
    px = img.load()
    x0, y0, x1, y1 = box
    for y in range(y0, y1):
        a, b = px[x0 - 1, y], px[x1, y]
        n = x1 - x0 + 1
        for x in range(x0, x1):
            t = (x - x0 + 1) / n
            px[x, y] = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(4))
    return img


def plate(base, text, box, cy=None, cx=None, align="centre", size=19, variation="SemiBold SemiCondensed",
          min_size=12, colours=PLATE_TEXT, scan=3, scan_dim=0.45, spacing=0, x=None, clear=None, shadow=True):
    """Bevelled plate label: clear `clear` (default `box`) with clear_rows, then draw the English with a vertical
    gradient and a dimmed row every `scan` rows (the originals' scanline look). `box` = (x0, y0, x1, y1) is the room
    for the text; it is centred in the box (or left/right aligned)."""
    img = clear_rows(base.copy(), clear or box)
    w, h = img.size
    room = box[2] - box[0]
    narrow = variation.replace("SemiCondensed", "Condensed")

    def width(f):
        return f.getlength(text) + spacing * (len(text) - 1)

    for sz, v in [(size, variation), (size, narrow)] + [(s, narrow) for s in range(size - 1, min_size - 1, -1)]:
        f = hfont(sz, v)
        if width(f) <= room:
            break
    else:
        raise ValueError(f"{text!r} does not fit in {room}px")
    cap = _cap(f)
    cy = (box[1] + box[3]) / 2 if cy is None else cy
    tw = width(f)
    if align == "left":
        tx = box[0]
    elif align == "right":
        tx = box[2] - tw
    else:
        tx = (box[0] + box[2] - tw) / 2
    by = round(cy + cap / 2)
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    xx = tx
    for ch in text:
        d.text((xx, by), ch, font=f, fill=255, anchor="ls")
        xx += f.getlength(ch) + spacing
    if spacing == 0:
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).text((tx, by), text, font=f, fill=255, anchor="ls")
    top, bottom = colours["top"], colours["bottom"]
    grad = Image.new("RGBA", (w, h))
    gd = ImageDraw.Draw(grad)
    g0, g1 = by - cap, by
    for y in range(h):
        t = min(1.0, max(0.0, (y - g0) / max(1, g1 - g0)))
        c = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom))
        gd.line((0, y, w, y), fill=c + (255,))
    if scan:
        mp = m.load()
        for y in range(h):
            if y % scan == 0:
                for x0_ in range(w):
                    mp[x0_, y] = round(mp[x0_, y] * scan_dim)
    if shadow:
        sh = Image.new("RGBA", (w, h), (8, 16, 28, 0))
        sm = Image.new("L", (w, h), 0)
        sm.paste(m.point(lambda v: v * 150 // 255), (1, 1))
        sh.putalpha(sm)
        img.alpha_composite(sh)
    grad.putalpha(m)
    img.alpha_composite(grad)
    return img


# ---------------------------------------------------------------- glow captions on black (DXT1, additive)
GBLUE = dict(top=(170, 240, 255), bottom=(60, 180, 255), glow=(0, 70, 150))
GCYAN = dict(top=(190, 255, 255), bottom=(100, 220, 255), glow=(0, 90, 150))
GORANGE = dict(top=(255, 205, 120), bottom=(240, 150, 30), glow=(150, 70, 0))
GRED = dict(top=(240, 120, 105), bottom=(220, 60, 45), glow=(140, 20, 10))


def glowcap(base, text, box, colours=GBLUE, height=14, align="left", clear="all", variation="Bold Condensed",
            scanline=2, halo=3, min_height=7, interp=False):
    """Gradient caption with a soft halo, on a black (additive) texture. `clear` ("all" = the whole texture, the
    default for captions that are only text; or a box) is blacked out first; anything outside it stays."""
    from .common import font
    w, h = base.size
    boxes = [(0, 0, w, h)] if clear == "all" else [clear] if isinstance(clear[0], int) else list(clear)
    if interp:  # blend each row across the box instead of blacking it out (dim backgrounds)
        img = base.copy()
        for cb in boxes:
            clear_rows(img, cb)
        img = img.convert("RGB")
    else:
        img = base.convert("RGB")
        for cb in boxes:
            ImageDraw.Draw(img).rectangle((cb[0], cb[1], cb[2] - 1, cb[3] - 1), fill=(0, 0, 0))
    lines = text.split("\n")
    lboxes = [box] if isinstance(box[0], (int, float)) else list(box)
    heights = height if isinstance(height, (list, tuple)) else [height] * len(lines)
    if len(lboxes) != len(lines):
        raise ValueError(f"{len(lines)} lines, {len(lboxes)} boxes")
    layer = Image.new("RGB", (w, h), (0, 0, 0))
    for line, lb, hg in zip(lines, lboxes, heights):
        layer = ImageChops.lighter(layer, _glow_layer((w, h), line, lb, hg, colours, align, variation, scanline,
                                                      halo, min_height))
    region = Image.new("L", (w, h), 0)
    for cb in boxes:
        ImageDraw.Draw(region).rectangle((cb[0], cb[1], cb[2] - 1, cb[3] - 1), fill=255)
    img.paste(ImageChops.lighter(img, layer), mask=region)
    return img.convert("RGBA")


def _glow_layer(size, text, box, height, colours, align, variation, scanline, halo, min_height):
    from .common import font
    w, h = size
    hgt = height
    while True:
        sz = hgt * 2
        while sz > 6:
            f = font(sz, variation)
            x0, y0, x1, y1 = f.getbbox("H")
            if y1 - y0 <= hgt:
                break
            sz -= 1
        if f.getlength(text) <= box[2] - box[0] or hgt <= min_height:
            break
        hgt -= 1
    if f.getlength(text) > box[2] - box[0]:
        raise ValueError(f"{text!r} does not fit in {box}")
    cap = _cap(f)
    tw = f.getlength(text)
    tx = box[0] if align == "left" else box[2] - tw if align == "right" else (box[0] + box[2] - tw) / 2
    by = round((box[1] + box[3]) / 2 + cap / 2)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((tx, by), text, font=f, fill=255, anchor="ls")
    top, bottom = colours["top"], colours["bottom"]
    grad = Image.new("RGB", (w, h))
    gd = ImageDraw.Draw(grad)
    for y in range(h):
        t = min(1.0, max(0.0, (y - (by - cap)) / max(1, cap)))
        c = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom))
        if scanline and y % scanline == 1:
            c = tuple(v * 3 // 4 for v in c)
        gd.line((0, y, w, y), fill=c)
    layer = Image.new("RGB", (w, h), (0, 0, 0))
    hm = mask.filter(ImageFilter.GaussianBlur(halo)).point(lambda v: min(255, v * 2))
    layer.paste(Image.new("RGB", (w, h), colours["glow"]), mask=hm)
    layer.paste(grad, mask=mask)
    return layer


# ---------------------------------------------------------------- jobs
D = "GP/ui/ui_dds/"
BACK, SEL, OK = "Back", "Select", "OK"

JOBS = [
    (D + "config/config_key1", f"Default|{SEL}|{BACK}", "keys", {}),
    (D + "config/config_key2", f"Default|{SEL}|Edit Emotions|Edit Text|{BACK}", "keys", {}),
    (D + "dialog/dialog_key3", f"{SEL}|{OK}|{BACK}", "keys", {}),
    (D + "grg_build/grg_build_finish_key1", "Next", "keys", {}),
    (D + "grg_build/grg_build_key1", f"Build All|{SEL}|Toggle Lock|{OK}|{BACK}", "keys", {}),
    (D + "grg_build/grg_build_key2", f"Sharp Nippers On/Off|Build All|{SEL}|Toggle Lock|{OK}|{BACK}", "keys", {}),
    (D + "grg_cstm/grg_cstm_key1", f"Toggle View|Rotate/Zoom|{SEL}|Sort|Put in Stock|{OK}|{BACK}", "keys", {}),
    (D + "grg_cstm/grg_cstm_key2", f"Toggle View|Rotate/Zoom|{SEL}|Sort|Put in Stock|{OK}|{BACK}", "keys", {}),
    (D + "grg_pnt/grg_pnt_key1", f"Default|Rotate/Zoom|{SEL}|Save Color Set|Load Color Set|{OK}|{BACK}", "keys", {}),
    (D + "grg_pnt/grg_pnt_key2", f"Default|Rotate/Zoom|{SEL}|Save Color|Load Color|{OK}|{BACK}", "keys", {}),
    (D + "grg_set/grg_set_key/grg_set_key1", BACK, "keys", {}),
    (D + "grg_set/grg_set_key/grg_set_key2", OK, "keys", {}),
    (D + "grg_set/grg_set_key/grg_set_key3", "Load Blueprint", "keys", {}),
    (D + "grg_set/grg_set_key/grg_set_key4", f"{SEL}|Save Blueprint", "keys", {}),
    (D + "grg_set/grg_set_key/grg_set_key5", "Toggle View|Rotate/Zoom", "keys", {}),
    (D + "grg_set/grg_set_plan/grg_set_plan_key", f"{SEL}|{OK}|{BACK}", "keys", {}),
    (D + "hud/hud_pause/hud_pause_key1", "Resume", "keys", dict(outline=True)),
    (D + "hud/hud_pause/hud_pause_key2", "Leave Party", "keys", dict(outline=True)),
    (D + "hud/hud_pause/hud_pause_key3", "Retire", "keys", dict(outline=True)),
    (D + "hud/hud_pause/hud_pause_key4", SEL, "keys", dict(outline=True)),
    (D + "hud/hud_pause/hud_pause_key5", "Settings", "keys", dict(outline=True)),
    (D + "mail/mail_key/mail_key_crcl", "Next Page", "keys", {}),
    (D + "mail/mail_key/mail_key_cross", SEL, "keys", {}),
    (D + "mail/mail_key/mail_key_rs", "Scroll Text", "keys", {}),
    (D + "mail/mail_key/mail_key_tri", "Prev. Page", "keys", {}),
    (D + "mail/mail_key/mail_key_x", BACK, "keys", {}),
    (D + "menu/menu_key1", f"Check Invites|{SEL}|{OK}|{BACK}", "keys", {}),
    (D + "meslog/meslog_key1", "Scroll Log", "keys", {}),
    (D + "mlist/mlist_key1", "Member List Actions", "keys", {}),
    (D + "mlist/mlist_key2", f"{SEL}|{OK}|{BACK}", "keys", {}),
    (D + "msel/msel_key1", f"{SEL}|{OK}|{BACK}", "keys", {}),
    (D + "result/result_key1", "Skip", "keys", {}),
    (D + "result/result_key2", "Next", "keys", {}),
    (D + "result/result_key3", f"{SEL}|Take All|Sell All|Take|Sell", "keys", {}),
    (D + "room/room_key1", f"{SEL}|{OK}|{BACK}", "keys", {}),
    (D + "room/room_key2", f"{SEL}|Search Again|{OK}|{BACK}", "keys", {}),
    (D + "shop/shop_key/shop_key1", f"{OK}|{BACK}", "keys", {}),
    (D + "shop/shop_key/shop_key2", "Exchange All", "keys", {}),
    (D + "shop/shop_key/shop_key3", f"Toggle View|Rotate|{SEL}|Sort", "keys", {}),
    (D + "shop/shop_key/shop_key4", f"Exchange|{BACK}", "keys", {}),
    (D + "shop/shop_key/shop_key5", f"Get|{BACK}", "keys", {}),
    (D + "shop/shop_key/shop_key6", f"Receive|{BACK}", "keys", {}),
    (D + "shop/shop_key/shop_key7", f"{SEL}|Exchange All Stock", "keys", {}),
    (D + "shop/shop_key/shop_key8", f"Take Out|{BACK}", "keys", {}),
    (D + "shop/shop_key/shop_key9", f"Toggle View|Rotate|{SEL}|Sort", "keys", {}),
]

# Blue help lines (config): one line at x=75, centred on the old text.
HELP1 = dict(at=[(75, 16, "left")])
JOBS += [
    (D + "config/config_help/config_help_01", "Sets the up/down camera controls", "blue", HELP1),
    (D + "config/config_help/config_help_02", "Sets the left/right camera controls", "blue", HELP1),
    (D + "config/config_help/config_help_03", "Sets the right stick sensitivity", "blue", HELP1),
    (D + "config/config_help/config_help_04", "Sets the controller vibration", "blue", HELP1),
    (D + "config/config_help/config_help_05", "Adjusts the music volume", "blue", HELP1),
    (D + "config/config_help/config_help_06", "Adjusts the sound effect volume", "blue", HELP1),
    (D + "config/config_help/config_help_07", "Adjusts the voice volume", "blue", HELP1),
    (D + "config/config_help/config_help_08", "Adjusts the screen brightness", "blue", HELP1),
    # the two lines next to the triangle/square brackets of the BATTLE SETTING diagram (auto / manual melee)
    (D + "config/config_type/config_pad_a", "Melee/Ranged Attack A (by distance)\nMelee/Ranged Attack B (by distance)",
     "blue", dict(at=[(4, 14, "left"), (4, 35, "left")])),
    (D + "config/config_type/config_pad_b", "Melee Attack A\nMelee Attack B", "blue",
     dict(at=[(4, 14, "left"), (4, 35, "left")])),
    # BATTLE SETTING controller diagram (840x320): labels right-aligned to the left brackets (x 174), left-aligned
    # after the right brackets (x 587). Lines, brackets, dots and the pad outline stay; button icons are re-placed.
    (D + "config/config_type/config_pad",
     "Hold + {sq} : Ranged Attack A\n"
     "Hold + {tri} : Ranged Attack B\n"
     "Switch Option Equipment\n"
     "Move\n"
     "With shield: Guard\n"
     "Part knocked off: Recapture Beam\n"
     "Hold + {ex} : EX-Action\n"
     "Use Option Equipment\n"
     "Jump\n"
     "Hold: Boost Dash\n"
     "With {r} held: Step\n"
     "Camera / Change Target\n"
     "Open Menu",
     "blue", dict(
         erase=[(0, 0, 173, 250), (588, 0, 840, 320)],
         icons=dict(sq=(71, 23, 95, 48), tri=(71, 63, 95, 88), ex=(652, 43, 745, 68), r=(587, 233, 621, 258)),
         at=[(172, 35, "right"), (172, 75, "right"), (172, 140, "right"), (172, 224, "right"),
             (589, 14, "left"), (589, 35, "left"), (589, 56, "left"), (589, 161, "left"), (589, 203, "left"),
             (589, 224, "left"), (589, 246, "left"), (589, 288, "left"), (589, 309, "left")])),
]

# GUNPLA CONTROL loading screen: white labels beside the pad picture, icon on the side nearest the pad.
LH = D + "load/load_help/load_help_"
JOBS += [
    (LH + "awake", "Awaken", "plain", dict(keep=[(0, 35)], box=(35, 67))),
    (LH + "camera", "Reset Camera", "plain", dict(keep=[(89, 124)], box=(1, 87), align="right")),
    (LH + "crcl", "Use Option Equipment", "plain", dict(keep=[(0, 23)], box=(25, 163))),
    (LH + "cross", "Switch Option Equipment", "plain", dict(keep=[(144, 172)], box=(1, 141), align="right")),
    (LH + "flick", "Flick left/up/down: Radio Chat (multiplayer only)", "plain",
     dict(keep=[(373, 408)], box=(1, 368), align="right")),
    (LH + "lock", "Lock-on On/Off", "plain", dict(keep=[(0, 35)], box=(37, 167))),
    (LH + "ls", "Move", "plain", dict(keep=[(34, 64)], box=(1, 32), align="right")),
    (LH + "r_0", "With shield: Guard\nPart knocked off: Recapture Beam", "plain",
     dict(keep=[(0, 33)], box=(35, 263), cy=[9.5, 27])),
    (LH + "r_1", "EX-Action 1", "plain", dict(keep=[(0, 69)], box=(71, 171))),
    (LH + "r_2", "EX-Action 2", "plain", dict(keep=[(0, 69)], box=(71, 171))),
    (LH + "r_3", "EX-Action 3", "plain", dict(keep=[(0, 69)], box=(71, 171))),
    (LH + "rs", "Camera / Change Target", "plain", dict(keep=[(0, 29)], box=(31, 199))),
    (LH + "sq_1", "Attack A", "plain", dict(keep=[(0, 23)], box=(25, 99))),
    (LH + "sq_2", "Melee Attack A", "plain", dict(keep=[(0, 23)], box=(25, 98))),
    (LH + "sq_3", "Ranged Attack A", "plain", dict(keep=[(78, 148)], box=(1, 76), align="right")),
    (LH + "start", "Open Menu", "plain", dict(keep=[(0, 35)], box=(37, 127))),
    (LH + "tri_1", "Attack B", "plain", dict(keep=[(0, 23)], box=(25, 99))),
    (LH + "tri_2", "Melee Attack B", "plain", dict(keep=[(0, 23)], box=(25, 98))),
    (LH + "tri_3", "Ranged Attack B", "plain", dict(keep=[(78, 148)], box=(1, 76), align="right")),
    (LH + "x_1", "Jump", "plain", dict(keep=[(0, 23)], box=(25, 79))),
    (LH + "x_2", "Hold: Boost", "plain", dict(keep=[(0, 23)], box=(25, 135))),
    (LH + "x_3", "Step", "plain", dict(keep=[(0, 70)], box=(72, 127))),
]

# Room settings help (512x64, flat blue on black, no halo): one or two lines from x=104.
RH = D + "room/room_set_help/room_set_help_"
ROOM1 = dict(at=[(104, 30, "left")], size=18, variation="SemiBold SemiCondensed", colour=(74, 211, 255), halo=(0, 0, 0))
ROOM2 = dict(ROOM1, at=[(104, 21, "left"), (104, 42, "left")])
JOBS += [
    (RH + "01", "Up to 16 characters. If left blank,\nyour online ID is used.", "blue", ROOM2),
    (RH + "02", "Up to 16 characters.\nThis is optional.", "blue", ROOM2),
    (RH + "03", "Allows any rank difference.", "blue", ROOM1),
    (RH + "04", "Searches for players within\n±1 rank of you.", "blue", ROOM2),
    (RH + "05", "Searches only for players\nof the same rank as you.", "blue", ROOM2),
    (RH + "06", "Searches for rooms that allow\nany rank difference.", "blue", ROOM2),
    (RH + "07", "Searches for rooms limited\nto ±1 rank.", "blue", ROOM2),
    (RH + "08", "Searches for rooms limited\nto the same rank only.", "blue", ROOM2),
    (RH + "09", "Sets the room's play style.\n*Voice chat is not available.", "blue", ROOM2),
    (RH + "10", "Up to 8 characters.\nThis is optional.", "blue", ROOM2),
    (RH + "11", "Up to 80 characters.\nThis is optional.", "blue", ROOM2),
    (RH + "12", "Turns the password set when the room\nwas created on or off.", "blue", ROOM2),
    (RH + "13", "Sets whether the room uses a password.", "blue", ROOM1),
    (RH + "14", "Makes the room for PlayStation®Vita\nplayers only.", "blue", ROOM2),
    (RH + "15", "Makes the room open\nto all players.", "blue", ROOM2),
    (RH + "16", "Searches for rooms for\nPlayStation®Vita players only.", "blue", ROOM2),
    (RH + "17", "Searches for rooms open\nto all players.", "blue", ROOM2),
    (RH + "18", "PlayStation®Vita players only.\nRe-create the room to change this.", "blue", ROOM2),
    (RH + "19", "Open to all players.\nRe-create the room to change this.", "blue", ROOM2),
]


# VR Hangar side menu (512x64 plates).
MB = dict(box=(120, 19, 300, 42), cy=30, size=22, spacing=1)
JOBS += [
    (D + "mobile/mobile_btn_01", "Invite Friends", "plate", MB),
    (D + "mobile/mobile_btn_02", "Room Settings", "plate", MB),
    (D + "mobile/mobile_btn_03", "Disband Party", "plate", MB),
    (D + "mobile/mobile_btn_04", "Mail", "plate", MB),
    (D + "mobile/mobile_btn_05", "Settings", "plate", MB),
    (D + "mobile/mobile_btn_06", "Leave Hangar", "plate", MB),
]


# Main menu (412x64 plates; the English subtitle under the title stays).
MH = dict(box=(91, 20, 330, 41), clear=(89, 20, 332, 43), align="left", cy=30, size=22, spacing=1)
JOBS += [(D + f"menu/menu_head_0{i + 1}", t, "plate", MH) for i, t in enumerate([
    "Single Player", "Multiplayer (Ad Hoc)", "Multiplayer (Online)", "Machine Setup", "Players' Shop", "Mail",
    "Upload Save Data", "Game Settings"])]
# Member list: profile menu plates (256x64).
MP = dict(box=(66, 21, 192, 40), cy=30.5, size=21, spacing=1)
JOBS += [(D + f"mlist/mlist_prof_{i + 1}", t, "plate", MP) for i, t in enumerate(["Profile", "Mute", "Unmute", "Kick"])]
# Multiplayer rooms: big buttons (512x128) and settings row headers (512x64).
RB = dict(box=(130, 50, 400, 75), clear=(130, 48, 400, 78), cy=62, size=24, spacing=1)
JOBS += [(D + f"room/room_btn/room_btn_0{i + 1}", t, "plate", RB) for i, t in enumerate([
    "Search Rooms", "Create Room", "Start Search", "Create Room", "Change Room Settings"])]
RS = dict(box=(60, 17, 262, 41), cy=28.5, size=22, spacing=1)
JOBS += [(D + f"room/room_set_head/room_set_head_0{i + 1}", t, "plate", RS) for i, t in enumerate([
    "Room Name", "Search Target", "Play Style", "Password", "Room Comment", "Platform"])]
# Players' Shop menu (304x64; the English subtitle stays) and sort plates (512x64).
SM = dict(box=(54, 12, 236, 37), clear=(52, 11, 240, 37), cy=24.5, size=22, spacing=1)
JOBS += [(D + f"shop/shop_menu/shop_menu_0{i + 1}", t, "plate", SM) for i, t in enumerate([
    "Get Gunpla", "Get Items", "Sell Parts", "Sell Runners", "Receive Gifts"])]
SS = dict(box=(135, 18, 375, 40), cy=28.5, size=21, spacing=1)
JOBS += [(D + f"shop/shop_sort/shop_sort_0{i + 1}", t, "plate", SS) for i, t in enumerate([
    "By Arrival", "Recently Added"])]


# Member list status (256x32, left at x 24) and room status / play style captions.
GRED2 = dict(top=(235, 140, 130), bottom=(200, 90, 80), glow=(120, 30, 20))
MS = dict(box=(24, 7, 252, 24), height=11)
JOBS += [(D + f"mlist/mlist_stat_0{i + 1}", t, "glowcap",
          dict(MS, colours=GBLUE if i == 0 else GORANGE if i == 5 else GRED2)) for i, t in enumerate([
              "Ready to Sortie", "Preparing", "Customizing", "Painting", "Building Parts", "Choosing Mission",
              "Choosing", "In Event"])]
RST = dict(box=(18, 17, 216, 43), height=19)
JOBS += [(D + f"room/room_status{i + 1}", t, "glowcap", dict(RST, colours=c)) for i, (t, c) in enumerate([
    ("Open Room", GBLUE), ("Waiting in Hangar", GORANGE), ("On a Mission", GRED)])]
STYLES = ["Any", "Clear Missions!", "Collect Items!", "Ace Points!", "Fun for Everyone!", "Looking for Friends!",
          "Voice Chat Welcome!"]
RSS = dict(box=(8, 20, 248, 44), height=16, align="centre", colours=GCYAN)
RSD = D + "room/room_set_style/room_set_"
JOBS += [(RSD + f"style_0{i}", t, "glowcap", RSS) for i, t in enumerate(STYLES)]
JOBS += [(RSD + n, t, "glowcap", RSS) for n, t in [
    ("pass_off", "Off"), ("pass_on", "On"), ("plat_01", "PS Vita Only"), ("rank_00", "Any Rank"),
    ("rank_01", "Similar Rank"), ("rank_02", "Same Rank Only")]]
RLS = dict(box=(30, 6, 233, 25), height=11, align="right", colours=GBLUE)
JOBS += [(D + f"room/room_list_style/room_list_style_0{i + 1}", t, "glowcap", RLS) for i, t in enumerate(STYLES)]

GHEAD = dict(top=(170, 250, 255), bottom=(40, 130, 220), glow=(0, 60, 130))
JOBS += [(D + f"room/room_list_head{i + 1}", t, "glowcap",
          dict(box=(18, 16, 192, 44), clear=[(0, 0, 290, 44), (0, 44, 199, 47)], height=18,
               colours=GHEAD)) for i, t in enumerate([
              "Member List", "Room Comment", "Room Status"])]
# Players' Shop captions.
JOBS += [
    (D + "shop/shop_no", "None Found", "glowcap", dict(box=(10, 14, 190, 44), height=16, align="centre")),
    (D + "shop/shop_price_0_l", "FREE", "glowcap", dict(box=(4, 12, 96, 60), height=30, align="centre",
                                                       colours=GCYAN)),
    (D + "shop/shop_price_0_s", "FREE", "glowcap", dict(box=(2, 7, 38, 25), height=12, align="centre",
                                                       colours=GCYAN, halo=1)),
    (D + "shop/shop_detail/shop_detail_caution", "*This kit contains no weapon parts", "glowcap",
     dict(box=(8, 10, 316, 28), height=12, colours=GRED)),
]
JOBS += [(D + f"shop/shop_detail/shop_detail_head_0{i + 1}", t, "glowcap",
          dict(box=(8, 17, 124, 39), height=14, align="right")) for i, t in enumerate([
              "Contents:", "Released:", "Period:"])]

# Shop detail banners (256x120, red): the small English line and the brackets stay; big line + sub line redrawn.
GBANNER = dict(top=(255, 240, 235), bottom=(255, 120, 100), glow=(170, 20, 10))
BAN = dict(box=[(81, 42, 228, 67), (81, 72, 228, 92)], height=[20, 13], align="centre", colours=GBANNER,
           clear=(79, 40, 228, 95), interp=True)
JOBS += [(D + f"shop/shop_detail/shop_banner_0{i + 1}", t, "glowcap", BAN) for i, t in enumerate([
    "NEW ARRIVALS!\nMore on the way", "CONTEST\nEligible kit", "LIMITED TIME!\nCampaign on now",
    "LIMITED TIME!\nPrice cut"])]


def draw(base, text, style, opt):
    if style == "keys":
        return keys(base, text, **opt)
    if style == "blue":
        return blue(base, text, **opt)
    if style == "plain":
        return plain(base, text, **opt)
    if style == "plate":
        return plate(base, text, **opt)
    if style == "glowcap":
        return glowcap(base, text, **opt)
    raise ValueError(f"unknown style {style}")

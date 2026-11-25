"""Redraws found after the first catalogue: loose-only UI textures in GxArchivedFile000.dat (no pac copy).

Their originals are exported by `python -E -P scripts/export_tex.py --ui` into game/ui_png/<path>.png: textures
whose name is known keep their GP/ui path; the others are addressed by hash1 as `_loose/<hash1>` (build_images.py
patches the 000 entry with that hash). See notes/images.md ("Loose-only UI textures").

JOBS: list of (texture path, English, style, options). draw(base, text, style, opt) -> RGBA image of base.size.
Styles: 'label' / 'glow' (labels.py), 'keys' (hints.py), and here:
  notice   title_00: the piracy notice before the logos (light grey box, red heading, grey body)
  banner   dialog/leadbanner: DLC store prompt (three slanted lines over artwork + two button labels)
  pause    pause screen: grey subtitle under the blue PAUSE, erased without touching the blue glow
  hint     icon(s) + white words on a soft dark band (erase the words by interpolating rows across the band)
"""
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from . import hints, labels
from .common import ORANGE
from .labels_lib import erase, fixed_gradient, add_glow, over, text_mask

UI = "GP/ui/ui_dds/"
FONTS = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")


def segoe(size, weight="sb"):
    name = {"r": "segoeui.ttf", "sb": "seguisb.ttf", "b": "segoeuib.ttf"}[weight]
    return ImageFont.truetype(os.path.join(FONTS, name), size)


# ---------------------------------------------------------------- notice (title_00)

NOTICE_TITLE = "Notice"
NOTICE_BODY = [
    ["Distributing game software over the Internet",
     "without the rights holder's permission, and",
     "downloading it while knowing that it has been",
     "distributed illegally, are strictly prohibited by law."],
    ["We ask for your understanding and cooperation."],
]


def notice(base, text, opt):
    img = base.copy()
    d = ImageDraw.Draw(img)
    inner = (214, 86, 746, 458)          # light grey inside of the frame (frame 6 px, colour 192)
    d.rectangle((inner[0], inner[1], inner[2] - 1, inner[3] - 1), fill=(239, 239, 239, 255))
    # heading: red, bold, centred where the original's is
    # body: grey, left-aligned at the original's margin, paragraph gap like the original; the whole block
    # (heading + body) is centred vertically in the box
    size = 24
    while size > 14:
        bf = segoe(size, "sb")
        if all(bf.getlength(s) <= 476 for p in NOTICE_BODY for s in p):
            break
        size -= 1
    lh, gap, head = size + 13, 14, 34
    n = sum(len(p) for p in NOTICE_BODY)
    total = head + 26 + n * lh + gap * (len(NOTICE_BODY) - 1)
    top = (inner[1] + inner[3] - total) // 2
    d.text((480, top + head // 2), NOTICE_TITLE, font=segoe(32, "b"), fill=(200, 60, 40, 255), anchor="mm")
    y = top + head + 26 + size - 2
    for k, para in enumerate(NOTICE_BODY):
        for s in para:
            d.text((248, y), s, font=bf, fill=(102, 102, 102, 255), anchor="ls")
            y += lh
        y += gap
    return img


# ---------------------------------------------------------------- banner (dialog/leadbanner)

def _fill_holes(img, mask, passes=(32, 16, 8, 4, 2), min_weight=6, ignore=None, smooth=0):
    """Fill the masked area of an RGB image from its surroundings: normalised Gaussian blur of the unmasked pixels,
    coarse to fine (each finer pass overwrites only where it has enough support, i.e. near the edge). `ignore`:
    extra pixels not used as a source (other text next to the hole); `smooth`: blur radius over the filled area,
    blended in with a feathered edge."""
    out = img.copy()
    keep = ImageChops.invert(mask)
    if ignore is not None:
        keep = ImageChops.subtract(keep, ignore)
    src = Image.composite(img, Image.new("RGB", img.size, 0), keep)
    W, H = img.size
    op, mp = out.load(), mask.load()
    for r in passes:
        wb = keep.filter(ImageFilter.GaussianBlur(r)).load()
        nb = src.filter(ImageFilter.GaussianBlur(r)).load()
        for y in range(H):
            for x in range(W):
                if mp[x, y]:
                    k = wb[x, y]
                    if k >= min_weight:
                        op[x, y] = tuple(min(255, v * 255 // k) for v in nb[x, y])
    if smooth:
        out = Image.composite(out.filter(ImageFilter.GaussianBlur(smooth)), out,
                              mask.filter(ImageFilter.GaussianBlur(smooth / 2)))
    return out


def _rich_line(size, runs, x, base_y, angle):
    """One slanted line of coloured runs [(text, font, fill, stroke, stroke_fill)] -> RGBA layer."""
    w, h = size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shadow = Image.new("L", (w, h), 0)
    d, ds = ImageDraw.Draw(layer), ImageDraw.Draw(shadow)
    xx = x
    for s, f, fill, stroke, sfill in runs:
        ds.text((xx + 2, base_y + 3), s, font=f, fill=200, anchor="ls", stroke_width=stroke + 1)
        d.text((xx, base_y), s, font=f, fill=fill, anchor="ls", stroke_width=stroke, stroke_fill=sfill)
        xx += f.getlength(s)
    sh = Image.new("RGBA", (w, h), (0, 10, 40, 0))
    sh.putalpha(shadow.filter(ImageFilter.GaussianBlur(2)))
    sh.alpha_composite(layer)
    return sh.rotate(angle, resample=Image.BICUBIC, center=(x, base_y)), xx


BANNER_LINES = [
    # (x, baseline, runs)
    (88, 248, [("Buy the add-on ", 23, "w"), ("“Giga Break Mission Pack”", 33, "r")]),
    (196, 292, [("New mobile suits", 31, "y"), (" join the fight in", 23, "w")]),
    (318, 334, [("new missions", 31, "y"), (" - play them now!", 23, "w")]),
]
BANNER_ANGLE = 4.5   # degrees, counter-clockwise (the original lines rise to the right)


def banner(base, text, opt):
    img = base.convert("RGB")
    w, h = img.size
    # 1. remove the three Japanese lines: polygon around them, filled from the surrounding glow and artwork
    m = Image.new("L", (w, h), 0)
    dm = ImageDraw.Draw(m)
    dm.polygon([(78, 212), (226, 200), (228, 176), (636, 160), (724, 168), (724, 218), (632, 238), (236, 258),
                (78, 268)], fill=255)
    dm.polygon([(194, 250), (458, 246), (458, 300), (194, 304)], fill=255)
    dm.polygon([(318, 290), (708, 280), (708, 342), (318, 344)], fill=255)
    filled = _fill_holes(img, m, smooth=4)
    # bring back the 2-px scanlines of the artwork
    sc = filled.load()
    mp = m.load()
    for y in range(1, h, 2):
        for x in range(w):
            if mp[x, y]:
                sc[x, y] = tuple(v * 9 // 10 for v in sc[x, y])
    img = filled.convert("RGBA")
    # 2. English, slanted like the original
    colours = {
        "w": ((255, 255, 255), 2, (20, 50, 110)),
        "y": ((255, 222, 40), 3, (40, 30, 10)),
        "r": ((230, 40, 30), 3, (255, 255, 255)),
    }
    for x, by, runs in BANNER_LINES:
        rr = []
        for s, size, c in runs:
            fill, stroke, sfill = colours[c]
            var = "Bold Condensed" if c != "w" else "SemiBold SemiCondensed"
            f = labels_font(size, var)
            rr.append((s, f, fill + (255,), stroke, sfill + (255,)))
        layer, end = _rich_line((w, h), rr, x, by, BANNER_ANGLE)
        if end > w - 8:
            raise ValueError(f"banner line at {x},{by} too long ({end:.0f})")
        img.alpha_composite(layer)
    # 3. bottom buttons: drop the particle after "PlayStation®Store", "Cancel" after the cross
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rectangle((368, 444, 399, 469), fill=255)
    ImageDraw.Draw(m).rectangle((537, 444, 638, 469), fill=255)
    bright = img.convert("L").point(lambda v: 255 if v > 120 else 0).filter(ImageFilter.MaxFilter(3))
    bar = _fill_holes(img.convert("RGB"), m, passes=(12, 6, 3), ignore=bright).convert("RGBA")
    d = ImageDraw.Draw(bar)
    d.text((538, 456), "Cancel", font=segoe(21, "r"), fill=(255, 255, 255, 255), anchor="lm")
    return bar


def labels_font(size, variation):
    from .common import font
    return font(size, variation)


# ---------------------------------------------------------------- pause screen subtitle

def pause(base, text, opt):
    img = base.convert("RGB")
    px = img.load()
    x0, y0, x1, y1 = opt["box"]
    for y in range(y0, y1):
        for x in range(x0, x1):
            r, g, b = px[x, y]
            m = min(r, g, b)
            px[x, y] = (r - m, g - m, b - m)   # grey text gone, the blue PAUSE glow stays
    img = img.convert("RGBA")
    mask = text_mask(img.size, text, opt["text_box"], opt["cap"], variation="Bold Condensed",
                     spacing=opt["spacing"], min_spacing=2.0)
    core = fixed_gradient(img.size, mask, (205, 205, 205), (150, 150, 150), scanline=2, dark=0.8)
    return add_glow(img, mask, core, (34, 34, 34), radius=1.5, strength=0.9)


# ---------------------------------------------------------------- icon + words on a soft dark band

def hint(base, text, opt):
    img = base.copy()
    box = opt["erase"]
    if opt.get("fill"):
        # flat plate: fill with its most common colour (the plate itself, not the text or its outline)
        counts = {}
        for p in img.crop(box).getdata():
            counts[p] = counts.get(p, 0) + 1
        erase(img, "fill", [box], colour=max(counts, key=counts.get))
    else:
        # soft dark band: alpha interpolated across the box, colour black
        erase(img, "rows", [box], left=opt["left"], right=opt["right"])
        r = img.crop(box)
        black = Image.new("RGBA", r.size, (0, 0, 0, 0))
        black.putalpha(r.getchannel("A"))
        img.paste(black, box[:2])
    f = hints.hfont(opt["size"], opt.get("variation", "SemiBold SemiCondensed"))
    room = opt["erase"][2] - opt["x"] - 2
    if f.getlength(text) > room:
        f = hints.hfont(opt["size"], "SemiBold Condensed")
    if f.getlength(text) > room:
        raise ValueError(f"{text!r} does not fit in {room}px")
    hints._text(img, (opt["x"], opt["base_y"]), text, f, (255, 255, 255, 255), opt.get("outline", False))
    return img


def draw(base, text, style, opt):
    if style in ("label", "glow"):
        return labels.draw(base, text, style, opt)
    if style == "keys":
        return hints.draw(base, text, style, opt)
    if style == "notice":
        return notice(base, text, opt)
    if style == "banner":
        return banner(base, text, opt)
    if style == "pause":
        return pause(base, text, opt)
    if style == "hint":
        return hint(base, text, opt)
    raise ValueError(f"unknown style {style}")


# ================================================================ jobs

JOBS = [
    (UI + "title/title_00", "Notice: piracy is prohibited by law (body in NOTICE_BODY)", "notice", {}),
    (UI + "dialog/leadbanner", "Buy the add-on Giga Break Mission Pack ... / PlayStation Store / Cancel", "banner",
     {}),
    # big ranks 08/09 repeat Admiral / Fleet Admiral (identical to rank_m_06/07)
    (UI + "rank/rank_m_08", "ADM", "glow", dict(colours=ORANGE, height=30, box=(8, 8, 120, 56))),
    (UI + "rank/rank_m_09", "FADM", "glow", dict(colours=ORANGE, height=30, box=(8, 8, 120, 56))),
    (UI + "result/result_key4", f"{hints.SEL}|Take All|Sell All|Take|Sell", "keys", {}),
    # PAUSE screen (1280x720 DXT1): subtitle "paused" under the big blue PAUSE
    ("_loose/00d9cea8", "GAME PAUSED", "pause",
     dict(box=(530, 384, 752, 410), text_box=(530, 388, 752, 406), cap=15, spacing=9.0)),
    # L2 + R2 free-word chat (icons and plus kept)
    ("_loose/49757e76", "Free-Word Chat", "hint",
     dict(erase=(97, 22, 238, 47), left=(96, 99), right=(238, 242), x=104, base_y=42, size=19)),
    # hand icon + "flick right to close" on a dark plate
    ("_loose/c1dad43f", "Flick right to close", "hint",
     dict(erase=(30, 4, 191, 36), fill=True, x=33, base_y=26, size=18, outline=True)),
]

# Option-equipment stat names in Customize (256x32 strips like grg_cstm_spec_01..08)
_SPEC = dict(cap=12, align="l", variation="Bold SemiCondensed", spacing=1.2, min_spacing=0.3, shadow=(0, 0, 0),
             shadow_alpha=150)
for n in range(1, 7):
    JOBS.append((UI + f"grg_cstm/grg_cstm_spec/grg_cstm_spec_{8 + n:02d}", f"Option {n} Power", "label",
                 dict(erase=[("clear", [(0, 4, 256, 28)])], box=(2, 7, 140, 24), sample=(2, 7, 133, 24), **_SPEC)))
# EX triangle / square / circle: the "EX" and the button symbol stay, only the word after them changes
for n in (15, 16, 17):
    JOBS.append((UI + f"grg_cstm/grg_cstm_spec/grg_cstm_spec_{n}", "Power (after EX + button)", "label",
                 dict(erase=[("clear", [(80, 4, 256, 28)])], parts=[dict(text="Power")], box=(82, 7, 160, 24),
                      sample=(89, 7, 133, 24), **_SPEC)))
# caption left of an option's carried count (like grg_cstm_help_2..4)
JOBS.append((UI + "grg_cstm/grg_cstm_help_1", "Carried", "label",
             dict(erase=[("clear", [(0, 6, 128, 28)])], box=(4, 9, 122, 26), sample=(68, 9, 121, 26),
                  variation="Bold SemiCondensed", spacing=0.5, shadow=(0, 0, 0), shadow_alpha=150, cap=12,
                  align="r")))
# demo build's copyright line (the retail title_copyright is romanised the same way)
JOBS.append((UI + "title_demo/title_copyright", "(c) SOTSU / SUNRISE (/ MBS)", "label",
             dict(erase=[("clear", [(0, 0, 224, 56)])],
                  parts=[dict(text="© SOTSU · SUNRISE", box=(6, 6, 218, 24)),
                         dict(text="© SOTSU · SUNRISE · MBS", box=(6, 31, 218, 49))],
                  cap=12, align="l", variation="SemiBold", spacing=0.3, top=(255, 255, 255), shadow=(0, 0, 0),
                  shadow_alpha=150)))
# red "... held" counters (128x32, transparent, right-aligned like header_quantity)
for h, en in (("fa959a56", "Runners Held"), ("fa959a57", "Parts Held"), ("fa959a58", "Modules Held")):
    JOBS.append((f"_loose/{h}", en, "label",
                 dict(erase=[("clear", [(0, 4, 128, 28)])], box=(4, 8, 125, 24), sample=(20, 8, 125, 24), cap=11,
                      align="r", variation="Bold Condensed", spacing=0.7, min_spacing=0.2, shadow=(0, 0, 0),
                      shadow_alpha=170)))
# weapon list headers (512x128): big white word above the line, English orange subtitle stays
for h, en in (("d16ee459", "Melee Weapons"), ("d16ee462", "Ranged Weapons")):
    JOBS.append((f"_loose/{h}", en, "label",
                 dict(erase=[("rows", [(22, 23, 134, 45)], dict(left=(18, 22), right=(134, 138)))],
                      box=(24, 26, 160, 44), cap=16, align="l", valign="b", variation="Bold SemiCondensed",
                      spacing=2.0, min_spacing=0.5, top=(255, 255, 255), bottom=(225, 228, 232), shadow=(0, 0, 0),
                      shadow_alpha=170)))

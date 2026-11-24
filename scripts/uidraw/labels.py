"""Stylised labels: plates, glow captions, headers, ranks (one agent owns this module).

JOBS: list of (texture path, English, style, options). draw(base, text, style, opt) -> RGBA image of base.size.

Styles:
  glow   opaque black DXT1 texture drawn additively: core text + halo (common.glow, kept for rank_m_00's proof)
  label  generic: `erase` the Japanese, then draw one or more `parts` (default: one part with the job's text).
         Each part is a dict merged over the job's own keys:
           text, box, cap (cap height px), variation, spacing, min_spacing, align (l/c/r), valign (c/t/b), squash_min,
           italic, dx, dy                                    -> labels_lib.text_mask
           colours: sample=box of the original to take row colours from (default: the part box), scale; or
                    top/bottom (+ scanline) for a fixed gradient
           mode 'glow': halo (colour; default sampled from the original), radius, strength, smear, wide
           mode 'over': alpha, shadow (colour), shadow_alpha, shadow_off, outline, outline_alpha
         erase: list of (how, [boxes], {kw}) for labels_lib.erase
"""
from .common import ORANGE, glow
from .labels_lib import (add_glow, erase, fixed_gradient, gradient_layer, mean_colour, over, sample_rows,
                         text_mask)

UI = "GP/ui/ui_dds/"

MASK_KEYS = ("variation", "spacing", "min_spacing", "align", "valign", "squash_min", "italic", "dx", "dy")


def _part(img, orig, p):
    size = img.size
    mask = text_mask(size, p["text"], p["box"], p["cap"], **{k: p[k] for k in MASK_KEYS if k in p})
    if "top" in p:
        core = fixed_gradient(size, mask, p["top"], p.get("bottom", p["top"]), p.get("scanline", 0),
                              p.get("dark", 0.75))
    else:
        sbox = p.get("sample", p["box"])
        rows, span = sample_rows(orig, sbox, p.get("frac", 0.12))
        core = gradient_layer(size, mask, rows, span, p.get("scale", 1.0))
    mode = p.get("mode", "over")
    if mode == "glow":
        halo = p.get("halo")
        if halo is None:
            sbox = p.get("sample", p["box"])
            halo = mean_colour(orig, sbox, p.get("halo_lo", 25), p.get("halo_hi", 90))
            k = p.get("halo_gain", 2.2)
            halo = tuple(min(255, int(v * k)) for v in halo)
        return add_glow(img, mask, core, halo, p.get("radius", 2.5), p.get("strength", 1.4), p.get("smear", 0),
                        p.get("smear_k", 0.35), p.get("wide", 0), p.get("wide_k", 0.5))
    return over(img, mask, core, p.get("alpha", 255), p.get("shadow"), p.get("shadow_alpha", 160),
                p.get("shadow_off", (1, 1)), p.get("outline"), p.get("outline_alpha", 140))


def label(base, text, opt):
    img = base.copy()
    for e in opt.get("erase", []):
        erase(img, e[0], e[1], **(e[2] if len(e) > 2 else {}))
    common = {k: v for k, v in opt.items() if k not in ("erase", "parts")}
    parts = opt["parts"] if "parts" in opt else [dict(text=text)]
    for p in parts:
        img = _part(img, base, {**common, **p})
    return img


def draw(base, text, style, opt):
    if style == "glow":
        return glow(base, text, **opt)
    if style == "label":
        return label(base, text, opt)
    raise ValueError(f"unknown style {style}")


JOBS = []


def job(path, text, **opt):
    JOBS.append((UI + path, text, "label", opt))


# ============================================================== Game Setting (config)

# Row label plates (512x64): plate interior rows 19..40 are horizontal stripes; erase by interpolating each row
# between clean columns left and right of the text, then letter-spaced pale blue text sampled from the original.
CONFIG_HEAD = dict(
    erase=[("rows", [(56, 19, 258, 41)], dict(left=(46, 56), right=(258, 268)))],
    box=(58, 19, 256, 41), cap=14, spacing=3.0, min_spacing=1.0, variation="Bold Condensed", scale=1.08,
    sample=(60, 19, 256, 41), shadow=(10, 20, 36), shadow_alpha=150,
)
for n, en in enumerate(["Vertical Camera", "Horizontal Camera", "Camera Sensitivity", "Vibration", "BGM Volume",
                        "SE Volume", "Voice Volume", "Brightness", "Auto Near/Far Switch"], 1):
    job(f"config/config_head/config_head_{n:02d}", en, **CONFIG_HEAD)

# Values (128x32 DXT1 glow, italic blue)
CONFIG_VALUE = dict(erase=[("black", [(0, 0, 128, 32)])], box=(10, 3, 120, 29), cap=17, italic=0.22,
                    variation="Bold Condensed", spacing=1.0, mode="glow", sample=(0, 0, 128, 32))
job("config/config_normal", "Normal", **CONFIG_VALUE)
job("config/config_reverse", "Reverse", **CONFIG_VALUE)


# ============================================================== Ranks
# Abbreviations as in the rank_name text table (it can't grow): CPO ENS LT LCDR CAPT RADM ADM FADM.
RANKS = ["CPO", "ENS", "LT", "LCDR", "CAPT", "RADM", "ADM", "FADM"]
for n, en in enumerate(RANKS):
    # big rank (128x64): rank_m_00 was the first proof, the others use the same style
    JOBS.append((UI + f"rank/rank_m_{n:02d}", en, "glow", dict(colours=ORANGE, height=30, box=(8, 8, 120, 56))))
for n, en in enumerate(RANKS + ["ADM", "FADM"]):
    # small rank (64x64); s_08/s_09 repeat Admiral / Fleet Admiral
    JOBS.append((UI + f"rank/rank_s_{n:02d}", en, "glow", dict(colours=ORANGE, height=13, box=(5, 24, 59, 43),
                                                                scanline=0)))


# ============================================================== shared shapes

def panel_header(path, text, lx0, lx1, ly, cap=14, right="auto", **kw):
    """White header word sitting on a panel's underline (line from lx0 to lx1 at row ly, then a slant up).
    The Japanese is erased by interpolating each row between the panel edge and a clean column just left of the
    slant (right=None when the Japanese reaches the slant)."""
    if right == "auto":
        right = (lx1 - 9, lx1 - 3)
    opt = dict(
        erase=[("rows", [(lx0 + 1, ly - 23, lx1 - (2 if right else 0), ly)],
                dict(left=(lx0 - 1, lx0 + 1), right=right))],
        box=(lx0 + 3, ly - 22, lx1 - 6, ly - 3), cap=cap, align="l", valign="b", variation="Bold SemiCondensed",
        spacing=0.6, sample=(lx0 + 2, ly - 22, lx0 + 60, ly - 2), shadow=(0, 0, 0), shadow_alpha=170,
    )
    opt.update(kw)
    job(path, text, **opt)


STATS = ["Durability", "Physical Armor", "Beam Armor", "Shield Durability", "Melee Power", "Ranged Power",
         "Capacity", "Equip Cost"]


def stat_parts(x0, x1, y0, pitch, names=STATS, h=17, cap=12, **kw):
    """Stat-name column: one part per row (text left-aligned, pale blue-white gradient sampled per row)."""
    parts = []
    for i, name in enumerate(names):
        y = y0 + i * pitch
        parts.append(dict(text=name, box=(x0, y, x1, y + h), sample=(x0, y, x1, y + h), **kw))
    return parts


STAT_STYLE = dict(cap=12, align="l", variation="Bold SemiCondensed", spacing=1.2, min_spacing=0.3,
                  shadow=(0, 0, 0), shadow_alpha=150)


def stat_column(path, text, x0, x1, y0, pitch, n=8, clean=None, h=17):
    rows = [(x0 - 1, y0 + i * pitch - 1, x1 + 2, y0 + i * pitch + h + 1) for i in range(n)]
    left, right = clean
    job(path, text, erase=[("rows", rows, dict(left=left, right=right))],
        parts=stat_parts(x0, x1, y0, pitch, h=h), **STAT_STYLE)


# ============================================================== Machine Setup (grg_set)

panel_header("grg_set/grg_set_name", "Gunpla Name", 13, 154, 31)
panel_header("grg_set/grg_set_setting", "Setting", 13, 154, 31)
panel_header("grg_set/grg_set_ex", "EX-Action", 22, 163, 46)
panel_header("grg_set/grg_set_opt", "Option Equipment", 350, 491, 35)
panel_header("grg_set/grg_set_module", "Enhancement Module", 22, 163, 46)

# Machine Specs: header + 8 stat names (rows 36 + 24i, 17 px, x 15..146) on the dark panel
_spec = dict(
    erase=[("rows", [(14, 8, 138, 31)], dict(left=(12, 14), right=(131, 137)))]
    + [("rows", [(14, 35 + 24 * i, 149, 54 + 24 * i) for i in range(8)], dict(left=(11, 14), right=(150, 158)))],
    parts=[dict(text="Machine Specs", box=(16, 9, 134, 28), cap=14, align="l", valign="b",
                variation="Bold SemiCondensed", spacing=0.6, sample=(15, 9, 75, 29), shadow=(0, 0, 0),
                shadow_alpha=170)]
    + [{**STAT_STYLE, **p} for p in stat_parts(15, 147, 36, 24)],
)
job("grg_set/grg_set_spec", "Machine Specs + stats", **_spec)

# Machine Setup menu plates (256x64): Japanese title on the plate, English subtitle below it stays.
MENU_PLATE = dict(
    erase=[("rows", [(48, 15, 214, 40)], dict(left=(44, 48), right=(214, 218)))],
    box=(52, 16, 210, 40), cap=14, spacing=2.5, min_spacing=0.5, variation="Bold Condensed",
    sample=(50, 15, 212, 40), shadow=(10, 20, 36), shadow_alpha=150, scale=1.05, align="l",
)
for n, en in enumerate(["Create Parts", "Customize", "Gunpla Paint", "Edit Gunpla Name", "Parts Stock"], 1):
    job(f"grg_set/grg_set_menu/grg_set_menu_{n:02d}", en, **MENU_PLATE)


# ============================================================== Customize (grg_cstm)

# Weapon Aptitude: header + 11 weapon types centred in the column between the red and blue gauges (x 112..206).
_APT_ROWS = [(45, 59), (64, 78), (82, 96), (100, 114), (118, 132), (136, 150),
             (162, 177), (180, 194), (198, 212), (216, 230), (234, 249)]
_APT = ["Saber", "Axe", "Two-Handed Sword", "Whip", "Lance", "Melee",
        "Rifle", "Long Rifle", "Machine Gun", "Gatling Gun", "Bazooka"]
job("grg_cstm/grg_cstm_apt", "Weapon Aptitude + weapon types",
    erase=[("rows", [(17, 15, 165, 38)], dict(left=(15, 17), right=(158, 164))),
           ("rows", [(109, y0 - 1, 210, y1 + 1) for y0, y1 in _APT_ROWS], dict(left=(107, 109), right=(209, 211)))],
    parts=[dict(text="Weapon Aptitude", box=(19, 16, 161, 35), cap=14, align="l", valign="b",
                variation="Bold SemiCondensed", spacing=0.6, sample=(18, 16, 80, 36), shadow=(0, 0, 0),
                shadow_alpha=170)]
    + [dict(text=t, box=(111, y0, 208, y1), cap=11, scale=1.15, align="c", variation="Bold SemiCondensed", spacing=1.0,
            min_spacing=0.0, squash_min=0.7, sample=(112, y0, 207, y1), shadow=(0, 0, 0), shadow_alpha=150)
       for t, (y0, y1) in zip(_APT, _APT_ROWS)])

panel_header("grg_cstm/grg_cstm_spec/grg_cstm_spec", "Machine Specs", 16, 167, 38, right=None)

# Stat names as separate strips (256x32, transparent background)
for n, en in enumerate(STATS, 1):
    job(f"grg_cstm/grg_cstm_spec/grg_cstm_spec_{n:02d}", en, erase=[("clear", [(0, 4, 256, 28)])],
        box=(2, 7, 140, 24), sample=(2, 7, 133, 24), **STAT_STYLE)

# Small grey-blue captions next to option-equipment numbers (transparent, right-aligned)
_HELP = dict(variation="Bold SemiCondensed", spacing=0.5, shadow=(0, 0, 0), shadow_alpha=150, cap=12, align="r")
job("grg_cstm/grg_cstm_help_2", "Uses", erase=[("clear", [(0, 6, 128, 28)])], box=(4, 9, 122, 26),
    sample=(50, 9, 121, 26), **_HELP)
job("grg_cstm/grg_cstm_help_3", "Charge Time", erase=[("clear", [(0, 6, 128, 28)])], box=(4, 9, 123, 26),
    sample=(25, 9, 123, 26), **_HELP)
job("grg_cstm/grg_cstm_help_4", "Power", erase=[("clear", [(0, 6, 40, 28)])], box=(1, 9, 40, 26),
    sample=(2, 9, 37, 26), **{**_HELP, "align": "l", "squash_min": 0.7})

# Over-capacity warning: red CAUTION! stays, two grey lines below
job("grg_cstm/grg_cstm_caution1", "Equip Cost exceeds Capacity. / You can't sortie like this.",
    erase=[("black", [(30, 61, 482, 110)])],
    parts=[dict(text="Equip Cost exceeds Capacity.", box=(40, 66, 472, 84), sample=(66, 66, 448, 84)),
           dict(text="You can't sortie like this.", box=(40, 87, 472, 105), sample=(142, 87, 371, 105))],
    cap=14, variation="Bold SemiCondensed", spacing=0.8, shadow=(0, 0, 0), shadow_alpha=200)

# Remove Equipment plate: clean plate from grg_cstm_list1 (same plate, no text); English subtitle stays.
job("grg_cstm/grg_cstm_list3", "Remove Equipment",
    erase=[("copy", [(120, 44, 262, 74)], dict(src=UI + "grg_cstm/grg_cstm_list1"))],
    box=(130, 49, 300, 71), cap=14, align="l", spacing=2.5, min_spacing=1.0, variation="Bold Condensed",
    sample=(128, 48, 245, 72), shadow=(10, 20, 36), shadow_alpha=150, scale=1.05)

# Sort-order plates (512x64)
SORT_PLATE = dict(
    erase=[("rows", [(152, 18, 372, 39)], dict(left=(148, 152), right=(372, 378)))],
    box=(156, 19, 368, 37), cap=13, spacing=2.5, min_spacing=0.5, variation="Bold Condensed",
    sample=(156, 18, 370, 38), shadow=(10, 20, 36), shadow_alpha=150, scale=1.15,
)
for n, en in enumerate(["By Acquisition", "By Name", "By Durability", "By Melee Aptitude", "By Capacity",
                        "By Shield Durability", "By Category Attack", "By Category", "By Ranged Aptitude"], 1):
    job(f"grg_cstm/grg_cstm_sort/grg_cstm_sort_{n:02d}", en, **SORT_PLATE)


# ============================================================== Create Parts (grg_build)

panel_header("grg_build/grg_build_finish_op", "Option List", 150, 301, 50, right=None)
job("grg_build/grg_build_finish_spec", "Parts Specs + stats",
    erase=[("rows", [(151, 16, 301, 39)], dict(left=(149, 151)))]
    + [("rows", [(151, 43 + 24 * i, 288, 62 + 24 * i) for i in range(8)], dict(left=(148, 151), right=(290, 298)))],
    parts=[dict(text="Parts Specs", box=(153, 17, 295, 36), cap=14, align="l", valign="b",
                variation="Bold SemiCondensed", spacing=0.6, sample=(152, 17, 215, 37), shadow=(0, 0, 0),
                shadow_alpha=170)]
    + [{**STAT_STYLE, **p} for p in stat_parts(152, 287, 44, 24)])
job("grg_build/grg_build_no", "You don't have the required Runner",
    erase=[("black", [(0, 0, 388, 60)])], box=(14, 16, 374, 42), cap=16, variation="Bold Condensed", spacing=0.8,
    mode="glow", sample=(20, 18, 368, 41), radius=2.5, strength=1.3, wide=7, wide_k=0.35)


# ============================================================== Mission result

panel_header("result/result_rep_base", "Mission Report", 108, 249, 31, right=None)
panel_header("result/result_trsr_base", "Spoils", 108, 249, 153)

# Grey item labels in the report / spoils lists (128x32, transparent, left-aligned)
RESULT_LABEL = dict(erase=[("clear", [(0, 5, 128, 29)])], box=(6, 9, 124, 26), cap=14, align="l",
                    variation="Bold SemiCondensed", spacing=0.6, squash_min=0.8, shadow=(0, 0, 0), shadow_alpha=130,
                    scale=0.92)
job("result/result_rep_time", "Elapsed Time", sample=(7, 9, 77, 26), **RESULT_LABEL)
job("result/result_rep_retry", "Retries", sample=(6, 9, 103, 26), **RESULT_LABEL)
job("result/result_rep_reward", "GP Earned", sample=(7, 9, 67, 26), **RESULT_LABEL)
job("result/result_rep_gp", "GP Held", sample=(7, 9, 67, 26), **RESULT_LABEL)
job("result/result_trsr_sell", "Trade Value", sample=(6, 9, 76, 26), **RESULT_LABEL)
# Required OS version: keep the original "OS VER." glyphs, replace only the Japanese word before them
job("result/result_trsr_os", "REQ. OS VER.", erase=[("clear", [(0, 5, 44, 29)])], parts=[dict(text="REQ.")],
    box=(5, 9, 42, 26), cap=14,
    align="r", variation="Bold Condensed", spacing=0.3, sample=(45, 9, 99, 26), shadow=(0, 0, 0),
    shadow_alpha=130)
job("result/result_pena_txt", "Spoils are confiscated based on the number of retries",
    erase=[("black", [(0, 0, 512, 32)])], box=(40, 6, 472, 25), cap=13, variation="SemiBold SemiCondensed",
    spacing=0.6, sample=(68, 6, 443, 25), mode="glow", halo=(40, 40, 40), radius=1.5, strength=0.8)


# ============================================================== Mission select

# Rank tabs (128x64 plates, like the English "+ PLUS" tab msel_tab_sp)
MSEL_TAB = dict(
    erase=[("rows", [(28, 20, 87, 43)], dict(left=(25, 28), right=(87, 90)))],
    box=(29, 22, 86, 41), cap=13, spacing=1.2, min_spacing=0.3, variation="Bold Condensed",
    sample=(30, 21, 86, 42), shadow=(10, 20, 36), shadow_alpha=150, scale=1.1,
)
for n, en in enumerate(["All"] + RANKS[1:]):
    job(f"msel/msel_tab_{n:02d}", en, **MSEL_TAB)

# Mission info captions (112x36 DXT1 glow, right-aligned on the colon at x 102)
MSEL_HEAD = dict(erase=[("black", [(0, 0, 112, 36)])], box=(4, 10, 103, 25), cap=11, align="r",
                 variation="Bold Condensed", spacing=0.8, min_spacing=0.2, squash_min=0.8, mode="glow",
                 radius=2.2, strength=1.3)
for n, en in enumerate(["Clear Condition:", "Failure Condition:", "Rare Runner:", "Time Limit:", "Decal:"], 1):
    job(f"msel/msel_head{n}", en, sample=(11, 10, 103, 26), **MSEL_HEAD)


# ============================================================== Battle HUD

# Subtitles under the big telops (DXT1, grey-white, very wide letter spacing, centred)
TELOP = dict(erase=[("black", [(0, 0, 512, 32)])], box=(8, 6, 504, 26), cap=15, variation="Bold Condensed",
             spacing=7.0, min_spacing=2.0, mode="glow", halo=(36, 36, 36), radius=1.5, strength=0.9)
job("telop/telop_txt/telop_txt_start", "COMMENCE OPERATIONS!", sample=(104, 6, 411, 26), **TELOP)
job("telop/telop_txt/telop_txt_ace", "ENEMY ACE SIGHTED!", sample=(52, 5, 462, 26), **TELOP)
job("telop/telop_txt/telop_txt_next", "PROCEED TO THE NEXT AREA", sample=(101, 5, 414, 26), **TELOP)
job("telop/telop_txt/telop_txt_over", "TIME LIMIT EXCEEDED", sample=(53, 5, 461, 26), **TELOP)
job("telop/telop_txt/telop_txt_failed", "MISSION FAILED", sample=(1, 5, 127, 26),
    **{**TELOP, "erase": [("black", [(0, 0, 128, 32)])], "box": (1, 6, 127, 26), "spacing": 2.0, "min_spacing": 0.5,
       "squash_min": 0.7})

# Countdown captions (128x64 DXT1 blue glow, right-aligned at x 115; the counter follows)
COUNT_HEAD = dict(erase=[("black", [(0, 0, 128, 64)])], box=(6, 25, 116, 42), cap=13, align="r",
                  variation="Bold Condensed", spacing=0.8, mode="glow", radius=2.2, strength=1.3, smear=4,
                  smear_k=0.45)
for n, en in enumerate(["Sortie in", "Re-sortie in", "Ends in", "Transfer in"], 1):
    job(f"count/count_head_{n:02d}", en, sample=(29, 25, 116, 42), **COUNT_HEAD)
# "[n] sec left": the game draws the number between the two words (x ~150..218). English: the word before the
# number is dropped ("Ends in 12 SEC"); the unit after it becomes SEC. The decorative lines above stay.
job("count/count_remain", "SEC (after the number)",
    erase=[("black", [(112, 36, 152, 64), (216, 36, 256, 64)])], parts=[dict(text="SEC")],
    box=(219, 40, 250, 57), cap=13, align="l", variation="Bold Condensed", spacing=0.8, mode="glow",
    sample=(218, 36, 240, 58), radius=2.2, strength=1.3, smear=4, smear_k=0.45)
job("count/count_skip", "Hold to end now", erase=[("black", [(70, 16, 240, 50)])], box=(72, 22, 236, 44), cap=14,
    align="l", variation="Bold Condensed", spacing=0.8, mode="glow", sample=(72, 22, 222, 44), radius=2.2,
    strength=1.3)
job("count/count_pena", "Re-sortie incurs a penalty", erase=[("black", [(123, 14, 430, 50)])],
    box=(126, 22, 420, 40), cap=14, align="l", variation="Bold Condensed", spacing=0.8, mode="glow",
    sample=(126, 24, 409, 39), radius=2.5, strength=1.4)

# DLC Area Raid captions
job("hud/hud_dlcm/hud_dlcm_nav1", "Capturing enemy base", erase=[("black", [(0, 0, 232, 40)])],
    box=(8, 11, 224, 28), cap=13, variation="Bold Condensed", spacing=0.8, mode="glow", sample=(48, 11, 184, 28),
    radius=2.3, strength=1.4)
job("hud/hud_dlcm/hud_dlcm_nav2", "Restoring Durability", erase=[("black", [(0, 0, 232, 40)])],
    box=(8, 10, 224, 29), cap=14, variation="Bold Condensed", spacing=0.8, mode="glow", sample=(10, 10, 223, 29),
    radius=2.3, strength=1.4)
# "Base [letter] captured!": the game puts the base letter in the gap at x ~50..75
job("hud/hud_dlcm/hud_dlcm_success", "Base [X] captured!", erase=[("black", [(0, 0, 200, 40)])],
    parts=[dict(text="Base", box=(4, 9, 49, 29), align="r"), dict(text="captured!", box=(77, 9, 198, 29),
                                                                  align="l")],
    cap=14, variation="Bold Condensed", spacing=0.8, mode="glow", sample=(12, 9, 191, 29), radius=2.3,
    strength=1.4)
job("action/action_skip", "Skip", erase=[("black", [(40, 8, 132, 44)])], box=(46, 15, 128, 37), cap=16,
    align="l", variation="Bold Condensed", spacing=1.0, mode="glow", sample=(43, 15, 125, 37), radius=2.3,
    strength=1.4)


# ============================================================== Paint (grg_pnt)

for n, en in enumerate(["Pattern", "Color Set", "Decal", "Gloss", "Chipping", "Airbrush", "Weathering", "Scratches",
                        "Foot Grime"], 1):
    job(f"grg_pnt/grg_pnt_head/grg_pnt_head_{n:02d}", en, **{**CONFIG_HEAD, "spacing": 6.0})
# grg_pnt_head_10 (question marks) has no Japanese: left as it is.


# ============================================================== Headers / counters

job("header/header_remind", "We're waiting for you to get ready!!", erase=[("black", [(33, 8, 340, 38)])],
    box=(36, 13, 336, 31), cap=14, align="l", variation="Bold Condensed", spacing=0.8, mode="glow",
    sample=(36, 14, 330, 30), radius=2.5, strength=1.4, scale=1.2)
QUANTITY = dict(erase=[("black", [(0, 4, 188, 28)])], box=(4, 9, 184, 22), cap=11, align="r",
                variation="Bold Condensed", spacing=0.7, min_spacing=0.2, mode="glow", radius=1.8, strength=1.2)
for n, en in enumerate(["Runners Held", "Head Parts Held", "Body Parts Held", "Arm Parts Held", "Leg Parts Held",
                        "Backpack Parts Held", "Shields Held", "Melee Weapons Held", "Ranged Weapons Held",
                        "Modules Held", "Parts Stock"], 1):
    job(f"header/header_quantity/header_quantity_{n:02d}", en, sample=(50, 9, 184, 22), **QUANTITY)


# ============================================================== Boosters

BOOSTER = dict(erase=[("black", [(0, 0, 160, 32)])], box=(8, 9, 152, 24), cap=12, variation="Bold Condensed",
               spacing=1.0, mode="glow", radius=2.2, strength=1.3, wide=5, wide_k=0.25)
job("booster/bst_name_01", "Luck Booster", sample=(33, 10, 144, 24), **BOOSTER)
job("booster/bst_name_02", "EXP Booster", sample=(35, 10, 144, 24), **BOOSTER)
job("booster/bst_name_03", "Sharp Nippers", sample=(26, 9, 145, 25), **BOOSTER)
# "[n] left" around the remaining-uses number: the word before the number is dropped, the unit after it says LEFT
job("booster/hngr_bst_remain", "(blank: word before the number)", erase=[("black", [(0, 0, 52, 32)])], parts=[])
job("booster/hngr_bst_remain2", "LEFT", erase=[("black", [(0, 0, 40, 32)])], box=(4, 9, 39, 23), cap=11,
    align="l", variation="Bold Condensed", spacing=0.6, mode="glow", sample=(13, 9, 27, 23), radius=2.0,
    strength=1.3)


# ============================================================== Intro subtitles (648x88, white with a dark shadow)

SUBTITLE = dict(erase=[("clear", [(0, 0, 648, 88)])], cap=17, variation="SemiBold", spacing=0.3,
                top=(255, 255, 255), outline=(0, 0, 0), outline_alpha=110, shadow=(0, 0, 0), shadow_alpha=170,
                shadow_off=(2, 2))
job("subtitle/subtitle_01", "The many amazing exhibits of the GGF", box=(8, 30, 640, 56), **SUBTITLE)
job("subtitle/subtitle_02", "Behind it all is the latest hologram technology!", box=(8, 29, 640, 56), **SUBTITLE)
job("subtitle/subtitle_03", "Using it, Odaiba itself becomes a battlefield where Gundams fight!!",
    parts=[dict(text="Using it, Odaiba itself becomes", box=(8, 12, 640, 38)),
           dict(text="a battlefield where Gundams fight!!", box=(8, 48, 640, 74))], **SUBTITLE)


# ============================================================== Title / save data

job("title/title_cross_help", "Select the data to load", erase=[("black", [(0, 0, 352, 56)])],
    box=(8, 17, 344, 38), cap=17, variation="Bold Condensed", spacing=0.8, mode="glow", sample=(19, 18, 333, 37),
    radius=2.5, strength=1.4, wide=7, wide_k=0.3)
CROSS_TXT = dict(erase=[("black", [(0, 0, 320, 56)])], box=(8, 14, 312, 32), cap=16, variation="Bold Condensed",
                 spacing=0.8, mode="glow", radius=2.5, strength=1.4, wide=6, wide_k=0.3)
for n, (en, sx) in enumerate([("Creating new data", (37, 284)), ("No data", (62, 258)),
                              ("Failed to get data", (16, 303)), ("Please sign in", (44, 276)),
                              ("Save data info not retrieved", (36, 283)), ("Data version mismatch", (22, 299))], 1):
    job(f"title/title_cross_txt{n:02d}", en, sample=(sx[0], 16, sx[1], 30), **CROSS_TXT)
job("title/title_copyright", "(c) SOTSU / SUNRISE (/ TV TOKYO)", erase=[("clear", [(0, 0, 248, 52)])],
    parts=[dict(text="© SOTSU · SUNRISE", box=(6, 6, 246, 23)),
           dict(text="© SOTSU · SUNRISE · TV TOKYO", box=(6, 30, 246, 47))],
    cap=12, align="l", variation="SemiBold", spacing=0.3, top=(255, 255, 255), shadow=(0, 0, 0), shadow_alpha=150)
job("dialog/dialog_cross_5min", "PSN limits rapid repeated access; please wait a while before trying again",
    erase=[("black", [(54, 6, 756, 30)]), ("black", [(0, 30, 756, 54)])],
    parts=[dict(text="PlayStation®Network limits rapid repeated access to its data.", box=(56, 11, 700, 29),
                align="l", sample=(56, 11, 647, 29)),
           dict(text="Please wait a while before trying again.", box=(56, 32, 600, 50), sample=(156, 32, 596, 49))],
    cap=14, variation="SemiBold SemiCondensed", spacing=0.4, mode="glow", radius=2.2, strength=1.3)

# Blueprint without a picture: NO IMAGE box stays, the three lines below are redrawn over the silhouette
job("grg_set/grg_set_plan/grg_set_plan_noimage", "Updated via cross-save, so there is no Gunpla image",
    erase=[("inpaint", [(18, 99, 206, 164)], dict(thr=55, grow=2))],
    parts=[dict(text="Updated via cross-save,", box=(20, 102, 204, 119)),
           dict(text="so there is no", box=(20, 123, 204, 140)),
           dict(text="Gunpla image", box=(20, 143, 204, 160))],
    cap=12, variation="Bold Condensed", spacing=0.6, mode="glow", sample=(29, 102, 197, 160), radius=2.0,
    strength=0.9, scale=1.15)

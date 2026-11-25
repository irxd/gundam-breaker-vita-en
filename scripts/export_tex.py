"""Export the textures outside GP/ui (or any prefix) to PNG with contact sheets, to look for Japanese text.

  python -E -P scripts/export_tex.py [--prefix GP/map/ ...] [--loose] [--all-maps] [--thumb 192]
  python -E -P scripts/export_tex.py --ui      loose-only UI textures with text -> game/ui_png (for draw_ui.py)

(-E -P instead of -I because Pillow lives in user site-packages; the script still reads the dump as data only.)

Sources:
  - every `tex` member of the pac bundles in GxArchivedFile001.dat and 002.dat (path known);
  - with --loose, every loose `tex` entry in GxArchivedFile000.dat whose hash1 matches no pac path
    (7,892 of 9,672; their names are unknown, so they are written as _loose/<hash1>).
GP/ui is skipped unless --prefix asks for it (scripts/export_ui.py covers it). Model maps that never hold text
(normal, specular, control, environment: *_nor, *_spc, *_ctl, *_env) are skipped unless --all-maps.

Writes (all under game/, git-ignored):
  game/tex_png/<path>.png            first mip level, padding cropped
  game/tex_png/_sheets/<group>.png   contact sheets (thumbnails, labelled), grouped by folder (GP/model, GP/preset
                                     and _loose as one group each)
  game/tex_index.tsv                 path, archive, copies, width, height, format bytes

Formats seen (header byte 4..7 = 12 4L xx Ld, L = mip levels): xx 00 DXT1, 10 DXT3, 20 DXT5; a few textures have
byte 4 = 0x64 (32-bit RGBA, decoded here as swizzled RGBA8). Level 0 comes first.
"""
import argparse
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gdat  # noqa: E402
import pac  # noqa: E402
import tex  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

SRC = os.path.join(ROOT, "dump", "app", "PCSG00126", "masterPSP2")
OUT = os.path.join(ROOT, "game", "tex_png")
TEX = 0xFC397BB3
SKIP_MAPS = ("_nor", "_spc", "_ctl", "_env")


def decode_any(payload):
    """First mip level of any tex payload as RGBA (DXT1/3/5 or RGBA8)."""
    w, h = struct.unpack_from("<HH", payload, 0)
    f = payload[4:8]
    pw, ph = max(4, tex._p2(w)), max(4, tex._p2(h))
    if f[0] == 0x64:  # 32-bit, swizzled per pixel
        data = payload[tex.HEADER:tex.HEADER + pw * ph * 4]
        m = min(pw, ph)
        px = bytearray(pw * ph * 4)
        for y in range(ph):
            for x in range(pw):
                if pw >= ph:
                    t, lx, ly = x // m, x % m, y
                else:
                    t, lx, ly = y // m, x, y % m
                s = (t * m * m + tex._morton(lx, ly)) * 4
                d = (y * pw + x) * 4
                px[d:d + 4] = data[s:s + 4]
        return Image.frombytes("RGBA", (pw, ph), bytes(px)).crop((0, 0, w, h))
    n = {0x00: 1, 0x10: 2, 0x20: 3}[f[2]]
    bs = 8 if n == 1 else 16
    bw, bh = pw // 4, ph // 4
    data = payload[tex.HEADER:tex.HEADER + bw * bh * bs]
    blocks = [data[s * bs:(s + 1) * bs] for s in tex._block_order(bw, bh)]
    return Image.frombytes("RGBA", (pw, ph), b"".join(blocks), "bcn", n).crop((0, 0, w, h))


# Loose-only UI textures in 000 (no pac copy) that show text. Names: from the eboot's string table (title_00,
# leadbanner, title_demo/*) or found by varying the last characters of known GP/ui paths (hash1 = name_hash(path));
# the rest have no known name and are addressed by hash1 as _loose/<hash1>. See notes/images.md.
LOOSE_UI = {
    0x8A91CB75: "GP/ui/ui_dds/title/title_00",                   # piracy notice before the logos
    0x9496D702: "GP/ui/ui_dds/dialog/leadbanner",                # DLC (Giga Break Mission Pack) store prompt
    0x52EA4FDD: "GP/ui/ui_dds/rank/rank_m_08",
    0x52EA4FDE: "GP/ui/ui_dds/rank/rank_m_09",
    0xD41110F6: "GP/ui/ui_dds/grg_cstm/grg_cstm_help_1",
    0x93E57294: "GP/ui/ui_dds/result/result_key4",
    0xA21BC2CA: "GP/ui/ui_dds/title_demo/title_copyright",
    0xDCA33E07: "GP/ui/ui_dds/grg_cstm/grg_cstm_spec/grg_cstm_spec_09",
    **{0xDCA33E23 + i: f"GP/ui/ui_dds/grg_cstm/grg_cstm_spec/grg_cstm_spec_{10 + i}" for i in range(8)},
    0x00D9CEA8: "_loose/00d9cea8",                               # PAUSE screen (1280x720)
    0x49757E76: "_loose/49757e76",                               # L2 + R2 free-word chat hint
    0xD16EE459: "_loose/d16ee459",                               # melee weapon header
    0xD16EE462: "_loose/d16ee462",                               # ranged weapon header
    0xC1DAD43F: "_loose/c1dad43f",                               # flick right to close
    0xFA959A56: "_loose/fa959a56",                               # runners held
    0xFA959A57: "_loose/fa959a57",                               # parts held
    0xFA959A58: "_loose/fa959a58",                               # modules held
}


def export_loose_ui():
    """Write the LOOSE_UI textures to game/ui_png/<path>.png (where scripts/draw_ui.py looks for originals)."""
    dst_root = os.path.join(ROOT, "game", "ui_png")
    n = 0
    for _, h1, _, _, _, data in gdat.iter_entries(os.path.join(SRC, "GxArchivedFile000.dat"), {"tex"}):
        if h1 in LOOSE_UI:
            dst = os.path.join(dst_root, *LOOSE_UI[h1].split("/")) + ".png"
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            tex.decode(gdat.unpack(data)).save(dst)
            n += 1
    print(f"exported {n} of {len(LOOSE_UI)} loose-only UI textures to game/ui_png")


def collect(prefixes, loose, all_maps):
    found = {}  # path -> [payload, archive, copies]
    for arc in ("GxArchivedFile001.dat", "GxArchivedFile002.dat"):
        for _, _, _, _, _, data in gdat.iter_entries(os.path.join(SRC, arc), {"pac"}):
            for path, typ, entry in pac.parse(gdat.unpack(data)):
                if typ != TEX:
                    continue
                if path in found:
                    found[path][2] += 1
                    continue
                found[path] = [None, arc[-5], 1, entry]
    names = {gdat.name_hash(p) for p in found}
    keep = {}
    for path, (_, arc, n, entry) in found.items():
        if prefixes:
            if not any(path.startswith(p) for p in prefixes):
                continue
        elif path.startswith("GP/ui/"):
            continue
        if not all_maps and path.endswith(SKIP_MAPS):
            continue
        keep[path] = [gdat.unpack(entry), arc, n]
    if loose:
        for _, h1, _, _, _, data in gdat.iter_entries(os.path.join(SRC, "GxArchivedFile000.dat"), {"tex"}):
            if h1 not in names:
                keep[f"_loose/{h1:08x}"] = [gdat.unpack(data), "0", 1]
    return keep


def checker(w, h, s=8):
    img = Image.new("RGBA", (w, h), (90, 90, 90, 255))
    d = ImageDraw.Draw(img)
    for y in range(0, h, s):
        for x in range((y // s) % 2 * s, w, 2 * s):
            d.rectangle((x, y, x + s - 1, y + s - 1), fill=(60, 60, 60, 255))
    return img


def sheets(items, font, thumb, page_w=1800, max_h=2400):
    pages, page, x, y, row_h = [], [], 0, 0, 0
    for name, img in items:
        im = img.copy()
        im.thumbnail((thumb, thumb))
        tw, th = max(im.width, 130) + 6, im.height + 16
        if x + tw > page_w:
            x, y, row_h = 0, y + row_h, 0
        if y + th > max_h and page:
            pages.append(page)
            page, x, y, row_h = [], 0, 0, 0
        page.append((x, y, name, img.size, im))
        x += tw
        row_h = max(row_h, th)
    if page:
        pages.append(page)
    out = []
    for p in pages:
        h = max(py + im.height + 16 for _, py, _, _, im in p)
        sheet = Image.new("RGBA", (page_w, h), (30, 30, 30, 255))
        d = ImageDraw.Draw(sheet)
        for px, py, name, size, im in p:
            sheet.paste(checker(im.width, im.height), (px, py + 14))
            sheet.alpha_composite(im, (px, py + 14))
            d.text((px, py + 1), f"{name} {size[0]}x{size[1]}", fill=(255, 255, 0, 255), font=font)
        out.append(sheet)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", action="append", default=[], help="only paths starting with this (repeatable)")
    ap.add_argument("--loose", action="store_true", help="also the unnamed loose textures in 000")
    ap.add_argument("--all-maps", action="store_true", help="also normal/specular/control/environment maps")
    ap.add_argument("--thumb", type=int, default=192, help="thumbnail size on the sheets")
    ap.add_argument("--no-sheets", action="store_true")
    ap.add_argument("--ui", action="store_true", help="only export the loose-only UI textures (LOOSE_UI) to "
                    "game/ui_png for scripts/draw_ui.py, then stop")
    a = ap.parse_args()
    if a.ui:
        export_loose_ui()
        return
    found = collect(a.prefix, a.loose, a.all_maps)
    groups, rows, bad = {}, [], 0
    for path in sorted(found):
        payload, arc, n = found[path]
        w, h = struct.unpack_from("<HH", payload, 0)
        rows.append(f"{path}\t{arc}\t{n}\t{w}\t{h}\t{payload[4:8].hex()}")
        try:
            img = decode_any(payload)
        except (KeyError, ValueError) as e:
            print(f"{path}: {e}")
            bad += 1
            continue
        dst = os.path.join(OUT, *path.split("/")) + ".png"
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        img.save(dst)
        if not a.no_sheets:
            parts = path.split("/")
            depth = 2 if parts[0] == "_loose" or parts[1] in ("model", "preset") else 3
            key = "_".join(parts[:min(depth, len(parts) - 1)])
            label = "/".join(parts[min(depth, len(parts) - 1):])
            groups.setdefault(key, []).append((label, img))
    with open(os.path.join(ROOT, "game", "tex_index.tsv"), "w", encoding="utf-8") as o:
        o.write("\n".join(rows) + "\n")
    print(f"exported {len(found) - bad} textures to {os.path.relpath(OUT, ROOT)} ({bad} failed)")
    if a.no_sheets:
        return
    font = ImageFont.truetype("arial.ttf", 11)
    sd = os.path.join(OUT, "_sheets")
    os.makedirs(sd, exist_ok=True)
    n = 0
    for g, items in sorted(groups.items()):
        for k, sheet in enumerate(sheets(items, font, a.thumb)):
            sheet.convert("RGB").save(os.path.join(sd, f"{g}{'' if k == 0 else f'_{k + 1:02d}'}.png"))
            n += 1
    print(f"wrote {n} contact sheets to {os.path.relpath(sd, ROOT)}")


if __name__ == "__main__":
    main()

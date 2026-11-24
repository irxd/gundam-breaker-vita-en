"""Export every UI texture (GP/ui/*, type tex) to PNG, plus contact sheets for browsing.

  python -E -P scripts/export_ui.py [--prefix GP/ui/] [--no-sheets]

(-E -P instead of -I because Pillow lives in user site-packages; the script still reads the dump as data only.)

Writes (all under game/, git-ignored):
  game/ui_png/<path>.png             one PNG per texture (padding cropped)
  game/ui_png/_sheets/<folder>.png   contact sheets, one per folder (several pages if large), each tile labelled
                                     with the file name and size, on a checkerboard so alpha is visible
  game/ui_index.tsv                  path, width, height, format, copies (002 bundle ids) and whether a loose copy
                                     with hash1 = name_hash(path) exists in archive 000

The textures live in pac bundles in GxArchivedFile002.dat (all copies of one path are identical); 1,889 of the
1,904 GP/ui members also exist as loose entries in GxArchivedFile000.dat (identical bytes).
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
OUT = os.path.join(ROOT, "game", "ui_png")
TEX = 0xFC397BB3


def ui_textures(prefix):
    """{path: (payload, [bundle hash1, ...])} for every tex member under prefix in 002."""
    found = {}
    for _, h1, _, _, _, data in gdat.iter_entries(os.path.join(SRC, "GxArchivedFile002.dat"), {"pac"}):
        for path, typ, entry in pac.parse(gdat.unpack(data)):
            if typ != TEX or not path.startswith(prefix):
                continue
            if path in found:
                found[path][1].append(h1)
            else:
                found[path] = (gdat.unpack(entry), [h1])
    return found


def checker(w, h, s=8):
    img = Image.new("RGBA", (w, h), (90, 90, 90, 255))
    d = ImageDraw.Draw(img)
    for y in range(0, h, s):
        for x in range((y // s) % 2 * s, w, 2 * s):
            d.rectangle((x, y, x + s - 1, y + s - 1), fill=(60, 60, 60, 255))
    return img


def sheets(folder, items, font, page_w=1600, max_h=2400):
    """items: [(name, image)] -> list of sheet images."""
    pages, x, y, row_h = [], 0, 0, 0
    placed = []
    for name, img in items:
        im = img
        if im.width > page_w - 8:
            im = im.resize((page_w - 8, max(1, im.height * (page_w - 8) // im.width)))
        if im.height > max_h - 40:
            im = im.resize((max(1, im.width * (max_h - 40) // im.height), max_h - 40))
        tw, th = max(im.width, 120) + 8, im.height + 22
        if x + tw > page_w:
            x, y, row_h = 0, y + row_h, 0
        if y + th > max_h and placed:
            pages.append(placed)
            placed, x, y, row_h = [], 0, 0, 0
        placed.append((x, y, name, img, im))
        x += tw
        row_h = max(row_h, th)
    if placed:
        pages.append(placed)
    out = []
    for p in pages:
        h = max(py + im.height + 22 for _, py, _, _, im in p)
        sheet = Image.new("RGBA", (page_w, h), (30, 30, 30, 255))
        d = ImageDraw.Draw(sheet)
        for px, py, name, img, im in p:
            sheet.paste(checker(im.width, im.height), (px, py + 18))
            sheet.alpha_composite(im, (px, py + 18))
            d.text((px, py + 2), f"{name} {img.width}x{img.height}", fill=(255, 255, 0, 255), font=font)
        out.append(sheet)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="GP/ui/")
    ap.add_argument("--no-sheets", action="store_true")
    a = ap.parse_args()
    found = ui_textures(a.prefix)
    with open(os.path.join(SRC, "GxArchivedFile000.dat"), "rb") as f:
        loose = {e[1] for e in gdat.read_table(f) if e[0] == TEX}
    by_folder = {}
    rows = []
    for path in sorted(found):
        payload, copies = found[path]
        info = tex.Info(payload)
        img = tex.decode(payload)
        dst = os.path.join(OUT, *path.split("/")) + ".png"
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        img.save(dst)
        by_folder.setdefault(path.rsplit("/", 1)[0], []).append((path.rsplit("/", 1)[1], img))
        rows.append(f"{path}\t{info.w}\t{info.h}\t{'DXT5' if info.dxt5 else 'DXT1'}\t"
                    f"{','.join(f'{c:08x}' for c in copies)}\t{'yes' if gdat.name_hash(path) in loose else 'no'}")
    with open(os.path.join(ROOT, "game", "ui_index.tsv"), "w", encoding="utf-8") as o:
        o.write("path\twidth\theight\tformat\tbundles_002\tloose_000\n" + "\n".join(rows) + "\n")
    print(f"exported {len(found)} textures to {os.path.relpath(OUT, ROOT)}")
    if a.no_sheets:
        return
    font = ImageFont.truetype("arial.ttf", 13)
    sd = os.path.join(OUT, "_sheets")
    os.makedirs(sd, exist_ok=True)
    n = 0
    for folder, items in sorted(by_folder.items()):
        base = folder.replace("GP/ui/ui_dds/", "").replace("GP/ui/", "").replace("/", "_")
        for k, sheet in enumerate(sheets(folder, items, font)):
            sheet.convert("RGB").save(os.path.join(sd, f"{base}{'' if k == 0 else f'_{k + 1}'}.png"))
            n += 1
    print(f"wrote {n} contact sheets to {os.path.relpath(sd, ROOT)}")


if __name__ == "__main__":
    main()

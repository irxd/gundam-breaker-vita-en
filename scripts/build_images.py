"""Inject English UI textures into the archives.

  python -E -P scripts/build_images.py [--from-dump] [--check]

(-E -P instead of -I because Pillow lives in user site-packages; the dump is only read as data.)

Input: game/images_en/<texture path>.png, e.g. game/images_en/GP/ui/ui_dds/rank/rank_m_00.png, one PNG per
texture, the same size as the original (see scripts/export_ui.py, scripts/draw_ui.py). These redraws are derived
from game art, so they live in git-ignored game/ for now.

Every copy of a texture is patched: each 002 pac bundle that has the path as a member, and the loose `tex` entry in
000 whose hash1 = gdat.name_hash(path) (1,889 of the 1,904 GP/ui members have one; which copy the game reads is not
known yet). Some UI textures exist only as loose 000 entries (scripts/export_tex.py LOOSE_UI): those are patched in
000 only; an unnamed one is given as game/images_en/_loose/<hash1>.png. Each texture is re-encoded from the
ORIGINAL payload in the dump (tex.encode keeps the header and every 4x4 block whose pixels did not change), so the
result does not depend on earlier builds.

Layering with the text build: scripts/build_text.py writes build/patched/PCSG00126/masterPSP2/GxArchivedFile000.dat
and 002.dat from the dump (and deletes an archive it doesn't change). This script uses those files as its base when
they exist, otherwise the dump (--from-dump forces the dump), and rewrites them in place with the textures replaced.
So the order is: build_text.py, then build_images.py. Re-running build_images.py is harmless (it replaces whole
texture payloads, so the result is the same); re-running build_text.py drops the images, so run this again after it.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gdat  # noqa: E402
import pac  # noqa: E402
import tex  # noqa: E402
from PIL import Image  # noqa: E402

DUMP = os.path.join(ROOT, "dump", "app", "PCSG00126", "masterPSP2")
OUT = os.path.join(ROOT, "build", "patched", "PCSG00126", "masterPSP2")
IMAGES = os.path.join(ROOT, "game", "images_en")
TEX = 0xFC397BB3


def find_images():
    """{texture path: png file}"""
    found = {}
    for d, _, files in os.walk(IMAGES):
        for f in files:
            if f.lower().endswith(".png"):
                full = os.path.join(d, f)
                rel = os.path.relpath(full, IMAGES)[:-4].replace(os.sep, "/")
                found[rel] = full
    return found


def loose_hash(path):
    """hash1 of the loose 000 entry: name_hash(path), or the hash itself for unnamed textures (_loose/<hash1>)."""
    if path.startswith("_loose/"):
        return int(path[7:], 16)
    return gdat.name_hash(path)


def base_archive(name, from_dump):
    patched = os.path.join(OUT, name)
    if not from_dump and os.path.exists(patched):
        return patched
    return os.path.join(DUMP, name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-dump", action="store_true", help="ignore the text build output, start from the dump")
    ap.add_argument("--check", action="store_true", help="encode and report, write nothing")
    ap.add_argument("--out", default=OUT, help="output folder (default build/patched/PCSG00126/masterPSP2); the "
                    "base archives are still taken from build/patched when present")
    a = ap.parse_args()

    images = find_images()
    if not images:
        sys.exit(f"no PNGs under {os.path.relpath(IMAGES, ROOT)}")

    # Original payloads (from the dump) and new payloads.
    orig = {}
    for _, _, _, _, _, data in gdat.iter_entries(os.path.join(DUMP, "GxArchivedFile002.dat"), {"pac"}):
        for path, typ, entry in pac.parse(gdat.unpack(data)):
            if typ == TEX and path in images and path not in orig:
                orig[path] = gdat.unpack(entry)
    # Loose-only textures (no 002 copy, see scripts/export_tex.py LOOSE_UI): original from the 000 entry.
    want = {loose_hash(p): p for p in set(images) - set(orig)}
    if want:
        for _, h1, _, _, _, data in gdat.iter_entries(os.path.join(DUMP, "GxArchivedFile000.dat"), {"tex"}):
            if h1 in want:
                orig[want[h1]] = gdat.unpack(data)
    missing = sorted(set(images) - set(orig))
    if missing:
        sys.exit("not a texture in any 002 bundle nor a loose 000 entry: " + ", ".join(missing))
    new = {}
    for path, png in sorted(images.items()):
        img = Image.open(png).convert("RGBA")
        new[path] = tex.encode(orig[path], img)
        print(f"{path}: {tex.encode.changed} blocks re-encoded")
    if a.check:
        return

    os.makedirs(a.out, exist_ok=True)
    # 002: every bundle holding one of the paths.
    src = base_archive("GxArchivedFile002.dat", a.from_dump)
    replace = {}
    copies = {p: 0 for p in new}
    for h0, h1, _, _, _, data in gdat.iter_entries(src, {"pac"}):
        payload = gdat.unpack(data)
        items = pac.parse(payload)
        changed = False
        for item in items:
            if item[1] == TEX and item[0] in new:
                item[2] = gdat.repack(item[2], new[item[0]])
                copies[item[0]] += 1
                changed = True
        if changed:
            replace[(h0, h1)] = pac.build(items, payload)
    archives = [("GxArchivedFile002.dat", src, replace)]

    # 000: loose copies.
    src = base_archive("GxArchivedFile000.dat", a.from_dump)
    with open(src, "rb") as f:
        table = {(e[0], e[1]) for e in gdat.read_table(f)}
    replace = {}
    for path, payload in new.items():
        key = (TEX, loose_hash(path))
        if key in table:
            replace[key] = payload
            copies[path] += 1
    archives.append(("GxArchivedFile000.dat", src, replace))

    for path, n in sorted(copies.items()):
        print(f"{path}: {n} copies patched")
    for name, src, rep in archives:
        if not rep:
            continue
        dst = os.path.join(a.out, name)
        if os.path.abspath(src) == os.path.abspath(dst):
            # Windows can't replace a file that is open for reading: rebuild from a renamed copy.
            old = dst + ".base"
            os.replace(dst, old)
            try:
                gdat.rebuild(old, dst, rep)
            except BaseException:
                os.replace(old, dst)
                raise
            os.remove(old)
        else:
            gdat.rebuild(src, dst, rep)
        print(f"wrote {os.path.relpath(dst, ROOT)} from {os.path.relpath(src, ROOT)} ({len(rep)} entries changed)")


if __name__ == "__main__":
    main()

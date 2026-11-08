"""Tag build: overwrite every Japanese string in every dt2 table with a short ASCII ID, in place.

Purpose: check that the game font draws ASCII, and find out which table/line each on-screen text comes from.

  python -I scripts/tag_build.py

Rules (nothing moves, only string bytes change):
  * A string = a run of valid UTF-8 ending in NUL that contains at least one kana/kanji/full-width character.
  * Only the bytes from the first non-ASCII character up to the NUL are overwritten. ASCII before it (ID bytes, a
    "HG " prefix) is kept. The new text is the tag followed by NUL; the rest of the old bytes become NUL.
  * One ID per unique string (base 36, uppercase), so equal strings stay equal across tables.
  * Strings that also appear in the eboot are skipped (the code may look them up by name).
  * A leading non-kana character (kanji etc.) is kept: binary fields before a string can decode as one CJK
    character (e5 8f 97 = 受 in the dialogue tables).
  * A tag that doesn't fit is cut; a 1-character string (3 bytes) gets 3 characters.

Output:
  build/tag/PCSG00126/masterPSP2/GxArchivedFile000.dat
  build/tag/tags.tsv  (id, Japanese, tables) - contains game text, stays in build/
"""
import os
import re
import sys
from collections import OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gdat  # noqa: E402

ARCHIVE = os.path.join(ROOT, "dump", "app", "PCSG00126", "masterPSP2", "GxArchivedFile000.dat")
EBOOT = os.path.join(ROOT, "dump", "eboot", "patch", "eboot.bin.elf")
OUT_DIR = os.path.join(ROOT, "build", "tag")
OUT = os.path.join(OUT_DIR, "PCSG00126", "masterPSP2", "GxArchivedFile000.dat")

# Valid UTF-8 (1-3 byte forms, no C0 controls except \n), ending in NUL.
U8 = rb"(?:[\x0a\x20-\x7e]|[\xc2-\xdf][\x80-\xbf]|[\xe0-\xef][\x80-\xbf]{2})"
STRING = re.compile(rb"(?<![\x80-\xbf])" + U8 + rb"+?\x00")
JP = re.compile(r"[　-ヿ一-鿿＀-￯]")
KANA = re.compile(r"[　-ヿ＀-￯]")  # kana, Japanese punctuation, full-width forms


def b36(n):
    s = ""
    while True:
        n, r = divmod(n, 36)
        s = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"[r] + s
        if n == 0:
            return s


def eboot_strings():
    data = open(EBOOT, "rb").read()
    out = set()
    for m in STRING.finditer(data):
        try:
            out.add(m.group()[:-1].decode("utf-8"))
        except UnicodeDecodeError:
            pass
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    skip = eboot_strings()
    ids = OrderedDict()           # Japanese part -> id
    where = {}                    # Japanese part -> set of table names
    replace = {}
    skipped = changed_strings = protected = 0

    for h0, h1, _, _, t, data in gdat.iter_entries(ARCHIVE, {"dt2"}):
        payload = gdat.unpack(data)
        buf = bytearray(payload)
        name = f"{h1:08x}"
        edits = 0
        for m in STRING.finditer(payload):
            raw = m.group()[:-1]
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            first = next((i for i, c in enumerate(text) if ord(c) > 0x7F), None)
            if first is None or not JP.search(text):
                continue
            if text in skip or text[first:] in skip:
                skipped += 1
                continue
            # Binary fields in front of a string can look like one CJK character (e.g. e5 8f 97 = 受).
            # Keep a leading non-kana character as it is and tag what follows.
            if not KANA.match(text[first]):
                first += 1
                if not JP.search(text[first:]):
                    protected += 1
                    continue
            ja = text[first:]
            start = m.start() + len(text[:first].encode("utf-8"))
            end = m.end() - 1                      # position of the NUL
            room = end - start
            if ja not in ids:
                ids[ja] = b36(len(ids))
                where[ja] = set()
            where[ja].add(name)
            tag = ids[ja].encode("ascii")[:room]
            buf[start:end + 1] = tag + bytes(room + 1 - len(tag))
            edits += 1
        if edits:
            replace[(h0, h1)] = bytes(buf)
            changed_strings += edits

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(os.path.join(OUT_DIR, "tags.tsv"), "w", encoding="utf-8", newline="\n") as f:
        f.write("id\tjapanese\ttables\n")
        for ja, i in ids.items():
            f.write(f"{i}\t{ja.replace(chr(10), '|')}\t{' '.join(sorted(where[ja]))}\n")
    gdat.rebuild(ARCHIVE, OUT, replace)
    print(f"{len(replace)} tables, {changed_strings} strings, {len(ids)} unique IDs, {skipped} skipped (in eboot), "
          f"{protected} left alone (single non-kana character)")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()

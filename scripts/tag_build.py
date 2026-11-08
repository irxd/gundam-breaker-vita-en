"""Tag build: overwrite every Japanese string in every dt2 table with a short ASCII ID, in place.

Purpose: check that the game font draws ASCII, and find out which file/line each on-screen text comes from.

  python -I scripts/tag_build.py [--only PREFIX ...]

--only limits the tagging inside pac bundles to members whose path starts with one of the prefixes (e.g.
--only GP/text/). Archive 000 is always tagged.

Covers the dt2 entries in GxArchivedFile000.dat and the dt2 members of the pac bundles in 001/002 (the copies the
game actually shows, e.g. GP/text/voice_event_text).

Rules (nothing moves, only string bytes change):
  * A string = a run of valid UTF-8 ending in NUL that contains at least one kana/kanji/full-width character.
  * Only the bytes from the first non-ASCII character up to the NUL are overwritten. ASCII before it (ID bytes, a
    "HG " prefix) is kept. The new text is the tag followed by NUL; the rest of the old bytes become NUL.
  * One ID per unique string (base 36, uppercase), so equal strings stay equal across files.
  * Strings that also appear in the eboot are skipped (the code may look them up by name).
  * A leading non-kana character (kanji etc.) is kept: binary fields before a string can decode as one CJK
    character (e5 8f 97 = 受 in the dialogue tables).
  * A tag that doesn't fit is cut.

Output:
  build/tag/PCSG00126/masterPSP2/GxArchivedFile00{0,1,2}.dat
  build/tag/tags.tsv  (id, Japanese, files) - contains game text, stays in build/
"""
import os
import re
import sys
from collections import OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gdat  # noqa: E402
import pac  # noqa: E402

SRC = os.path.join(ROOT, "dump", "app", "PCSG00126", "masterPSP2")
EBOOT = os.path.join(ROOT, "dump", "eboot", "patch", "eboot.bin.elf")
OUT_DIR = os.path.join(ROOT, "build", "tag")
OUT = os.path.join(OUT_DIR, "PCSG00126", "masterPSP2")
DT2 = 0x2C1CF0E2

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


class Tagger:
    def __init__(self, skip):
        self.skip = skip
        self.ids = OrderedDict()   # Japanese -> id
        self.where = {}            # Japanese -> set of file names
        self.strings = self.skipped = self.protected = 0

    def tag(self, payload: bytes, name: str):
        """Return the tagged payload, or None when nothing changed."""
        buf = bytearray(payload)
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
            if text in self.skip or text[first:] in self.skip:
                self.skipped += 1
                continue
            if not KANA.match(text[first]):
                first += 1
                if not JP.search(text[first:]):
                    self.protected += 1
                    continue
            ja = text[first:]
            start = m.start() + len(text[:first].encode("utf-8"))
            end = m.end() - 1
            room = end - start
            if ja not in self.ids:
                self.ids[ja] = b36(len(self.ids))
                self.where[ja] = set()
            self.where[ja].add(name)
            t = self.ids[ja].encode("ascii")[:room]
            buf[start:end + 1] = t + bytes(room + 1 - len(t))
            edits += 1
        self.strings += edits
        return bytes(buf) if edits else None


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
    only = tuple(sys.argv[sys.argv.index("--only") + 1:]) if "--only" in sys.argv else None
    tagger = Tagger(eboot_strings())
    os.makedirs(OUT, exist_ok=True)

    # Bundles first: they also give us the real names for archive 000.
    names = {}
    for arc in ("001", "002"):
        path = os.path.join(SRC, f"GxArchivedFile{arc}.dat")
        replace = {}
        members_changed = 0
        for h0, h1, _, _, t, data in gdat.iter_entries(path, {"pac"}):
            payload = gdat.unpack(data)
            items = pac.parse(payload)
            changed = False
            for item in items:
                fname, typ, entry = item
                names[gdat.name_hash(fname)] = fname
                if typ != DT2 or (only and not fname.startswith(only)):
                    continue
                new = tagger.tag(gdat.unpack(entry), fname)
                if new is not None:
                    item[2] = gdat.repack(entry, new)
                    changed = True
                    members_changed += 1
            if changed:
                replace[(h0, h1)] = pac.build(items, payload)
        gdat.rebuild(path, os.path.join(OUT, f"GxArchivedFile{arc}.dat"), replace)
        print(f"{arc}: {len(replace)} bundles, {members_changed} dt2 members changed")

    path = os.path.join(SRC, "GxArchivedFile000.dat")
    replace = {}
    for h0, h1, _, _, t, data in gdat.iter_entries(path, {"dt2"}):
        new = tagger.tag(gdat.unpack(data), names.get(h1, f"000:{h1:08x}"))
        if new is not None:
            replace[(h0, h1)] = new
    gdat.rebuild(path, os.path.join(OUT, "GxArchivedFile000.dat"), replace)
    print(f"000: {len(replace)} dt2 entries changed")

    with open(os.path.join(OUT_DIR, "tags.tsv"), "w", encoding="utf-8", newline="\n") as f:
        f.write("id\tjapanese\tfiles\n")
        for ja, i in tagger.ids.items():
            f.write(f"{i}\t{ja.replace(chr(10), '|')}\t{' '.join(sorted(tagger.where[ja]))}\n")
    print(f"{tagger.strings} strings, {len(tagger.ids)} unique IDs, {tagger.skipped} skipped (in eboot), "
          f"{tagger.protected} left alone (single non-kana character)")


if __name__ == "__main__":
    main()

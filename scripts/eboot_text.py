"""Japanese strings inside the eboot (UI labels, lobby text, the default Gunpla name, ...): extract and patch.

  python -I scripts/eboot_text.py extract   -> work/eboot.csv (id, ja, en, notes); merges en/notes like extract_text
  python -I scripts/sync_text.py            -> text/eboot.csv (shared step for all tables)
  python -I scripts/eboot_text.py build [--check]
                                            -> build/patched_elf/<app|patch>/eboot.bin.elf, then the fake-signed
                                               build/eboot/<app|patch>/eboot.bin (via make_eboot.build)

Strings are null-terminated UTF-8 in the read-only part of the first (text) LOAD segment. Code reaches them
through movw/movt pairs with relocations, so a string can't move: English is written **in place** and must fit
the slot = the Japanese bytes plus the zero padding up to the next 4-byte boundary (never past it, the next
object may start there). The rest of the slot is cleared with zeros. Japanese is ~3 bytes per character, so short
English fits almost always; the build fails on anything that doesn't.

id = file offset in the 1.02 ELF (hex). The 1.00 ELF is matched string by string: the n-th occurrence of the same
Japanese among the candidates in 1.02 is the n-th occurrence in 1.00 (the build fails if the counts differ).
Candidates: 4-byte aligned, preceded by a zero byte, valid UTF-8 with kana/kanji, no control characters. Many are
debug/tool names (motion properties, sound editor); leave their en empty and they stay as they are.
Checks (shared with build_text.check): printf conversions in the same order, markup, button icons, charset.
"""
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import textdb  # noqa: E402

CSV = "eboot.csv"
VERSIONS = ("app", "patch")
REF = "patch"
JP = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
NOISE = re.compile(r"[\u3040-\u9fff][\x21-\x7e]{1,2}")


def elf_path(version):
    return os.path.join(ROOT, "dump", "eboot", version, "eboot.bin.elf")


def text_segment(d):
    phoff, = struct.unpack_from("<I", d, 0x1C)
    es, n = struct.unpack_from("<HH", d, 0x2A)
    for i in range(n):
        t, off, _, _, fs, _, _, _ = struct.unpack_from("<8I", d, phoff + i * es)
        if t == 1:
            return off, off + fs
    raise ValueError("no LOAD segment")


def strings(d):
    """Return [(offset, slot size, text)] for every Japanese string candidate, in file order."""
    lo, hi = text_segment(d)
    out = []
    pos = lo
    while True:
        pos = d.find(b"\x00", pos, hi)
        if pos < 0:
            break
        start = pos + 1
        while start < hi and d[start] == 0:
            start += 1
        end = d.find(b"\x00", start, hi)
        if end < 0:
            break
        pos = end
        # The string may follow a zero byte or sit right after a pointer/other data: try every 4-byte aligned
        # start inside the non-zero run and keep the first that is a clean Japanese string up to the zero.
        text = None
        for a in range((start + 3) & ~3, end - 1, 4):
            try:
                t = d[a:end].decode("utf-8")
            except UnicodeDecodeError:
                continue
            if not JP.search(t) or any(ord(c) < 0x20 or 0x7F <= ord(c) < 0xA0 for c in t):
                continue
            if NOISE.fullmatch(t):  # entries of a kana/kanji conversion table, e.g. one kanji + 1-2 code bytes
                continue
            start, text = a, t
            break
        if text is None:
            continue
        slot = (end + 1 + 3) & ~3
        while slot > end + 1 and any(d[end + 1:slot]):
            slot -= 1
        out.append((start, slot - start, text))
    return out


def matched():
    """Return {version: {id: (offset, slot)}} plus the reference list."""
    ref = strings(open(elf_path(REF), "rb").read())
    result = {}
    for v in VERSIONS:
        cand = ref if v == REF else strings(open(elf_path(v), "rb").read())
        by_text = {}
        for off, slot, text in cand:
            by_text.setdefault(text, []).append((off, slot))
        seen = {}
        m = {}
        for off, _, text in ref:
            k = seen.get(text, 0)
            seen[text] = k + 1
            lst = by_text.get(text, [])
            if k < len(lst):
                m[f"{off:x}"] = lst[k]
        result[v] = m
    return ref, result


def extract():
    ref, _ = matched()
    work = textdb.read_work(CSV)
    text = textdb.read_text(CSV)
    rows = []
    for off, _, ja in ref:
        rid = f"{off:x}"
        row = {"id": rid, "ja": ja, "en": "", "notes": ""}
        w, t = work.get(rid), text.get(rid)
        if w and w["ja"] == ja and (w["en"] or w["notes"]):
            row["en"], row["notes"] = w["en"], w["notes"]
        elif t and t["ja_hash"] == textdb.ja_hash(ja):
            row["en"], row["notes"] = t["en"], t["notes"]
        rows.append(row)
    textdb.write_work(CSV, rows)
    print(f"{CSV}: {len(rows)} strings, {sum(1 for r in rows if r['en'])} with English -> work/{CSV}")


def build(check_only):
    import build_text  # check() and the charset
    ref, where = matched()
    ja_by_id = {f"{off:x}": ja for off, _, ja in ref}
    rows = textdb.read_text(CSV)
    charset = build_text.charset() if hasattr(build_text, "charset") else None
    problems = []
    todo = []
    for rid, r in rows.items():
        if not r["en"]:
            continue
        ja = ja_by_id.get(rid)
        if ja is None or textdb.ja_hash(ja) != r["ja_hash"]:
            problems.append(f"{rid}: unknown id or the Japanese changed")
            continue
        cs = charset if charset is not None else set(map(chr, range(0x20, 0x7F))) | set(ja)
        for p in build_text.check(ja, r["en"], cs):
            problems.append(f"{rid}: {p}")
        en = r["en"].encode("utf-8")
        for v in VERSIONS:
            if rid not in where[v]:
                # 1.00 lacks a few strings that later updates added (e.g. the PS3 controls note): skip there.
                print(f"note: {rid} is not in the {v} eboot, skipped for that version")
                continue
            off, slot = where[v][rid]
            if len(en) + 1 > slot:
                problems.append(f"{rid}: '{r['en']}' is {len(en)} bytes, the slot holds {slot - 1}")
            todo.append((v, off, slot, en))
    if problems:
        sys.exit("eboot text problems:\n" + "\n".join(f"- {p}" for p in problems))
    print(f"eboot: {len(todo)} string patches OK")
    if check_only:
        return
    import fself
    import make_eboot
    for v in VERSIONS:
        d = bytearray(open(elf_path(v), "rb").read())
        for vv, off, slot, en in todo:
            if vv == v:
                d[off:off + slot] = en + b"\x00" * (slot - len(en))
        out = os.path.join(ROOT, "build", "patched_elf", v, "eboot.bin.elf")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, "wb").write(d)
        authid = fself.authid_from_self_auth(os.path.join(ROOT, "dump", "eboot", v, "self_auth.bin"))
        make_eboot.build(out, os.path.join(ROOT, "build", "eboot", v, "eboot.bin"), authid, check_sha=False)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "extract":
        extract()
    elif cmd == "build":
        build("--check" in sys.argv)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()

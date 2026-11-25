"""Build patched archives from the committed English (text/*.csv) and the original dump.

  python -I scripts/build_text.py           check, then write build/patched/PCSG00126/masterPSP2/*.dat
  python -I scripts/build_text.py --check   only check the translations (fast, writes nothing)
  python -I scripts/build_text.py --strict-size
                                            also fail when a compressed entry or bundle grows. By default that is
                                            only a warning (archive offsets are rebuilt; a larger bundle works in
                                            Vita3K, 2026-11-09; not yet tested on a real Vita). Tables never grow.

Lines with an empty `en` keep the Japanese. All problems are collected and the build fails if there are any:
  * id unknown, or ja_hash doesn't match the Japanese in the dump
  * printf conversions (%d, %s, ...) not the same and in the same order, or a stray % (crashes the game)
  * colour tags <cNN> / </c> not the same sequence
  * button icons (circled numbers ①-⑳, drawn as Vita buttons) not the same set
  * a short one-line label (no <br>, at most LABEL_MAX characters) that gets a <br>
  * a real line break in the English (use <br>)
  * in the name fields of the data tables (unitData, csv, map): a grade prefix at the start of the Japanese
    ("HG ", "MG ", "PG") not kept at the start of the English (the game cuts "HG " off part names in the Set Up
    list). Sentences that start with a grade (mission text, descriptions) are not checked.
  * a character the font may not have: allowed are printable ASCII and anything used in the Japanese text
  * a table that would grow (a compressed entry or bundle that grows is only a warning, see --strict-size)
Only GxArchivedFile000.dat and 002.dat can change; an archive is written only when something in it changed.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import dt2  # noqa: E402
import gbtext  # noqa: E402
import gdat  # noqa: E402
import pac  # noqa: E402
import textdb  # noqa: E402

SRC = os.path.join(ROOT, "dump", "app", "PCSG00126", "masterPSP2")
OUT = os.path.join(ROOT, "build", "patched", "PCSG00126", "masterPSP2")

PRINTF = re.compile(r"%[-+ #0]*\d*(?:\.\d+)?(?:hh|h|ll|l)?[diouxXcsfFeEgGp]")
COLOUR = re.compile(r"</?c\d*>")
ICONS = re.compile("[①-⑳]")
TAG = re.compile(r"<[^>]*>|\\n")
LABEL_MAX = 12
GRADE = re.compile(r"^(?:HG|MG|PG|ＰＧ) ?")
DESCRIPTION_TABLES = {"000_parts_phonetic.csv"}   # data tables that hold descriptions, not names


def check(ja, en, charset, names=False):
    """Return a list of problems with one translation. names: the line is a name in a data table (grade check)."""
    problems = []
    want = PRINTF.findall(ja)
    if want and (PRINTF.findall(en) != want or "%" in PRINTF.sub("", en).replace("%%", "")):
        problems.append(f"printf: Japanese has {want}, English has {PRINTF.findall(en)} (a literal % must be %%)")
    elif not want and "%" in en:
        problems.append("a % in a line without printf conversions could be read as a format: use the full-width ％ "
                        "(as the Japanese does)")
    if COLOUR.findall(ja) != COLOUR.findall(en):
        problems.append(f"colour tags: Japanese {COLOUR.findall(ja)}, English {COLOUR.findall(en)}")
    if sorted(ICONS.findall(ja)) != sorted(ICONS.findall(en)):
        problems.append(f"button icons: Japanese {''.join(ICONS.findall(ja))}, English {''.join(ICONS.findall(en))}")
    if "<br>" not in ja and "<br>" in en and len(TAG.sub("", ja)) <= LABEL_MAX:
        problems.append("one-line label got a <br>")
    if "\n" in en or "\r" in en:
        problems.append("real line break in the English (use <br>)")
    m = GRADE.match(ja) if names else None
    if m:
        grade = m.group(0).strip().replace("ＰＧ", "PG")
        if not en.startswith(grade):
            problems.append(f"grade prefix: the Japanese starts with {m.group(0)!r}, the English must start with "
                            f"{grade!r} (the Set Up list cuts it off)")
    bad = sorted({c for c in en if c not in charset})
    if bad:
        problems.append(f"characters the font may not have: {''.join(bad)!r}")
    return problems


def rebuild(t, edits, errors):
    """Return the re-packed payload of table t with edits {(i, k): en}; size problems go to errors."""
    table = dt2.Dt2(t.payload)
    table.rebuild(edits)
    try:
        table.clear_unused()
    except ValueError:
        pass                        # unknown field sizes: leave leftovers alone
    new = table.to_bytes()
    if len(new) > len(t.payload):
        errors.append(f"text/{t.csv} ({t.label}): table would grow {len(t.payload)} -> {len(new)} bytes "
                      "(shorten lines)")
    # Read back: edited strings are the English, all others unchanged.
    before = {(i, k): s for i, k, _, s in dt2.Dt2(t.payload).strings()}
    after = {(i, k): s for i, k, _, s in dt2.Dt2(new).strings()}
    assert before.keys() == after.keys()
    for ik, s in before.items():
        assert after[ik] == edits.get(ik, s), (t.label, ik)
    return new


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    check_only = "--check" in sys.argv
    strict_size = "--strict-size" in sys.argv
    tables = gbtext.load_tables(SRC)
    charset = {chr(c) for c in range(0x20, 0x7F)}
    for t in tables:
        for _, _, _, ja in t.japanese():
            charset.update(ja)

    errors = []
    new_tables = {}       # key -> new payload (data tables: under the member path and the loose 000 key)
    translated = 0
    groups = {}           # csv name -> tables (the unitData folders share one csv)
    for t in tables:
        groups.setdefault(t.csv, []).append(t)
    for name, group in groups.items():
        rows = textdb.read_text(name)
        if not rows:
            continue
        lines = {rid: (t, i, k, ja) for t in group for rid, i, k, ja in t.japanese()}
        edits = {}        # table name -> {(i, k): en}
        for rid, r in rows.items():
            if not r["en"]:
                continue
            where = f"text/{name} id {rid}"
            if rid not in lines:
                errors.append(f"{where}: no such Japanese line")
                continue
            t, i, k, ja = lines[rid]
            if r["ja_hash"] != textdb.ja_hash(ja):
                errors.append(f"{where}: ja_hash {r['ja_hash']} doesn't match the Japanese {ja!r}")
                continue
            names = t.source == "data" and t.csv not in DESCRIPTION_TABLES
            for p in check(ja, r["en"], charset, names):
                errors.append(f"{where}: {p}\n    ja: {ja}\n    en: {r['en']}")
            edits.setdefault(t.label, {})[(i, k)] = r["en"]
        old_size = new_size = 0
        for t in group:
            if t.label not in edits:
                continue
            new = rebuild(t, edits[t.label], errors)
            new_tables[t.key] = new
            if t.loose:
                new_tables[t.loose] = new
            translated += len(edits[t.label])
            old_size += len(t.payload)
            new_size += len(new)
        if edits:
            n = sum(len(e) for e in edits.values())
            files = f" in {len(edits)} files" if len(group) > 1 else ""
            print(f"{name:32} {n:5} lines{files}  {old_size} -> {new_size} bytes")

    if errors:
        print(f"\n{len(errors)} problem(s):")
        for e in errors:
            print(f"- {e}")
        sys.exit(1)
    print(f"checks passed: {translated} translated lines in {len(new_tables)} tables")
    if check_only or not new_tables:
        return

    os.makedirs(OUT, exist_ok=True)
    size_errors = []

    def entry(old, payload, what):
        new = gdat.repack(old, payload)
        if len(new) > len(old):
            msg = f"{what}: compressed entry would grow {len(old)} -> {len(new)} bytes"
            if strict_size:
                size_errors.append(msg)
            else:
                print(f"warning: {msg}")
        return new

    # Archive 002: every bundle that holds a changed member (GP/text or a data table).
    path = os.path.join(SRC, "GxArchivedFile002.dat")
    replace = {}
    for h0, h1, _, _, _, data in gdat.iter_entries(path, {"pac"}):
        payload = gdat.unpack(data)
        items = pac.parse(payload)
        changed = False
        for item in items:
            if item[0] in new_tables:
                item[2] = entry(item[2], new_tables[item[0]], f"{item[0]} in bundle {h1:08x}")
                changed = True
        if changed:
            bundle = pac.build(items, payload)
            entry(data, bundle, f"bundle {h1:08x}")
            replace[(h0, h1)] = bundle
    archives = [("GxArchivedFile002.dat", path, replace)]

    # Archive 000.
    path = os.path.join(SRC, "GxArchivedFile000.dat")
    replace = {}
    for h0, h1, _, _, _, data in gdat.iter_entries(path, {"dt2"}):
        if (h0, h1) in new_tables:
            entry(data, new_tables[(h0, h1)], f"000 entry {h1:08x}")
            replace[(h0, h1)] = new_tables[(h0, h1)]
    archives.append(("GxArchivedFile000.dat", path, replace))

    if size_errors:
        print("\n".join(f"- {e}" for e in size_errors))
        sys.exit(1)
    for name, src, rep in archives:
        dst = os.path.join(OUT, name)
        if rep:
            gdat.rebuild(src, dst, rep)
            print(f"wrote {os.path.relpath(dst, ROOT)} ({len(rep)} entries changed)")
        elif os.path.exists(dst):
            os.remove(dst)          # unchanged: don't leave an old patched copy behind


if __name__ == "__main__":
    main()

"""Extract the game's text tables to CSV files for translation.

  python -I scripts/extract_text.py

Writes text/<name>.csv with columns:
  id     record index:field index inside the original table (stable, used by the inserter)
  ja     the Japanese string, exactly as stored (markup such as <br>, <c02>…</c>, \\n kept)
  en     English (empty = keep the Japanese)
  notes  free text
Only strings that contain Japanese are listed. An existing CSV is not overwritten (so translations are never lost);
use --force to rewrite it, which keeps the en/notes of rows whose id and ja are unchanged.

Sources (see notes/formats.md):
  * bundle  - GP/text/* members of the pac bundles in GxArchivedFile002.dat (identical copies: the first is read)
  * 000     - dt2 entries in GxArchivedFile000.dat, by name hash (TABLES_000)
"""
import csv
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import dt2  # noqa: E402
import gdat  # noqa: E402
import pac  # noqa: E402

SRC = os.path.join(ROOT, "dump", "app", "PCSG00126", "masterPSP2")
OUT = os.path.join(ROOT, "text")
DT2 = 0x2C1CF0E2
JP = re.compile("[぀-ヿ一-鿿！-～]")

# Text tables in archive 000. Names from hashing eboot strings; two are still unknown.
TABLES_000 = [
    "GP/text/avatar_detail", "GP/text/avatar_name", "GP/text/booster_name", "GP/text/boxes_name",
    "GP/text/chip_detail", "GP/text/chip_name", "GP/text/generalaction_text", "GP/text/load_text",
    "GP/text/mail", "GP/text/mail_category", "GP/text/patterns_detail", "GP/text/patterns_name",
    "GP/text/rank_name", "GP/text/runners_detail", "GP/text/skill_detail", "GP/text/system_text",
    0xBBCF42D0, 0xC4829255,
]
# Left out on purpose: GP/text/parts_phonetic (sort readings), GP/csv/* (data), GP/unitData/* (names may be keys).


def csv_name(source, name):
    base = name.split("/")[-1] if isinstance(name, str) else f"{name:08x}"
    return f"{source}_{base}.csv" if source == "000" else f"{base}.csv"


def rows_of(payload):
    table = dt2.Dt2(payload)
    for i, k, _, text in table.strings():
        if JP.search(text):
            yield f"{i}:{k}", text


def write_csv(path, rows, force):
    old = {}
    if os.path.exists(path):
        if not force:
            return "kept (exists)"
        with open(path, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                old[r["id"]] = r
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["id", "ja", "en", "notes"])
        kept = 0
        for rid, ja in rows:
            prev = old.get(rid)
            if prev and prev["ja"] == ja:
                w.writerow([rid, ja, prev["en"], prev["notes"]])
                kept += prev["en"] != ""
            else:
                w.writerow([rid, ja, "", ""])
    return f"written ({kept} translations kept)" if old else "written"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    force = "--force" in sys.argv
    os.makedirs(OUT, exist_ok=True)
    tables = []   # (source, name, payload)

    seen = set()
    for _, _, _, _, _, data in gdat.iter_entries(os.path.join(SRC, "GxArchivedFile002.dat"), {"pac"}):
        for path, typ, entry in pac.parse(gdat.unpack(data)):
            if typ == DT2 and path.startswith("GP/text/") and path not in seen:
                seen.add(path)
                tables.append(("bundle", path, gdat.unpack(entry)))

    want = {(gdat.name_hash(n) if isinstance(n, str) else n): n for n in TABLES_000}
    for _, h1, _, _, _, data in gdat.iter_entries(os.path.join(SRC, "GxArchivedFile000.dat"), {"dt2"}):
        if h1 in want:
            tables.append(("000", want.pop(h1), gdat.unpack(data)))
    if want:
        sys.exit(f"not found in archive 000: {list(want.values())}")

    total = chars = 0
    for source, name, payload in sorted(tables, key=lambda t: (t[0], str(t[1]))):
        rows = list(rows_of(payload))
        if not rows:
            continue
        total += len(rows)
        chars += sum(len(ja) for _, ja in rows)
        fname = csv_name(source, name)
        status = write_csv(os.path.join(OUT, fname), rows, force)
        label = name if isinstance(name, str) else f"{name:08x}"
        print(f"{fname:32} {len(rows):5} strings  {source:6} {label}  {status}")
    print(f"total: {total} strings, {chars} characters, {len(tables)} tables")


if __name__ == "__main__":
    main()

"""Extract the game's text tables to local working copies for translation.

  python -I scripts/extract_text.py

Writes work/<name>.csv (git-ignored) with columns id, ja, en, notes:
  id     record index:field index inside the original table (stable, used by the inserter)
  ja     the Japanese string, exactly as stored (markup such as <br>, <c02>…</c>, \\n kept)
  en     English (empty = keep the Japanese)
  notes  free text
Only strings that contain Japanese are listed. en/notes are merged in, never lost:
  1. from the existing work/<name>.csv when its row has the same id and ja (unsynced edits win),
  2. otherwise from the committed text/<name>.csv when id and ja_hash match.
Committed rows whose ja_hash no longer matches are reported. After translating, run scripts/sync_text.py.

Sources (see notes/formats.md):
  * bundle  - GP/text/* members of the pac bundles in GxArchivedFile002.dat (identical copies: the first is read)
  * 000     - dt2 entries in GxArchivedFile000.dat, by name hash (TABLES_000)
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import dt2  # noqa: E402
import gdat  # noqa: E402
import pac  # noqa: E402
import textdb  # noqa: E402

SRC = os.path.join(ROOT, "dump", "app", "PCSG00126", "masterPSP2")
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


def load_tables():
    """Return [(source, name, payload)] for every text table."""
    tables = []
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
    return sorted(tables, key=lambda t: (t[0], str(t[1])))


def japanese_rows(payload):
    for i, k, _, text in dt2.Dt2(payload).strings():
        if JP.search(text):
            yield f"{i}:{k}", text


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    total = chars = 0
    for source, name, payload in load_tables():
        rows = list(japanese_rows(payload))
        if not rows:
            continue
        fname = csv_name(source, name)
        work = textdb.read_work(fname)
        text = textdb.read_text(fname)
        out = []
        from_work = from_text = 0
        ids = set()
        for rid, ja in rows:
            ids.add(rid)
            row = {"id": rid, "ja": ja, "en": "", "notes": ""}
            w, t = work.get(rid), text.get(rid)
            if w and w["ja"] == ja and (w["en"] or w["notes"]):
                row["en"], row["notes"] = w["en"], w["notes"]
                from_work += 1
            elif t and t["ja_hash"] == textdb.ja_hash(ja):
                row["en"], row["notes"] = t["en"], t["notes"]
                from_text += 1
            out.append(row)
        stale = [rid for rid, t in text.items()
                 if rid not in ids or t["ja_hash"] != textdb.ja_hash(dict(rows).get(rid, ""))]
        textdb.write_work(fname, out)
        total += len(rows)
        chars += sum(len(ja) for _, ja in rows)
        label = name if isinstance(name, str) else f"{name:08x}"
        extra = f"  ({from_work} from work, {from_text} from text)" if from_work or from_text else ""
        print(f"{fname:32} {len(rows):5} strings  {source:6} {label}{extra}")
        if stale:
            print(f"  WARNING: {len(stale)} committed rows in text/{fname} don't match the Japanese: {stale[:5]}")
    print(f"total: {total} strings, {chars} characters -> {os.path.relpath(textdb.WORK, ROOT)}/")


if __name__ == "__main__":
    main()

"""Extract the game's text tables to local working copies for translation.

  python -I scripts/extract_text.py

Writes work/<name>.csv (git-ignored) with columns id, ja, en, notes:
  id     record index:field index inside the original table (stable, used by the build)
  ja     the Japanese string, exactly as stored (markup such as <br>, <c02>…</c>, \\n kept)
  en     English (empty = keep the Japanese)
  notes  free text
Only strings that contain Japanese are listed. en/notes are merged in, never lost:
  1. from the existing work/<name>.csv when its row has the same id and ja (unsynced edits win),
  2. otherwise from the committed text/<name>.csv when id and ja_hash match.
Committed rows whose ja_hash no longer matches are reported. After translating, run scripts/sync_text.py.
The table list is in tools/gbtext.py.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gbtext  # noqa: E402
import textdb  # noqa: E402

SRC = os.path.join(ROOT, "dump", "app", "PCSG00126", "masterPSP2")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    total = chars = 0
    for table in gbtext.load_tables(SRC):
        rows = [(rid, ja) for rid, _, _, ja in table.japanese()]
        if not rows:
            continue
        work = textdb.read_work(table.csv)
        text = textdb.read_text(table.csv)
        jas = dict(rows)
        out = []
        from_work = from_text = 0
        for rid, ja in rows:
            row = {"id": rid, "ja": ja, "en": "", "notes": ""}
            w, t = work.get(rid), text.get(rid)
            if w and w["ja"] == ja and (w["en"] or w["notes"]):
                row["en"], row["notes"] = w["en"], w["notes"]
                from_work += 1
            elif t and t["ja_hash"] == textdb.ja_hash(ja):
                row["en"], row["notes"] = t["en"], t["notes"]
                from_text += 1
            out.append(row)
        stale = [rid for rid, t in text.items() if t["ja_hash"] != textdb.ja_hash(jas.get(rid, ""))]
        textdb.write_work(table.csv, out)
        total += len(rows)
        chars += sum(len(ja) for _, ja in rows)
        extra = f"  ({from_work} from work, {from_text} from text)" if from_work or from_text else ""
        print(f"{table.csv:32} {len(rows):5} strings  {table.source:6} {table.label}{extra}")
        if stale:
            print(f"  WARNING: {len(stale)} committed rows in text/{table.csv} don't match the Japanese: {stale[:5]}")
    print(f"total: {total} strings, {chars} characters -> {os.path.relpath(textdb.WORK, ROOT)}/")


if __name__ == "__main__":
    main()

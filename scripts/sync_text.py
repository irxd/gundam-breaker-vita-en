"""Copy translations from the local working copies (work/) into the committed English files (text/).

  python -I scripts/sync_text.py

For every work/<name>.csv, writes text/<name>.csv with id, ja_hash, en, notes for the rows that have English or
notes. No Japanese is written to text/. Rows that were in text/ but are now empty in work/ are dropped (so
clearing a translation in work/ removes it).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import textdb  # noqa: E402


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if not os.path.isdir(textdb.WORK):
        sys.exit("no work/ folder: run scripts/extract_text.py first")
    total = 0
    for fname in sorted(os.listdir(textdb.WORK)):
        if not fname.endswith(".csv"):
            continue
        work = textdb.read_work(fname)
        rows = [{"id": r["id"], "ja_hash": textdb.ja_hash(r["ja"]), "en": r["en"], "notes": r["notes"]}
                for r in work.values() if r["en"] or r["notes"]]
        path = os.path.join(textdb.TEXT, fname)
        if not rows and not os.path.exists(path):
            continue
        before = textdb.read_text(fname)
        textdb.write_text(fname, rows)
        total += sum(1 for r in rows if r["en"])
        changed = sum(1 for r in rows if before.get(r["id"], {}).get("en") != r["en"])
        print(f"{fname:32} {sum(1 for r in rows if r['en']):5} translated  ({changed} changed)")
    print(f"total translated: {total}")


if __name__ == "__main__":
    main()

"""Copy translations from the local working copies (work/) into the committed English files (text/).

  python -I scripts/sync_text.py

For every work/<name>.csv, writes text/<name>.csv with id, ja_hash, en, notes for the rows that have English or
notes. No Japanese is written to text/: if any en or notes cell contains kana or kanji, nothing is written. Rows that were in text/ but are now empty in work/ are dropped (so
clearing a translation in work/ removes it).
"""
import os
import re
import sys

KANA_KANJI = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import textdb  # noqa: E402


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if not os.path.isdir(textdb.WORK):
        sys.exit("no work/ folder: run scripts/extract_text.py first")
    names = sorted(f for f in os.listdir(textdb.WORK) if f.endswith(".csv"))
    # text/ is public: refuse kana/kanji anywhere in en or notes (write romaji or English in notes instead).
    bad = [f"work/{f} id {r['id']} {col}: {r[col]}"
           for f in names for r in textdb.read_work(f).values() for col in ("en", "notes") if KANA_KANJI.search(r[col])]
    if bad:
        sys.exit("Japanese in en/notes would be committed; nothing written:\n" + "\n".join(f"- {b}" for b in bad))
    total = 0
    for fname in names:
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

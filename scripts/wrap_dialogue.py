"""Check (and fix) the width of the hangar / event dialogue lines (voice_event_text) against the dialogue box.

  python -E -P scripts/wrap_dialogue.py [--apply] [table.csv]     (default voice_event_text.csv, in work/)

(-E -P: Pillow lives in user site-packages.) Then run sync_text.py as usual.

Measured on a real Vita (2026-11-25): the dialogue box text starts at x ~222 and must end before x ~760, so a
line may be ~538 px wide; the game's font is matched within ~3% by Tahoma at 17 px (calibrated on screenshots).
Limit used: 520 px, or the original Japanese line's width when that is wider (16 px per full-width character,
8 per ASCII), since those rows are shown somewhere wider. A row may use max(3, Japanese line count) lines.

Too-wide lines are re-wrapped with balanced lines (as few lines as greedy wrapping, longest line as short as
possible); if that needs too many lines the whole row is re-flowed; rows that still don't fit are listed for a
shorter translation. Without --apply nothing is written.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import textdb  # noqa: E402
from PIL import ImageFont  # noqa: E402

FONT = ImageFont.truetype(os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", "tahoma.ttf"), 17)
LIMIT = 520
BR = "<br>"
TAG = re.compile(r"<[^>]*>")
SKIP = {"916:1", "917:1"}                           # designer sound labels, never shown


def en_width(s):
    return FONT.getlength(TAG.sub("", s))


def ja_width(s):
    return sum(8 if ord(c) < 0x80 else 16 for c in TAG.sub("", s))


def greedy(text, lim):
    out, cur = [], ""
    for w in text.split(" "):
        t = w if not cur else cur + " " + w
        if cur and en_width(t) > lim:
            out.append(cur)
            cur = w
        else:
            cur = t
    out.append(cur)
    return out


def balanced(text, lim):
    n = len(greedy(text, lim))
    lo, hi = 0, lim
    while hi - lo > 1:
        mid = (lo + hi) / 2
        if len(greedy(text, mid)) <= n:
            hi = mid
        else:
            lo = mid
    return greedy(text, hi)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    name = args[0] if args else "voice_event_text.csv"
    rows = list(textdb.read_work(name).values())
    changed, bad = 0, 0
    for r in rows:
        en = r["en"]
        if not en or r["id"] in SKIP or "\\n" in en:
            continue
        ja_lines = r["ja"].split(BR)
        lim = max(LIMIT, max(ja_width(x) for x in ja_lines))
        lines = en.split(BR)
        if max(en_width(x) for x in lines) <= lim:
            continue
        most = max(3, len(ja_lines))
        new = [y for x in lines for y in (balanced(x, lim) if en_width(x) > lim else [x])]
        if len(new) > most:
            new = balanced(" ".join(x for x in lines if x), lim)
        if len(new) > most:
            bad += 1
            print(f"TOO LONG {r['id']}: {len(new)} lines (max {most}) | {en}")
            continue
        changed += 1
        r["en"] = BR.join(new)
        print(f"{r['id']} | {r['en']}")
    print(f"{name}: {changed} rows re-wrapped, {bad} need a shorter translation")
    if "--apply" in sys.argv and changed:
        textdb.write_work(name, rows)
        print(f"written to work/{name}; now run scripts/sync_text.py")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

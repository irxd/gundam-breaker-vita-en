"""Check (and fix) the width of English text against the boxes it is shown in, for every table in work/.

  python -E -P scripts/check_widths.py [--apply] [--all] [table.csv ...]

(-E -P: Pillow lives in user site-packages.) Then run sync_text.py as usual. voice_event_text has its own checker,
scripts/wrap_dialogue.py, and is skipped here.

Widths use the same measure as wrap_dialogue.py (Tahoma 17 px for English, 16 per full-width / 8 per ASCII
character for Japanese). Each table field is shown in one box, so a field's limit is:
- MEASURED (below): box sizes measured on real-Vita screenshots;
- otherwise the widest Japanese line of that field, and as many lines as its longest Japanese row. That's only an
  estimate of the box, so those rows are listed (CHECK) but not changed: fix them by hand. Single-line names that
  are wider are listed only with --all (the box is often wider than the longest Japanese name).

Too-wide lines are split with balanced lines. Fields marked "flow" (briefings: the Japanese line breaks are only
wrapping) are always re-flowed into balanced lines, keeping a "*" note line on its own. Rows that still don't fit are
listed as TOO LONG and need a shorter translation. A colour tag (<cNN>...</c>) may not span a line break (the build
keeps the Japanese tags, so it can't be closed and reopened): such rows are listed too. Without --apply nothing is written.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import textdb  # noqa: E402
from wrap_dialogue import BR, TAG, balanced, en_width, ja_width  # noqa: E402

# (table, field) -> (width limit, max lines, flow). Screen px = 0.78 x these units on the mission select panel.
MEASURED = {
    # Mission select (2026-11-25 screenshot): briefing text x 439..~895, 5 lines above "Clear Condition".
    ("mission_name.csv", "9"): (575, 5, True),
    ("mission_name.csv", "6"): (485, 1, False),       # Clear Condition, text from x 508
    ("mission_name.csv", "7"): (485, 1, False),       # Failure Condition
    ("mission_name.csv", "12"): (490, 2, False),      # Rare Runner
}
SKIP_TABLES = {"voice_event_text.csv"}
HEADER = re.compile(r"\[[^\]]*\]")


def split_tag(lines):
    """True if a colour tag is left open at the end of a line (the build wants the Japanese tags, so we can't add
    a closing and reopening tag)."""
    for line in lines:
        tags = re.findall(r"<c\d+>|</c>", line)
        if tags and tags[-1] != "</c>":
            return True
    return False


def rewrap(en, lim, flow):
    lines = en.split(BR)
    if flow:
        return [y for keep, para in paragraphs(lines)
                for y in (para if keep else balanced(" ".join(para), lim))]
    return [y for x in lines for y in (balanced(x, lim) if en_width(x) > lim else [x])]


def paragraphs(lines):
    """(keep, lines) groups for re-flowing. A "[...]" header line stays on its own, and a "*" note line and the
    lines after it (e.g. the special-rule line) are kept as they are."""
    out = []
    for x in lines:
        plain = TAG.sub("", x).strip()
        if out and out[-1][0] == "note":
            out[-1][1].append(x)
        elif plain.startswith("*"):
            out.append(("note", [x]))
        elif HEADER.fullmatch(plain):
            out.append(("header", [x]))
        elif x and out and not out[-1][0]:
            out[-1][1].append(x)
        elif x:
            out.append(("", [x]))
    return [(bool(kind), para) for kind, para in out]


def field_limits(rows):
    out = {}
    for r in rows:
        f = r["id"].split(":")[-1]
        ja = r["ja"].split(BR)
        w, n = out.get(f, (0, 0))
        out[f] = (max(w, max(ja_width(x) for x in ja)), max(n, len(ja)))
    return out


def check(name, apply, show_all):
    rows = list(textdb.read_work(name).values())
    limits = field_limits([r for r in rows if r["ja"]])
    changed, bad, wide = 0, 0, 0
    for r in rows:
        en = r["en"]
        if not en or not r["ja"] or "\\n" in en:
            continue
        f = r["id"].split(":")[-1]
        measured = (name, f) in MEASURED
        lim, most, flow = MEASURED.get((name, f), limits[f] + (False,))
        lines = en.split(BR)
        fits = max(en_width(x) for x in lines) <= lim and len(lines) <= most
        if fits and not (flow and rewrap(en, lim, flow) != lines):
            continue
        if not measured:
            if most == 1:
                wide += 1
                if show_all:
                    print(f"  wider than the Japanese {r['id']}: {en_width(en):.0f} > {lim} | {en}")
            else:
                bad += 1
                widths = ", ".join(f"{en_width(x):.0f}" for x in lines)
                print(f"CHECK {name} {r['id']}: {len(lines)} lines (Japanese max {most}, width {lim}): {widths} | {en}")
            continue
        new = rewrap(en, lim, flow)
        if len(new) > most or max(en_width(x) for x in new) > lim or split_tag(new):
            bad += 1
            print(f"TOO LONG {name} {r['id']}: {len(new)} lines (max {most}, width {lim}) | {en}")
            continue
        changed += 1
        r["en"] = BR.join(new)
        print(f"{name} {r['id']} | {r['en']}")
    if changed or bad or wide:
        print(f"{name}: {changed} re-wrapped, {bad} too long" + (f", {wide} names wider than the Japanese" if wide else ""))
    if apply and changed:
        textdb.write_work(name, rows)
    return bad


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    names = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not names:
        names = sorted(n for n in os.listdir(textdb.WORK) if n.endswith(".csv") and n not in SKIP_TABLES)
    bad = sum(check(n, "--apply" in sys.argv, "--all" in sys.argv) for n in names)
    if "--apply" in sys.argv:
        print("written to work/; now run scripts/sync_text.py")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

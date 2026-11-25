"""Show the game's name in English on the home screen (optional).

Usage: python -I tools/rename_title.py <app.db | param.sfo> [--restore]

Real Vita: the home screen and LiveArea take the name from the system's app database, ur0:shell/db/app.db,
which is filled in when the game is installed (param.sfo is not read again, and rePatch does not apply to
the system software). Copy app.db to the PC, run this on it, copy it back and restart the Vita.
Changed: the tbl_appinfo rows and tbl_appinfo_icon.title of PCSG00126 that still hold the Japanese title or
the two-line short title. Nothing else in the database is touched.

A param.sfo (sce_sys/param.sfo) is also accepted: its TITLE/STITLE fields are changed.

A copy of the original is kept next to the file (<name>.orig) on the first run; --restore puts it back.
Adapted from the Battride War Genesis patch.
"""
import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_sfo import NL, STITLE, TITLE, VALUES, set_strings  # noqa: E402

TITLE_ID = "PCSG00126"
# The Japanese title as code points (the repo keeps kana out of its files): "Gandamu Bureika".
JA_TITLE = "".join(map(chr, [0x30AC, 0x30F3, 0x30C0, 0x30E0, 0x30D6, 0x30EC, 0x30A4, 0x30AB, 0x30FC]))
JA = {JA_TITLE: TITLE, JA_TITLE[:4] + NL + JA_TITLE[4:]: STITLE}


def rename_db(path):
    db = sqlite3.connect(path)
    n = 0
    try:
        with db:
            for old, new in JA.items():
                n += db.execute("UPDATE tbl_appinfo SET val=? WHERE titleId=? AND val=?",
                                (new, TITLE_ID, old)).rowcount
                n += db.execute("UPDATE tbl_appinfo_icon SET title=? WHERE titleId=? AND title=?",
                                (new, TITLE_ID, old)).rowcount
        ok = db.execute("pragma integrity_check").fetchone()[0]
    finally:
        db.close()
    assert ok == "ok", f"database check failed: {ok}"
    return n


def rename_sfo(path):
    p = Path(path)
    old = p.read_bytes()
    out = set_strings(old, VALUES)
    p.write_bytes(out)
    return int(out != old)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split(NL)[0])
    ap.add_argument("file", help="app.db (ur0:shell/db/app.db) or param.sfo")
    ap.add_argument("--restore", action="store_true", help="put back the original file saved on the first run")
    a = ap.parse_args()
    p = Path(a.file)
    orig = p.with_name(p.name + ".orig")
    if a.restore:
        if not orig.exists():
            sys.exit(f"no {orig.name} next to {p.name}: nothing to restore")
        shutil.copyfile(orig, p)
        print(f"restored {p} from {orig.name}")
        return
    head = p.read_bytes()[:16]
    is_db = head == b"SQLite format 3" + bytes(1)
    if not is_db and head[:4] != bytes(1) + b"PSF":
        sys.exit(f"{p.name} is neither app.db nor param.sfo")
    if not orig.exists():
        shutil.copyfile(p, orig)
        print(f"saved the original as {orig.name}")
    n = rename_db(p) if is_db else rename_sfo(p)
    if n:
        print(f'{p.name}: game name set to "{TITLE}" ({n} {"entries" if is_db else "file"} changed)')
    else:
        print(f"{p.name}: nothing to change (already English, or {TITLE_ID} is not in this file)")


if __name__ == "__main__":
    main()

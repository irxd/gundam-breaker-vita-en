"""Translation files: committed English (text/) and local working copies with Japanese (work/).

text/<name>.csv   committed, public-safe:  id, ja_hash, en, notes   (only rows with en or notes)
work/<name>.csv   local, git-ignored:      id, ja, en, notes        (every Japanese string)

id       record index:field index in the original table
ja_hash  first 8 hex digits of SHA-1 of the Japanese (UTF-8); checks that a translation still belongs to that line
"""
import csv
import hashlib
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXT = os.path.join(ROOT, "text")
WORK = os.path.join(ROOT, "work")


def ja_hash(ja: str) -> str:
    return hashlib.sha1(ja.encode("utf-8")).hexdigest()[:8]


def read(path):
    """Return {id: row dict}, or {} when the file doesn't exist."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8", newline="") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def write(path, columns, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(columns)
        for r in rows:
            w.writerow([r.get(c, "") for c in columns])
    os.replace(tmp, path)


def read_text(name):
    return read(os.path.join(TEXT, name))


def read_work(name):
    return read(os.path.join(WORK, name))


def write_text(name, rows):
    write(os.path.join(TEXT, name), ["id", "ja_hash", "en", "notes"], rows)


def write_work(name, rows):
    write(os.path.join(WORK, name), ["id", "ja", "en", "notes"], rows)

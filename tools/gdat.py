"""GDAT archive tool for Gundam Breaker (PS Vita), GxArchivedFile00x.dat.

Format (big-endian):
  0x00  "GDAT"
  0x04  u32 entry count N
  0x08  N x 16-byte entries, sorted by (hash0, hash1):
          u32 hash0   (type/group hash; same for every entry of one kind)
          u32 hash1   (name hash)
          u32 offset  (absolute, in this file)
          u32 size
  Entries are packed back to back with no gaps, in offset order.

Each entry starts with a 0x80-byte header:
  0x00  type tag as reversed fourcc, e.g. b"\\0kpm" = "mpk", b"\\0xet" = "tex", b"\\02td" = "dt2"
  0x04  u32 2 (version?), 0x08 u32 subtype, 0x2C u32 1 = BILZ payload follows
Then at 0x80, when present:
  "BILZ"  u32 uncompressed size  u32 stored size  u32 level
  stored data (level 0 = raw, otherwise a zlib stream)
Some entries (@UTF, DSSP) have no 0x80 header and are raw.

Usage (run with python -I):
  gdat.py list    ARCHIVE [--type dt2]
  gdat.py extract ARCHIVE OUTDIR [--type dt2] [--raw]
"""
import argparse
import os
import struct
import sys
import zlib


def read_table(f):
    head = f.read(8)
    if head[:4] != b"GDAT":
        raise ValueError("not a GDAT archive")
    n = struct.unpack(">I", head[4:])[0]
    tab = f.read(16 * n)
    return [struct.unpack_from(">IIII", tab, 16 * i) for i in range(n)]


def type_of(data):
    if data[:4] in (b"@UTF", b"DSSP"):
        return data[:4].decode("latin1").strip("@")
    return data[1:4][::-1].decode("latin1")


def unpack(data):
    """Return the payload of an entry (decompressed when BILZ)."""
    if data[0x80:0x84] != b"BILZ":
        return data
    usize, csize, level = struct.unpack_from(">III", data, 0x84)
    body = data[0x90:0x90 + csize]
    out = body if level == 0 else zlib.decompress(body)
    if len(out) != usize:
        raise ValueError(f"size mismatch {len(out)} != {usize}")
    return out


def iter_entries(path, want=None):
    with open(path, "rb") as f:
        for h0, h1, off, size in read_table(f):
            f.seek(off)
            data = f.read(size)
            t = type_of(data)
            if want and t not in want:
                continue
            yield h0, h1, off, size, t, data


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "extract"])
    ap.add_argument("archive")
    ap.add_argument("outdir", nargs="?")
    ap.add_argument("--type", action="append", help="only this entry type (repeatable)")
    ap.add_argument("--raw", action="store_true", help="extract without decompressing")
    a = ap.parse_args()
    want = set(a.type) if a.type else None

    if a.cmd == "list":
        for h0, h1, off, size, t, _ in iter_entries(a.archive, want):
            print(f"{h0:08x} {h1:08x} {off:#010x} {size:#09x} {t}")
        return

    if not a.outdir:
        ap.error("extract needs OUTDIR")
    base = os.path.splitext(os.path.basename(a.archive))[0]
    count = 0
    for h0, h1, off, size, t, data in iter_entries(a.archive, want):
        d = os.path.join(a.outdir, base, t)
        os.makedirs(d, exist_ok=True)
        out = data if a.raw else unpack(data)
        with open(os.path.join(d, f"{h0:08x}_{h1:08x}.{t}"), "wb") as o:
            o.write(out)
        count += 1
    print(f"extracted {count} entries to {os.path.join(a.outdir, base)}")


if __name__ == "__main__":
    main()

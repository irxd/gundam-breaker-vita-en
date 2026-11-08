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
  hash1 = name_hash(path) for named files (see below); in 001/002 (pac bundles) it is a running ID.

Each entry starts with a 0x80-byte header:
  0x00  type tag as reversed fourcc, e.g. b"\\0kpm" = "mpk", b"\\0xet" = "tex", b"\\02td" = "dt2"
  0x04  u32 2 (version?), 0x08 u32 subtype, 0x2C u32 1 = BILZ payload follows, 0 = raw payload (pac)
Then at 0x80, when present:
  "BILZ"  u32 uncompressed size  u32 stored size  u32 level
  stored data (level 0 = raw, otherwise a zlib stream)
Some entries (@UTF, DSSP) have no 0x80 header and are raw.

Usage (run with python -I):
  gdat.py list    ARCHIVE [--type dt2]
  gdat.py extract ARCHIVE OUTDIR [--type dt2] [--raw]
  gdat.py rebuild ARCHIVE OUT.dat [--replace HASH0_HASH1=payload.bin ...]
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


def name_hash(path):
    """hash1 of an entry: h = 37, then h = h*37 + byte for each byte of the path.

    The path is as stored in pac records, without extension, e.g. "GP/text/voice_event_text".
    """
    h = 37
    for c in path.encode("utf-8"):
        h = (h * 37 + c) & 0xFFFFFFFF
    return h


def has_header(data):
    """True for entries with the 0x80-byte header (type tag starts with a NUL)."""
    return len(data) >= 0x80 and data[0] == 0


def unpack(data):
    """Return the payload of an entry: decompressed when BILZ, after the 0x80 header when stored raw
    (pac), or the whole entry when it has no header (@UTF, DSSP)."""
    if data[0x80:0x84] != b"BILZ":
        return data[0x80:] if has_header(data) else data
    usize, csize, level = struct.unpack_from(">III", data, 0x84)
    body = data[0x90:0x90 + csize]
    out = body if level == 0 else zlib.decompress(body)
    if len(out) != usize:
        raise ValueError(f"size mismatch {len(out)} != {usize}")
    return out


def repack(orig_entry, payload):
    """Build a new entry from an original one (header kept) and a new payload."""
    if orig_entry[0x80:0x84] != b"BILZ":
        return orig_entry[:0x80] + payload if has_header(orig_entry) else payload
    level = struct.unpack_from(">I", orig_entry, 0x8C)[0]
    body = payload if level == 0 else zlib.compress(payload, 9)
    return (orig_entry[:0x80] + b"BILZ"
            + struct.pack(">III", len(payload), len(body), level) + body)


def rebuild(src, dst, replace):
    """Copy archive src to dst, swapping the payloads given in replace {(h0, h1): bytes}.

    Table order and data order are kept; offsets are recomputed.
    """
    with open(src, "rb") as f:
        ents = read_table(f)
        by_off = sorted(range(len(ents)), key=lambda i: ents[i][2])
        new_off = [0] * len(ents)
        new_size = [e[3] for e in ents]
        new_data = {}
        for i, (h0, h1, off, size) in enumerate(ents):
            if (h0, h1) in replace:
                f.seek(off)
                new_data[i] = repack(f.read(size), replace[(h0, h1)])
                new_size[i] = len(new_data[i])
        missing = set(replace) - {(e[0], e[1]) for e in ents}
        if missing:
            raise KeyError(f"not in archive: {missing}")
        pos = 8 + 16 * len(ents)
        for i in by_off:
            new_off[i] = pos
            pos += new_size[i]
        tmp = dst + ".tmp"
        with open(tmp, "wb") as o:
            o.write(b"GDAT" + struct.pack(">I", len(ents)))
            for i, (h0, h1, _, _) in enumerate(ents):
                o.write(struct.pack(">IIII", h0, h1, new_off[i], new_size[i]))
            for i in by_off:
                if i in new_data:
                    o.write(new_data[i])
                else:
                    f.seek(ents[i][2])
                    left = ents[i][3]
                    while left:
                        chunk = f.read(min(left, 1 << 22))
                        o.write(chunk)
                        left -= len(chunk)
        os.replace(tmp, dst)


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
    ap.add_argument("cmd", choices=["list", "extract", "rebuild"])
    ap.add_argument("archive")
    ap.add_argument("outdir", nargs="?", help="extract: output folder; rebuild: output archive")
    ap.add_argument("--type", action="append", help="only this entry type (repeatable)")
    ap.add_argument("--raw", action="store_true", help="extract without decompressing")
    ap.add_argument("--replace", action="append", default=[],
                    help="rebuild: HASH0_HASH1=FILE, a decompressed payload (repeatable)")
    a = ap.parse_args()
    want = set(a.type) if a.type else None

    if a.cmd == "rebuild":
        if not a.outdir:
            ap.error("rebuild needs an output path")
        rep = {}
        for r in a.replace:
            key, path = r.split("=", 1)
            h0, h1 = (int(x, 16) for x in key.split("_"))
            with open(path, "rb") as p:
                rep[(h0, h1)] = p.read()
        rebuild(a.archive, a.outdir, rep)
        print(f"wrote {a.outdir} ({len(rep)} entries replaced)")
        return

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

"""Set the game's name in sce_sys/param.sfo (LiveArea bubble and home screen).

Usage: python -I tools/build_sfo.py <original param.sfo> <output param.sfo>

PSF layout: header (magic NUL "PSF", version, key table, data table, count), then 16-byte index entries
(key offset u16, format u16, length u32, max length u32, data offset u32). Strings (fmt 0x204) are
NUL-terminated UTF-8 inside a fixed max-length slot, so they can be replaced in place.
GB's param.sfo (game 1.00 and update 1.02) has TITLE (slot 0x80) and STITLE (slot 0x34); the short title is
split over two lines under the icon, so the English is too. Adapted from the Battride War Genesis patch.
"""
import os
import struct
import sys

NL = chr(10)
TITLE = "GUNDAM BREAKER"                # upper case, like the official "GUNDAM BREAKER 3"
STITLE = "GUNDAM" + NL + "BREAKER"      # short title under the icon, two lines like the original
VALUES = {"TITLE": TITLE, "TITLE_00": TITLE, "STITLE": STITLE, "STITLE_00": STITLE}


def set_strings(sfo: bytes, values: dict, required=("TITLE", "STITLE")) -> bytes:
    """Replace the given string keys that exist in the file (keys that are missing are skipped)."""
    d = bytearray(sfo)
    magic, _, key_tab, data_tab, n = struct.unpack_from("<4sIIII", d)
    assert magic == bytes([0]) + b"PSF"
    done = set()
    for i in range(n):
        ko, fmt, ln, mx, do = struct.unpack_from("<HHIII", d, 20 + 16 * i)
        key = d[key_tab + ko:d.index(0, key_tab + ko)].decode()
        if key in values:
            assert fmt == 0x204
            v = values[key].encode("utf-8") + bytes(1)
            assert len(v) <= mx, f"{key}: {len(v)} > {mx} bytes"
            d[data_tab + do:data_tab + do + mx] = v + bytes(mx - len(v))
            struct.pack_into("<I", d, 20 + 16 * i + 4, len(v))
            done.add(key)
    assert set(required) <= done, f"missing keys: {set(required) - done}"
    return bytes(d)


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src, dst = sys.argv[1:3]
    out = set_strings(open(src, "rb").read(), VALUES)
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    open(dst, "wb").write(out)
    print(f"{dst}: title set to {TITLE!r} / {STITLE!r}")


if __name__ == "__main__":
    main()

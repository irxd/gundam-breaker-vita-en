"""pac bundles (Gundam Breaker, Vita): the payload of "pac" entries in GxArchivedFile001/002.dat.

Layout (little-endian):
  0x00  u32 count N
  0x04  u32 largest member size
  0x08  N x { char path[0x100] (NUL-padded, no extension), u32 type hash (hash0), u32 size }
  then the N members back to back, each a full entry (0x80 header + BILZ), in table order.
The bundles map to the loose paths pacPSP2/... that the game probes.
"""
import struct

REC = 0x108


def parse(pac: bytes):
    """Return a list of [path, type_hash, entry_bytes]."""
    n = struct.unpack_from("<I", pac, 0)[0]
    pos = 8 + n * REC
    out = []
    for k in range(n):
        o = 8 + k * REC
        path = pac[o:o + 0x100].split(b"\0")[0].decode("utf-8")
        typ, size = struct.unpack_from("<II", pac, o + 0x100)
        out.append([path, typ, pac[pos:pos + size]])
        pos += size
    if pos != len(pac):
        raise ValueError(f"pac size mismatch: members end at {pos:#x}, data is {len(pac):#x}")
    return out


def build(members, orig: bytes = None) -> bytes:
    """Rebuild a pac from [path, type_hash, entry_bytes] items. When orig is given, each record's path field
    (all 0x100 bytes, including any bytes after the NUL) is copied from it so unchanged bundles stay identical."""
    n = len(members)
    head = bytearray(8 + n * REC)
    struct.pack_into("<II", head, 0, n, max((len(m[2]) for m in members), default=0))
    for k, (path, typ, data) in enumerate(members):
        o = 8 + k * REC
        if orig is not None:
            head[o:o + 0x100] = orig[o:o + 0x100]
        else:
            raw = path.encode("utf-8")
            head[o:o + len(raw)] = raw
        struct.pack_into("<II", head, o + 0x100, typ, len(data))
    return bytes(head) + b"".join(m[2] for m in members)

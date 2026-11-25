"""dt2 data tables (Gundam Breaker, Vita): read and replace strings.

Layout (little-endian), checked on all 3,070 tables (every string field lands on valid NUL-terminated UTF-8):
  0x00  u32 schema id
  0x04  u32 N
  0x08  N x { u32 record offset, u32 (descriptor offset << 8) | field count }
  then the descriptors, then the records (all descriptors come before all records).
  A descriptor is `field count` x u16 = (type << 12) | offset of the field inside the record.
    type 0 = NUL-terminated UTF-8 string, 5 = 1 byte, 6 = 2 bytes, 2/4/7/8 = other (4-byte values, lists).
  No descriptor is shared by two records. Bytes in a record that no field points to are leftovers.

Replacing strings (rebuild): the records are re-packed in their original order; an edited string takes its
real length (the change padded to a multiple of 4 so 2/4-byte fields keep their alignment), the descriptor
offsets of the fields after it are shifted, and the record pointers are updated.

In-game results (Vita3K): a table that grew (raw and compressed) crashed mission loading; tables that kept or
reduced their size worked. Keep both the raw and the compressed size at or below the original. clear_unused()
zeroes leftover bytes between fields, which makes the compressed data much smaller.
"""
import struct

STRING = 0


class Dt2:
    def __init__(self, data: bytes):
        self.data = bytearray(data)
        self.schema, n = struct.unpack_from("<II", data, 0)
        self.relocs = []
        for i in range(n):
            target, loc = struct.unpack_from("<II", data, 8 + 8 * i)
            self.relocs.append([target, loc >> 8, loc & 0xFF])

    def to_bytes(self) -> bytes:
        for i, (target, desc, count) in enumerate(self.relocs):
            struct.pack_into("<II", self.data, 8 + 8 * i, target, (desc << 8) | count)
        return bytes(self.data)

    def fields(self, i):
        _, desc, count = self.relocs[i]
        out = []
        for k in range(count):
            v = struct.unpack_from("<H", self.data, desc + 2 * k)[0]
            out.append((v >> 12, v & 0x0FFF))
        return out

    def _set_field(self, i, k, typ, off):
        if not 0 <= off <= 0x0FFF:
            raise ValueError(f"field offset {off:#x} does not fit in 12 bits")
        struct.pack_into("<H", self.data, self.relocs[i][1] + 2 * k, (typ << 12) | off)

    def strings(self):
        """Yield (record index, field index, absolute offset, text) for every string field."""
        for i, (target, _, _) in enumerate(self.relocs):
            for k, (typ, off) in enumerate(self.fields(i)):
                if typ == STRING:
                    p = target + off
                    yield i, k, p, self.data[p:self.data.index(0, p)].decode("utf-8")

    def _record_end(self, i):
        target = self.relocs[i][0]
        later = [r[0] for r in self.relocs if r[0] > target]
        return min(later) if later else len(self.data)

    FIELD_SIZE = {5: 1, 6: 2, 2: 4}   # fixed-size field types; 0 = string

    def clear_unused(self):
        """Zero the record bytes that no field points to (stale leftovers that compress badly).

        Only for tables whose field types all have a known size; raises otherwise. Returns the number of bytes
        cleared.
        """
        used = bytearray(len(self.data))
        for i, (target, _, _) in enumerate(self.relocs):
            for typ, off in self.fields(i):
                p = target + off
                if typ == STRING:
                    n = self.data.index(0, p) + 1 - p
                elif typ in self.FIELD_SIZE:
                    n = self.FIELD_SIZE[typ]
                else:
                    raise ValueError(f"field type {typ} has no known size")
                used[p:p + n] = b"\1" * n
        first = min(r[0] for r in self.relocs)
        cleared = 0
        for p in range(first, len(self.data)):
            if not used[p] and self.data[p]:
                self.data[p] = 0
                cleared += 1
        return cleared

    def rebuild(self, edits):
        """Replace strings and re-pack the records. edits: {(record index, field index): text}.

        Records keep their order and their start alignment (mod 4). An edited string takes its real length,
        padded so the change is a multiple of 4; the descriptor offsets of the fields after it are shifted. A
        string that gets longer first fills the leftover bytes up to the next field of its record (bytes no
        field points to), so e.g. "HG X" with 2 stale bytes after its NUL has 2 bytes of free room.
        Unedited bytes (other fields, leftovers between fields) are copied as they are. In-game tests showed
        that a table must not grow (see notes/formats.md), so callers should check the size.
        """
        by_target = {}
        for (i, k), text in edits.items():
            typ, off = self.fields(i)[k]
            if typ != STRING:
                raise ValueError(f"field {k} of record {i} is not a string")
            by_target.setdefault(self.relocs[i][0], {})[off] = text

        targets = sorted({r[0] for r in self.relocs})
        first = targets[0]
        records = []
        for n, t in enumerate(targets):
            end = targets[n + 1] if n + 1 < len(targets) else len(self.data)
            rec = bytearray(self.data[t:end])
            for off in sorted(by_target.get(t, {}), reverse=True):
                old_end = rec.index(0, off) + 1
                new = by_target[t][off].encode("utf-8") + b"\0"
                if len(new) > old_end - off:
                    # A longer string may first use the leftover bytes between its NUL and the next field of the
                    # record (no field points into them), so fields only move when that room runs out.
                    later = [o for j, r in enumerate(self.relocs) if r[0] == t for _, o in self.fields(j) if o > off]
                    if later and min(later) >= old_end:
                        old_end = min(later)
                delta = len(new) - (old_end - off)
                pad = (-delta) % 4
                new += bytes(pad)
                delta += pad
                rec[off:old_end] = new
                for j, r in enumerate(self.relocs):
                    if r[0] == t:
                        for kk, (ty, o) in enumerate(self.fields(j)):
                            if o > off:
                                self._set_field(j, kk, ty, o + delta)
            records.append((t, rec))

        out = bytearray(self.data[:first])        # header, relocation table, descriptors (already updated)
        moved = {}
        for t, rec in records:
            while len(out) % 4 != t % 4:
                out.append(0)
            moved[t] = len(out)
            out += rec
        for r in self.relocs:
            r[0] = moved[r[0]]
        self.data = out

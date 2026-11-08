"""dt2 data tables (Gundam Breaker, Vita): read and replace strings.

Layout (little-endian), checked on all 3,070 tables (every string field lands on valid NUL-terminated UTF-8):
  0x00  u32 schema id
  0x04  u32 N
  0x08  N x { u32 record offset, u32 (descriptor offset << 8) | field count }
  then the descriptors, then the records (all descriptors come before all records).
  A descriptor is `field count` x u16 = (type << 12) | offset of the field inside the record.
    type 0 = NUL-terminated UTF-8 string, 5 = 1 byte, 6 = 2 bytes, 2/4/7/8 = other (4-byte values, lists).
  No descriptor is shared by two records. Bytes in a record that no field points to are leftovers.

Replacing a string:
  * fits in the old bytes (with its NUL) -> written in place, the rest zeroed;
  * longer -> the record (up to the next record) is copied to the end of the file with the new string, the
    descriptor offsets of the fields after the string are shifted in place, and the record is repointed.
    The shift is kept a multiple of 4 so 2/4-byte fields keep their alignment.
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

    def set_string(self, i, k, text, force_move=False):
        """Replace string field k of record i. Returns "in place" or "moved"."""
        target = self.relocs[i][0]
        typ, off = self.fields(i)[k]
        if typ != STRING:
            raise ValueError(f"field {k} of record {i} is not a string")
        p = target + off
        old_end = self.data.index(0, p) + 1              # one past the NUL
        new = text.encode("utf-8") + b"\0"
        if len(new) <= old_end - p and not force_move:
            self.data[p:old_end] = new + bytes(old_end - p - len(new))
            return "in place"

        rec_end = self._record_end(i)
        old_len = old_end - p
        delta = len(new) - old_len
        pad = (-delta) % 4
        new += bytes(pad)
        delta += pad
        record = bytes(self.data[target:p]) + new + bytes(self.data[old_end:rec_end])
        # Shift the fields that come after this string, in every record entry pointing here.
        for j, r in enumerate(self.relocs):
            if r[0] != target:
                continue
            for kk, (t, o) in enumerate(self.fields(j)):
                if o > off:
                    self._set_field(j, kk, t, o + delta)
        while len(self.data) % 4:
            self.data.append(0)
        new_target = len(self.data)
        self.data += record
        for r in self.relocs:
            if r[0] == target:
                r[0] = new_target
        return "moved"

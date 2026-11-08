"""dt2 data tables (Gundam Breaker, Vita): read and replace strings.

Layout (little-endian), as understood so far:
  0x00  u32 schema id
  0x04  u32 N  (relocation entries)
  0x08  N x { u32 target, u32 loc }
          target = absolute offset of a record in this file
          loc    = (descriptor position << 8) | sub-field byte offset in that descriptor
  then the descriptor block (u16 values: type << 12 | field offset inside the record)
  then the records, which hold binary fields and null-terminated UTF-8 strings.

Records are only reached through `target`. Descriptors hold offsets relative to the record, so a record can be
copied to the end of the file and its target(s) repointed. Bytes between records are kept as they are.

THEORY, still being tested in game: see notes/formats.md.
"""
import struct


class Dt2:
    def __init__(self, data: bytes):
        self.data = bytearray(data)
        self.schema, n = struct.unpack_from("<II", data, 0)
        self.relocs = [list(struct.unpack_from("<II", data, 8 + 8 * i)) for i in range(n)]

    def to_bytes(self) -> bytes:
        for i, (t, loc) in enumerate(self.relocs):
            struct.pack_into("<II", self.data, 8 + 8 * i, t, loc)
        return bytes(self.data)

    def cstring_at(self, off: int) -> str:
        end = self.data.index(0, off)
        return self.data[off:end].decode("utf-8")

    def replace_string(self, str_off: int, text: str, record_off: int):
        """Replace the null-terminated string at str_off, which belongs to the record at record_off.

        Fits (with its NUL) -> written in place, the rest of the old string is zeroed.
        Too long -> the record (record_off .. end of the old string) is copied to the end of the file with the new
        string, and every relocation that targets record_off is repointed.
        """
        new = text.encode("utf-8") + b"\0"
        old_end = self.data.index(0, str_off) + 1
        if len(new) <= old_end - str_off:
            self.data[str_off:old_end] = new + bytes(old_end - str_off - len(new))
            return "in place"
        prefix = bytes(self.data[record_off:str_off])
        new_off = len(self.data)
        self.data += prefix + new
        hits = 0
        for r in self.relocs:
            if r[0] == record_off:
                r[0] = new_off
                hits += 1
        if hits == 0:
            raise ValueError(f"no relocation targets record {record_off:#x}")
        return f"moved to {new_off:#x} ({hits} pointer(s))"

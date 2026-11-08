"""Which tables hold the game's text, and where they live in the archives.

Sources (see notes/formats.md):
  * bundle  - GP/text/* members of the pac bundles in GxArchivedFile002.dat; every copy must be patched
  * 000     - dt2 entries in GxArchivedFile000.dat, by name hash (TABLES_000)
"""
import os
import re

import dt2
import gdat
import pac

DT2 = 0x2C1CF0E2
JP = re.compile("[぀-ヿ一-鿿！-～]")

# Text tables in archive 000. Names from hashing eboot strings; two are still unknown.
TABLES_000 = [
    "GP/text/avatar_detail", "GP/text/avatar_name", "GP/text/booster_name", "GP/text/boxes_name",
    "GP/text/chip_detail", "GP/text/chip_name", "GP/text/generalaction_text", "GP/text/load_text",
    "GP/text/mail", "GP/text/mail_category", "GP/text/patterns_detail", "GP/text/patterns_name",
    "GP/text/rank_name", "GP/text/runners_detail", "GP/text/skill_detail", "GP/text/system_text",
    0xBBCF42D0, 0xC4829255,
]
# Left out on purpose: GP/text/parts_phonetic (sort readings), GP/csv/* (data), GP/unitData/* (names may be keys).


class Table:
    def __init__(self, source, name, payload, key):
        self.source = source      # "bundle" or "000"
        self.name = name          # path, or the hash1 for unnamed 000 tables
        self.payload = payload    # decompressed dt2
        self.key = key            # bundle: member path; 000: (hash0, hash1)

    @property
    def label(self):
        return self.name if isinstance(self.name, str) else f"{self.name:08x}"

    @property
    def csv(self):
        base = self.name.split("/")[-1] if isinstance(self.name, str) else f"{self.name:08x}"
        return f"000_{base}.csv" if self.source == "000" else f"{base}.csv"

    def japanese(self):
        """Yield (id, record index, field index, text) for every string containing Japanese."""
        for i, k, _, text in dt2.Dt2(self.payload).strings():
            if JP.search(text):
                yield f"{i}:{k}", i, k, text


def load_tables(src):
    """Return the text tables from the archives in folder src (e.g. dump/app/PCSG00126/masterPSP2)."""
    tables = []
    seen = set()
    for _, _, _, _, _, data in gdat.iter_entries(os.path.join(src, "GxArchivedFile002.dat"), {"pac"}):
        for path, typ, entry in pac.parse(gdat.unpack(data)):
            if typ == DT2 and path.startswith("GP/text/") and path not in seen:
                seen.add(path)
                tables.append(Table("bundle", path, gdat.unpack(entry), path))
    want = {(gdat.name_hash(n) if isinstance(n, str) else n): n for n in TABLES_000}
    for h0, h1, _, _, _, data in gdat.iter_entries(os.path.join(src, "GxArchivedFile000.dat"), {"dt2"}):
        if h1 in want:
            tables.append(Table("000", want.pop(h1), gdat.unpack(data), (h0, h1)))
    if want:
        raise KeyError(f"not found in archive 000: {list(want.values())}")
    return sorted(tables, key=lambda t: (t.source, t.label))

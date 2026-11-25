"""Which tables hold the game's text, and where they live in the archives.

Sources (see notes/formats.md):
  * bundle  - GP/text/* members of the pac bundles in GxArchivedFile002.dat; every copy must be patched
  * 000     - dt2 entries in GxArchivedFile000.dat, by name hash (TABLES_000)
  * data    - display fields of data tables (GP/unitData/*, GP/csv/*, GP/map/map, GP/text/parts_phonetic;
              DATA_TABLES). Most are members of the 002 bundles, and many also have a loose dt2 copy in archive 000
              (hash1 = gdat.name_hash(path)); the build patches every bundle copy and the loose copy with the same
              payload. A few exist only as a loose entry in archive 000 (GP/csv/decalData, GP/text/parts_phonetic).

CSV names and ids:
  * GP/text/<name>            -> <name>.csv,      id = "record:field"
  * archive 000 <name>        -> 000_<name>.csv,  id = "record:field"
  * GP/unitData/<name>        -> unitData_<name>.csv, id = "record:field"
  * GP/unitData/<dir>/<file>  -> ONE combined unitData_<dir>.csv per folder (parts, equip, ex), so there are
                                 not hundreds of files; id = "<file>:record:field", e.g. "chr0242:31:1".
  * GP/csv/<name>             -> csv_<name>.csv,  GP/map/<name> -> map_<name>.csv, id = "record:field"
  * GP/text/parts_phonetic    -> 000_parts_phonetic.csv (a data table: only field 3 is extracted; loose in 000)

Only the fields listed in DATA_TABLES are extracted. A field is picked by (number of fields in the record, field
index), because each record kind has its own field count. Each record also has a numeric ID in field 0 that
the game uses as the key; the picked fields are names or descriptions (see notes/formats.md, "unitData" and
"GP/csv, GP/map and parts_phonetic"). Internal labels in
the same tables (attack names like "<name>'s attack A", short weapon names in equip field 8 such as joke spellings,
comment names next to IDs in ex sub-records, awakeparam labels) are left out.
"""
import os
import re

import dt2
import gdat
import pac

DT2 = 0x2C1CF0E2
JP = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff\uff01-\uff5e]")

# Text tables in archive 000. Names from hashing eboot strings; two are still unknown.
TABLES_000 = [
    "GP/text/avatar_detail", "GP/text/avatar_name", "GP/text/booster_name", "GP/text/boxes_name",
    "GP/text/chip_detail", "GP/text/chip_name", "GP/text/generalaction_text", "GP/text/load_text",
    "GP/text/mail", "GP/text/mail_category", "GP/text/patterns_detail", "GP/text/patterns_name",
    "GP/text/rank_name", "GP/text/runners_detail", "GP/text/skill_detail", "GP/text/system_text",
    0xBBCF42D0, 0xC4829255,
]

# Data tables: path or folder prefix (ending in "/") -> set of (field count of the record, field index).
DATA_TABLES = {
    "GP/unitData/partsList": {(6, 1)},             # part names per slot, "HG Gundam Head"
    "GP/unitData/weaponList": {(8, 1)},            # weapon names, "HG Beam Saber"
    "GP/unitData/itemSkillParam": {(32, 1)},       # items used in battle, "Repair Kit S"
    "GP/unitData/parts/": {(11, 1),                # MS name of the part, "HG GM" (Set Up list drops "HG ")
                           (24, 1)},               # option equipment, "Head Vulcan (GM)"
    "GP/unitData/equip/": {(18, 3), (20, 3)},      # weapon name, "HG Beam Saber"
    "GP/unitData/ex/": {(18, 1)},                  # EX-Action name, "Mirage Shot"
    "GP/text/parts_phonetic": {(4, 3)},            # kit trait / part description, "no special traits" (field 1 is a
                                                   # sort reading such as the kit name without spaces: left out)
    "GP/csv/decalData": {(10, 1)},                 # decal name, "HG Gundam Decal B" (field 0 = numeric ID)
    "GP/csv/AiIntensificationChipData": {(49, 1)},  # chip name, same as GP/text/chip_name
    "GP/csv/scoreAchievementsTable": {(6, 5), (7, 5), (8, 5)},  # ace point description (field 1 = ID such as
                                                   # FIRST_KILL, field 7 = developer comment: left out)
    "GP/map/map": {(4, 1)},                        # map name with time of day (field 2 = map code jab_01: left out)
}
# Left out on purpose (internal labels, see notes/formats.md): GP/unitData/awakeparam (boss, escorts, HT + awakening:
# ...); GP/unitData/effect, sound (comments); GP/csv/NPCParam, BOSSParam field 0 (designer labels with loadout or
# phase), GP/csv/MA/* and multiplayer (parameter names), GP/csv/parts_build_viewoffset (part names as row labels of
# a camera offset table), GP/csv/ui_resource (developer notes).
CSV_PREFIX = {"unitData": "unitData_", "csv": "csv_", "map": "map_", "text": "000_"}


def data_spec(path):
    """Return (fields, csv name, id prefix) for a data table path, or None."""
    for key, fields in DATA_TABLES.items():
        if key.endswith("/"):
            if path.startswith(key) and "/" not in path[len(key):]:
                folder = key.rstrip("/").split("/")[-1]
                return fields, f"{CSV_PREFIX[key.split('/')[1]]}{folder}.csv", path[len(key):] + ":"
        elif path == key:
            return fields, f"{CSV_PREFIX[key.split('/')[1]]}{key.split('/')[-1]}.csv", ""
    return None


class Table:
    def __init__(self, source, name, payload, key, loose=None):
        self.source = source      # "bundle", "000" or "data"
        self.name = name          # path, or the hash1 for unnamed 000 tables
        self.payload = payload    # decompressed dt2
        self.key = key            # bundle/data: member path; 000 (and data tables only in 000): (hash0, hash1)
        self.loose = loose        # data: (hash0, hash1) of the loose copy in archive 000, or None
        spec = data_spec(name) if source == "data" else None
        self.fields = spec[0] if spec else None
        self.prefix = spec[2] if spec else ""
        self._csv = spec[1] if spec else None

    @property
    def label(self):
        return self.name if isinstance(self.name, str) else f"{self.name:08x}"

    @property
    def csv(self):
        if self._csv:
            return self._csv
        base = self.name.split("/")[-1] if isinstance(self.name, str) else f"{self.name:08x}"
        return f"000_{base}.csv" if self.source == "000" else f"{base}.csv"

    def japanese(self):
        """Yield (id, record index, field index, text) for every string containing Japanese (data tables: only
        in the picked fields)."""
        table = dt2.Dt2(self.payload)
        for i, k, _, text in table.strings():
            if self.fields is not None and (len(table.fields(i)), k) not in self.fields:
                continue
            if JP.search(text):
                yield f"{self.prefix}{i}:{k}", i, k, text


def load_tables(src):
    """Return the text tables from the archives in folder src (e.g. dump/app/PCSG00126/masterPSP2)."""
    tables = []
    seen = set()
    for _, _, _, _, _, data in gdat.iter_entries(os.path.join(src, "GxArchivedFile002.dat"), {"pac"}):
        for path, typ, entry in pac.parse(gdat.unpack(data)):
            if typ != DT2 or path in seen:
                continue
            if path.startswith("GP/text/"):
                seen.add(path)
                tables.append(Table("bundle", path, gdat.unpack(entry), path))
            elif data_spec(path):
                seen.add(path)
                tables.append(Table("data", path, gdat.unpack(entry), path))
    want = {(gdat.name_hash(n) if isinstance(n, str) else n): n for n in TABLES_000}
    loose = {gdat.name_hash(t.name): t for t in tables if t.source == "data"}
    only000 = {gdat.name_hash(p): p for p in DATA_TABLES if not p.endswith("/") and p not in seen}
    for h0, h1, _, _, _, data in gdat.iter_entries(os.path.join(src, "GxArchivedFile000.dat"), {"dt2"}):
        if h1 in want:
            tables.append(Table("000", want.pop(h1), gdat.unpack(data), (h0, h1)))
        elif h1 in only000:
            tables.append(Table("data", only000.pop(h1), gdat.unpack(data), (h0, h1)))
        elif h1 in loose:
            t = loose[h1]
            if gdat.unpack(data) != t.payload:
                raise ValueError(f"loose copy of {t.name} in archive 000 differs from the bundle copy")
            t.loose = (h0, h1)
    if want or only000:
        raise KeyError(f"not found in archive 000: {list(want.values()) + list(only000.values())}")
    return sorted(tables, key=lambda t: (t.source, t.label))

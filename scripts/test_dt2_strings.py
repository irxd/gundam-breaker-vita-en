"""Build a test archive that changes four system messages, to check the dt2 relocation theory in game.

  #3 Create save data?      -> in place (shorter)
  #4 Creating save data...  -> longer, record moved to the end of the table
  #5 Writing save data...   -> in place
  #6 Loading save data...   -> longer, record moved

Run from the repo root:  python -I scripts/test_dt2_strings.py
Output: build/test_dt2/PCSG00126/masterPSP2/GxArchivedFile000.dat
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import dt2  # noqa: E402
import gdat  # noqa: E402

ARCHIVE = os.path.join(ROOT, "dump", "app", "PCSG00126", "masterPSP2", "GxArchivedFile000.dat")
OUT = os.path.join(ROOT, "build", "test_dt2", "PCSG00126", "masterPSP2", "GxArchivedFile000.dat")
KEY = (0x2C1CF0E2, 0x2DFACC58)  # system messages (schema 2)

EDITS = {  # relocation index -> (expected Japanese, English)
    3: ("セーブデータを作成します、よろしいですか？", "Create save data. OK?"),
    4: ("セーブデータを作成しています。電源を切らずにお待ちください。",
        "Creating save data. Please do not turn off the system while saving. "
        "(test: this line was moved to the end of the table)"),
    5: ("セーブデータを書き込んでいます、電源を切らずにお待ちください。",
        "Writing save data. Do not turn off the power."),
    6: ("セーブデータを読み込んでいます、電源を切らずにお待ちください。",
        "Loading save data. Please do not turn off the system while loading. "
        "(test: this line was moved to the end of the table)"),
}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    payload = None
    for h0, h1, _, _, _, data in gdat.iter_entries(ARCHIVE, {"dt2"}):
        if (h0, h1) == KEY:
            payload = gdat.unpack(data)
            break
    table = dt2.Dt2(payload)
    assert table.schema == 2, table.schema

    # Work out each string's offset before editing, while the original records are in place.
    plan = []
    for idx, (ja, en) in EDITS.items():
        target, loc = table.relocs[idx]
        desc = loc >> 8
        field = struct.unpack_from("<H", table.data, desc + (loc & 0xFF))[0] & 0x0FFF
        str_off = target + field
        got = table.cstring_at(str_off)
        if got != ja:
            sys.exit(f"#{idx}: expected {ja!r}, found {got!r}")
        plan.append((idx, target, str_off, en))

    for idx, target, str_off, en in plan:
        how = table.replace_string(str_off, en, target)
        print(f"#{idx}: {how}")

    new = table.to_bytes()
    # Re-read every edited string through the relocation table.
    check = dt2.Dt2(new)
    for idx, (ja, en) in EDITS.items():
        target, loc = check.relocs[idx]
        field = struct.unpack_from("<H", check.data, (loc >> 8) + (loc & 0xFF))[0] & 0x0FFF
        assert check.cstring_at(target + field) == en, idx

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    gdat.rebuild(ARCHIVE, OUT, {KEY: new})
    print(f"table {len(payload):#x} -> {len(new):#x} bytes")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()

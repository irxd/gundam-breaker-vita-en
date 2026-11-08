# Gundam Breaker (Vita) file formats

Confirmed against the dump on 2026-11-08. Engine: Crafts & Meister **"Gx"** (GxCore, GxHud, GxShader…), not
Koei Tecmo, so none of SGM's LINKDATA/G1T code applies.

## Versions

| | Title ID | APP_VER | eboot (SELF) | Decrypted ELF |
|---|---|---|---|---|
| Base game | PCSG00126 | 01.00 | 3,930,256 B | `dump/eboot/app/eboot.bin.elf` (7,776,902 B) |
| Update | PCSG00126 | 01.02 | 3,909,680 B | `dump/eboot/patch/eboot.bin.elf` (7,732,198 B) |

Original `GxArchivedFile000.dat`: 1,497,701,319 B, SHA-1 `0cbdab3cf7c5ea798ead3e9284de9e61ba8e4ede`.
FAGDec `self_auth.bin` is the same for both versions (authid `0x210000101cce007e`). `scripts/make_eboot.py` builds a
fake-signed eboot from the ELF. Converting it back with SGM's `unfself.py` gives a byte-identical ELF.

The update (`ux0:patch/PCSG00126`) has **only** the eboot, modules and sce_sys, so all game data comes from the base
game. 1.01 added a control-scheme screen for PS TV and showed the version on the title screen; 1.02 is "stability".
No DLC folder has been checked yet.

## Layout of `app/PCSG00126/`

- `masterPSP2/GxArchivedFile000.dat` (1.5 GB, 104,126 entries): almost everything (text, textures, models, effects…)
- `masterPSP2/GxArchivedFile001.dat` / `002.dat` (273 MB / 542 MB): only `pac` entries (map texture packs; they hold
  plain path strings such as `GP/map/jab/jab_tex/...`)
- `finalizedPSP2/GP/movie/*.usm` (CRI Sofdec video), `GP/soundStream/*.awb` (CRI ADX2 audio)
- `finalizedPSP2/GxCore/...`: loose engine files (debug font, shaders)

## GDAT archive (`GxArchivedFile00x.dat`), big-endian

```
0x00 "GDAT"
0x04 u32 N
0x08 N x { u32 hash0 (type), u32 hash1 (name/id), u32 offset (absolute), u32 size }
```
- Sorted by (hash0, hash1). Data is packed back to back in offset order, **no gaps, no padding**.
- hash0 is one value per entry type (`tex` = `fc397bb3`, `dt2` = `2c1cf0e2`, `csh` = `add2e39f`, …). The hash function
  is **unknown**: it isn't CRC32, FNV-1/1a, djb2, sdbm, x31 or x65599 of the type name. Names like
  `GP/font/gp_font_DFG_Kakou_W5_size21_0` are in the eboot, so the function can be found there if needed.
- In 001/002, hash1 counts up by one per entry (IDs, not hashes).
- Tool: [tools/gdat.py](../tools/gdat.py) (`list`, `extract [--type T]`).

### Entry header

```
0x00 type tag, a reversed fourcc: "\0xet" = tex, "\02td" = dt2, "\0kpm" = mpk, ...
0x04 u32 2   0x08 u32 subtype   0x0C u32 2   0x2C u32 1 if a BILZ payload follows
0x80 "BILZ" u32 uncompressed size, u32 stored size, u32 level
0x90 data: level 0 = stored raw, otherwise a plain zlib stream (78 DA)
```
`@UTF` (CRI tables) and `DSSP` entries have no header and are stored raw.

Entry counts in 000: mpk 88,165 · tex 9,668 · dt2 3,058 · eff 754 · mdc/mdl 520 each · csd 444 · DSSP 223 · @UTF 159
· csh 116 · and a few more.

## Text: `dt2` tables (UTF-8)

- All game text found so far is **UTF-8**, inside `dt2` entries (the eboot only has ~560 short UTF-8 strings, mostly
  debug motion/state names).
- Layout: `u32 schema id`, `u32 count`, then a table of `count` pairs `(u32 target offset, u32 location)`, then a
  type/layout block, then records. Strings are null-terminated UTF-8 **inline among the record bytes**.
  - The `location` word looks like `(byte position << 8) | sub-field`. The pairs act as a **relocation table**: the
    record slots don't hold raw string offsets, so it should be possible to put a longer string at the end of the
    entry and just repoint the table. **Still to be confirmed on hardware/Vita3K.**
  - The layout block looks like u16 values `type << 12 | field offset` (type 5 = 1 byte, 6 = 2 bytes, 8 = struct?).
  - Between strings there are sometimes 1–3 leftover bytes (possibly packed fields); keep them as they are.
- Rough count (regex scan, overestimates a bit): **~5,500 unique strings, under ~300k characters**.

| schema | files | unique strings | looks like |
|---|---|---|---|
| 3 | 10 | 1,521 | missions, menu/help text (largest by characters) |
| 4 | 107 | 613 | story dialogue (speaker names such as 藤木コウタ) |
| 6, 10, 21, 23, 25 | many | ~2,900 | parts, weapons, MS names (`HG ガンダム`, `RX-78-2`) |
| 8 | 459 | 249 | shop / tutorial pages (long text) |
| 2 | 7 | 286 | system messages (network, save data) |
| 5, 24, 15, 16 | few | ~165 | titles, skills, paint names |

## Fonts

From the eboot: `GP/font/gp_font_DFG_Kakou_W5_size21{,_0,_table}` (main) and
`GP/font/gp_font_Square721_Cn_BT_size30{,_0,_table}` (Latin, condensed; probably HUD numbers).

- **Main atlas** = `tex fc397bb3_4a19f327`: 1796×1796 (data padded to 2048×2048), **DXT5**, Vita Morton swizzle on
  4×4 blocks with **y on the even bits, x on the odd bits**.
  - It contains **full ASCII** plus full-width forms, kana, Greek/Cyrillic and ~7k kanji, **packed proportionally**
    (Latin glyphs are narrow, not full-width cells as in SGM).
- **Glyph tables** (`csh`, same serialized container as dt2, schema 9): `add2e39f_caf6c48b` (512,000 B, 7,111
  glyphs, main font) and `add2e39f_d6720358` / `add2e39f_f4536489` (8,144 B, 113 glyphs). The record format (code
  point, UV, width) is **not decoded yet**: no plain UTF-16/UTF-32/SJIS code sequences were found.
- Debug font (loose, not used in game): `finalizedPSP2/GxCore/texture/font12color2_*`.

## Textures (`tex`)

Header (decompressed): `u16 width, u16 height` (LE), then 4 format bytes `12 41 xx yy`, then 4 more bytes, data at
0x0C. Low nibble `d` of byte 7 = DXT; byte 6 `0x20` = DXT5 (otherwise DXT1); high nibble of byte 7 looks like the
mip count (1 = no mips). Swizzle as above. Images with Japanese text are not catalogued yet.

## pac bundles (GxArchivedFile001/002) and the name hash

- **The text the game shows comes from here**, not from the dt2 entries in archive 000 (the tag build that only
  changed 000 left all in-game text Japanese). E.g. `GP/text/voice_event_text` (mission dialogue, 150 KB),
  `GP/text/mission_object_detail` (objectives), `GP/text/information_detail`, `GP/unitData/itemSkillParam`.
- `pac` entries: 0x80 header with flag 0 (no BILZ), then the bundle (LE):
  `u32 count, u32 largest member size, count x {char path[0x100], u32 type hash, u32 size}`, then the members
  back to back, each a full entry (0x80 header + BILZ). Tool: [tools/pac.py](../tools/pac.py), byte-identical
  round trip on all 5,078 bundles (57,253 members, 33,707 distinct paths).
- 1,278 dt2 files with Japanese live in bundles, each in 1–2 bundles (identical copies). All copies must be patched.
- **Name hash** (hash1 in archive 000): `h = 37; for each byte: h = h*37 + byte` (32-bit) over the path as stored
  in the bundles, no extension, e.g. `GP/text/voice_event_text`. Matches 1,612 of 1,703 content-matched pairs
  (the rest are files with identical content). `gdat.name_hash()`. The type hash (hash0) is a different function,
  but the bundles store it.
- **Markup** seen in strings: `<br>` (line break), `<c02>…</c>` (colour), `\n` as two literal characters in
  system-dialog texts. Keep exactly.

## Tag build results (Vita3K, Vulkan, 2026-11-08)

- **ASCII renders in the game font**, proportionally spaced (`NEW GAME1GW`, `上1GX`). System dialogs (drawn by
  Vita3K) also show the dt2 text, so the "empty" Yes/No dialog was a Japanese dt2 message Vita3K couldn't draw.
- **Both sources are live:** dialogue, menus and help come from `GP/text/*` inside the bundles in 002; the loading
  tips come from a dt2 entry in archive 000 (`000:8a96336f`). Patch both.
- **Changing names in the data tables inside the 002 bundles crashed mission loading** (`GP/csv/NPCParam`,
  `GP/unitData/*`, `GP/csv/MA/*`, `GP/map/*`; render-target error, then an access violation). Tagging only
  `GP/text/*` (13 files in 2 bundles) plus all of archive 000 works. Some names in those data tables are probably
  used as keys. Translate them only after finding which fields are display-only.
- Text drawn from images (e.g. the GUNPLA CONTROL loading screen) stays Japanese.
- String finding: record ID bytes in front of a string can be 0x80–0xBF, so don't use a "not after a continuation
  byte" look-behind.

## Running in Vita3K (2026-11-08)

- Works up to the title screen with: the fself eboot **and** fself `sce_module/*.suprx` (from FAGDec-decrypted 1.02
  modules; `scripts/make_eboot.py` builds both). With the encrypted modules from the dump, libc fails to load and
  the main thread crashes 0.6 s after boot while the launch image stays on screen.
- The title screen shows **"Game Version: 1.12"** with the 1.02 update (internal version number).
- On first boot the save is created **silently** (no dialog). A Yes/No system dialog with an empty body appears
  (Vita3K draws system dialogs; it isn't the dt2 save message). Changing system messages #3–#6 showed nothing, so
  the relocation theory is **not confirmed yet**. It needs a string drawn by the game itself.
- **Loose files before the archive:** for some files the game calls `stat` on `app0:/masterPSP2/<path>` first and
  only falls back to the archive when it's missing. It also probes `GxArchivedFile003.dat` / `004.dat` (missing),
  which suggests extra archives can be added. Paths seen in one boot (88): engine shaders (`GxCore/…`, `GxShader/…`),
  `GP/unitData/preset/presetNNNN.dt2`, `GP/csv/default_colorset_param.dt2`, `GP/partsConfig/default.cpc`,
  `pacPSP2/ui/uiNNNN.pac`, `pacPSP2/sysgameboot.pac`, `sysgamecommon.pac`, `sysunitcsv.pac`.
  - If loose files override archive entries, a release can ship small files through rePatch instead of a 1.5 GB
    archive. Not tested yet.
- Name hash: none of fnv1/1a, djb2, sdbm, CRC32, Jenkins one-at-a-time, ELF hash or x31/33/37/131/65599 (on path
  variants, UTF-8/UTF-16) gives the hash1 of those probed names. It has to be found in the eboot (follow the
  `stat` → archive fallback).

## Open questions

1. dt2: confirm the relocation-table theory (lengthen one string, test in Vita3K).
2. csh glyph table record format (widths/kerning, line height). Find where the game does line breaking.
3. Find UI textures with Japanese text (title, menus, mission cards).
4. Whether the game can load loose files instead of the 1.5 GB archive (otherwise the release patches
   `GxArchivedFile000.dat` as one xdelta).
5. CRI `@UTF`/`DSSP` hold some Shift-JIS (cue names?); probably not shown in game.

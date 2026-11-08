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

## Open questions

1. dt2: confirm the relocation-table theory (lengthen one string, test in Vita3K).
2. csh glyph table record format (widths/kerning, line height). Find where the game does line breaking.
3. Find UI textures with Japanese text (title, menus, mission cards).
4. Whether the game can load loose files instead of the 1.5 GB archive (otherwise the release patches
   `GxArchivedFile000.dat` as one xdelta).
5. CRI `@UTF`/`DSSP` hold some Shift-JIS (cue names?); probably not shown in game.

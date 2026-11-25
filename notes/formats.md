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
**DLC (checked 2026-11-26): probably none was ever released.** The game has DLC code and art: a store banner for a
"Giga Break Mission Pack" (`GP/ui/ui_dds/dialog/leadbanner`), `hud_dlcm_*` HUD textures, `title_btn_dlc_*`, and three
help lines (ui_help_detail 668-670) saying the DLC is needed. Those help lines still use a placeholder name ("DLC
name TBD"), and no web source mentions the pack. The `hud_dlcm_*` HUD matches Area Raid / Team Attack battles,
which shipped free with the 30 extra missions of the Vita release and PS3 update 1.02 (31 Oct 2013). So there's no
`ux0:addcont` to dump; the banner and help lines are translated anyway (harmless if never shown).

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

- Almost all game text is **UTF-8**, inside `dt2` entries. The eboot has more (see "Text in the eboot"; the old
  count of ~560 was wrong).
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
| 4 | 107 | 613 | story dialogue (speaker names such as the hero, Kota Fujiki) |
| 6, 10, 21, 23, 25 | many | ~2,900 | parts, weapons, MS names (grade + name such as "HG Gundam", model numbers such as `RX-78-2`) |
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

## Vita3K renderer (important for reading test results)

- **OpenGL** draws the 3D world but **crashes on mission load now and then, even with the original files**
  (`sceGxmCreateRenderTarget` → `SCE_GXM_ERROR_DRIVER`, "two different surfaces have the same base address",
  then an access violation). The config had silently stayed on OpenGL for most of the tests below.
- **Vulkan** loads the mission with the original files, but the 3D world is black. HUD and dialogue text render
  fine, so use Vulkan for text tests.
- So the crashes below that were blamed on the data tables and on tables growing are **not proven**. They all
  happened on OpenGL. Re-test on Vulkan before relying on them. The build still keeps tables from growing
  (costs nothing).

## Re-pack test: confirmed in game (Vita3K Vulkan, 2026-11-08)

`scripts/test_dt2_strings.py`: three first-mission lines in `GP/text/voice_event_text` replaced with English,
one of them longer in bytes than the Japanese; the table re-packed (records shifted, field offsets updated,
leftover bytes cleared, raw and compressed size smaller than the original). **All three show correctly**, the
following Japanese lines (in shifted records) are intact, `<br>` breaks lines. The dialogue box takes two lines of
about 50–55 Latin characters ("To test your machine and your aptitude as a pilot," nearly fills a line).

## Tag build results (Vita3K, mostly OpenGL, 2026-11-08)

- **ASCII renders in the game font**, proportionally spaced (`NEW GAME1GW`, and a kanji followed by `1GX`). System dialogs (drawn by
  Vita3K) also show the dt2 text, so the "empty" Yes/No dialog was a Japanese dt2 message Vita3K couldn't draw.
- **Both sources are live:** dialogue, menus and help come from `GP/text/*` inside the bundles in 002; the loading
  tips come from a dt2 entry in archive 000 (`000:8a96336f`). Patch both.
- **Changing names in the data tables inside the 002 bundles crashed mission loading** (`GP/csv/NPCParam`,
  `GP/unitData/*`, `GP/csv/MA/*`, `GP/map/*`; render-target error, then an access violation). Tagging only
  `GP/text/*` (13 files in 2 bundles) plus all of archive 000 works. Some names in those data tables are probably
  used as keys. Translate them only after finding which fields are display-only (done for `GP/unitData/*`, see below).
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

## Larger entries: work in Vita3K (2026-11-09)

English mission_name compresses 222 bytes larger than the Japanese (the table itself shrinks), so its bundle in
002 grew 113136 -> 113358 bytes; `gdat.rebuild` recomputed all offsets. In Vita3K (Vulkan) the tutorial mission
loaded and the pause map showed the English name. So compressed entries and bundles may grow;
`build_text.py` only warns (`--strict-size` makes it an error). Uncompressed tables still never grow.
To check on a real Vita before release.

## Text that is not in any table

Not found in any archive, entry or bundle (UTF-8, UTF-16 LE/BE, Shift-JIS) nor in the eboot, so probably drawn
in UI textures: the pause map buttons (Settings / Resume), and English-looking headers such as MISSION AREA MAP,
TREASURE LIST. Needs the image work (find the texture, decode DXT, redraw, re-encode).

## Gundam Breaker 3

Read only as the source for terms (notes/terms.md). Dump: `dump_gb3/app/PCSH10042/` (Vita, Asia, English + Korean;
no update). Checked 2026-11-08.

- Same engine and layout (`masterPSP2/GxArchivedFile000-002.dat`, `finalizedPSP2/` for movies, sound, shaders),
  but the GDAT is **little-endian**: "GDAT", u32 N, then N × {u32 hash1 (name), u32 hash0 (type), u32 offset,
  u32 size}. `tools/gdat.read_table` (big-endian) doesn't read it.
- Entry type tags are written forwards (`dt2\0`, `pac\0`, `tex\0`), not reversed. Payload at 0x80 as in GB1.
- Archive 000 holds only `pac` bundles (89), which `tools/pac.py` parses. Archives 001/002 hold loose entries.
- All 27,515 dt2 tables parse with `tools/dt2.py` unchanged.
- Text tables come in pairs, English and Korean, whose hash1 differ by 0xE2 (a language suffix in the path).
  Records line up one to one. GB1's `GP/text/*` names don't hash to any GB3 entry.
- The Japanese text tables are not in this build. Japanese remains only in data tables (`GP/unitData/*`,
  `GP/csv/*`, internal labels), so Japanese and English can't be paired automatically. Terms were matched by
  searching the English for each name.

## unitData name tables (added 2026-11-21, not yet tested in game)

The Set Up screen, option equipment, items and EX-Action screens read names from `GP/unitData/*` in the 002 bundles,
not from `GP/text/*` (000_bbcf42d0 99:10 "Mirage Shot" did not change the EX-Action learned screen). Every record
has a **numeric ID in field 0** (part/weapon/EX ID, e.g. 242, 5101, 400) that the tables use to point at each other;
the names are not keys: no `GP/csv/*` or `GP/map/*` string equals any of them, and partsList names differ from the
parts/* names for the same ID ("HG Gundam Head" vs "HG Gundam"), so nothing matches names at runtime as far as the data
shows. Picked by (field count of the record, field index), see `DATA_TABLES` in tools/gbtext.py:

| table | field | content | CSV / id |
|---|---|---|---|
| `GP/unitData/partsList` | (6, 1) | part name per slot, e.g. "HG Gundam Head" | `unitData_partsList.csv`, `rec:field` |
| `GP/unitData/weaponList` | (8, 1) | weapon name, e.g. "HG Beam Saber"; entry 0 = bare hands | `unitData_weaponList.csv` |
| `GP/unitData/itemSkillParam` | (32, 1) | battle items, e.g. "Repair Kit S", "HG Cracker" | `unitData_itemSkillParam.csv` |
| `GP/unitData/parts/chrNNNN` (882) | (11, 1) | MS name of the part, e.g. "HG GM" (the Set Up list cuts off `HG `) | `unitData_parts.csv`, `chr0242:1:1` |
| | (24, 1) | option equipment, e.g. "Head Vulcan (GM)" | `chr0242:31:1` |
| `GP/unitData/equip/equipNNNN` (308) | (18, 3), (20, 3) | weapon name | `unitData_equip.csv`, `equip5101:1:3` |
| `GP/unitData/ex/exNNN` (59) | (18, 1) | EX-Action name, e.g. "Mirage Shot" | `unitData_ex.csv`, `ex400:1:1` |

- One combined CSV per folder (parts, equip, ex) with id `<file>:<record>:<field>`, so there aren't ~1,250 files.
- Copies: each member is in 1–2 bundles of 002 (identical), and parts/equip/ex also have a **loose copy in archive
  000** (hash1 = `name_hash(path)`, e.g. chr0242 = `a762fe9a`, ex400 = `b22082d9`). The build writes the same payload
  to every bundle copy and the loose copy (`Table.loose`). Only 002 holds these members (none in 001).
- Left out as internal labels: equip field 8 (short weapon name, placeholders such as a beam spray gun name on PG weapons
  and joke spellings of "Zaku bazooka"), equip attack records ("<name>'s attack A", "dummy", `test`), ex sub-records field 2/23 (unit or
  weapon name next to an ID, e.g. "God Gundam variant", `NULL`), `awakeparam` field 1 ("boss", "escorts",
  "base: infinite spawns", "HT + awakening: ..."), `effect/*` and `sound/*` comments.
- Build check added: a grade prefix (`HG `, `MG `, `PG`) at the start of the Japanese must stay at the start of the
  English, because the Set Up list drops it.
- Many of these tables are tiny (one or two strings), so the "table must not grow" rule bites: about 60 rows use a
  shorter form (notes say "short form, the table can't grow"), and HG/MG Hyaku-Shiki is `Type 100` in its part
  tables (see "Longer strings may use stale bytes" below). If Vulkan shows grown tables are fine, these can be
  relaxed.
- The default Gunpla name (GM) and "not equipped" are eboot strings (0x747b04); no data table supplies them
  (only `GP/text/partner_ms_name` has a bare "GM", which is a partner MS name).

## GP/csv, GP/map and parts_phonetic (added 2026-11-25, not yet tested in game)

Display fields of these tables are extracted like the unitData ones (`DATA_TABLES` in tools/gbtext.py). Two of them
exist **only as loose dt2 entries in archive 000** (no bundle copy): `GP/text/parts_phonetic` (`4e461bc6`) and
`GP/csv/decalData` (`7b592c49`); the build writes those back into 000. The others are members of one 002 bundle each
and have no loose copy.

| table | field | content | CSV |
|---|---|---|---|
| `GP/text/parts_phonetic` | (4, 3) | part / weapon description shown for a part: traits ("no special traits", "movement type becomes Flight"), option equipment, EX-Actions it teaches, weapon type and attacks; `<c00>`–`<c05>` colour tags | `000_parts_phonetic.csv` |
| `GP/csv/decalData` | (10, 1) | decal name, "HG Gundam Decal B"; field 0 = numeric decal ID (1001…), the rest are numbers | `csv_decalData.csv` |
| `GP/csv/AiIntensificationChipData` | (49, 1) | chip name, the same strings as `GP/text/chip_name` (translations copied); the other 48 fields are numbers | `csv_AiIntensificationChipData.csv` |
| `GP/csv/scoreAchievementsTable` | (6, 5), (7, 5), (8, 5) | ace point description; the same text as `acepoint_detail` without the points (translations copied) | `csv_scoreAchievementsTable.csv` |
| `GP/map/map` | (4, 1) | map name with time of day ("Jaburo (Evening)", "Boss 1", "Home") | `map_map.csv` |

- Left alone in those tables: parts_phonetic field 1 (sort reading: the kit name in katakana without spaces, e.g.
  "HGGundam"), scoreAchievementsTable field 1 (ID such as `FIRST_KILL`) and field 7 (developer comment: "not used at
  the moment", "damage dealt to the enemy"), map field 2 (map code `jab_01`).
- scoreAchievementsTable 18 and 49 ("last enemy of the area", "shooting with head and left arm off") stay Japanese: the
  matching acepoint_name rows say "if this appears it's a bug" (unused); 22/23 are that bug text itself.
- Not extracted, because they are internal labels:

| table | strings | why |
|---|---|---|
| `GP/csv/NPCParam` field 0 (1,411) | "[HG] GM with shield, beam rifle" | designer labels (grade tag, loadout); enemy names on the HUD come from the parts tables |
| `GP/csv/BOSSParam` field 0 (191) | "[PG] PG Gundam phase 1" | designer labels with phase numbers |
| `GP/csv/MA/*` (42) | "bullet spawn offset X", "1_front" | parameter names |
| `GP/csv/multiplayer` (15) | "grunt HP", "strong enemy HP" | parameter names |
| `GP/csv/parts_build_viewoffset` (971, loose in 000, `4e253684`) | part names ("HG Gundam Head") | row labels of a camera offset table (an older, longer list than partsList) |
| `GP/csv/ui_resource` (2, loose in 000, `84485bdb`) | "shown when Start is pressed in the hangar" | developer notes |
| `GP/unitData/awakeparam` field 1 (26) | "Hyper Mode", "boss", "escorts", "HT + awakening: Wings of Light" | awakening parameter labels |
| `GP/unitData/effect/*`, `sound/*` (4) | "2-barrel mega beam rifle (ZZ) attack B" | comments |

  No other dt2 with Japanese is left: every bundle member and loose 000 table with Japanese is either extracted or
  in this list (checked 2026-11-25).

### Longer strings may use stale bytes (tools/dt2.py, 2026-11-25)

Many strings are followed by 1–3 stale bytes before the next field (leftovers of an older, longer string; no field
points to them). `Dt2.rebuild` now lets a string that gets longer fill those bytes first, so fields only move when that
room runs out. Even so `HG Hyaku-Shiki` doesn't fit in chr0313/0314/0316/0317 and chr2313/2314/2316/2317: the
table's only other string is the model number `MSN-00100`, the whole table has just 4 stale bytes, and the name
needs 5 more bytes than the Japanese, so even a fully compacted table would grow by 1 byte. Decision (2026-11-25):
all 12 Hyaku-Shiki part tables (chr0312-0317, chr2312-2317) use `HG/MG Type 100` (the literal meaning) so the parts
of one Gunpla match on the Set Up list; everything else keeps GB3's Hyaku-Shiki. Re-checking the "short form" rows
with this change restored `PG Zeta Gundam Variant` in chr4482-4487; the others still don't fit.

## Movies (CRI USM, added 2026-11-25, not yet tested on hardware)

`finalizedPSP2/GP/movie/*.usm`: 57 loose files (not in the archives), so rePatch replaces them as
`ux0:rePatch/PCSG00126/finalizedPSP2/GP/movie/<name>.usm`. The eboot names them as `GP/movie/<name>` (all except
`GB_PV1` and the character clips, which are reached through `GP/movie/%s`).

- **Container** ([tools/usm.py](../tools/usm.py)): big-endian chunks aligned to 32 bytes (`CRID`, `@SFV` video,
  `@SFA` audio; header: size, payload offset 0x18, padding, kind 0 data / 1 header / 2 text marker / 3 seek, time,
  rate). Video data chunks hold one MPEG-1 picture each in coded order. `@UTF` tables: `CRIUSF_DIR_STREAM` (file and
  stream sizes, avbps = int(bytes * 8 / duration) with 29.97 fps counted as 30000/1001 and audio by samples, minbuf),
  `VIDEO_HDRINFO` (total_frames, ixsize, mpeg_dcprec 11), `VIDEO_SEEKINFO` (one row per GOP: byte offset of its first
  chunk and frame number). Parse + rebuild is byte-identical on all 57 files, also when every picture is
  "replaced" by itself (which recomputes all the tables).
- **Video**: MPEG-1, closed GOPs of up to 13 pictures (I P B B P B B ... P B B; `advertise` up to 7), 960x544 at
  30 fps (story, shop), 1280x720 at 29.97 (`GB_PV1`), 960x448 (`advertise`). Every GOP repeats the sequence header
  with **its own quantiser matrices** (they change from GOP to GOP) and TMPGEnc user data `TMPGEXS ... IDCPREC
  00000008 00000003`: the intra DC coefficients use **11-bit precision** (as MPEG-2 intra_dc_precision 3). ffmpeg
  decodes that; its MPEG-1 encoder can't write it, so [tools/mpeg1.py](../tools/mpeg1.py) re-codes the DC
  differentials of the encoded pictures (x8, extended dct_dc_size tables). The parser round-trips every original
  picture bit for bit. Audio: ADX, copied untouched.
- **Burned-in Japanese** (white text with a dark outline, bottom centre, y ~428-490): `me01` (opening narration and
  the MC), `me09` (closing ceremony), `me10` (the developer), `shop_ev_01`-`09` (shop owner), `me_ending` (epilogue
  lines revealed one by one over the sunset, upper half; then staff credits). The spoken lines are the same as
  `GP/text/voice_event_text` 410-424 and 716-762, so the English follows those rows.
- Clean (no Japanese subtitles): `title_bg`, `main_menu_bg`, `shop_no_talk`, `advertise` (song credit and logo
  only), the character clips `C10`-`C50`. Left as they are: `GB_PV1` (the PS3 promo trailer; not referenced by
  name, only a calligraphy tagline card), the staff credits in `me_ending`, the katakana in the logo.
- **Build** ([scripts/build_movies.py](../scripts/build_movies.py), cues in `text/movies/<name>.json`): only the GOPs
  that overlap a cue are re-encoded (each on its own, same picture count, the GOP's matrices, original sequence and
  GOP headers kept); all other pictures are copied byte for byte. A re-encoded GOP may use up to 1.5x its original
  bytes, and no picture may be larger than the file's largest original picture (the buffer fields stay valid).

## Text in the eboot (2026-11-24)

`scripts/eboot_text.py` finds 565 Japanese UTF-8 strings in the text segment of each eboot (4-byte aligned, after a zero byte or
right after a pointer; entries of a kana/kanji conversion table are filtered out). Most are debug/tool names (motion states,
attack names, material/sound editor properties). Player-visible ones include: the **default radio chat messages**
and the **default Gunpla name** (both copied into the save when it is created, so an existing save keeps the
Japanese), "not equipped" on the Set Up screen, keyboard prompts (Gunpla name, chat message), Next/Back, play time,
palette save/load prompts, the lobby/room strings, and an intro text (Odaiba) plus a main-menu explanation (not yet
seen in game).
- Strings are reached through movw/movt relocations, so they are patched **in place**: the English must fit the
  Japanese bytes plus zero padding up to the next 4-byte boundary. The build fails otherwise.
- id = offset in the 1.02 ELF; 1.00 is matched by the n-th occurrence of the same Japanese (all match except one 1.01+ string, the PS3 controls note, which is skipped for 1.00).
- Output: `build/patched_elf/<app|patch>/eboot.bin.elf` and the fake-signed `build/eboot/<app|patch>/eboot.bin`.
- Untested in game.

## Open questions

1. dt2: confirm the relocation-table theory (lengthen one string, test in Vita3K).
2. csh glyph table record format (widths/kerning, line height). Find where the game does line breaking.
3. Find UI textures with Japanese text (title, menus, mission cards).
4. Whether the game can load loose files instead of the 1.5 GB archive (otherwise the release patches
   `GxArchivedFile000.dat` as one xdelta).
5. CRI `@UTF`/`DSSP` hold some Shift-JIS (cue names?); probably not shown in game.

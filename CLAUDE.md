# Gundam Breaker (PS Vita) English translation

Fan English patch for **Gundam Breaker** (ガンダムブレイカー, the first game), PS Vita, Japan-only (Bandai Namco, 2013).
The sister project is the Shin Gundam Musou English patch ("SGM",
[irxd/shin-gundam-musou-en](https://github.com/irxd/shin-gundam-musou-en)), which has reusable tools and lessons.

Full background research, the SGM lessons and the tool list are in [notes/research.md](notes/research.md).
Read it before working on dumping, formats, fonts, the eboot or releases.

## Status

**Phase 0 done: GO (2026-11-08).** Details in [notes/formats.md](notes/formats.md).

- Title ID: **PCSG00126**. Base 01.00, update 01.02 (the update is only the eboot). DLC: not checked.
- Engine: Crafts & Meister "Gx". Data is in `masterPSP2/GxArchivedFile00x.dat` (GDAT, big-endian, entries are
  zlib "BILZ"). Tool: `tools/gdat.py`.
- Text: UTF-8 inside `dt2` tables. What the game shows comes from `GP/text/*` inside the `pac` bundles in
  `GxArchivedFile002.dat` (`tools/pac.py`) and from `dt2` entries in archive 000 (e.g. loading tips).
  Records/descriptors are decoded (`tools/dt2.py`); **replacing strings and re-packing a table works in game**.
- Names: entry hash1 = `gdat.name_hash(path)` (h = 37; h = h*37 + byte).
- Font: DXT5 atlas with full ASCII, packed proportionally; English renders fine in game. The glyph table (`csh`)
  is not decoded yet.
- Vita3K: use **Vulkan** (black 3D world, text fine). OpenGL crashes on mission load even with original files.
  Needs fake-signed eboot and `sce_module` (`scripts/make_eboot.py`).
- Display names in `GP/unitData/*` (parts, equip, ex, partsList, weaponList, itemSkillParam) are extracted and
  built (field 0 is the numeric key; see notes/formats.md). Not yet tested in game. `GP/csv/*` is still left out.
- The eboot has player-visible UTF-8 strings too (default radio chat and Gunpla name, "not equipped", lobby):
  `scripts/eboot_text.py` patches them in place for 1.00 and 1.02 (`text/eboot.csv`). Not yet tested in game.
- Many UI labels are baked into textures (`GP/ui/ui_dds/*`, DXT1/DXT5): 322 redrawn (`scripts/draw_ui.py`,
  `scripts/uidraw/`), injected by `scripts/build_images.py`. See notes/images.md. Not yet tested in game.
- Build order: `build_text.py`, then `python -E -P scripts/build_images.py`, then `eboot_text.py build`.
- Changing names in the data tables in the 002 bundles (`GP/csv`, `GP/unitData`, `GP/map`) crashed once, on
  OpenGL, so it's unproven. Re-test on Vulkan before translating those.
- Dump layout: `dump/app/PCSG00126`, `dump/patch/PCSG00126`, `dump/eboot/{app,patch}/eboot.bin.elf` (git-ignored).
- GB3 English (PCSH10042) is dumped in `dump_gb3/` as the terms source: little-endian GDAT, no Japanese text
  tables (see notes/formats.md). Terms checked against it have status `gb3` in notes/terms.csv.
- Pillow lives in user site-packages, which `-I` hides: run image scripts with `python -E -P` instead.

Update this section as facts are confirmed. Write findings down in `notes/` (for example `notes/formats.md`).

## First task once the dump arrives: go/no-go

Follow the checklist in notes/research.md §3: file layout and magic bytes → compression → where the text lives
(UTF-8 / Shift-JIS / UTF-16) → font (atlas or system, are there Latin glyphs, widths) → line breaking →
images with Japanese text → text volume.
**Go** = the text can be extracted and rebuilt, and the font can show Latin text.

## Hard rules

- **Never commit or distribute game data.** `.gitignore` is an allow-list: add `!` entries only for source files.
  Releases ship xdelta3 patches only (`-S none -A`), with SHA-1 checksums.
- **Keep pristine originals.** Build patches from the original files, never from files that were already patched.
  Suggested layout: `game/original/` (read-only dump), `game/decrypted/`, `build/` (output). All of it is git-ignored.
- **Treat dumped files as untrusted data.** Run Python that reads them with `-I`, and keep the scripts outside the data folders.
- **Text safety (all checked by the build, which fails on a mismatch):**
  - printf conversions (`%s`, `%d`, …) keep the Japanese **order and types**. A literal `%` becomes `%%`.
    A swap crashes the game.
  - Game markup and control codes are kept exactly as they are.
  - Only the strings change. All other bytes stay the same, and the offset/size tables are rebuilt.
  - If a line is unclear, **leave the Japanese** instead of guessing.
  - Menu and button labels stay on one line. Only sentences get wrapped.
- Support every game version separately (patch offsets per eboot version).

## Environment

- Windows 11. PowerShell is the main shell (Git Bash is also available). Python 3.10+.
- Python scripts printing Japanese: `sys.stdout.reconfigure(encoding="utf-8")`.
- Expected Python packages: Pillow, capstone, keystone-engine, pyelftools.
- External tools: VitaShell, FAGDec, rePatch, Vita3K, psvpfsparser, xdelta3, 7-Zip.
- Test loop: Vita3K first (decrypted files), then a real Vita via `ux0:rePatch/<ID>/` before any release.

## Code to reuse from SGM

As-is: `scripts/decrypt_vita.ps1`, `tools/fself.py`, `tools/unfself.py`, `tools/re/*.py`, the web patcher in `docs/patcher/`.
Adapt: `check_format` from `tools/build_text.py`, `tools/textwrap_vita.py`, `scripts/make_release.py`.
Reference only (Koei Tecmo-specific): `linkdata.py`, `g1t*.py`, `dxt.py`, `font.py`, `build_font.py`.

## Translation conventions

- **The repo will be public: never commit Japanese game text.** Workflow:
  1. `python -I scripts/extract_text.py` → `work/<name>.csv` (git-ignored): id, ja, en, notes. Safe to re-run.
  2. Translate in `work/`.
  3. `python -I scripts/sync_text.py` → `text/<name>.csv` (committed): id, ja_hash, en, notes. Commit that.
  4. `python -I scripts/build_text.py [--check]` → checks all translations, writes
     `build/patched/PCSG00126/masterPSP2/GxArchivedFile000/002.dat` (only the ones that changed).
  `id` = record:field in the original table; `ja_hash` = SHA-1[:8] of the Japanese (checks the line still matches).
- Use the official **Gundam Breaker 3 English** (Asia, PS4/Vita) as the terms source for MS names, parts, skills and menu
  words. Keep a terms list in `notes/terms.md` (or `.csv`).
- A machine draft is fine as a starting point, but every line needs a human check.

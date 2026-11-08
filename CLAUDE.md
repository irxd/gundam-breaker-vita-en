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
- Text: UTF-8 inside `dt2` tables (~5.5k unique strings), with a relocation table for the strings.
- Font: DXT5 atlas with full ASCII, packed proportionally. The glyph table (`csh`) is not decoded yet.
- Dump layout: `dump/app/PCSG00126`, `dump/patch/PCSG00126`, `dump/eboot/{app,patch}/eboot.bin.elf` (git-ignored).
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

- Working text format: CSV/JSON with id, Japanese, English, notes, and max width.
- Use the official **Gundam Breaker 3 English** (Asia, PS4/Vita) as the terms source for MS names, parts, skills and menu
  words. Keep a terms list in `notes/terms.md` (or `.csv`).
- A machine draft is fine as a starting point, but every line needs a human check.

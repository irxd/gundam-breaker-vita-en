# Gundam Breaker (PS Vita) English patch: starting notes

These notes cover what we know before the project starts. They come from web research (November 2026) and
from building the Shin Gundam Musou English patch
([irxd/shin-gundam-musou-en](https://github.com/irxd/shin-gundam-musou-en), "SGM" below).

## 1. The game

| | |
|---|---|
| Title | Gundam Breaker (ガンダムブレイカー), the first game |
| Platforms | PS3 (June 2013), PS Vita (31 Oct 2013, Japan only; adds about 30 extra missions) |
| Publisher | Bandai Namco |
| Vita title ID | **TBD:** read it from `sce_sys/param.sfo` after dumping |
| Updates / DLC | **TBD:** check `ux0:patch/<ID>` and `ux0:addcont/<ID>` |

## 2. What already exists (research)

- **No English release** of Gundam Breaker 1 (or 2) anywhere.
- **No fan translation** found, in English or Japanese searches, and no public tools for its file formats.
- **Gundam Breaker 3 has an official English version** (Asia, PS4 and **Vita**, 2016; "Break Edition" with all
  DLC, 2017). It's the only official English source in the series that's close to GB1.
  - It's useful for **terms**: mobile suit names, part slots, weapon and skill names, and menu wording, to keep
    names consistent with the official ones.
  - It's **not** a 1:1 text source the way Gundam Reborn was for SGM. The story, missions and GB1-only content
    have to be translated new.

Sources: [Gematsu: GB Vita release date](https://www.gematsu.com/2013/08/gundam-breaker-ps-vita-japanese-release-date-set),
[Siliconera: GB Vita, Oct 31](https://www.siliconera.com/gundam-breaker-coming-to-vita-on-october-31-with-more-mecha-like-gundam-x/),
[Siliconera: GB3 English subs in Asia](https://www.siliconera.com/gundam-breaker-3-releasing-english-subs-asia-version/),
[Gematsu: GB3 Break Edition English](https://gematsu.com/2017/03/gundam-breaker-3-break-edition-launches-english-may-2-asia).

### How this differs from SGM

| | SGM | Gundam Breaker 1 |
|---|---|---|
| English source | Gundam Reborn PS3: same engine, a nearly 1:1 text match | None. GB3 English covers the shared terms only |
| Text work | Mostly porting by entry index | Mostly new translation, plus a terms list from GB3 |
| Formats | LINKDATA (Koei Tecmo), solved | Unknown, possibly a different engine/developer: start from zero |
| Amount of text | Very large (~66k mission strings, 5k table strings, 5.4k story lines) | Probably smaller (to be counted) |

## 3. Go/no-go checklist (do this first on the dump)

1. **File layout:** list everything under `app/<ID>/`. Note the big files and their magic bytes.
   - A CRI **CPK** (`CPK ` magic) has existing tools (CriPakTools and others).
   - Anything else needs its own reader. Look for a header with a count plus an offset/size table, as with
     SGM's LINKDATA.
2. **Compression:** look for high-entropy data, zlib (`78 9C`/`78 DA`), or a custom LZ. Compressed archives
   mean we need a compressor too, or the eboot has to accept uncompressed data.
3. **Text:** search the decompressed data for known Japanese strings, encoded as UTF-8, Shift-JIS and UTF-16.
   Find the container: string table, script bytecode with text mixed in, or fixed-length records.
4. **Font:** a texture atlas (as in SGM: 20×20 cells, glyph list in the eboot) or a system font. Check
   whether Latin glyphs exist and whether they're fixed-width.
5. **Line breaks / box sizes:** whether Japanese lines are hand-broken (SGM: yes, so English has to be
   pre-wrapped) or whether the engine wraps by itself.
6. **Images with Japanese text:** menus, buttons, title screen, briefing cards.
7. **Count the text:** number of strings and characters, so the translation work can be sized.

**Go** if the text can be extracted and rebuilt and the font can show Latin text. Everything else can be
worked around.

## 4. Dumping and decrypting (what worked for SGM)

- **Game data:** VitaShell → the game's folder → **Open decrypted** (△ menu), then copy the files out.
  Or decrypt a NoNpDRM dump on the PC with **psvpfsparser**: the key (klicensee) is at `0x50` in
  `sce_sys/package/work.bin`. It needs internet access for the F00D service (`cma.henkaku.xyz`). SGM's
  `scripts/decrypt_vita.ps1` does this for the game and every DLC folder, and can be reused as-is.
- **eboot:** **FAGDec** → START DECRYPT (ELF) → `ux0:FAGDec/app/<ID>/eboot.bin.elf` + `self_auth.bin`.
  Use the **update's** eboot (`ux0:patch/<ID>/eboot.bin`) if there's an update. Each game version needs its
  own eboot patch.
  - Other routes: Vita3K Settings → Debug → *ELF dumping*, or SGM `tools/unfself.py` (a decrypted SELF → ELF).
- **Keep pristine copies** of everything. Patches are always built from the originals.
- Keep `sce_sys/param.sfo` too (for the title ID, the version, and in case we rename the game later).

## 5. Running patched files

- **Real Vita: rePatch** (`*KERNEL` in `ur0:tai/config.txt`). Files in `ux0:rePatch/<ID>/` override the
  game's files with the same paths, so nothing in `ux0:app` or `ux0:patch` is touched. To uninstall, delete
  the folder.
- rePatch files must be **decrypted** (that's why we patch the decrypted LINKDATA).
- A modified eboot must be rebuilt as a **fake-signed SELF** (fself). SGM `tools/fself.py` is a Python port of
  `vita-make-fself` that keeps the module NID and takes the authid from FAGDec's `self_auth.bin`. It can be
  reused as-is.
- **Vita3K** works with decrypted files directly, which makes it the fastest test loop. Always confirm on real
  hardware before a release. A crash that didn't happen in Vita3K can happen on the Vita.

## 6. Hard-won lessons from SGM

### Text
- **printf placeholders must keep their order and type.** The eboot fills in `%s`/`%d` in the Japanese order.
  If the English swaps `%s` and `%d`, the game **crashes** (an int is read as a `char*`). This was the v0.2.1
  crash, on the "material item obtained" popup. A bare `%` must be written as `%%`.
  → **Have the build check every string with printf conversions:** same sequence as the Japanese, no stray
  `%`. Fail the build on a mismatch. (SGM `tools/build_text.py`: `check_format`.)
- Also keep **game markup tags** exactly as they are: colour tags like `[g]…[/]`, and name substitutions like
  `[n:NAME]`. Check them in the build the same way.
- **Keep every non-text byte as-is.** Swap only the strings and rebuild the offset tables. Script bytecode stays
  original.
- When unsure about a line (blank or mismatched), **leave the Japanese** rather than guess. A Japanese line is
  better than a crash or the wrong text.
- Short labels (menus, buttons) must stay **on one line**. Only sentences get wrapped. SGM tells them apart by
  the Japanese length (`TABLE_SENTENCE = 12` full-width units).
- Keep a **manual override table** for strings that need hand fixes (SGM `TABLE_OVERRIDES`).
- The font may lack some characters (é, ü, —, non-breaking space…). Map them to glyphs it has (SGM `FIXUPS`).

### Font and line breaking
- SGM's font was an atlas of 20×20 cells (DXT5, Vita Morton-swizzled), with the glyph code list in the eboot.
  Latin glyphs were drawn **full width**, so English looked spaced out.
- The fix was eboot code hooks (Thumb ARM, assembled with keystone):
  1. a width table per glyph,
  2. sample only `w` pixels of each cell,
  3. advance the pen by `size*w/20`.
  The hook code went into the free space after the text segment; the segment was extended.
- The engine's line wrapping then used the real widths, so **word wrap** came almost free once the advance
  value was correct.
- For boxes that don't wrap, we **pre-wrap** in the build. The box width is estimated from the Japanese text's
  own hand-placed line breaks.
- Lines that still don't fit get an **inline scale marker** (ESC + char) that a hook reads to draw that line
  smaller.
- RE workflow (`tools/re/`): load the ELF (pyelftools) → Capstone Thumb linear sweep → find movw/movt-built
  constants (xrefs) and the callers of a function → find dead functions to reuse as code space. Find the
  glyph-draw function by following the string-render call chain from a known UI call.

### Images
- Vita textures were G1T (`GT1G`, little-endian) with DXT1/DXT5 in **Morton-swizzled** blocks. PS3 uses
  big-endian and linear blocks. The image tools (`g1t.py`, `dxt.py`) only help if GB1 uses G1T, which it
  probably doesn't, since that's a Koei Tecmo format.
- Re-encode **only the blocks you change**, and keep the entry size the same so it can be overwritten in place.

### param.sfo / home screen name
- Changing `TITLE`/`STITLE` in `param.sfo` **did not** update the LiveArea name on the Vita (it's probably cached
  in `app.db`). It's still unsolved, so don't promise it.

### Release and distribution
- **Never distribute game data.** Use a `.gitignore` **allow-list** (`*`, then `!` only the source files). Also
  block `*.bin`, `*.iso`, `LINKDATA*`-style names, and so on. Note that Windows git is case-insensitive.
- Ship **xdelta3** patches made with `-S none -A` (no secondary compression, no app header), so they work in
  Delta Patcher **and** in a browser VCDIFF decoder.
- A `checksums.txt` lists the SHA-1 of each source and patched file. Check the input before patching, so users
  get a clear error instead of a broken file.
- **Web patcher** (GitHub Pages from `docs/`): it identifies files by size and hash, applies the VCDIFF patches
  in the browser, and saves into a folder (`showDirectoryPicker`, Chrome/Edge) or as a zip (streamed, with
  CRC32). It supports patching only some files, for updates. Users liked it most. Reuse SGM `docs/patcher/`
  (`core.js`, `vcdiff.js`, `zip.js`, `app.js`) and swap only the manifest.
- One script builds everything: `make_release.py <version>` builds, makes the patches, **round-trip
  verifies** them, and writes the zip plus the web patcher's `manifest.json`.
- Release notes say **which files changed**, so users who already patched only redo those files from their
  original copies.
- Support **each game version** (SGM: 1.00 and 1.02). Only the eboot differs between versions, so patch
  offsets are kept per version.
- Python on Windows: use `sys.stdout.reconfigure(encoding="utf-8")` (the cp1252 console breaks on Japanese).
  Run scripts with `-P`, or `-I` for anything that reads untrusted files.

## 7. Code to bring over from SGM

| File | Reusable? |
|---|---|
| `scripts/decrypt_vita.ps1` | Yes, as-is (change the source folder name) |
| `tools/fself.py`, `tools/unfself.py` | Yes, as-is |
| `tools/re/*.py` (velf, disasm, xrefs, callers, deadfuncs) | Yes, as-is |
| `tools/textwrap_vita.py` | The ideas (wrapping, scale markers); tags and metrics are game-specific |
| `tools/build_text.py` `check_format` | Yes; adapt the tag syntax |
| `scripts/make_release.py` | The structure (build → xdelta → verify → zip → manifest) |
| `docs/` web patcher | Yes; new manifest, title and texts |
| `tools/linkdata.py`, `g1t*.py`, `dxt.py`, `story.py`, `font.py`, `build_font.py` | SGM/Koei Tecmo-specific, for reference only |

Tools used: VitaShell, FAGDec, rePatch, Vita3K, psvpfsparser, xdelta3 / Delta Patcher, Python 3.10+ with
Pillow, capstone, keystone-engine and pyelftools, and 7-Zip.

## 8. Translation plan (if it's a go)

1. Extract **all** text to a working format (CSV or JSON: id, Japanese, English, notes, max width).
2. Build a **terms list** from GB3's English (MS names, parts, skills, menu words), and from SGM/Gundam Reborn
   for shared series terms.
3. Translate. A machine draft is fine as a start, but **every line needs a human check**. Watch the
   placeholders and tags (checked by the build).
4. Insert, wrap, fit, then test on Vita3K and on a real Vita, then release a test version for testers.

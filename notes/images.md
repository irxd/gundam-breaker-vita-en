# UI textures with Japanese text

Checked 2026-11-21/24. Many menu labels, button hints and help lines are baked into textures (GP/ui/ui_dds/*), not
text tables. This page lists them by screen with a proposed English. **No Japanese here** (public repo): textures are
named by path, the text by its English meaning. Terms follow [terms.csv](terms.csv) (GB3 first).

## Format and tools

- **tex payload** (decompressed entry): `u16 w, u16 h` (LE, visible size, often not a power of two), format bytes
  `12 41 xx 1d` (`xx` = `20` DXT5 / BC3, `00` DXT1 / BC1; `1d` = DXT, one level, no mips on every UI texture), 4 more
  bytes that look like leftover memory (keep them), data at 0x0C. The block data covers the size **padded up to powers
  of two in both directions** (300x40 -> 512x64); true for all 1,688 GP/ui textures. Blocks are in Vita Morton order
  (y on even bits, x on odd bits; non-square = row/column of square tiles of the smaller side).
- Only DXT1 (1,085) and DXT5 (603) occur under GP/ui. Many DXT1 UI textures are opaque black-background "glow"
  images (additive blend); many DXT5 ones are labels on transparent plates.
- **Where they live**: every GP/ui texture is a member of one or more pac bundles in GxArchivedFile002.dat (1–13
  copies per path, all identical; 44 bundles hold UI textures). 1,889 of the 1,904 GP/ui members also exist as loose
  `tex` entries in GxArchivedFile000.dat (hash1 = `gdat.name_hash(path)`, identical bytes). Which copy the game reads
  is not known, so the build patches all of them (as build_text.py does for GP/text).
- [tools/tex.py](../tools/tex.py): `decode(payload) -> RGBA image`, `encode(payload, image) -> payload` (same size,
  header kept). Only 4x4 blocks whose pixels changed are re-encoded, so an untouched image gives the original bytes
  back (40/40 sampled textures byte-identical). Changed blocks use the better of an own BC1/BC3 encoder and Pillow's
  `bcn` encoder (Pillow alone gave visibly wrong blocks on glow text). Full forced re-encode of 40 samples: mean
  error under 2 per channel.
- [scripts/export_ui.py](../scripts/export_ui.py) (`python -E -P`): all GP/ui textures to `game/ui_png/<path>.png`,
  contact sheets per folder in `game/ui_png/_sheets/` (115 sheets), index `game/ui_index.tsv` (size, format, 002
  bundles, loose copy in 000). ~30 s.
- [scripts/draw_ui.py](../scripts/draw_ui.py): draws English replacements into `game/images_en/<path>.png`. One
  style so far, `glow` (gradient + scanlines + halo on black; Bahnschrift Bold Condensed). Plate labels (blue-grey
  bevelled plates), button-hint strips and blue help lines will need more styles: erase the Japanese, keep the plate
  and button icons, draw the English.
- [scripts/build_images.py](../scripts/build_images.py): injects `game/images_en/**.png` (see "Build" below).
- `game/images_en/` is git-ignored for now: the redraws are our work but derived from game art. Decide later whether
  to commit them or only commit the drawing jobs (draw_ui.py) and regenerate.

### Build

`build_text.py` rebuilds 000/002 from the dump into `build/patched/PCSG00126/masterPSP2/` (and deletes an archive it
didn't change). `build_images.py` takes those files as its base when they exist (else the dump; `--from-dump` forces
the dump), re-encodes each texture from the **original** payload in the dump, swaps every copy (002 bundles + loose
000 entry) and rewrites the archives in place (via a renamed `.base` copy, since Windows can't replace an open file).
Order: **build_text.py, then build_images.py**. Re-running build_images is idempotent; re-running build_text drops the
images, so run build_images again after it. `--out DIR` writes elsewhere (used for the proof so the text build output
wasn't touched). A later shared `build.py` could call both.

**Proof (2026-11-24)**: `rank/rank_m_00` (big orange rank, 128x64 DXT1) redrawn as `CPO` (terms: rank_name uses
CPO), `build_images.py --from-dump --out build/images_test`: 279 blocks re-encoded, 2 copies patched (bundle
`fa528904` in 002, loose `fc397bb3_52ea4fd5` in 000), each archive changed in exactly that one entry (+19 bytes,
offsets rebuilt). Decoding the texture back from both rebuilt archives gives the drawn image (mean error 3, max 43
on glow edges, DXT1 limit). **Not yet tested in Vita3K.**

## Redraw status (2026-11-25)

All 322 catalogued textures are redrawn and built; not yet tested in Vita3K. `python -E -P scripts/draw_ui.py` draws
them into `game/images_en/`, from two job modules split by style family (plus `scripts/uidraw/extra.py`, 24 jobs for
loose-only textures found later, see "Loose-only UI textures" below; run `export_tex.py --ui` first):
- `scripts/uidraw/labels.py` (+ `labels_lib.py`), 144 jobs: Game Setting row labels/values, Machine Setup and
  Customize headers and stats, weapon aptitude, Create Parts, mission result, mission-select labels and rank tabs,
  battle captions and counters, ranks, Paint, quantity headers, boosters, title/intro subtitles and cross-save texts.
- `scripts/uidraw/hints.py`, 178 jobs: every `*_key*` button strip, config help lines, BATTLE SETTING diagram,
  GUNPLA CONTROL loading screen, main menu / VR Hangar / member list, multiplayer rooms, Players' Shop.

Choices made while drawing (rank abbreviations, OK for confirm, upper-case captions: decided 2026-11-25):
- Rank abbreviations everywhere (CPO, ENS, LT, LCDR, CAPT, RADM, ADM, FADM), as in rank_name.
- Confirm button = "OK" (as the game's own English dialog_key1). Weapon categories as in terms.csv (Melee, Martial
  Arts, Two-Handed Sword).
- Counters drop the word before the number and put the unit after it ("Ends in 16 SEC", "3 LEFT").
- Battle captions in upper case, widely spaced. "Prev. Page" is the only abbreviation in the button strips.
- Left as they are: title_logo, title_gpg, grg_pnt_head_10 (no Japanese), and textures already in English.

To check on the Vita: the smallest text (quantity headers, weapon aptitude names, about 11 px cap height), the shop
banner sub-line (lighter red than the original) and plate text (slightly greyer).

## Catalogue

~322 textures with Japanese (counted from the sheets). Paths below are under `GP/ui/ui_dds/`. Button-hint strips:
keep the button icons, replace only the words. Sizes are fixed, so long English must be condensed or abbreviated.

Weapon category names: the game's own English icons (`icons/icon_s/icon_s_wep_*`) say *Saber, Double Saber, Axe,
Two-Handed Sword, Whip, Lance, Melee, Martial Arts, Rifle, Double Rifle, Long Rifle, Machine Gun, Gatling Gun,
Bazooka*. GB3 uses the same words, so terms.csv now follows them (Two-Handed Sword, Melee, Martial Arts;
decided 2026-11-24).

### Game Setting (config) — 24
| texture | English |
|---|---|
| config/config_key1 (512x32) | SELECT Default · Select · Back |
| config/config_key2 (580x32) | SELECT Default · Select · Edit Emotions · Edit Text · Back |
| config/config_normal, config_reverse (128x32, glow) | Normal / Reverse |
| config/config_head/config_head_01..09 (512x64 plates) | Vertical Camera · Horizontal Camera · Camera Sensitivity · Vibration · BGM Volume · SE Volume · VOICE Volume · Brightness · Auto Near/Far Switch |
| config/config_help/config_help_01..08 (512x32, blue) | Sets vertical (up/down) camera control · Sets horizontal (left/right) camera control · Sets right stick sensitivity · Sets controller vibration · Adjusts music volume · Adjusts sound effect volume · Adjusts voice volume · Adjusts screen brightness |
| config/config_type/config_pad (840x320) | BATTLE SETTING controller diagram: Hold + □: Ranged Attack A · Hold + △: Ranged Attack B · Switch Option Equipment · Move · With shield: Guard · Part knocked off: Recapture Beam · Hold + △/□/○: EX-Action · Use Option Equipment · Jump · Hold: Boost Dash · Hold R +: Step · Camera / Change Target · Open Menu |
| config/config_type/config_pad_a (240x48) | Melee A / Ranged A (by distance) · Melee B / Ranged B (by distance) |
| config/config_type/config_pad_b (240x48) | Melee Attack A · Melee Attack B |

The tab plates (CONTROL SETTINGS…) are already English.

### Battle controls loading screen (GUNPLA CONTROL) — 22
`load/load_help/*` (the pad picture and title are English):
awake Awakening · camera Reset Camera · crcl Use Option Equipment · cross Switch Option Equipment · flick
Flick left/up/down: Radio Chat (multiplayer only) · lock Lock-on On/Off · ls Move · r_0 With shield: Guard / Part
knocked off: Recapture Beam · r_1/2/3 EX-Action 1/2/3 · rs Camera / Change Target · sq_1 Attack A · sq_2 Melee
Attack A · sq_3 Ranged Attack A · start Open Menu · tri_1 Attack B · tri_2 Melee Attack B · tri_3 Ranged Attack B ·
x_1 Jump · x_2 Hold: Boost · x_3 Step.

### Pause / map — 5
`hud/hud_pause/hud_pause_key1..5`: Resume · Leave Party · Retire · Select · SELECT Settings. (MISSION AREA MAP /
TREASURE LIST are English.)

### Battle HUD — 18
| texture | English |
|---|---|
| telop/telop_txt/telop_txt_start (512x32) | Commence operations! (MISSION START subtitle) |
| telop/telop_txt/telop_txt_ace / _next / _over / _failed | Enemy ace sighted! · Proceed to the next area · Time limit exceeded · Mission failed (128x32) |
| count/count_head_01..04 (128x64 glow) | Until sortie · Until re-sortie · Until end · Until transfer |
| count/count_remain (256x64) | word left, unit right, game draws the number between: "[n] sec left" layout needs a rethink (e.g. "LEFT … SEC") |
| count/count_skip (256x64) | SELECT Hold to end now |
| count/count_pena (512x64, red) | ⚠ Re-sortie incurs a penalty |
| hud/hud_dlcm/hud_dlcm_nav1, nav2, success | Capturing enemy base · Restoring Durability · Base [letter] captured! (gap for the letter icon; DLC Area Raid) |
| action/action_skip (132x48) | START Skip |
| meslog/meslog_key1 | Scroll Log |

### Mission select — 14
msel/msel_tab_00..07 (128x64 plates): All · Ensign · Lieutenant · Lt. Cmdr. · Captain · Rear Adm. · Admiral · Fleet Adm. ·
msel/msel_head1..5 (112x36): Clear Condition: · Failure Condition: · Rare Runner: · Time Limit: · Decal: (very
narrow: may need a smaller font or "Clear:", "Fail:") · msel/msel_key1: Select · OK · Back.

### Ranks — 18
rank/rank_m_00..07 (128x64 glow): CPO · Ensign · Lieutenant · Lt. Cmdr. · Captain · Rear Adm. · Admiral · Fleet Adm.
rank/rank_s_00..09 (64x64): same order, s_08/s_09 repeat Admiral / Fleet Admiral (abbreviate: CPO, ENS, LT, LCDR,
CAPT, RADM, ADM, FADM). **rank_m_00 done (proof).**

### Mission result — 12
result/result_key1 Skip · key2 Next · key3 Select · Take All · Sell All · Take · Sell · result_pena_txt Spoils are
confiscated based on the number of retries · result_rep_base header Mission Report · result_rep_time Elapsed Time ·
result_rep_retry Retries · result_rep_reward GP Earned · result_rep_gp GP Held · result_trsr_base header Spoils
(subtitle TREASURE LIST) · result_trsr_os Req. OS Ver. · result_trsr_sell Trade Value.

### Main menu, VR Hangar, member list — 29
menu/menu_head_01..08 (412x64 plates): Single Player · Multiplayer (Ad Hoc) · Multiplayer (Online) · Machine Setup ·
Players' Shop · Mail · Upload Save Data · Game Settings. menu/menu_key1: SELECT Check Invites · Select · OK · Back.
mobile/mobile_btn_01..06 (VR Hangar side menu, 512x64): Invite Friends · Room Settings · Disband Party · Mail ·
Settings · Leave Hangar.
mlist/mlist_key1 SELECT Member List Actions · mlist_key2 Select · OK · Back · mlist_prof_1..4 Profile · Mute ·
Unmute · Kick · mlist_stat_01..08 Ready to Sortie · Preparing · Customizing · Painting · Building Parts · Choosing
Mission · Choosing · In Event.

### Machine Setup (grg_set) — 18
grg_set/grg_set_name Gunpla Name · grg_set_setting Setting · grg_set_spec Machine Specs + stat column (Durability ·
Physical Armor · Beam Armor · Shield Durability · Melee Power · Ranged Power · Capacity · Equip Cost) · grg_set_ex
EX-Action · grg_set_opt Option Equipment · grg_set_module Enhancement Module.
grg_set/grg_set_key/key1..5: Back · OK · Load Blueprint · Select / Save Blueprint · SELECT Toggle View / Rotate/Zoom.
grg_set/grg_set_menu/_01..05: Create Parts · Customize · Gunpla Paint · Edit Gunpla Name · Parts Stock.
grg_set/grg_set_plan/grg_set_plan_key Select · OK · Back; grg_set_plan_noimage "NO IMAGE / Updated by cross-save, so
there is no Gunpla image".

### Customize (grg_cstm) — 26
grg_cstm/grg_cstm_apt header Weapon Aptitude + 11 types (Saber, Axe, Two-Handed Sword, Whip, Lance, Martial Arts /
Rifle, Long Rifle, Machine Gun, Gatling Gun, Bazooka) · grg_cstm_spec + grg_cstm_spec_01..08 (Machine Specs + the 8
stats) · grg_cstm_caution1 "Equip Cost exceeds Capacity. You can't sortie like this." · grg_cstm_help_2/3/4 Uses ·
Charge Time · Power · grg_cstm_key1/key2 SELECT Toggle View · Rotate/Zoom · Select · Sort · Put in Stock · OK · Back
(key2 = Sort/Stock greyed) · grg_cstm_list3 Remove Equipment · grg_cstm_sublist Option List.
grg_cstm/grg_cstm_sort/_01..09: By Acquisition · By Name · By Durability · By Melee Aptitude · By Capacity · By
Shield Durability · By Category Attack · By Category · By Ranged Aptitude.

### Create Parts (grg_build) — 6
grg_build_finish_key1 Next · grg_build_finish_op Option List · grg_build_finish_spec Parts Specs + 8 stats ·
grg_build_key1 START Build All · Select · Toggle Lock · OK · Back · grg_build_key2 SELECT Toggle Sharp Nippers + key1 ·
grg_build_no "You don't have the required Runner".

### Paint (grg_pnt) — 11
grg_pnt_key1/2: SELECT Default · Rotate/Zoom · Select · Save Color Set / Save Color · Load Color Set / Load Color · OK ·
Back. grg_pnt/grg_pnt_head/_01..09: Pattern · Color Set · Decal · Gloss · Chipping · Airbrush · Weathering · Scratches
· Foot Grime (_10 "?????" stays).

### Headers / counters — 12
header/header_remind ⚠ We're waiting for you to get ready!! · header/header_quantity/_01..11 (188x32, red):
Runners · Head Parts · Body Parts · Arm Parts · Leg Parts · Backpack Parts · Shields · Melee Weapons · Ranged Weapons ·
Modules (all "held") · Parts Stock.

### Multiplayer rooms (room) — 58
room_key1 Select · OK · Back; room_key2 + Search Again · room_list_head1..3 Member List · Room Comment · Room Status ·
room_status1..3 Open Room · Waiting in Hangar · On a Mission · room_btn/_01..05 Search Rooms · Create Room · Start
Search · Create Room · Change Room Settings · room_set_head/_01..06 Room Name · Search Target · Play Style · Password ·
Room Comment · Platform · room_set_style: pass_off None · pass_on On · plat_01 PS Vita Only · rank_00 Any Rank ·
rank_01 Similar Rank · rank_02 Same Rank Only · style_00 Any · 01 Clear Missions! · 02 Collect Items! · 03 Ace Points! ·
04 Fun for Everyone! · 05 Looking for Friends! · 06 Voice Chat Welcome! · room_list_style/_01..07 the same 7 styles
(small). room_set_help/_01..19 (two-line blue help): 01 Up to 16 characters. If empty, your online ID is used · 02
Up to 16 characters. Optional · 03 Allow any rank difference · 04 Search players within ±1 rank of you · 05 Search
only players of your rank · 06 Search rooms with any rank · 07 Search rooms limited to ±1 rank · 08 Search rooms
limited to the same rank · 09 Sets the play style. *Voice chat not available · 10 Up to 8 characters. Optional · 11
Up to 80 characters. Optional · 12 Turns the room password on/off · 13 Sets whether a password is used · 14 Room for
PS Vita players only · 15 Room open to all players · 16 Search rooms for PS Vita players only · 17 Search rooms open
to all players · 18 PS Vita players only. Re-create the room to change · 19 Open to all players. Re-create the room
to change.

### Players' Shop — 27
shop_no None Found · shop_price_0_l / _0_s Free · shop_menu/_01..05 Gunpla · Items · Sell Parts · Sell Runners ·
Receive Gift (English subtitles exist) · shop_key/key1..9 OK/Back · Exchange All · SELECT Toggle View · Rotate ·
Select · Sort · Exchange/Back · Get/Back · Receive/Back · Select · Exchange All Stock · Take Out/Back · (key9 greyed) ·
shop_detail/shop_banner_01..04 New Products! (more coming) · Contest (eligible products) · Limited Time! (campaign) ·
Limited Time! (price down) · shop_detail_caution *This kit has no weapon parts · shop_detail_head_01..03 Contents: ·
Released: · Period: · shop_sort/_01..02 By Arrival · Recently Added.

### Mail — 5
mail/mail_key/mail_key_crcl Next Page · _cross Select · _rs Scroll Text · _tri Previous Page · _x Back.

### Title / save data — 8 (+2 optional)
title/title_cross_help Select the data to load · title_cross_txt01..06 Creating new data · No data · Failed to get
data · Please sign in · Save data info not retrieved · Data version mismatch · title_copyright ©SOTSU·SUNRISE /
©SOTSU·SUNRISE·TV TOKYO (legal line; romanise) · dialog/dialog_cross_5min PSN limits rapid repeated access; please
wait a while before trying again · dialog/dialog_key3 Select · OK · Back. Optional: title_logo (katakana subtitle
under the English logo), title_gpg (small caption by the QR code): leave.

### Intro subtitles — 3
subtitle/subtitle_01..03 (648x88, white): GGF's amazing exhibits · Behind it all is the latest hologram technology! ·
Using it, Odaiba itself becomes a battlefield where Gundams fight!!

### Boosters — 5
booster/bst_name_01..03 Luck Booster · EXP Booster · Sharp Nippers · hngr_bst_remain / remain2 "[n] left" word and
unit around a number (needs layout check).

## Screenshot strings: where they are

Found: settings rows -> config_head_01/02/03/05/06/07/09; value Normal -> config_normal; row descriptions ->
config_help_*; BATTLE SETTING diagram -> config_pad (+ pad_a/pad_b); Default/Select/Back/OK hints -> *_key* strips
(config_key1/2, msel_key1, grg_set_key*, …); Toggle View, Rotate/Zoom -> grg_cstm_key1, grg_set_key5, grg_pnt_key*;
Next -> result_key2, grg_build_finish_key1; Resume, Settings (pause) -> hud_pause_key1/key5; Edit Emotions/Edit Text ->
config_key2; VR Hangar Settings / Leave Hangar -> mobile_btn_05/06; All -> msel_tab_00; Clear/Failure Condition,
Rare Runner -> msel_head1/2/3; Gunpla Name, Setting, Machine Specs, stat names -> grg_set_name/_setting/_spec
(also grg_cstm_spec_*, grg_build_finish_spec); Weapon Aptitude + weapon types -> grg_cstm_apt; Option Equipment,
EX-Action, Enhancement Module -> grg_set_opt/_ex/_module; big rank -> rank_m_00; Mission Report, Elapsed Time,
Retries, GP Earned, GP Held -> result_rep_*; Until end / left / sec -> count_head_03, count_remain; Hold to end now ->
count_skip; Commence operations! -> telop_txt_start; GUNPLA CONTROL labels -> load/load_help/*; pause map buttons ->
hud_pause_key*.

Not in any texture: "not equipped" (it is a UTF-8 string in the eboot, separate job).

## Loose-only UI textures and textures outside GP/ui (checked 2026-11-25)

**Tools.** [scripts/export_tex.py](../scripts/export_tex.py) (`python -E -P`) decodes any `tex` (DXT1/DXT3/DXT5,
mipmapped, and the few 32-bit RGBA ones; level 0 only) to `game/tex_png/<path>.png` with contact sheets in
`game/tex_png/_sheets/` and an index `game/tex_index.tsv`. `--loose` adds the 000 entries whose name is unknown as
`_loose/<hash1>`; normal/specular/control/environment maps are skipped unless `--all-maps`. A full run takes ~20 min.
`--ui` only writes the loose-only UI textures listed in its `LOOSE_UI` table to `game/ui_png/` (where draw_ui.py looks
for originals; ~15 s). Header format bytes `12 4L xx Ld`: L = mip levels, xx = 00 DXT1 / 10 DXT3 / 20 DXT5;
first byte 0x64 = 32-bit RGBA.

**Loose-only textures.** 7,892 of the 9,672 loose `tex` entries in 000 match no pac member name. Most are
Gunpla/map textures, but some are UI textures that exist **only** in 000 (no 002 copy). Names were recovered from the
eboot's strings (`title/title_00..05`, `dialog/leadbanner`, `title_demo/*`, hud_map area maps) and by varying the last
one or two characters of known GP/ui paths (`rank_m_08/09`, `grg_cstm_spec_09..17`, `grg_cstm_help_1`,
`result_key4`, `icon_s_module_*`, `icon_s_option_*`, `msel_gp`); the rest keep `_loose/<hash1>`.
`build_images.py` now patches these in 000 (by name_hash(path), or the hash for `_loose/<hash1>`).

Redrawn (jobs in [scripts/uidraw/extra.py](../scripts/uidraw/extra.py), 24 textures, not yet tested in game):
| texture | English |
|---|---|
| title/title_00 (960x544) | piracy notice before the logos: Notice / Distributing game software over the Internet without the rights holder's permission, and downloading it while knowing that it has been distributed illegally, are strictly prohibited by law. / We ask for your understanding and cooperation. |
| dialog/leadbanner (800x480) | DLC store prompt: Buy the add-on "Giga Break Mission Pack" / New mobile suits join the fight in / new missions - play them now! · ◯ PlayStation®Store · ✕ Cancel (Japanese lines removed by filling from the surrounding glow) |
| rank/rank_m_08, rank_m_09 | ADM, FADM (copies of rank_m_06/07) |
| grg_cstm/grg_cstm_spec/grg_cstm_spec_09..14 | Option 1..6 Power |
| grg_cstm/grg_cstm_spec/grg_cstm_spec_15..17 | EX △/□/◯ Power (the "EX" and the symbol are kept) |
| grg_cstm/grg_cstm_help_1 | Carried (option equipment's carried count; help_2..4 are Uses, Charge Time, Power) |
| result/result_key4 | Select · Take All · Sell All · Take · Sell (like result_key3) |
| title_demo/title_copyright | © SOTSU · SUNRISE / © SOTSU · SUNRISE · MBS (demo build; romanised like title_copyright) |
| _loose/00d9cea8 (1280x720) | PAUSE screen subtitle: GAME PAUSED (blue PAUSE kept) |
| _loose/49757e76 | L2 + R2 Free-Word Chat |
| _loose/c1dad43f | (hand icon) Flick right to close |
| _loose/d16ee459, d16ee462 | Melee Weapons / Ranged Weapons headers (orange English subtitles kept) |
| _loose/fa959a56..58 | Runners Held · Parts Held · Modules Held |

Left as they are: title_demo/title_logo and the small red logo `_loose/b8693ec2` (game logo, see below);
`_loose/2bdf1aac` (white debug placeholder with one kanji and "TOP"); `_loose/9e855617/618` (character portraits
stamped SAMPLE); title_01..05 (publisher/middleware logos, no Japanese); the English ones (module/option icons,
INFORMATION CONSOLE, GUNPLA HANGAR 01–04, READY, PREPARATION, area names, NEW GAME/CONTINUE/OPTIONS/PRESS START).

**Outside GP/ui (pac members in 001/002), all clean of UI text:**
- GP/effect (233): no text except `ef_t_enm_pg_kanji_01`, the kanji of a Master Gundam special attack's name, as in
  the anime: left (in-universe art).
- GP/map (417 colour maps of 12 areas): only real-world-style props: paint and marker labels and Gunpla instruction
  sheets on the b04 desk stage (`b04_ink01/02_col`, `b04_obj02_col`), building signage (`b01_dcity01_col`, English).
  Left as they are (like decals).
- GP/model (14,701 colour/emission maps of 992 models; sampled through the identical loose copies and the gimmick
  `gmk_*` textures), GP/preset (2,705 Gunpla preset textures), GP/texture (black, white, fever_ground): no UI text.
  Gunpla markings are part of the kit art. Some unused/placeholder part textures are white with a red kanji meaning
  "provisional"; they are left (not expected to be seen).
- Loose `_loose/*` sheets were looked at after filtering out normal maps, specular maps and flat textures.

**GP/ui sheets that had only been skimmed**, now looked at at full size: hud/* (ace, awake, bonus, boss, chat,
damage, drop, enemy, ex, info, lock, mes, npc, obj, range, sight, status, hud_face, sub, touch), hud_map (all areas
and icons), icons (drop, icon_l, icon_s, icon_progress), ace_medal, num, msel_map, load_scan_bg, meswin, etc: no
Japanese.

**Logo (title_logo, title_gpg; also title_demo/title_logo, _loose/b8693ec2).** The main logo is the English
"GUNDAM BREAKER" wordmark with a small katakana reading under it, the way the Japanese packaging shows it; title_gpg
is the QR code with the Gundam Perfect Games caption and URL. Recommendation: keep all of them. The katakana is part
of the official logo (like a subtitle on the box art), and redrawing a logo risks looking off. If wanted later, the
only safe change is erasing the katakana line under the wordmark, nothing else.

## Not covered yet

- Nothing tested in Vita3K yet: which copy (002 bundle or 000 loose) the game reads, and whether a re-encoded
  texture shows correctly. The loose-only textures above only exist in 000, so 000 must be read for them at least.

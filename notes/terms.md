# Terms and naming conventions

The glossary itself is [terms.csv](terms.csv) (`ja, en, category, status, notes`). This page has the rules that apply
across many names.

## Status values in terms.csv

| status | meaning |
|---|---|
| `gb3` | Found word for word in the Gundam Breaker 3 English (Asia) text. Use it. |
| `official` | Standard English franchise name (Bandai/Sunrise), but not seen in GB3. Confident. |
| `draft` | A suggestion with no official source. Change freely, but change it everywhere. |
| `ok` | Checked and agreed. Use exactly. |

Source: the GB3 Vita English dump (PCSH10042, Asia: English + Korean, no Japanese text tables), checked
2026-11-08. Its text was searched for each English name; there is no direct Japanese-to-English table, so a `gb3`
row means "GB3 writes it this way", matched by meaning. How to read GB3: [formats.md](formats.md#gundam-breaker-3).
GB3 uses full-width （）, but we keep ASCII `()`.

## Rules

- **Grades** stay as they are: `HG`, `MG`, `PG`, `1/144`, `1/100`, `1/60`. Keep the space after the grade
  (`HG Gundam Head`).
- **Part names** = grade + MS + slot: `HG ザクⅡヘッド` → `HG Zaku II Head`. Slots are singular as in GB3
  (`Head`, `Body`, `Arm`, `Leg`, `Backpack`): see `slot` rows in terms.csv.
- **専用 (personal custom)** is a possessive, as in GB3: `シャア専用ザクⅡ` → `Char's Zaku II`,
  `ギラ・ドーガ（レズン専用機）` → `Rezin Schnyder's Geara Doga`.
- **【…】 variants** use the official name where one exists (`ストライクガンダム【エール】` → `Aile Strike Gundam`),
  otherwise parentheses without "Equipped", as in GB3: `【ミサイル・ポッド装備】` → `(Missile Pod)`.
  `【U】`/`【D】` are always written in full: `(Unicorn Mode)`/`(Destroy Mode)`, also in part names (decided).
- **Runners**: `プラモランナー` and `ランナー` are both `Runner`; `ガンプラランナー` is `Gunpla Runner` (decided).
- **（EW）** etc. keep the parentheses: `(EW)`. Colour variants use the GB3 name where there is one
  (`ガンダムMk-Ⅱ（黒）` → `Gundam Mk-II Titans`), otherwise parentheses: `(Black)`.
- **Weapon owner in parentheses** stays: `ビーム・サーベル（ジム）` → `Beam Saber (GM)`. GB3 also writes owner-named shields
  this way: `ジム・シールド` → `Shield (GM)`, `ν・シールド` → `Shield (Nu)`, `Mk-Ⅱ・シールド` → `Shield (Mk-II AEUG)`.
- **Roman numerals** Ⅱ/Ⅲ become `II`/`III` (ASCII). Greek letters are spelled out: `ν` → `Nu` (`Nu Gundam`,
  `Hi-Nu Gundam`, `Shield (Nu)`), `∀` → `Turn A` (decided).
- **Button icons** (`⑪ ⑫ ⑬ ⑭ ⑮ ⑯ ⑲ ⑳`, drawn as Vita buttons) are copied as they are. The build checks this.
- **Markup** (`<br>`, `<cNN>…</c>`, `\n`) is copied as it is. Colour tags keep their order.
- **Ranks** use the Navy-style ladder of the UC Earth Federation (decided): Chief Petty Officer, Ensign,
  Lieutenant, Lieutenant Commander, Captain, Rear Admiral, Admiral, Fleet Admiral.
- **Developer leftovers** (e.g. `出たらバグです…`, `使用しません 旧：…`, `ハンガーでスタートボタン押すと出る`) are never
  shown: leave them untranslated.

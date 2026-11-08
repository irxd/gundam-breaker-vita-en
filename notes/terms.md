# Terms and naming conventions

The glossary itself is [terms.csv](terms.csv) (`ja, en, category, status, notes`). This page has the rules that apply
across many names.

## Status values in terms.csv

| status | meaning |
|---|---|
| `official` | Standard English name used by Bandai/Sunrise for the franchise (MS, weapons, factions). Confident. |
| `gb3?` | Believed to be the Gundam Breaker 3 English (Asia) term. **Check against GB3** before relying on it. |
| `draft` | A suggestion with no official source. Change freely, but change it everywhere. |
| `ok` | Checked and agreed. Use exactly. |

Best source for `gb3?`: a dump of Gundam Breaker 3 English (Vita, PCSG00xxx Asia). It's the same developer and
probably the same engine, so `tools/gdat.py` / `pac.py` / `dt2.py` may read its text directly. Until then, nothing
is confirmed against GB3.

## Rules

- **Grades** stay as they are: `HG`, `MG`, `PG`, `1/144`, `1/100`, `1/60`. Keep the space after the grade
  (`HG Gundam Head`).
- **Part names** = grade + MS + slot: `HG ザクⅡヘッド` → `HG Zaku II Head`. Slots: see `slot` rows in terms.csv.
- **専用 (personal custom)**: `シャア専用ザクⅡ` → `Char's Zaku II`. `（レズン専用機）` → `(Rezin Schnyder Custom)`.
- **【…】 variants** use the official name where one exists (`ストライクガンダム【エール】` → `Aile Strike Gundam`),
  otherwise parentheses: `【…装備】` → `(… Equipped)`. `【U】`/`【D】` are `(Unicorn Mode)`/`(Destroy Mode)` in
  descriptions; in part names, where space is tight, `(U)`/`(D)` (draft, decide once box widths are known).
- **（EW）, （黒）** etc. keep the parentheses: `(EW)`, `(Black)`.
- **Weapon owner in parentheses** stays: `ビーム・サーベル（ジム）` → `Beam Saber (GM)`.
- **Roman numerals** Ⅱ/Ⅲ become `II`/`III` (ASCII). Greek `ν` and `∀` are in the font and may stay
  (`ν Gundam`), but see the `∀` row.
- **Button icons** (`⑪ ⑫ ⑬ ⑭ ⑮ ⑯ ⑲ ⑳`, drawn as Vita buttons) are copied as they are. The build checks this.
- **Markup** (`<br>`, `<cNN>…</c>`, `\n`) is copied as it is. Colour tags keep their order.
- **Ranks** follow the UC Earth Federation convention used in English Gundam material.
- **Developer leftovers** (e.g. `出たらバグです…`, `使用しません 旧：…`, `ハンガーでスタートボタン押すと出る`) are never
  shown: leave them untranslated.

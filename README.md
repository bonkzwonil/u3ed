# u3edit

Terminal savegame editor for **Ultima III: Exodus** (DOS / Ultima Trilogy 1989).
Pure Python + [Textual](https://textual.textualize.io/). No Windows, no Wine.

## Usage

```sh
uv run u3edit /path/to/ultima3          # TUI
uv run u3edit --dump /path/to/ultima3   # print characters and exit
```

The directory must contain `ROSTER.ULT` and `PARTY.ULT`; `SOSARIA.ULT` (moon phases) is optional.
File-name case doesn't matter.

Work on a copy of your save directory. On the first save, the editor keeps every
original file as `*.ult.bak`.

| Key | Action |
|---|---|
| `↑`/`↓` | select roster slot (★ = in active party) |
| `Tab` | move between fields |
| `Ctrl+S` / `F2` | save |
| `F3` | heal (status Good, HP = max HP) |
| `F4` | revert selected character to file contents |
| `Ctrl+Q` | quit (asks if unsaved) |

Editable: name, status, race, class, gender, stats, MP/HP/max HP/exp, food, gold, gems,
keys, powders, torches, armour/weapon counts plus worn/readied, marks & cards; party
transport, moves, position, moon phases.

## How party members are handled

While a party is formed, the game uses the copies in `PARTY.ULT`, and `ROSTER.ULT`
can be stale. Selecting a roster slot that belongs to the active party edits the
`PARTY.ULT` record. On save, party records are mirrored back into their roster slots.

## File format (DOS)

All numbers are BCD, **little-endian** (HP 150 = `50 01`), unlike the Apple II original.

Character record (64 bytes; `ROSTER.ULT` = 20 records, `PARTY.ULT` = 18-byte header + 4 records):

| Off | Size | Field |
|---|---|---|
| 00 | 10 | name, NUL-padded |
| 0E | 1 | marks/cards bits: Love, Sol, Moon, Death, Force, Fire, Snake, Kings (bit 0..7) |
| 0F | 1 | torches |
| 10 | 1 | `FF` = in party |
| 11 | 1 | status `G P D A` |
| 12-15 | 4 | Str Dex Int Wis |
| 16/17/18 | 1 | race / class / gender letter |
| 19 | 1 | MP |
| 1A/1C/1E | 2 | HP / max HP / exp |
| 20 | 1 | sub-morsels |
| 21/23 | 2 | food / gold |
| 25-27 | 1 | gems, keys, powders |
| 28 | 1 | worn armour index, then 29-2F armour counts |
| 30 | 1 | readied weapon index, then 31-3F weapon counts |

Party header: `00` transport (`3F` foot, `0A` horse, `0B` ship), `03` moves (4 bytes),
`07` party size, `08/09` x/y, `0A` roster numbers (1-based) of party slots.
Moons: `SOSARIA.ULT` offset `0x1224` (left/right phase 0-7).

Sources: [Ultima Codex: Ultima III internal formats](https://wiki.ultimacodex.com/wiki/Ultima_III_internal_formats),
verified against real DOS saves (`tests/fixtures`).

## Development

```sh
uv run pytest
```

"""Ultima III savegame editor."""

from __future__ import annotations

import argparse
import sys

from .format import ARMOR, MARKS, WEAPONS, SaveGame


def dump(save: SaveGame) -> None:
    print(f"Party: {save.party_size} members, roster #{save.party_order}, "
          f"pos {save.position}, moves {save.moves}, moons {save.moons}")
    for slot in range(20):
        c = save.roster_char(slot)
        if c.empty:
            continue
        if slot + 1 in save.party_order:
            c = save.party_char(save.party_order.index(slot + 1))
        marks = [m for i, m in enumerate(MARKS) if c.marks & 1 << i]
        print(f"{slot + 1:2} {'*' if c.in_party else ' '} {c.summary()}  "
              f"Str {c.get('str')} Dex {c.get('dex')} Int {c.get('int')} Wis {c.get('wis')} "
              f"MP {c.get('mp')} Exp {c.get('exp')} Food {c.get('food')} Gold {c.get('gold')} "
              f"Armor {ARMOR[c.armor] if c.armor < len(ARMOR) else c.armor} "
              f"Weapon {WEAPONS[c.weapon] if c.weapon < len(WEAPONS) else c.weapon} "
              f"Marks {','.join(marks) or '-'}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="u3edit", description="Ultima III (DOS) savegame editor")
    parser.add_argument("directory", nargs="?", default=".",
                        help="game directory containing ROSTER.ULT and PARTY.ULT")
    parser.add_argument("--dump", action="store_true", help="print characters and exit")
    args = parser.parse_args()
    try:
        save = SaveGame(args.directory)
    except (OSError, ValueError) as exc:
        sys.exit(f"u3edit: {exc}")
    if args.dump:
        dump(save)
        return
    from .app import U3EditApp

    U3EditApp(save).run()

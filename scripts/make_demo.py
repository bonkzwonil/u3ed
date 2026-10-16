"""Build the demo save in tests/fixtures/demo (used for README screenshots).

A party of CRPG celebrities, built on top of a real DOS save so all
unknown bytes are authentic.
"""

from pathlib import Path

from u3edit.format import (
    ARMOR, PARTY_SLOTS, RECORD_SIZE, ROSTER_SLOTS, WEAPONS, SaveGame,
)

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "tests/fixtures/played"
DST = ROOT / "tests/fixtures/demo"

# name, race, class, gender, status, str dex int wis, mp, hp, maxhp, exp,
# food, gold, gems, keys, powders, torches, marks, worn armour, readied weapon
CAST = [
    ("Iolo",      "H", "L", "M", "P", (45, 60, 40, 35), 20, 87, 412, 1873, 812, 2240, 3, 2, 1, 4, 0b10000101, 3, 9),
    ("Shamino",   "E", "R", "M", "G", (40, 75, 50, 45), 25, 545, 545, 2214, 905, 1312, 5, 3, 2, 6, 0b10000111, 5, 10),
    ("Dupre",     "H", "P", "M", "G", (75, 45, 25, 60), 30, 790, 790, 2511, 677, 851, 2, 1, 0, 2, 0b10010101, 6, 14),
    ("Werdna",    "F", "W", "M", "G", (25, 50, 99, 30), 99, 302, 330, 3150, 1203, 9999, 9, 4, 5, 8, 0b11111111, 1, 1),
    ("Minsc",     "H", "B", "M", "G", (75, 50, 15, 15), 0, 680, 680, 980, 340, 120, 0, 0, 0, 3, 0b00000000, 4, 7),
    ("Boo",       "F", "T", "O", "A", (10, 70, 30, 20), 0, 0, 120, 210, 25, 3, 0, 1, 0, 0, 0b00000000, 1, 1),
    ("Trebor",    "D", "F", "M", "D", (75, 40, 20, 20), 0, 0, 640, 1420, 210, 450, 1, 0, 0, 1, 0b10000000, 4, 6),
    ("Elminster", "E", "W", "M", "G", (20, 55, 95, 40), 75, 260, 260, 1777, 500, 3333, 6, 2, 3, 5, 0b00000100, 1, 1),
]
PARTY = [1, 2, 3, 4]  # roster numbers of the active party


def build() -> None:
    save = SaveGame(SRC)
    template = save.party_char(0).raw
    save.roster[:] = bytes(RECORD_SIZE * ROSTER_SLOTS)
    for slot, (name, race, klass, gender, status, stats, mp, hp, maxhp, exp, food, gold,
               gems, keys, powders, torches, marks, armor, weapon) in enumerate(CAST):
        c = save.roster_char(slot)
        save.roster[slot * RECORD_SIZE : (slot + 1) * RECORD_SIZE] = template
        c.name = name
        c.race, c.klass, c.gender, c.status = race, klass, gender, status
        for key, value in zip(("str", "dex", "int", "wis"), stats):
            c.set(key, value)
        for key, value in (("mp", mp), ("hp", hp), ("maxhp", maxhp), ("exp", exp),
                           ("food", food), ("submorsels", 0), ("gold", gold), ("gems", gems),
                           ("keys", keys), ("powders", powders), ("torches", torches)):
            c.set(key, value)
        c.marks = marks
        for i in range(1, len(ARMOR)):
            c.set(f"armor{i}", 1 if i in (1, armor) else 0)
        for i in range(1, len(WEAPONS)):
            c.set(f"weapon{i}", 1 if i in (1, weapon) else 0)
        c.armor, c.weapon = armor, weapon
        c.in_party = slot + 1 in PARTY
    save.party[0x0A : 0x0A + PARTY_SLOTS] = bytes(PARTY)
    save.party[0x07] = len(PARTY)
    for i, number in enumerate(PARTY):
        base = 0x12 + i * RECORD_SIZE
        save.party[base : base + RECORD_SIZE] = save.roster_char(number - 1).raw
    save.moves = 31337
    save.position = (42, 23)
    DST.mkdir(exist_ok=True)
    for name, data in save.files().items():
        (DST / name).write_bytes(data)


if __name__ == "__main__":
    build()

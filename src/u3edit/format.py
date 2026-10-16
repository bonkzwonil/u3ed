"""Ultima III (DOS) save file formats: ROSTER.ULT, PARTY.ULT, SOSARIA.ULT.

All edits happen in place on the raw bytes, so unknown fields survive a
round trip untouched. Multi-byte numbers are BCD, stored little-endian
(HP 150 is ``50 01``).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

RECORD_SIZE = 0x40
ROSTER_SLOTS = 20
ROSTER_SIZE = RECORD_SIZE * ROSTER_SLOTS
PARTY_HEADER = 0x12
PARTY_SLOTS = 4
PARTY_SIZE = PARTY_HEADER + RECORD_SIZE * PARTY_SLOTS
SOSARIA_SIZE = 4648
MOON_OFFSET = 0x1224
NAME_LEN = 10

STATUS = {"G": "Good", "P": "Poisoned", "D": "Dead", "A": "Ashes"}
RACES = {"H": "Human", "E": "Elf", "D": "Dwarf", "B": "Bobbit", "F": "Fuzzy"}
CLASSES = {
    "F": "Fighter", "C": "Cleric", "W": "Wizard", "T": "Thief", "P": "Paladin",
    "B": "Barbarian", "L": "Lark", "I": "Illusionist", "D": "Druid", "A": "Alchemist",
    "R": "Ranger",
}
GENDERS = {"M": "Male", "F": "Female", "O": "Other"}
MARKS = ["Love", "Sol", "Moon", "Death", "Force", "Fire", "Snake", "Kings"]
# Index 0 is "nothing worn/readied"; counts exist for indices 1..n.
ARMOR = ["Skin", "Cloth", "Leather", "Chain", "Plate", "+2 Chain", "+2 Plate", "Exotic"]
WEAPONS = [
    "Hands", "Dagger", "Mace", "Sling", "Axe", "Bow", "Sword", "2-H Sword",
    "+2 Axe", "+2 Bow", "+2 Sword", "Gloves", "+4 Axe", "+4 Bow", "+4 Sword", "Exotic",
]
TRANSPORT = {0x3F: "On foot", 0x0A: "Horse", 0x0B: "Ship"}


def bcd_decode(data: bytes | bytearray) -> int:
    value = 0
    for byte in reversed(data):
        value = value * 100 + (byte >> 4) * 10 + (byte & 0x0F)
    return value


def bcd_encode(value: int, size: int) -> bytes:
    limit = 10 ** (2 * size) - 1
    if not 0 <= value <= limit:
        raise ValueError(f"{value} out of range 0..{limit}")
    out = bytearray()
    for _ in range(size):
        lo, value = value % 10, value // 10
        hi, value = value % 10, value // 10
        out.append(hi << 4 | lo)
    return bytes(out)


@dataclass(frozen=True)
class Field:
    """A numeric BCD field inside a 64-byte character record."""

    key: str
    label: str
    offset: int
    size: int = 1

    @property
    def max(self) -> int:
        return 10 ** (2 * self.size) - 1


STATS = [
    Field("str", "Strength", 0x12),
    Field("dex", "Dexterity", 0x13),
    Field("int", "Intelligence", 0x14),
    Field("wis", "Wisdom", 0x15),
]
VITALS = [
    Field("mp", "Magic", 0x19),
    Field("hp", "Hit points", 0x1A, 2),
    Field("maxhp", "Max HP", 0x1C, 2),
    Field("exp", "Experience", 0x1E, 2),
]
GOODS = [
    Field("food", "Food", 0x21, 2),
    Field("submorsels", "Sub-morsels", 0x20),
    Field("gold", "Gold", 0x23, 2),
    Field("gems", "Gems", 0x25),
    Field("keys", "Keys", 0x26),
    Field("powders", "Powders", 0x27),
    Field("torches", "Torches", 0x0F),
]
ARMOR_COUNTS = [Field(f"armor{i}", ARMOR[i], 0x28 + i) for i in range(1, len(ARMOR))]
WEAPON_COUNTS = [Field(f"weapon{i}", WEAPONS[i], 0x30 + i) for i in range(1, len(WEAPONS))]
NUMERIC_FIELDS = {f.key: f for f in STATS + VITALS + GOODS + ARMOR_COUNTS + WEAPON_COUNTS}


class Character:
    """View over one 64-byte record inside a larger buffer."""

    def __init__(self, buf: bytearray, base: int):
        self.buf = buf
        self.base = base

    def _get(self, offset: int, size: int = 1) -> bytearray:
        return self.buf[self.base + offset : self.base + offset + size]

    def _set(self, offset: int, data: bytes) -> None:
        self.buf[self.base + offset : self.base + offset + len(data)] = data

    @property
    def raw(self) -> bytes:
        return bytes(self._get(0, RECORD_SIZE))

    @property
    def empty(self) -> bool:
        return self._get(0)[0] == 0

    @property
    def name(self) -> str:
        return self._get(0, NAME_LEN).split(b"\0", 1)[0].decode("ascii", "replace")

    @name.setter
    def name(self, value: str) -> None:
        data = value.encode("ascii")
        if not 1 <= len(data) < NAME_LEN:
            raise ValueError(f"name must be 1..{NAME_LEN - 1} ASCII characters")
        self._set(0, data.ljust(NAME_LEN, b"\0"))

    def get(self, key: str) -> int:
        f = NUMERIC_FIELDS[key]
        return bcd_decode(self._get(f.offset, f.size))

    def set(self, key: str, value: int) -> None:
        f = NUMERIC_FIELDS[key]
        self._set(f.offset, bcd_encode(value, f.size))

    def _letter(self, offset: int) -> str:
        return chr(self._get(offset)[0])

    def _set_letter(self, offset: int, value: str, table: dict[str, str]) -> None:
        if value not in table:
            raise ValueError(f"{value!r} not one of {', '.join(table)}")
        self._set(offset, value.encode("ascii"))

    status = property(lambda s: s._letter(0x11), lambda s, v: s._set_letter(0x11, v, STATUS))
    race = property(lambda s: s._letter(0x16), lambda s, v: s._set_letter(0x16, v, RACES))
    klass = property(lambda s: s._letter(0x17), lambda s, v: s._set_letter(0x17, v, CLASSES))
    gender = property(lambda s: s._letter(0x18), lambda s, v: s._set_letter(0x18, v, GENDERS))

    @property
    def in_party(self) -> bool:
        return self._get(0x10)[0] == 0xFF

    @property
    def marks(self) -> int:
        return self._get(0x0E)[0]

    @marks.setter
    def marks(self, value: int) -> None:
        self._set(0x0E, bytes([value & 0xFF]))

    @property
    def armor(self) -> int:
        return self._get(0x28)[0]

    @armor.setter
    def armor(self, value: int) -> None:
        if not 0 <= value < len(ARMOR):
            raise ValueError("bad armor index")
        self._set(0x28, bytes([value]))

    @property
    def weapon(self) -> int:
        return self._get(0x30)[0]

    @weapon.setter
    def weapon(self, value: int) -> None:
        if not 0 <= value < len(WEAPONS):
            raise ValueError("bad weapon index")
        self._set(0x30, bytes([value]))

    def heal(self) -> None:
        self.status = "G"
        self.set("hp", self.get("maxhp"))

    def summary(self) -> str:
        return (
            f"{self.name} {RACES.get(self.race, '?')} {CLASSES.get(self.klass, '?')} "
            f"[{STATUS.get(self.status, '?')}] HP {self.get('hp')}/{self.get('maxhp')}"
        )


class SaveGame:
    """The three save files of one Ultima III directory."""

    def __init__(self, directory: str | Path):
        self.dir = Path(directory)
        self.roster_path = self._find("roster.ult")
        self.party_path = self._find("party.ult")
        self.sosaria_path = self._find("sosaria.ult", required=False)
        self.roster = self._load(self.roster_path, ROSTER_SIZE)
        self.party = self._load(self.party_path, PARTY_SIZE)
        self.sosaria = self._load(self.sosaria_path, SOSARIA_SIZE) if self.sosaria_path else None
        self._original = self._snapshot()

    def _find(self, name: str, required: bool = True) -> Path | None:
        # DOS file names: accept any case.
        for p in self.dir.iterdir():
            if p.name.lower() == name:
                return p
        if required:
            raise FileNotFoundError(f"{name} not found in {self.dir}")
        return None

    @staticmethod
    def _load(path: Path, size: int) -> bytearray:
        data = bytearray(path.read_bytes())
        if len(data) != size:
            raise ValueError(f"{path.name}: expected {size} bytes, got {len(data)}")
        return data

    def _snapshot(self) -> tuple[bytes, bytes, bytes | None]:
        return bytes(self.roster), bytes(self.party), bytes(self.sosaria) if self.sosaria else None

    @property
    def dirty(self) -> bool:
        return self._snapshot() != self._original

    def roster_char(self, slot: int) -> Character:
        return Character(self.roster, slot * RECORD_SIZE)

    def party_char(self, slot: int) -> Character:
        return Character(self.party, PARTY_HEADER + slot * RECORD_SIZE)

    # --- party header -------------------------------------------------
    @property
    def party_size(self) -> int:
        return self.party[0x07]

    @property
    def party_order(self) -> list[int]:
        """1-based roster numbers of the active party members."""
        return list(self.party[0x0A : 0x0A + self.party_size])

    @property
    def transport(self) -> int:
        return self.party[0x00]

    @transport.setter
    def transport(self, value: int) -> None:
        if value not in TRANSPORT:
            raise ValueError("bad transport")
        self.party[0x00] = value

    @property
    def moves(self) -> int:
        return bcd_decode(self.party[0x03:0x07])

    @moves.setter
    def moves(self, value: int) -> None:
        self.party[0x03:0x07] = bcd_encode(value, 4)

    @property
    def position(self) -> tuple[int, int]:
        return self.party[0x08], self.party[0x09]

    @position.setter
    def position(self, xy: tuple[int, int]) -> None:
        x, y = xy
        if not (0 <= x < 64 and 0 <= y < 64):
            raise ValueError("position must be within 0..63")
        self.party[0x08], self.party[0x09] = x, y

    # --- moons ----------------------------------------------------------
    @property
    def moons(self) -> tuple[int, int] | None:
        if self.sosaria is None:
            return None
        return self.sosaria[MOON_OFFSET], self.sosaria[MOON_OFFSET + 1]

    @moons.setter
    def moons(self, phases: tuple[int, int]) -> None:
        if self.sosaria is None:
            raise ValueError("no sosaria.ult")
        if not all(0 <= p <= 7 for p in phases):
            raise ValueError("moon phases are 0..7")
        self.sosaria[MOON_OFFSET], self.sosaria[MOON_OFFSET + 1] = phases

    # --- persistence ----------------------------------------------------
    def sync_party_to_roster(self) -> None:
        """Copy active party records into their roster slots.

        The game works on PARTY.ULT while a party is formed; mirroring the
        edits into ROSTER.ULT keeps both views consistent.
        """
        for slot, number in enumerate(self.party_order):
            if 1 <= number <= ROSTER_SLOTS:
                rec = self.party_char(slot).raw
                base = (number - 1) * RECORD_SIZE
                self.roster[base : base + RECORD_SIZE] = rec

    def save(self, backup: bool = True) -> list[Path]:
        written = []
        for path, data, orig in zip(
            (self.roster_path, self.party_path, self.sosaria_path),
            self._snapshot(),
            self._original,
        ):
            if path is None or data == orig:
                continue
            if backup:
                bak = path.with_name(path.name + ".bak")
                if not bak.exists():
                    bak.write_bytes(path.read_bytes())
            path.write_bytes(data)
            written.append(path)
        self._original = self._snapshot()
        return written

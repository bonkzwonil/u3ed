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


FILE_SIZES = {"roster.ult": ROSTER_SIZE, "party.ult": PARTY_SIZE, "sosaria.ult": SOSARIA_SIZE}
OPTIONAL_FILES = {"sosaria.ult"}


class SaveGame:
    """The save files of one Ultima III directory, held in memory.

    Files are keyed by their lower-case DOS name (``roster.ult`` ...).
    """

    def __init__(self, directory: str | Path):
        self.dir = Path(directory)
        self.paths = {
            name: path
            for name in FILE_SIZES
            if (path := self._find(name, required=name not in OPTIONAL_FILES))
        }
        self.load(self.read_disk())

    @classmethod
    def from_files(cls, files: dict[str, bytes]) -> SaveGame:
        """In-memory save game, e.g. for a history version."""
        save = cls.__new__(cls)
        save.dir = None
        save.paths = {}
        save.load(files)
        return save

    def _find(self, name: str, required: bool = True) -> Path | None:
        # DOS file names: accept any case.
        for p in self.dir.iterdir():
            if p.name.lower() == name:
                return p
        if required:
            raise FileNotFoundError(f"{name} not found in {self.dir}")
        return None

    def read_disk(self) -> dict[str, bytes]:
        return {name: path.read_bytes() for name, path in self.paths.items()}

    def load(self, files: dict[str, bytes]) -> None:
        """Replace the in-memory state; the loaded state counts as unmodified."""
        for name, data in files.items():
            if len(data) != FILE_SIZES[name]:
                raise ValueError(f"{name}: expected {FILE_SIZES[name]} bytes, got {len(data)}")
        self.roster = bytearray(files["roster.ult"])
        self.party = bytearray(files["party.ult"])
        sosaria = files.get("sosaria.ult")
        self.sosaria = bytearray(sosaria) if sosaria is not None else None
        self._original = self.files()

    def files(self) -> dict[str, bytes]:
        files = {"roster.ult": bytes(self.roster), "party.ult": bytes(self.party)}
        if self.sosaria is not None:
            files["sosaria.ult"] = bytes(self.sosaria)
        return files

    @property
    def original(self) -> dict[str, bytes]:
        """The state last loaded or saved."""
        return dict(self._original)

    @property
    def dirty(self) -> bool:
        return self.files() != self._original

    def rebase(self, base: dict[str, bytes]) -> None:
        """Re-apply the in-memory edits on top of ``base`` (e.g. files the game
        wrote since loading). Fields edited here win; everything else comes
        from ``base``. Buffers are updated in place so Character views stay valid.
        """
        mine = self.files()
        for name, buf in (("roster.ult", self.roster), ("party.ult", self.party),
                          ("sosaria.ult", self.sosaria)):
            if buf is not None and name in base:
                buf[:] = merge(self._original[name], mine[name], base[name], _spans(name))
        self._original = dict(base)

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

        The game itself only writes PARTY.ULT while a party is formed and
        leaves ROSTER.ULT stale; this is an opt-in convenience.
        """
        for slot, number in enumerate(self.party_order):
            if 1 <= number <= ROSTER_SLOTS:
                rec = self.party_char(slot).raw
                base = (number - 1) * RECORD_SIZE
                self.roster[base : base + RECORD_SIZE] = rec

    def save(self) -> list[str]:
        """Write the files that differ from the loaded state; return their names."""
        written = []
        for name, data in self.files().items():
            if data != self._original.get(name):
                self.paths[name].write_bytes(data)
                written.append(name)
        self._original = self.files()
        return written

    def write_files(self, files: dict[str, bytes]) -> None:
        """Overwrite the files on disk with ``files`` and load them."""
        for name, data in files.items():
            if name in self.paths:
                self.paths[name].write_bytes(data)
        self.load(files)


def _record_spans(base: int) -> list[tuple[int, int]]:
    fields = [(0, NAME_LEN)] + [(fl.offset, fl.size) for fl in NUMERIC_FIELDS.values()]
    return [(base + off, size) for off, size in fields]


def _spans(name: str) -> list[tuple[int, int]]:
    """Multi-byte fields that must be merged as a unit; other bytes merge singly."""
    if name == "roster.ult":
        return [s for i in range(ROSTER_SLOTS) for s in _record_spans(i * RECORD_SIZE)]
    if name == "party.ult":
        header = [(0x03, 4), (0x0A, 4)]  # moves, party order
        return header + [s for i in range(PARTY_SLOTS)
                         for s in _record_spans(PARTY_HEADER + i * RECORD_SIZE)]
    return []


def merge(base: bytes, mine: bytes, theirs: bytes, spans: list[tuple[int, int]]) -> bytes:
    """Three-way merge: spans changed in ``mine`` (vs ``base``) win over ``theirs``."""
    out = bytearray(theirs)
    covered = bytearray(len(base))
    units = []
    for start, size in spans:
        units.append((start, size))
        covered[start : start + size] = b"\1" * size
    units += [(i, 1) for i in range(len(base)) if not covered[i]]
    for start, size in units:
        end = start + size
        if mine[start:end] != base[start:end]:
            out[start:end] = mine[start:end]
    return bytes(out)


def _char_changes(a: Character, b: Character) -> list[str]:
    out = []
    if a.name != b.name:
        out.append(f"name {a.name!r} → {b.name!r}")
    for attr, label, table in (("status", "status", STATUS), ("race", "race", RACES),
                               ("klass", "class", CLASSES), ("gender", "gender", GENDERS)):
        x, y = getattr(a, attr), getattr(b, attr)
        if x != y:
            out.append(f"{label} {table.get(x, x)} → {table.get(y, y)}")
    for key, field in NUMERIC_FIELDS.items():
        x, y = a.get(key), b.get(key)
        if x != y:
            out.append(f"{field.label.lower()} {x} → {y}")
    gained = [m for i, m in enumerate(MARKS) if b.marks & ~a.marks & 1 << i]
    lost = [m for i, m in enumerate(MARKS) if a.marks & ~b.marks & 1 << i]
    out += [f"+{m}" for m in gained] + [f"-{m}" for m in lost]
    for attr, label, names in (("armor", "worn", ARMOR), ("weapon", "readied", WEAPONS)):
        x, y = getattr(a, attr), getattr(b, attr)
        if x != y:
            name = lambda i: names[i] if i < len(names) else str(i)  # noqa: E731
            out.append(f"{label} {name(x)} → {name(y)}")
    if not out:
        out.append("other bytes")
    return out


def describe_changes(old: SaveGame, new: SaveGame) -> list[str]:
    """Human-readable list of differences between two save states."""
    out = []
    for label, get in (
        ("transport", lambda s: TRANSPORT.get(s.transport, hex(s.transport))),
        ("moves", lambda s: s.moves),
        ("position", lambda s: s.position),
        ("party order", lambda s: s.party_order),
        ("moons", lambda s: s.moons),
    ):
        if get(old) != get(new):
            out.append(f"Party {label}: {get(old)} → {get(new)}")
    if old.party[:PARTY_HEADER] != new.party[:PARTY_HEADER] and not out:
        out.append("Party header: other bytes")
    party_records = {new.party_char(i).raw for i in range(PARTY_SLOTS)}
    mirrored = []
    for where, count, getter in (("party", PARTY_SLOTS, SaveGame.party_char),
                                 ("roster", ROSTER_SLOTS, SaveGame.roster_char)):
        for i in range(count):
            a, b = getter(old, i), getter(new, i)
            if a.raw == b.raw:
                continue
            name = b.name or a.name or "(empty)"
            if where == "roster" and b.raw in party_records:
                mirrored.append(name)
                continue
            out.append(f"{name} ({where} {i + 1}): " + ", ".join(_char_changes(a, b)))
    if mirrored:
        out.append("Roster synced from party: " + ", ".join(mirrored))
    if old.sosaria != new.sosaria and old.moons == new.moons:
        out.append("sosaria.ult: other bytes")
    return out

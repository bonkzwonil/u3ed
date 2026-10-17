import shutil
from pathlib import Path

import pytest

from u3edit.format import SaveGame, bcd_decode, bcd_encode, describe_changes
from u3edit.history import History

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def played(tmp_path):
    dst = tmp_path / "game"
    shutil.copytree(FIXTURES / "played", dst)
    return dst


def test_bcd_roundtrip():
    assert bcd_encode(150, 2) == b"\x50\x01"
    assert bcd_decode(b"\x50\x01") == 150
    assert bcd_decode(bcd_encode(9999, 2)) == 9999
    with pytest.raises(ValueError):
        bcd_encode(100, 1)


def test_reads_played_save(played):
    s = SaveGame(played)
    assert s.party_order == [4, 2, 1, 3]
    assert s.position == (45, 19)
    assert s.moves == 45295
    korq = s.party_char(0)
    assert korq.name == "Korq"
    assert (korq.race, korq.klass, korq.gender) == ("D", "F", "M")
    assert korq.get("hp") == 150 and korq.get("exp") == 52
    assert korq.armor == 3 and korq.get("armor3") == 1
    assert s.roster_char(0).name == "Bonk"


def test_no_changes_writes_nothing(played):
    before = {p.name: p.read_bytes() for p in played.iterdir()}
    s = SaveGame(played)
    assert not s.dirty
    assert s.save() == []
    assert {p.name: p.read_bytes() for p in played.iterdir()} == before


def test_edit_save_reload(played):
    original = (played / "party.ult").read_bytes()
    s = SaveGame(played)
    c = s.party_char(1)
    c.set("gold", 9999)
    c.set("hp", 1234)
    c.name = "Gwen"
    c.marks = 0xFF
    s.moves = 1
    s.moons = (0, 7)
    assert set(s.save()) == {"party.ult", "sosaria.ult"}  # no sync by default
    assert SaveGame(played).roster_char(1).name == "Girl"
    s.sync_party_to_roster()
    assert s.save() == ["roster.ult"]

    r = SaveGame(played)
    c = r.party_char(1)
    assert (c.name, c.get("gold"), c.get("hp"), c.marks) == ("Gwen", 9999, 1234, 0xFF)
    assert r.moves == 1 and r.moons == (0, 7)
    # party slot 2 is roster #2: mirrored there
    assert r.roster_char(1).raw == c.raw
    # only the touched bytes changed in party.ult
    diff = [i for i, (a, b) in enumerate(zip(original, (played / "party.ult").read_bytes())) if a != b]
    assert all(i < 0x12 or 0x52 <= i < 0x92 for i in diff)


def test_validation(played):
    c = SaveGame(played).party_char(0)
    with pytest.raises(ValueError):
        c.name = "ThisNameIsTooLong"
    with pytest.raises(ValueError):
        c.klass = "X"
    with pytest.raises(ValueError):
        c.set("str", 100)


def test_case_insensitive_files(tmp_path):
    for name in ("roster.ult", "party.ult"):
        shutil.copy(FIXTURES / "fresh" / name, tmp_path / name.upper())
    s = SaveGame(tmp_path)
    assert s.sosaria is None and s.roster_char(0).empty


def test_describe_changes(played):
    old = SaveGame(played)
    new = SaveGame.from_files(old.files())
    new.party_char(0).set("gold", 4321)
    new.party_char(0).marks |= 1
    new.moves = 7
    new.sync_party_to_roster()
    changes = describe_changes(old, new)
    assert "Korq (party 1): gold 113 → 4321, +Card of Love" in changes
    assert "Party moves: 45295 → 7" in changes
    assert changes[-1].startswith("Roster synced from party: ")


def test_history_roundtrip(played):
    h = History(played)
    assert h.versions() == []
    files = SaveGame(played).files()
    v1 = h.record(files, "Original files")
    v2 = h.record({**files, "party.ult": bytes(274)}, "zeroed", ["a", "b"])
    assert v1.path.name.endswith(".tar.bz2") and v1.number == 1 and v2.number == 2
    assert [v.number for v in h.versions()] == [2, 1]
    latest = h.latest()
    assert (latest.label, latest.changes) == ("zeroed", ["a", "b"])
    assert h.files(h.versions()[1]) == files


def test_rebase_keeps_game_progress(played):
    s = SaveGame(played)
    s.party_char(0).set("gold", 4321)       # our edit: 113 -> 4321
    game = SaveGame.from_files(s.original)  # meanwhile the game saves
    game.moves = 50000
    game.party_char(0).set("gold", 250)     # conflicting field: ours wins as a unit
    game.party_char(0).set("food", 1500)
    s.rebase(game.files())
    c = s.party_char(0)
    assert (s.moves, c.get("gold"), c.get("food")) == (50000, 4321, 1500)
    assert describe_changes(game, s) == ["Korq (party 1): gold 250 → 4321"]

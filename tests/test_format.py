import shutil
from pathlib import Path

import pytest

from u3edit.format import SaveGame, bcd_decode, bcd_encode

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
    s.sync_party_to_roster()  # roster is stale in the fixture, so this dirties it
    s.roster[:] = (played / "roster.ult").read_bytes()
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
    s.sync_party_to_roster()
    written = {p.name for p in s.save()}
    assert written == {"party.ult", "roster.ult", "sosaria.ult"}
    assert (played / "party.ult.bak").read_bytes() == original

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

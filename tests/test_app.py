import asyncio
import shutil
from pathlib import Path

from textual.widgets import Input

from u3edit.app import HistoryScreen, U3EditApp
from u3edit.format import SaveGame
from u3edit.history import History

FIXTURES = Path(__file__).parent / "fixtures"


def make_game(tmp_path):
    game = tmp_path / "game"
    shutil.copytree(FIXTURES / "played", game)
    return game


def test_edit_save_history_restore(tmp_path):
    game = make_game(tmp_path)
    original = SaveGame(game).files()
    app = U3EditApp(SaveGame(game))

    async def run():
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # roster slot 4 is Korq, who is party slot 1 -> edits party.ult
            app.query_one("#chars").index = 3
            await pilot.pause()
            assert app.query_one("#name", Input).value == "Korq"
            app.query_one("#num-gold", Input).value = "4321"
            await pilot.pause()
            await pilot.press("ctrl+s")
            await pilot.pause()
            assert SaveGame(game).party_char(0).get("gold") == 4321

            await pilot.press("f5")
            await pilot.pause()
            assert isinstance(app.screen, HistoryScreen)
            await pilot.press("down", "r")  # version 1 = original files
            await pilot.pause()
            await pilot.click("#yes")
            await pilot.pause()
            assert not isinstance(app.screen, HistoryScreen)
            assert app.query_one("#num-gold", Input).value == "113"

    asyncio.run(run())
    assert SaveGame(game).files() == original
    versions = History(game).versions()
    assert [v.label for v in versions] == [
        "Restored version 1",
        "Korq (party 1): gold 113 → 4321",
        "Original files",
    ]
    # roster untouched without sync
    assert SaveGame(game).roster_char(3).get("gold") == 150


def test_sync_toggle_and_external_change(tmp_path):
    game = make_game(tmp_path)
    app = U3EditApp(SaveGame(game))

    async def run():
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_toggle_sync()
            await pilot.pause()
            assert "roster sync: on" in str(app.query_one("#status").render())
            app.query_one("#chars").index = 3
            await pilot.pause()
            app.query_one("#num-gold", Input).value = "500"
            await pilot.pause()
            await pilot.press("ctrl+s")
            await pilot.pause()
            # the "game" changes the files, then we save again
            s = SaveGame(game)
            s.moves = 1
            s.save()
            app.query_one("#num-gold", Input).value = "600"
            await pilot.pause()
            await pilot.press("ctrl+s")
            await pilot.pause()

    asyncio.run(run())
    final = SaveGame(game)
    assert final.roster_char(3).get("gold") == 600
    assert final.party_char(0).get("gold") == 600
    assert final.moves == 1  # the game's change survived our second save
    labels = [v.label for v in History(game).versions()]
    assert labels[1] == "Changed outside u3edit (game?)"
    assert len(labels) == 4

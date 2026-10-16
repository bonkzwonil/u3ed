import asyncio
import shutil
from pathlib import Path

from textual.widgets import Input

from u3edit.app import U3EditApp
from u3edit.format import SaveGame

FIXTURES = Path(__file__).parent / "fixtures"


def test_edit_gold_and_save(tmp_path):
    shutil.copytree(FIXTURES / "played", tmp_path / "game")
    save = SaveGame(tmp_path / "game")
    app = U3EditApp(save)

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

    asyncio.run(run())
    reloaded = SaveGame(tmp_path / "game")
    assert reloaded.party_char(0).get("gold") == 4321
    assert reloaded.roster_char(3).get("gold") == 4321

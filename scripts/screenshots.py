"""Render the README screenshots from the demo save (needs inkscape for PNG).

    uv run python scripts/screenshots.py
"""

import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path

from textual.widgets import Checkbox, Input

from u3edit.app import U3EditApp
from u3edit.format import SaveGame

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs/screenshots"
SHOWN_DIR = "~/dos/ultima3"


async def scenario(game: Path) -> None:
    app = U3EditApp(SaveGame(game))
    async with app.run_test(size=(112, 40)) as pilot:
        async def shot(name: str) -> None:
            history = name == "history"
            app.screen.sub_title = f"History: {SHOWN_DIR}/.u3edit-history" if history else SHOWN_DIR
            await pilot.pause(0.3)
            app.save_screenshot(str(OUT / f"{name}.svg"))

        chars = app.query_one("#chars")
        await pilot.pause()
        # Dupre gets rich
        chars.index = 2
        await pilot.pause()
        app.query_one("#num-gold", Input).value = "5000"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        # meanwhile the game saves
        s = SaveGame(game)
        s.moves, s.position = 31402, (43, 25)
        s.save()
        # cure Iolo and hand him the Mark of Sol
        chars.index = 0
        await pilot.pause()
        app.action_heal()
        await pilot.pause()
        app.query_one("#mark-1", Checkbox).value = True
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause(0.5)

        await shot("character")
        app.query_one("#editor").active = "tab-inv"
        await shot("inventory")
        app.query_one("#editor").active = "tab-party"
        await shot("party")
        app.query_one("#editor").active = "tab-char"
        await pilot.press("ctrl+p")
        await pilot.pause(0.3)
        await pilot.press(*"sync")
        await shot("palette")
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("f5")
        await shot("history")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        game = Path(tmp) / "ultima3"
        shutil.copytree(ROOT / "tests/fixtures/demo", game)
        asyncio.run(scenario(game))
    for svg in sorted(OUT.glob("*.svg")):
        subprocess.run(["inkscape", str(svg), "-o", str(svg.with_suffix(".png"))],
                       check=True, capture_output=True)
        svg.unlink()
        print(svg.with_suffix(".png").relative_to(ROOT))


if __name__ == "__main__":
    main()

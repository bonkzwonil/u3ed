"""Textual TUI for editing Ultima III save games."""

from __future__ import annotations

from collections.abc import Iterable

from textual import on
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.containers import Grid, Horizontal, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button, Checkbox, DataTable, Footer, Header, Input, Label, ListItem, ListView,
    Select, Static, TabbedContent, TabPane,
)

from . import format as f
from .history import History, Version

LETTER_SELECTS = {
    "status": f.STATUS,
    "race": f.RACES,
    "klass": f.CLASSES,
    "gender": f.GENDERS,
}


def number_row(field: f.Field) -> ComposeResult:
    yield Label(field.label)
    yield Input(id=f"num-{field.key}", type="integer", max_length=2 * field.size, classes="num")


class Confirm(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, question: str, yes: str):
        super().__init__()
        self.question, self.yes = question, yes

    def compose(self) -> ComposeResult:
        with Grid(id="dialog"):
            yield Label(self.question, id="question")
            yield Button(self.yes, variant="error", id="yes")
            yield Button("Cancel", variant="primary", id="no")

    @on(Button.Pressed)
    def done(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_cancel(self) -> None:
        self.dismiss(False)


class Choice(ModalScreen[str | None]):
    """Question with several answers; dismisses with the chosen button id."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, question: str, choices: list[tuple[str, str]]):
        super().__init__()
        self.question, self.choices = question, choices

    def compose(self) -> ComposeResult:
        with Grid(id="dialog", classes="three"):
            yield Label(self.question, id="question")
            for i, (cid, label) in enumerate(self.choices):
                yield Button(label, variant="primary" if i == 0 else "default", id=cid)
            yield Button("Cancel", id="cancel")

    @on(Button.Pressed)
    def done(self, event: Button.Pressed) -> None:
        self.dismiss(None if event.button.id == "cancel" else event.button.id)

    def action_cancel(self) -> None:
        self.dismiss(None)


class HistoryScreen(Screen):
    """Browse saved versions and restore one."""

    BINDINGS = [
        Binding("escape,q", "app.pop_screen", "Back"),
        Binding("r", "restore", "Restore"),
    ]

    def __init__(self, history: History, disk: dict[str, bytes]):
        super().__init__()
        self.history = history
        self.disk = disk
        self.versions: list[Version] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="versions", cursor_type="row", zebra_stripes=True)
        with VerticalScroll(id="changes-box"):
            yield Static(id="changes")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = f"History: {self.history.dir}"
        table = self.query_one(DataTable)
        table.add_columns("#", "Saved", "", "Summary")
        self.versions = self.history.versions()
        for v in self.versions:
            current = "● on disk" if self.history.files(v) == self.disk else ""
            table.add_row(v.number, f"{v.time:%Y-%m-%d %H:%M:%S}", current, v.label, key=str(v.number))
        if not self.versions:
            self.query_one("#changes", Static).update("No versions yet. Every save adds one.")
        table.focus()

    @on(DataTable.RowHighlighted)
    def show_changes(self, event: DataTable.RowHighlighted) -> None:
        v = self.selected
        if v:
            body = "\n".join(f"• {c}" for c in v.changes) or "(no changes listed)"
            self.query_one("#changes", Static).update(
                f"[b]Version {v.number}[/b]  {v.time:%Y-%m-%d %H:%M:%S}  {v.label}\n\n{body}"
            )

    @on(DataTable.RowSelected)
    def row_selected(self, event: DataTable.RowSelected) -> None:
        self.action_restore()

    @property
    def selected(self) -> Version | None:
        table = self.query_one(DataTable)
        if not self.versions or table.cursor_row is None:
            return None
        return self.versions[table.cursor_row]

    def action_restore(self) -> None:
        v = self.selected
        if v is None:
            return
        unsaved = " Unsaved edits are discarded." if self.app.save.dirty else ""

        def done(ok: bool | None) -> None:
            if ok:
                self.app.restore_version(v)
                self.app.pop_screen()

        self.app.push_screen(Confirm(f"Restore version {v.number}?{unsaved}", "Restore"), done)


class U3EditApp(App):
    TITLE = "u3edit"
    CSS = """
    #chars { width: 34; border: round $primary; }
    #editor { width: 1fr; border: round $primary; }
    .form { grid-size: 4; grid-columns: 14 1fr 14 1fr; grid-gutter: 0 1; height: auto; padding: 1 1; }
    .form Label { padding: 1 0 0 1; }
    .section { color: $accent; text-style: bold; padding: 1 1 0 1; }
    #tokens { height: auto; padding: 0 1; }
    .tokens { grid-size: 2; grid-columns: 1fr 1fr; height: auto; width: 1fr;
              border: round $accent; border-title-color: $accent; border-title-style: bold;
              margin: 1 1 0 0; }
    Input.-invalid { border: tall $error; }
    #status { height: 1; padding: 0 1; background: $panel; }
    #dialog { grid-size: 2; grid-gutter: 1 2; padding: 1 2; width: 50; height: 11;
              border: thick $error; background: $surface; }
    #question { column-span: 2; height: 1fr; width: 1fr; content-align: center middle; }
    Confirm, Choice { align: center middle; }
    #dialog.three { grid-size: 3; width: 72; }
    #dialog.three #question { column-span: 3; }
    #versions { height: 1fr; border: round $primary; }
    #changes-box { height: 12; border: round $primary; padding: 0 1; }
    """
    BINDINGS = [
        Binding("ctrl+s,f2", "save", "Save"),
        Binding("f3", "heal", "Heal"),
        Binding("f4", "revert", "Revert char"),
        Binding("f5", "history", "History"),
        Binding("ctrl+r,f6", "reload", "Reload"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, save: f.SaveGame, sync_roster: bool = False):
        super().__init__()
        self.save = save
        self.sync_roster = sync_roster
        self.history = History(save.dir)
        self.char: f.Character | None = None
        self.char_label = ""
        self._loading = False
        self.sub_title = str(save.dir)

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        yield from super().get_system_commands(screen)
        state = "off" if self.sync_roster else "on"
        yield SystemCommand(
            f"Roster sync: turn {state}",
            "Mirror party members into roster.ult on save (the game itself doesn't)",
            self.action_toggle_sync,
        )
        yield SystemCommand("History", "Show saved versions and restore one", self.action_history)
        yield SystemCommand("Reload from disk", "Pick up what the game saved", self.action_reload)

    # --- layout ---------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield ListView(id="chars")
            with TabbedContent(id="editor"):
                with TabPane("Character", id="tab-char"):
                    with VerticalScroll():
                        with Grid(classes="form"):
                            yield Label("Name")
                            yield Input(id="name", max_length=f.NAME_LEN - 1)
                            for key, label in (("status", "Status"), ("race", "Race"),
                                               ("klass", "Class"), ("gender", "Gender")):
                                yield Label(label)
                                yield Select(
                                    [(f"{v} ({k})", k) for k, v in LETTER_SELECTS[key].items()],
                                    id=f"sel-{key}", allow_blank=False,
                                )
                            yield Static()
                            yield Static()
                            for field in f.STATS + f.VITALS:
                                yield from number_row(field)
                        with Horizontal(id="tokens"):
                            for title, bits in (("Cards", f.CARD_BITS), ("Marks", f.MARK_BITS)):
                                with Grid(classes="tokens") as box:
                                    box.border_title = title
                                    for bit, name in bits:
                                        yield Checkbox(name, id=f"mark-{bit}")
                with TabPane("Inventory", id="tab-inv"):
                    with VerticalScroll():
                        with Grid(classes="form"):
                            for field in f.GOODS:
                                yield from number_row(field)
                        yield Label("Armour", classes="section")
                        with Grid(classes="form"):
                            yield Label("Worn")
                            yield Select([(n, i) for i, n in enumerate(f.ARMOR)],
                                         id="sel-armor", allow_blank=False)
                            for field in f.ARMOR_COUNTS:
                                yield from number_row(field)
                        yield Label("Weapons", classes="section")
                        with Grid(classes="form"):
                            yield Label("Readied")
                            yield Select([(n, i) for i, n in enumerate(f.WEAPONS)],
                                         id="sel-weapon", allow_blank=False)
                            for field in f.WEAPON_COUNTS:
                                yield from number_row(field)
                with TabPane("Party", id="tab-party"):
                    with Grid(classes="form"):
                        yield Label("Transport")
                        yield Select([(v, k) for k, v in f.TRANSPORT.items()],
                                     id="transport", allow_blank=False)
                        yield Label("Moves")
                        yield Input(id="moves", type="integer", max_length=8)
                        yield Label("X")
                        yield Input(id="pos-x", type="integer", max_length=2)
                        yield Label("Y")
                        yield Input(id="pos-y", type="integer", max_length=2)
                        if self.save.sosaria is not None:
                            yield Label("Moon (left)")
                            yield Input(id="moon-0", type="integer", max_length=1)
                            yield Label("Moon (right)")
                            yield Input(id="moon-1", type="integer", max_length=1)
                    yield Static(id="party-info", classes="section")
        yield Static(id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_list()
        self.load_party()
        chars = self.query_one("#chars", ListView)
        chars.index = 0
        chars.focus()

    # --- character list -------------------------------------------------
    def resolve(self, slot: int) -> tuple[f.Character, str]:
        """Roster slot -> record to edit. Active party members live in PARTY.ULT."""
        order = self.save.party_order
        if slot + 1 in order:
            p = order.index(slot + 1)
            return self.save.party_char(p), f"party slot {p + 1} (party.ult)"
        return self.save.roster_char(slot), f"roster slot {slot + 1} (roster.ult)"

    def list_label(self, slot: int) -> str:
        char, where = self.resolve(slot)
        if char.empty:
            return f"{slot + 1:2}  ·"
        star = "★" if where.startswith("party") else " "
        return f"{slot + 1:2} {star}{char.name:<9} {char.race}{char.klass} {char.status}"

    def refresh_list(self) -> None:
        view = self.query_one("#chars", ListView)
        index = view.index
        view.clear()
        view.extend(ListItem(Label(self.list_label(s))) for s in range(f.ROSTER_SLOTS))
        view.index = index

    def refresh_current_label(self) -> None:
        view = self.query_one("#chars", ListView)
        if view.index is not None and view.highlighted_child:
            view.highlighted_child.query_one(Label).update(self.list_label(view.index))

    @on(ListView.Highlighted, "#chars")
    def select_char(self, event: ListView.Highlighted) -> None:
        if event.list_view.index is None:
            return
        self.char, self.char_label = self.resolve(event.list_view.index)
        self.load_char()

    # --- populate widgets ------------------------------------------------
    def load_char(self) -> None:
        c = self.char
        if c is None:
            return
        self._loading = True
        try:
            self.query_one("#name", Input).value = c.name
            for key, table in LETTER_SELECTS.items():
                sel = self.query_one(f"#sel-{key}", Select)
                letter = getattr(c, key)
                if letter in table:
                    sel.value = letter
            for key in f.NUMERIC_FIELDS:
                self.query_one(f"#num-{key}", Input).value = str(c.get(key))
            for bit in range(8):
                self.query_one(f"#mark-{bit}", Checkbox).value = bool(c.marks & (1 << bit))
            if c.armor < len(f.ARMOR):
                self.query_one("#sel-armor", Select).value = c.armor
            if c.weapon < len(f.WEAPONS):
                self.query_one("#sel-weapon", Select).value = c.weapon
        finally:
            self.call_after_refresh(self._done_loading)
        hint = "  (empty slot: give it a name to create)" if c.empty else ""
        self.set_status(f"Editing {self.char_label}{hint}")

    def _done_loading(self) -> None:
        self._loading = False

    def load_party(self) -> None:
        s = self.save
        self._loading = True
        if s.transport in f.TRANSPORT:
            self.query_one("#transport", Select).value = s.transport
        self.query_one("#moves", Input).value = str(s.moves)
        x, y = s.position
        self.query_one("#pos-x", Input).value = str(x)
        self.query_one("#pos-y", Input).value = str(y)
        if s.moons:
            for i, phase in enumerate(s.moons):
                self.query_one(f"#moon-{i}", Input).value = str(phase)
        names = [self.save.roster_char(n - 1).name or f"#{n}" for n in s.party_order]
        self.query_one("#party-info", Static).update(
            f"Party ({s.party_size}): " + ", ".join(names)
        )
        self.call_after_refresh(self._done_loading)

    # --- apply edits ----------------------------------------------------
    def set_status(self, text: str, error: bool = False) -> None:
        dirty = "  [b yellow]modified[/]" if self.save.dirty else ""
        sync = "[b green]on[/]" if self.sync_roster else "off"
        msg = f"[b red]{text}[/]" if error else text
        self.query_one("#status", Static).update(f"{msg}{dirty}  │ roster sync: {sync}")

    def apply(self, widget, setter) -> None:
        if self._loading:
            return
        try:
            setter()
        except ValueError as exc:
            widget.add_class("-invalid")
            self.set_status(str(exc), error=True)
            return
        widget.remove_class("-invalid")
        self.refresh_current_label()
        self.set_status(f"Editing {self.char_label}")

    @on(Input.Changed)
    def input_changed(self, event: Input.Changed) -> None:
        wid, value, c = event.input.id or "", event.value, self.char
        s = self.save

        def as_int() -> int:
            if not value.strip():
                raise ValueError("value required")
            return int(value)

        if wid == "name" and c:
            self.apply(event.input, lambda: setattr(c, "name", value))
        elif wid.startswith("num-") and c:
            self.apply(event.input, lambda: c.set(wid[4:], as_int()))
        elif wid == "moves":
            self.apply(event.input, lambda: setattr(s, "moves", as_int()))
        elif wid in ("pos-x", "pos-y"):
            def set_pos() -> None:
                x, y = s.position
                s.position = (as_int(), y) if wid == "pos-x" else (x, as_int())
            self.apply(event.input, set_pos)
        elif wid.startswith("moon-"):
            def set_moon() -> None:
                moons = list(s.moons or (0, 0))
                moons[int(wid[-1])] = as_int()
                s.moons = tuple(moons)
            self.apply(event.input, set_moon)

    @on(Select.Changed)
    def select_changed(self, event: Select.Changed) -> None:
        wid, value, c = event.select.id or "", event.value, self.char
        if value is Select.BLANK:
            return
        if wid.startswith("sel-") and c:
            attr = wid[4:]
            self.apply(event.select, lambda: setattr(c, attr, value))
        elif wid == "transport":
            self.apply(event.select, lambda: setattr(self.save, "transport", value))

    @on(Checkbox.Changed)
    def mark_changed(self, event: Checkbox.Changed) -> None:
        c = self.char
        if not c or not (event.checkbox.id or "").startswith("mark-"):
            return
        bit = 1 << int(event.checkbox.id[5:])
        self.apply(event.checkbox,
                   lambda: setattr(c, "marks", c.marks | bit if event.value else c.marks & ~bit))

    # --- actions ----------------------------------------------------------
    def snapshot_disk(self) -> dict[str, bytes]:
        """Record the on-disk state if history doesn't have it yet; return it.

        This keeps the original files and anything the game wrote since the
        last version.
        """
        disk = self.save.read_disk()
        latest = self.history.latest()
        if latest is None:
            # Without history nothing was saved yet: what we loaded is the original.
            previous = self.save.original
            self.history.record(previous, "Original files")
        else:
            previous = self.history.files(latest)
        if previous != disk:
            changes = f.describe_changes(f.SaveGame.from_files(previous), f.SaveGame.from_files(disk))
            self.history.record(disk, "Changed outside u3edit (game?)", changes)
        return disk

    def action_save(self) -> None:
        try:
            disk = self.save.read_disk()
        except OSError as exc:
            self.set_status(f"Save failed: {exc}", error=True)
            return
        merged = disk != self.save.original
        if merged:
            # The game saved since we loaded: keep its progress, re-apply our edits.
            self.save.rebase(disk)
        if self.sync_roster:
            self.save.sync_party_to_roster()
        if merged:
            self.reload_view()
        if not self.save.dirty:
            self.notify("Nothing to save" + (" (reloaded changes from disk)" if merged else ""))
            return
        try:
            disk = self.snapshot_disk()
            changes = f.describe_changes(f.SaveGame.from_files(disk), self.save)
            written = self.save.save()
            label = "; ".join(changes[:2]) + (f" (+{len(changes) - 2} more)" if len(changes) > 2 else "")
            version = self.history.record(self.save.files(), label or "Saved", changes)
        except OSError as exc:
            self.set_status(f"Save failed: {exc}", error=True)
            return
        note = "; merged with newer files on disk" if merged else ""
        self.notify(f"Saved {', '.join(written)} (version {version.number}{note})")
        self.refresh_list()
        self.set_status(f"Editing {self.char_label}")

    def reload_view(self) -> None:
        self.refresh_list()
        self.load_party()
        view = self.query_one("#chars", ListView)
        if view.index is not None:
            self.char, self.char_label = self.resolve(view.index)
            self.load_char()

    def restore_version(self, version: Version) -> None:
        try:
            disk = self.snapshot_disk()
            files = self.history.files(version)
            self.save.write_files(files)
            changes = f.describe_changes(f.SaveGame.from_files(disk), self.save)
            self.history.record(files, f"Restored version {version.number}", changes)
        except (OSError, ValueError) as exc:
            self.notify(f"Restore failed: {exc}", severity="error")
            return
        self.reload_view()
        self.notify(f"Restored version {version.number}")

    def action_reload(self) -> None:
        if not self.save.dirty:
            self.reload_from_disk(keep_edits=False)
            return

        def done(choice: str | None) -> None:
            if choice:
                self.reload_from_disk(keep_edits=choice == "keep")

        self.push_screen(Choice(
            "You have unsaved edits. Reload the files from disk and…",
            [("keep", "Keep my edits"), ("discard", "Discard edits")],
        ), done)

    def reload_from_disk(self, keep_edits: bool) -> None:
        try:
            before = self.save.original
            disk = self.snapshot_disk()  # the game's new state lands in the history
        except OSError as exc:
            self.notify(f"Reload failed: {exc}", severity="error")
            return
        if keep_edits:
            self.save.rebase(disk)
        else:
            self.save.load(disk)
        self.reload_view()
        if disk == before:
            self.notify("Reloaded: files unchanged on disk")
        else:
            changes = f.describe_changes(f.SaveGame.from_files(before), f.SaveGame.from_files(disk))
            summary = "; ".join(changes[:3]) + (f" (+{len(changes) - 3} more)" if len(changes) > 3 else "")
            self.notify(f"Reloaded: {summary}" + (" — your edits kept on top" if keep_edits else ""))

    def action_history(self) -> None:
        self.push_screen(HistoryScreen(self.history, self.save.read_disk()))

    def action_toggle_sync(self) -> None:
        self.sync_roster = not self.sync_roster
        self.set_status(f"Editing {self.char_label}")
        self.notify(f"Roster sync {'on' if self.sync_roster else 'off'}")

    def action_heal(self) -> None:
        if self.char and not self.char.empty:
            self.char.heal()
            self.load_char()
            self.refresh_current_label()
            self.notify(f"{self.char.name} healed")

    def action_revert(self) -> None:
        """Restore the selected record from disk."""
        c = self.char
        if c is None:
            return
        disk = self.save.read_disk()["party.ult" if c.buf is self.save.party else "roster.ult"]
        c.buf[c.base : c.base + f.RECORD_SIZE] = disk[c.base : c.base + f.RECORD_SIZE]
        self.load_char()
        self.refresh_current_label()
        self.notify("Character reverted to file contents")

    async def action_quit(self) -> None:
        if not self.save.dirty:
            self.exit()
            return

        def done(quit_: bool | None) -> None:
            if quit_:
                self.exit()

        self.push_screen(Confirm("Unsaved changes. Quit anyway?", "Quit"), done)

"""Textual TUI for editing Ultima III save games."""

from __future__ import annotations

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button, Checkbox, Footer, Header, Input, Label, ListItem, ListView, Select,
    Static, TabbedContent, TabPane,
)

from . import format as f

LETTER_SELECTS = {
    "status": f.STATUS,
    "race": f.RACES,
    "klass": f.CLASSES,
    "gender": f.GENDERS,
}


def number_row(field: f.Field) -> ComposeResult:
    yield Label(field.label)
    yield Input(id=f"num-{field.key}", type="integer", max_length=2 * field.size, classes="num")


class ConfirmQuit(ModalScreen[bool]):
    def compose(self) -> ComposeResult:
        with Grid(id="dialog"):
            yield Label("Unsaved changes. Quit anyway?", id="question")
            yield Button("Quit", variant="error", id="yes")
            yield Button("Cancel", variant="primary", id="no")

    @on(Button.Pressed)
    def done(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")


class U3EditApp(App):
    TITLE = "u3edit"
    CSS = """
    #chars { width: 34; border: round $primary; }
    #editor { width: 1fr; border: round $primary; }
    .form { grid-size: 4; grid-columns: 14 1fr 14 1fr; grid-gutter: 0 1; height: auto; padding: 1 1; }
    .form Label { padding: 1 0 0 1; }
    .section { color: $accent; text-style: bold; padding: 1 1 0 1; }
    Input.-invalid { border: tall $error; }
    #status { height: 1; padding: 0 1; background: $panel; }
    #dialog { grid-size: 2; grid-gutter: 1 2; padding: 1 2; width: 50; height: 11;
              border: thick $error; background: $surface; }
    #question { column-span: 2; height: 1fr; width: 1fr; content-align: center middle; }
    ConfirmQuit { align: center middle; }
    """
    BINDINGS = [
        Binding("ctrl+s,f2", "save", "Save"),
        Binding("f3", "heal", "Heal"),
        Binding("f4", "revert", "Revert char"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, save: f.SaveGame):
        super().__init__()
        self.save = save
        self.char: f.Character | None = None
        self.char_label = ""
        self._loading = False
        self.sub_title = str(save.dir)

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
                        yield Label("Marks & Cards", classes="section")
                        with Grid(classes="form"):
                            for bit, mark in enumerate(f.MARKS):
                                yield Checkbox(mark, id=f"mark-{bit}")
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
        dirty = " [modified]" if self.save.dirty else ""
        style = "bold red" if error else ""
        self.query_one("#status", Static).update(
            f"[{style}]{text}[/]{dirty}" if style else f"{text}{dirty}"
        )

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
    def action_save(self) -> None:
        self.save.sync_party_to_roster()
        try:
            written = self.save.save()
        except OSError as exc:
            self.set_status(f"Save failed: {exc}", error=True)
            return
        if written:
            self.notify("Saved " + ", ".join(p.name for p in written)
                        + " (originals kept as *.bak)")
        else:
            self.notify("Nothing to save")
        self.set_status(f"Editing {self.char_label}")

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
        buf_path = self.save.party_path if c.buf is self.save.party else self.save.roster_path
        disk = buf_path.read_bytes()
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

        self.push_screen(ConfirmQuit(), done)

"""Staff tab: a left list of an organization's people and a right detail editor.

The bottom strip manages clash rules ("these two must never share a shift"),
which are organization-wide rather than per-person, so they live outside the
detail pane.
"""
from __future__ import annotations

import customtkinter as ctk

from config import WEEKDAYS_SHORT
from core.models import Person
from gui import dialogs
from gui.theme import ACCENT, C, FONT_UI, FONT_UI_BOLD, accent_button


class StaffTab(ctk.CTkFrame):
    """Staff list + detail editor + clash rules for the current organization."""

    def __init__(self, parent, app) -> None:
        """Build the static layout; refresh() fills in the live data."""
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.pack(fill="both", expand=True)

        self._people: list[Person] = []
        self._selected_id: int | None = None
        self._row_widgets: dict[int, ctk.CTkFrame] = {}
        self._weekday_vars: list[ctk.BooleanVar] = []
        self._placeholder: ctk.CTkLabel | None = None

        self._body = ctk.CTkFrame(self, fg_color="transparent")
        self._body.pack(fill="both", expand=True)

        self._build_body()

    # -- static layout -----------------------------------------------------
    def _build_body(self) -> None:
        """Lay out the left list panel, right detail panel and bottom clash strip."""
        self._body.grid_columnconfigure(0, weight=0)
        self._body.grid_columnconfigure(1, weight=1)
        self._body.grid_rowconfigure(0, weight=1)

        # -- left: staff list --
        left = ctk.CTkFrame(self._body, fg_color=C["panel"], width=220)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 8))
        left.grid_propagate(False)

        self._list_frame = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self._list_frame.pack(fill="both", expand=True, padx=4, pady=4)

        list_btns = ctk.CTkFrame(left, fg_color="transparent")
        list_btns.pack(fill="x", padx=4, pady=(0, 4))
        accent_button(ctk, list_btns, "+ Add person", self._add_person,
                      colour=ACCENT).pack(fill="x", pady=2)
        accent_button(ctk, list_btns, "Delete", self._delete_person,
                      colour=C["red"]).pack(fill="x", pady=2)

        # -- right: detail editor --
        self._detail = ctk.CTkScrollableFrame(self._body, fg_color=C["panel"])
        self._detail.grid(row=0, column=1, sticky="nsew")

        # -- bottom: clash rules --
        self._clash_frame = ctk.CTkFrame(self, fg_color=C["panel"])
        self._clash_frame.pack(fill="x", pady=(8, 0))

    # -- refresh -------------------------------------------------------------
    def refresh(self) -> None:
        """Reload people for the current org and rebuild the list/detail/clash panes."""
        if self._placeholder is not None:
            self._placeholder.destroy()
            self._placeholder = None

        if self.app.org_id is None:
            self._body.pack_forget()
            self._placeholder = ctk.CTkLabel(
                self, text="Create an organization to get started.",
                font=FONT_UI, text_color=C["dim"])
            self._placeholder.pack(expand=True)
            return

        if not self._body.winfo_ismapped():
            self._body.pack(fill="both", expand=True)

        self._people = self.app.db.people(self.app.org_id)
        if self._selected_id not in {p.id for p in self._people}:
            self._selected_id = self._people[0].id if self._people else None

        self._rebuild_list()
        self._rebuild_detail()
        self._rebuild_clashes()

    # -- list panel ------------------------------------------------------
    def _rebuild_list(self) -> None:
        """Destroy and recreate one row per person, marking the selection."""
        for child in self._list_frame.winfo_children():
            child.destroy()
        self._row_widgets.clear()

        for person in self._people:
            selected = person.id == self._selected_id
            row = ctk.CTkFrame(
                self._list_frame,
                fg_color=C["select"] if selected else "transparent")
            row.pack(fill="x", pady=1)

            label_text = person.name
            if not person.active:
                label_text += "  (inactive)"
            label = ctk.CTkLabel(
                row, text=label_text, font=FONT_UI, anchor="w",
                text_color=C["text"] if person.active else C["dim"])
            label.pack(fill="x", padx=8, pady=6)

            # Clicking anywhere in the row selects that person.
            for widget in (row, label):
                widget.bind("<Button-1>", lambda _e, pid=person.id: self._select(pid))
            self._row_widgets[person.id] = row

    def _select(self, person_id: int) -> None:
        """Select a person by id and redraw the list + detail pane."""
        self._selected_id = person_id
        self._rebuild_list()
        self._rebuild_detail()

    def _add_person(self) -> None:
        """Prompt for a name, create the person, then select and edit them."""
        if self.app.org_id is None:
            return
        name = dialogs.prompt_text(self, "New person", "Name")
        if not name:
            return
        person = Person(id=0, org_id=self.app.org_id, name=name)
        new_id = self.app.db.save_person(person)
        self._selected_id = new_id
        self.app.refresh_all()

    def _delete_person(self) -> None:
        """Confirm and delete the selected person."""
        person = self._current_person()
        if person is None:
            return
        if not dialogs.confirm(self, "Delete person",
                               f"Delete {person.name}? This cannot be undone."):
            return
        self.app.db.delete_person(person.id)
        self._selected_id = None
        self.app.refresh_all()

    def _current_person(self) -> Person | None:
        """The Person object matching the current selection, if any."""
        return next((p for p in self._people if p.id == self._selected_id), None)

    # -- detail panel ------------------------------------------------------
    def _rebuild_detail(self) -> None:
        """Destroy and rebuild the right-hand editor for the selected person."""
        for child in self._detail.winfo_children():
            child.destroy()
        self._weekday_vars = []

        person = self._current_person()
        if person is None:
            ctk.CTkLabel(self._detail, text="Select or add a person.",
                        font=FONT_UI, text_color=C["dim"]).pack(pady=40)
            return

        pad = {"padx": 16, "pady": (10, 2)}

        ctk.CTkLabel(self._detail, text="Name", font=FONT_UI_BOLD,
                    text_color=C["text"]).pack(anchor="w", **pad)
        name_entry = ctk.CTkEntry(self._detail, width=280)
        name_entry.insert(0, person.name)
        name_entry.pack(anchor="w", padx=16)

        active_var = ctk.BooleanVar(value=person.active)
        ctk.CTkSwitch(self._detail, text="Active", variable=active_var,
                     font=FONT_UI).pack(anchor="w", padx=16, pady=(12, 2))

        ctk.CTkLabel(self._detail, text="Max shifts per roster (blank = no cap)",
                    font=FONT_UI, text_color=C["text"]).pack(anchor="w", **pad)
        max_entry = ctk.CTkEntry(self._detail, width=120)
        max_entry.insert(0, "" if person.max_shifts is None else str(person.max_shifts))
        max_entry.pack(anchor="w", padx=16)

        ctk.CTkLabel(self._detail, text="Availability", font=FONT_UI_BOLD,
                    text_color=C["text"]).pack(anchor="w", **pad)
        week_row = ctk.CTkFrame(self._detail, fg_color="transparent")
        week_row.pack(anchor="w", padx=16)
        for i, day in enumerate(WEEKDAYS_SHORT):
            var = ctk.BooleanVar(value=i in person.available_weekdays)
            # Narrow enough that all seven fit the detail pane without the last
            # one being clipped off the edge.
            ctk.CTkCheckBox(week_row, text=day, variable=var, font=FONT_UI,
                           width=58).grid(row=0, column=i, padx=1)
            self._weekday_vars.append(var)

        preset_row = ctk.CTkFrame(self._detail, fg_color="transparent")
        preset_row.pack(anchor="w", padx=16, pady=(4, 0))
        ctk.CTkButton(preset_row, text="All", width=70,
                     command=lambda: self._set_weekdays(range(7))).pack(side="left", padx=2)
        ctk.CTkButton(preset_row, text="Weekdays", width=70,
                     command=lambda: self._set_weekdays(range(5))).pack(side="left", padx=2)
        ctk.CTkButton(preset_row, text="None", width=70,
                     command=lambda: self._set_weekdays([])).pack(side="left", padx=2)

        ctk.CTkLabel(self._detail, text="Notes", font=FONT_UI_BOLD,
                    text_color=C["text"]).pack(anchor="w", **pad)
        notes_box = ctk.CTkTextbox(self._detail, width=400, height=70)
        notes_box.insert("1.0", person.notes)
        notes_box.pack(anchor="w", padx=16)

        error_label = ctk.CTkLabel(self._detail, text="", font=FONT_UI, text_color=C["red"])
        error_label.pack(anchor="w", padx=16, pady=(6, 0))

        def _save() -> None:
            """Validate the form, then write the person back and refresh the app."""
            max_text = max_entry.get().strip()
            max_shifts = None
            if max_text:
                if not max_text.isdigit() or int(max_text) <= 0:
                    error_label.configure(
                        text="Max shifts must be a positive whole number, or blank.")
                    return
                max_shifts = int(max_text)

            name = name_entry.get().strip()
            if not name:
                error_label.configure(text="Name is required.")
                return

            person.name = name
            person.active = active_var.get()
            person.max_shifts = max_shifts
            person.available_weekdays = {i for i, v in enumerate(self._weekday_vars) if v.get()}
            person.notes = notes_box.get("1.0", "end").rstrip("\n")
            self.app.db.save_person(person)
            self.app.refresh_all()

        accent_button(ctk, self._detail, "Save", _save,
                      colour=ACCENT, width=100).pack(anchor="w", padx=16, pady=(6, 12))

        # -- blackouts --
        ctk.CTkLabel(self._detail, text="Blackouts", font=FONT_UI_BOLD,
                    text_color=C["text"]).pack(anchor="w", padx=16, pady=(4, 2))
        # height=0 so the list collapses when the person has no blackouts.
        blackout_list = ctk.CTkFrame(self._detail, fg_color="transparent", height=0)
        blackout_list.pack(anchor="w", fill="x", padx=16)

        for bid, start, end, reason in self.app.db.blackouts(person.id):
            row = ctk.CTkFrame(blackout_list, fg_color="transparent")
            row.pack(fill="x", pady=1)
            text = f"{start:%d %b %Y} - {end:%d %b %Y}"
            if reason:
                text += f"  {reason}"
            ctk.CTkLabel(row, text=text, font=FONT_UI, text_color=C["text"]).pack(
                side="left", padx=(0, 8))
            ctk.CTkButton(row, text="Remove", width=70,
                         command=lambda i=bid: self._remove_blackout(i)).pack(side="left")

        ctk.CTkButton(self._detail, text="+ Add", width=80,
                     command=self._add_blackout).pack(anchor="w", padx=16, pady=(4, 12))

    def _set_weekdays(self, indices) -> None:
        """Tick exactly the given weekday indices in the availability row."""
        indices = set(indices)
        for i, var in enumerate(self._weekday_vars):
            var.set(i in indices)

    def _add_blackout(self) -> None:
        """Prompt for a date range/reason and save it against the selected person."""
        person = self._current_person()
        if person is None:
            return
        result = dialogs.prompt_date_range(self, "Add blackout")
        if result is None:
            return
        start, end, reason = result
        self.app.db.add_blackout(person.id, start, end, reason)
        self.app.refresh_all()

    def _remove_blackout(self, blackout_id: int) -> None:
        """Delete one blackout range and refresh."""
        self.app.db.delete_blackout(blackout_id)
        self.app.refresh_all()

    # -- clash rules ---------------------------------------------------------
    def _rebuild_clashes(self) -> None:
        """Destroy and rebuild the clash-rule strip at the bottom of the tab."""
        for child in self._clash_frame.winfo_children():
            child.destroy()

        ctk.CTkLabel(self._clash_frame, text="Clash rules", font=FONT_UI_BOLD,
                    text_color=C["text"]).pack(anchor="w", padx=12, pady=(8, 2))

        by_id = {p.id: p.name for p in self._people}
        pairs = self.app.db.clashes(self.app.org_id)

        # height=0 so an empty container collapses: a bare CTkFrame otherwise
        # reserves its 200px default and squeezes the detail pane above it.
        rows = ctk.CTkFrame(self._clash_frame, fg_color="transparent", height=0)
        rows.pack(fill="x", padx=12)
        for a, b in pairs:
            if a not in by_id or b not in by_id:
                continue
            row = ctk.CTkFrame(rows, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text=f"{by_id[a]} + {by_id[b]}", font=FONT_UI,
                        text_color=C["text"]).pack(side="left", padx=(0, 8))
            ctk.CTkButton(row, text="Remove", width=70,
                         command=lambda x=a, y=b: self._remove_clash(x, y)).pack(side="left")

        add_row = ctk.CTkFrame(self._clash_frame, fg_color="transparent")
        add_row.pack(fill="x", padx=12, pady=(4, 10))

        names = [p.name for p in self._people]
        if len(names) >= 2:
            a_var = ctk.StringVar(value=names[0])
            b_var = ctk.StringVar(value=names[1])
            ctk.CTkOptionMenu(add_row, values=names, variable=a_var, width=160).pack(
                side="left", padx=(0, 4))
            ctk.CTkLabel(add_row, text="+", font=FONT_UI, text_color=C["dim"]).pack(
                side="left", padx=4)
            ctk.CTkOptionMenu(add_row, values=names, variable=b_var, width=160).pack(
                side="left", padx=4)

            def _add() -> None:
                """Add a clash rule between the two chosen names, ignoring a self-pair."""
                name_to_id = {p.name: p.id for p in self._people}
                a_id, b_id = name_to_id.get(a_var.get()), name_to_id.get(b_var.get())
                if a_id is None or b_id is None or a_id == b_id:
                    return
                self.app.db.add_clash(self.app.org_id, a_id, b_id)
                self.app.refresh_all()

            ctk.CTkButton(add_row, text="+ Add clash", command=_add).pack(side="left", padx=8)
        else:
            ctk.CTkLabel(add_row, text="Add at least two people to set a clash rule.",
                        font=FONT_UI, text_color=C["dim"]).pack(anchor="w")

    def _remove_clash(self, a: int, b: int) -> None:
        """Delete a clash rule and refresh."""
        self.app.db.delete_clash(a, b)
        self.app.refresh_all()

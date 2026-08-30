"""Shifts tab: an editable table of an organization's shift types.

Row order (``sort_order``) is the order the scheduler fills shifts in when it
builds a roster, so moving a row up/down has a real effect beyond display.
"""
from __future__ import annotations

import customtkinter as ctk

from core.models import ShiftType
from gui import dialogs
from gui.theme import ACCENT, C, FONT_UI, FONT_UI_BOLD, accent_button


class ShiftsTab(ctk.CTkFrame):
    """Editable list of shift types for the current organization."""

    def __init__(self, parent, app) -> None:
        """Build the static layout; refresh() fills in the live rows."""
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.pack(fill="both", expand=True)

        self._shifts: list[ShiftType] = []
        # One dict of widgets per shift id, so Save all can read them back.
        self._row_entries: dict[int, dict] = {}

        ctk.CTkLabel(
            self, text="Shifts are filled in this order when a roster is built.",
            font=FONT_UI, text_color=C["dim"]).pack(anchor="w", padx=4, pady=(0, 6))

        self._table = ctk.CTkScrollableFrame(self, fg_color=C["panel"])
        self._table.pack(fill="both", expand=True)

        self._error_label = ctk.CTkLabel(self, text="", font=FONT_UI, text_color=C["red"])
        self._error_label.pack(anchor="w", padx=4, pady=(4, 0))

        self._footer = ctk.CTkFrame(self, fg_color="transparent")
        self._footer.pack(fill="x", pady=(6, 0))

    # -- refresh -------------------------------------------------------------
    def refresh(self) -> None:
        """Reload shift types for the current org and rebuild the table."""
        for child in self._table.winfo_children():
            child.destroy()
        for child in self._footer.winfo_children():
            child.destroy()
        self._row_entries.clear()
        self._error_label.configure(text="")

        if self.app.org_id is None:
            ctk.CTkLabel(self._table, text="Create an organization to get started.",
                        font=FONT_UI, text_color=C["dim"]).pack(expand=True, pady=40)
            return

        self._shifts = self.app.db.shift_types(self.app.org_id)

        if not self._shifts:
            self._build_empty_state()
            return

        self._build_header_row()
        for shift in self._shifts:
            self._build_row(shift)

        accent_button(ctk, self._footer, "+ Add shift", self._add_shift,
                      colour=ACCENT, width=110).pack(side="left")
        accent_button(ctk, self._footer, "Save all", self._save_all,
                      colour=C["blue"], width=110).pack(side="left", padx=8)

    def _build_empty_state(self) -> None:
        """Explain what a shift type is and offer a one-click starter shift."""
        box = ctk.CTkFrame(self._table, fg_color="transparent")
        box.pack(expand=True, pady=40)
        ctk.CTkLabel(
            box, text="No shift types yet.", font=FONT_UI_BOLD,
            text_color=C["text"]).pack()
        ctk.CTkLabel(
            box, text=(
                "A shift type is a named block of work with a headcount,\n"
                "e.g. \"Early 06:00-14:00, needs 2\".\n"
                "At least one is required before a roster can be built."),
            font=FONT_UI, text_color=C["dim"], justify="center").pack(pady=(4, 12))
        accent_button(ctk, box, "Add a standard 'Day' shift", self._add_standard_day,
                      colour=ACCENT).pack()

    def _add_standard_day(self) -> None:
        """Create one default 'Day' shift so the empty state has a quick way out."""
        shift = ShiftType(id=0, org_id=self.app.org_id, name="Day",
                          start_time="09:00", end_time="17:00",
                          headcount=1, sort_order=0)
        self.app.db.save_shift_type(shift)
        self.refresh()

    # -- table -----------------------------------------------------------
    def _build_header_row(self) -> None:
        """Column headings above the shift rows."""
        header = ctk.CTkFrame(self._table, fg_color="transparent")
        header.pack(fill="x", padx=4, pady=(4, 2))
        for text, width in (("Name", 200), ("Start", 90), ("End", 90),
                            ("Staff needed", 100), ("", 160)):
            ctk.CTkLabel(header, text=text, font=FONT_UI_BOLD, text_color=C["dim"],
                        width=width, anchor="w").pack(side="left", padx=4)

    def _build_row(self, shift: ShiftType) -> None:
        """One editable row: name/start/end/headcount entries plus row actions."""
        row = ctk.CTkFrame(self._table, fg_color=C["row"])
        row.pack(fill="x", padx=4, pady=2)

        name_entry = ctk.CTkEntry(row, width=200)
        name_entry.insert(0, shift.name)
        name_entry.pack(side="left", padx=4, pady=6)

        start_entry = ctk.CTkEntry(row, width=90)
        start_entry.insert(0, shift.start_time)
        start_entry.pack(side="left", padx=4)

        end_entry = ctk.CTkEntry(row, width=90)
        end_entry.insert(0, shift.end_time)
        end_entry.pack(side="left", padx=4)

        headcount_entry = ctk.CTkEntry(row, width=100)
        headcount_entry.insert(0, str(shift.headcount))
        headcount_entry.pack(side="left", padx=4)

        actions = ctk.CTkFrame(row, fg_color="transparent")
        actions.pack(side="left", padx=4)
        ctk.CTkButton(actions, text="↑", width=32,
                     command=lambda s=shift: self._move(s, -1)).pack(side="left", padx=1)
        ctk.CTkButton(actions, text="↓", width=32,
                     command=lambda s=shift: self._move(s, 1)).pack(side="left", padx=1)
        ctk.CTkButton(actions, text="Delete", width=70, fg_color=C["red"],
                     hover_color=C["red"],
                     command=lambda s=shift: self._delete(s)).pack(side="left", padx=(6, 1))

        self._row_entries[shift.id] = {
            "shift": shift, "name": name_entry, "start": start_entry,
            "end": end_entry, "headcount": headcount_entry,
        }

    # -- actions -----------------------------------------------------------
    def _add_shift(self) -> None:
        """Create a new shift type appended to the end of the order."""
        shift = ShiftType(id=0, org_id=self.app.org_id, name="New shift",
                          start_time="", end_time="",
                          headcount=1, sort_order=len(self._shifts))
        self.app.db.save_shift_type(shift)
        self.refresh()

    def _delete(self, shift: ShiftType) -> None:
        """Confirm and delete one shift type."""
        if not dialogs.confirm(self, "Delete shift",
                               f"Delete '{shift.name}'? This cannot be undone."):
            return
        self.app.db.delete_shift_type(shift.id)
        self.refresh()

    def _move(self, shift: ShiftType, direction: int) -> None:
        """Swap this shift's sort_order with its neighbour in ``direction`` and save both."""
        ordered = sorted(self._shifts, key=lambda s: s.sort_order)
        idx = ordered.index(shift)
        neighbour_idx = idx + direction
        if not (0 <= neighbour_idx < len(ordered)):
            return
        neighbour = ordered[neighbour_idx]
        shift.sort_order, neighbour.sort_order = neighbour.sort_order, shift.sort_order
        self.app.db.save_shift_type(shift)
        self.app.db.save_shift_type(neighbour)
        self.refresh()

    def _save_all(self) -> None:
        """Validate every row's headcount, then write all rows back if all are valid."""
        parsed = []
        for shift_id, widgets in self._row_entries.items():
            headcount_text = widgets["headcount"].get().strip()
            if not headcount_text.isdigit():
                self._error_label.configure(
                    text=f"'{widgets['name'].get().strip() or shift_id}' needs a "
                         "whole number >= 0 for staff needed.")
                return
            parsed.append((widgets["shift"], widgets["name"].get().strip(),
                          widgets["start"].get().strip(), widgets["end"].get().strip(),
                          int(headcount_text)))

        self._error_label.configure(text="")
        for shift, name, start, end, headcount in parsed:
            shift.name = name or shift.name
            shift.start_time = start
            shift.end_time = end
            shift.headcount = headcount
            self.app.db.save_shift_type(shift)
        self.refresh()

"""Build Roster tab: the app's main screen.

Left column gathers the roster parameters (name, date range, rostered
weekdays, optional AI-assisted availability notes) and triggers the
deterministic scheduler. Right column shows the resulting table, with
Save/Copy/Export actions once a roster has been built.
"""
from __future__ import annotations

import re
import threading
from datetime import date, timedelta
from tkinter import messagebox

import customtkinter as ctk

import config
from core import ai_parse, scheduler
from core.ai_parse import AIError
from core.models import Roster
from gui import dialogs
from gui.theme import ACCENT, C, FONT_DATA, FONT_UI, FONT_UI_BOLD, accent_button


class BuildTab(ctk.CTkFrame):
    """Roster-building screen: inputs on the left, generated table on the right."""

    def __init__(self, parent, app) -> None:
        """Build the (initially empty) two-column layout; refresh() fills it in."""
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.pack(fill="both", expand=True)

        self._roster: Roster | None = None   # last roster built, for Save/Copy/Export
        self._weekday_vars: list[ctk.BooleanVar] = []
        self._placeholder: ctk.CTkLabel | None = None
        self._content: ctk.CTkFrame | None = None

        self.refresh()

    # -- top-level refresh -------------------------------------------------
    def refresh(self) -> None:
        """Rebuild the whole tab: placeholder when there is no organization."""
        for child in self.winfo_children():
            child.destroy()
        self._roster = None

        if self.app.org_id is None:
            self._placeholder = ctk.CTkLabel(
                self, text="Create an organization to get started.",
                font=FONT_UI, text_color=C["dim"])
            self._placeholder.place(relx=0.5, rely=0.5, anchor="center")
            return

        self._build_content()

    def _build_content(self) -> None:
        """Lay out the left (inputs) and right (result) columns."""
        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.pack(fill="both", expand=True, padx=10, pady=10)
        self._content.grid_columnconfigure(0, weight=1, uniform="col")
        self._content.grid_columnconfigure(1, weight=1, uniform="col")
        self._content.grid_rowconfigure(0, weight=1)

        self._build_left(self._content)
        self._build_right(self._content)

    # -- left column: inputs -----------------------------------------------
    def _build_left(self, parent) -> None:
        """Everything needed to describe the roster about to be generated."""
        left = ctk.CTkScrollableFrame(parent, fg_color=C["panel"])
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        ctk.CTkLabel(left, text="Roster name", font=FONT_UI,
                     text_color=C["text"]).pack(anchor="w", padx=12, pady=(12, 2))
        self._name_entry = ctk.CTkEntry(left, width=280)
        self._name_entry.insert(0, f"Roster w/c {date.today().isoformat()}")
        self._name_entry.pack(anchor="w", padx=12, fill="x")

        dates_row = ctk.CTkFrame(left, fg_color="transparent")
        dates_row.pack(anchor="w", padx=12, pady=(10, 0), fill="x")
        ctk.CTkLabel(dates_row, text="Start date (YYYY-MM-DD)", font=FONT_UI,
                     text_color=C["text"]).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(dates_row, text="End date (YYYY-MM-DD)", font=FONT_UI,
                     text_color=C["text"]).grid(row=0, column=1, sticky="w", padx=(12, 0))
        today = date.today()
        self._start_entry = ctk.CTkEntry(dates_row, width=130)
        self._start_entry.insert(0, today.isoformat())
        self._start_entry.grid(row=1, column=0, sticky="w")
        self._end_entry = ctk.CTkEntry(dates_row, width=130)
        self._end_entry.insert(0, (today + timedelta(days=6)).isoformat())
        self._end_entry.grid(row=1, column=1, sticky="w", padx=(12, 0))

        self._date_error = ctk.CTkLabel(left, text="", font=FONT_UI, text_color=C["red"])
        self._date_error.pack(anchor="w", padx=12, pady=(4, 0))

        ctk.CTkLabel(left, text="Roster days", font=FONT_UI,
                     text_color=C["text"]).pack(anchor="w", padx=12, pady=(12, 2))
        presets = ctk.CTkFrame(left, fg_color="transparent")
        presets.pack(anchor="w", padx=12)
        ctk.CTkButton(presets, text="All", width=70,
                      command=lambda: self._set_weekdays(range(7))).pack(side="left", padx=(0, 4))
        ctk.CTkButton(presets, text="Weekdays", width=80,
                      command=lambda: self._set_weekdays(range(5))).pack(side="left", padx=4)
        ctk.CTkButton(presets, text="Weekends", width=80,
                      command=lambda: self._set_weekdays((5, 6))).pack(side="left", padx=4)

        days_row = ctk.CTkFrame(left, fg_color="transparent")
        days_row.pack(anchor="w", padx=12, pady=(6, 0))
        self._weekday_vars = []
        for i, label in enumerate(config.WEEKDAYS_SHORT):
            var = ctk.BooleanVar(value=(i < 5))   # default: weekdays only
            # Narrow enough that all seven fit the left column without the
            # last one being clipped off the edge.
            ctk.CTkCheckBox(days_row, text=label, variable=var, width=58,
                            font=FONT_UI).grid(row=0, column=i, padx=1)
            self._weekday_vars.append(var)

        # At-a-glance readiness: how much data this org actually has to work with.
        people_count = len(self.app.db.people(self.app.org_id, active_only=True))
        shift_count = len(self.app.db.shift_types(self.app.org_id))
        ctk.CTkLabel(
            left, font=FONT_UI, text_color=C["dim"],
            text=f"{people_count} active staff, {shift_count} shift types configured.",
        ).pack(anchor="w", padx=12, pady=(14, 0))

        ctk.CTkLabel(left, text="Availability notes (optional)", font=FONT_UI,
                     text_color=C["text"]).pack(anchor="w", padx=12, pady=(14, 2))
        self._notes_box = ctk.CTkTextbox(left, height=90, font=FONT_UI,
                                         fg_color=C["row"], text_color=C["text"])
        self._notes_box.pack(anchor="w", padx=12, fill="x")

        self._ai_button = ctk.CTkButton(left, text="Parse with AI", width=140,
                                        command=self._parse_with_ai)
        self._ai_button.pack(anchor="w", padx=12, pady=(6, 0))

        accent_button(ctk, left, "Build roster", self._build_roster,
                      colour=ACCENT, height=40).pack(fill="x", padx=12, pady=(20, 12))

    def _set_weekdays(self, indices) -> None:
        """Tick exactly the given weekday indices, e.g. from a preset button."""
        wanted = set(indices)
        for i, var in enumerate(self._weekday_vars):
            var.set(i in wanted)

    # -- right column: result ------------------------------------------------
    def _build_right(self, parent) -> None:
        """Result table plus Save/Copy/Export actions."""
        right = ctk.CTkFrame(parent, fg_color=C["panel"])
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self._warning_strip = ctk.CTkLabel(
            right, text="", font=FONT_UI_BOLD, text_color=C["bg"],
            fg_color=C["yellow"], corner_radius=4, height=28)
        # Packed on demand only when there are notes to flag - see _show_roster.

        self._result_box = ctk.CTkTextbox(right, font=FONT_DATA, wrap="none",
                                          fg_color=C["row"], text_color=C["text"])
        self._result_box.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self._result_box.insert("1.0", "Build a roster to see it here.")
        self._result_box.configure(state="disabled")

        btns = ctk.CTkFrame(right, fg_color="transparent")
        btns.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        ctk.CTkButton(btns, text="Save roster", command=self._save_roster).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btns, text="Copy", command=self._copy_result).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="Export .txt", command=self._export_result).pack(side="left", padx=6)

    # -- building --------------------------------------------------------
    def _parse_dates(self) -> tuple[date, date] | None:
        """Validate the start/end entries, showing an inline error instead of raising."""
        self._date_error.configure(text="")
        try:
            start = date.fromisoformat(self._start_entry.get().strip())
            end = date.fromisoformat(self._end_entry.get().strip())
        except ValueError:
            self._date_error.configure(text="Dates must look like 2026-06-05.")
            return None
        if end < start:
            self._date_error.configure(text="End date must not be before the start date.")
            return None
        return start, end

    def _build_roster(self) -> None:
        """Gather inputs, run the deterministic scheduler, and show the result."""
        dates = self._parse_dates()
        if dates is None:
            return
        start, end = dates

        weekdays = {i for i, var in enumerate(self._weekday_vars) if var.get()}
        if not weekdays:
            self._date_error.configure(text="Tick at least one weekday to roster.")
            return

        db = self.app.db
        org_id = self.app.org_id
        people = db.people(org_id, active_only=True)
        shifts = db.shift_types(org_id)
        if not shifts:
            self._date_error.configure(text="Add at least one shift type on the Shifts tab first.")
            return
        if not people:
            self._date_error.configure(text="Add at least one active staff member on the Staff tab first.")
            return

        clashes = db.clashes(org_id)
        name = self._name_entry.get().strip() or f"Roster {start.isoformat()}"
        roster = scheduler.build_roster(org_id, name, people, shifts, clashes,
                                        start, end, weekdays)
        self._show_roster(roster, people, shifts)

    def _show_roster(self, roster: Roster, people, shifts) -> None:
        """Render a built (or reloaded) roster into the result textbox."""
        self._roster = roster
        table = scheduler.format_table(roster, people, shifts)

        if roster.notes:
            n = len(roster.notes)
            self._warning_strip.configure(
                text=f"  {n} issue{'s' if n != 1 else ''} - see Notes below the table")
            self._warning_strip.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        else:
            self._warning_strip.grid_forget()

        self._result_box.configure(state="normal")
        self._result_box.delete("1.0", "end")
        self._result_box.insert("1.0", table)
        self._result_box.configure(state="disabled")

    # -- AI parse ----------------------------------------------------------
    def _parse_with_ai(self) -> None:
        """Send the free-text notes to the configured AI provider on a background thread."""
        text = self._notes_box.get("1.0", "end").strip()
        if not text:
            return
        org_id = self.app.org_id
        people = self.app.db.people(org_id)
        if not people:
            messagebox.showinfo("Rosterm8", "Add staff first so their names can be matched.")
            return

        dates = self._parse_dates()
        if dates is None:
            return
        start, end = dates
        names = [p.name for p in people]

        settings = self.app.settings
        provider = settings.get("ai.provider")
        model = settings.get("ai.model")
        api_key = settings.api_key()

        self._ai_button.configure(state="disabled", text="Parsing...")

        def _work() -> None:
            """Background-thread body: call the provider, marshal the outcome back."""
            try:
                result = ai_parse.parse_availability(text, names, start, end,
                                                      provider, model, api_key)
            except AIError as exc:
                self.after(0, lambda: self._ai_failed(str(exc)))
                return
            self.after(0, lambda: self._ai_succeeded(result))

        threading.Thread(target=_work, daemon=True).start()

    def _ai_failed(self, message: str) -> None:
        """GUI-thread callback: re-enable the button and show the error."""
        self._ai_button.configure(state="normal", text="Parse with AI")
        messagebox.showerror("AI parse failed", message)

    def _ai_succeeded(self, result: dict) -> None:
        """GUI-thread callback: preview the proposed changes and apply on confirmation."""
        self._ai_button.configure(state="normal", text="Parse with AI")
        preview = ai_parse.describe(result)
        if not dialogs.confirm(self, "Apply these changes?", preview):
            return
        self._apply_ai_result(result)

    def _apply_ai_result(self, result: dict) -> None:
        """Write an accepted AI parse result into the database."""
        db = self.app.db
        org_id = self.app.org_id
        people = {p.name: p for p in db.people(org_id)}

        for entry in result.get("people", []):
            person = people.get(entry["name"])
            if person is None:
                continue
            if "weekdays" in entry:
                person.available_weekdays = set(entry["weekdays"])
                db.save_person(person)
            for b in entry.get("blackouts", []):
                db.add_blackout(person.id, b["start"], b["end"], b.get("reason", ""))

        for a_name, b_name in result.get("clashes", []):
            a, b = people.get(a_name), people.get(b_name)
            if a and b:
                db.add_clash(org_id, a.id, b.id)

        self.app.refresh_all()

    # -- result actions ------------------------------------------------------
    def _save_roster(self) -> None:
        """Persist the last-built roster and refresh the rest of the app."""
        if self._roster is None:
            messagebox.showinfo("Rosterm8", "Build a roster first.")
            return
        self.app.db.save_roster(self._roster)
        self.app.refresh_all()
        messagebox.showinfo("Rosterm8", "Roster saved.")

    def _copy_result(self) -> None:
        """Copy the rendered table text to the clipboard."""
        text = self._result_box.get("1.0", "end").rstrip("\n")
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)

    def _export_result(self) -> None:
        """Write the rendered table to a .txt file under config.EXPORT_DIR."""
        if self._roster is None:
            messagebox.showinfo("Rosterm8", "Build a roster first.")
            return
        config.ensure_dirs()
        safe_name = re.sub(r"[^\w\- ]+", "", self._roster.name).strip() or "roster"
        filename = f"{safe_name} {self._roster.start_date.isoformat()}.txt"
        path = config.EXPORT_DIR / filename
        text = self._result_box.get("1.0", "end").rstrip("\n")
        path.write_text(text, encoding="utf-8")
        messagebox.showinfo("Rosterm8", f"Exported to:\n{path}")

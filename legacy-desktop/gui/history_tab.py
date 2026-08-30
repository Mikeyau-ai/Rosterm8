"""History tab: browse and re-view previously saved rosters.

Left is a scrollable list of every saved roster for the current organization;
selecting one renders it with the same monospace table used on the Build tab,
with Copy/Export/Delete actions.
"""
from __future__ import annotations

import re
from tkinter import messagebox

import customtkinter as ctk

import config
from core import scheduler
from gui import dialogs
from gui.theme import C, FONT_DATA, FONT_UI, FONT_UI_BOLD


class HistoryTab(ctk.CTkFrame):
    """Saved-roster browser: list on the left, rendered table on the right."""

    def __init__(self, parent, app) -> None:
        """Build the (initially empty) layout; refresh() fills it in."""
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.pack(fill="both", expand=True)

        self._rows = []          # sqlite3.Row objects from db.roster_history
        self._row_frames: dict[int, ctk.CTkFrame] = {}   # roster id -> its list row
        self._selected_id: int | None = None

        self.refresh()

    # -- top-level refresh -------------------------------------------------
    def refresh(self) -> None:
        """Rebuild the whole tab: placeholder when there is no organization."""
        for child in self.winfo_children():
            child.destroy()
        self._row_frames = {}
        self._selected_id = None

        if self.app.org_id is None:
            ctk.CTkLabel(self, text="Create an organization to get started.",
                        font=FONT_UI, text_color=C["dim"]).place(
                relx=0.5, rely=0.5, anchor="center")
            return

        self._rows = self.app.db.roster_history(self.app.org_id)
        if not self._rows:
            ctk.CTkLabel(
                self, text="No saved rosters yet - build one on the Build Roster tab.",
                font=FONT_UI, text_color=C["dim"],
            ).place(relx=0.5, rely=0.5, anchor="center")
            return

        self._build_content()

    def _build_content(self) -> None:
        """Lay out the left (list) and right (viewer) columns."""
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=10, pady=10)
        content.grid_columnconfigure(0, weight=0, minsize=260)
        content.grid_columnconfigure(1, weight=1)
        content.grid_rowconfigure(0, weight=1)

        self._build_list(content)
        self._build_viewer(content)

        # Select the newest roster (rows are already newest-first) by default.
        self._select(self._rows[0]["id"])

    def _build_list(self, parent) -> None:
        """Scrollable list of saved rosters, newest first."""
        list_frame = ctk.CTkScrollableFrame(parent, fg_color=C["panel"], width=260)
        list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        for row in self._rows:
            span = f"{row['start_date']} to {row['end_date']}"
            created = row["created_at"].split("T")[0]
            item = ctk.CTkFrame(list_frame, fg_color=C["row"], corner_radius=4)
            item.pack(fill="x", pady=3, padx=2)
            ctk.CTkLabel(item, text=row["name"], font=FONT_UI_BOLD,
                        text_color=C["text"], anchor="w").pack(fill="x", padx=8, pady=(6, 0))
            # Span and saved-date go on separate lines: side by side they are
            # wider than the list column and the date gets clipped mid-word.
            ctk.CTkLabel(item, text=span, font=FONT_UI,
                        text_color=C["dim"], anchor="w").pack(fill="x", padx=8)
            ctk.CTkLabel(item, text=f"saved {created}", font=FONT_UI,
                        text_color=C["dimmer"], anchor="w").pack(fill="x", padx=8, pady=(0, 6))

            roster_id = row["id"]
            # Clicking anywhere on the row (or its labels) selects it.
            for widget in (item, *item.winfo_children()):
                widget.bind("<Button-1>", lambda _e, rid=roster_id: self._select(rid))
            self._row_frames[roster_id] = item

    def _build_viewer(self, parent) -> None:
        """Rendered table for the selected roster, plus Copy/Export/Delete."""
        right = ctk.CTkFrame(parent, fg_color=C["panel"])
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self._result_box = ctk.CTkTextbox(right, font=FONT_DATA, wrap="none",
                                          fg_color=C["row"], text_color=C["text"])
        self._result_box.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self._result_box.configure(state="disabled")

        btns = ctk.CTkFrame(right, fg_color="transparent")
        btns.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        ctk.CTkButton(btns, text="Copy", command=self._copy_result).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btns, text="Export .txt", command=self._export_result).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="Delete", command=self._delete_selected,
                     fg_color=C["red"], hover_color=C["warn"]).pack(side="left", padx=6)

    # -- selection -----------------------------------------------------------
    def _select(self, roster_id: int) -> None:
        """Load and render one saved roster, highlighting its row in the list."""
        for rid, frame in self._row_frames.items():
            frame.configure(fg_color=C["select"] if rid == roster_id else C["row"])
        self._selected_id = roster_id

        roster = self.app.db.load_roster(roster_id)
        if roster is None:
            return
        people = self.app.db.people(self.app.org_id)
        shifts = self.app.db.shift_types(self.app.org_id)
        table = scheduler.format_table(roster, people, shifts)

        self._result_box.configure(state="normal")
        self._result_box.delete("1.0", "end")
        self._result_box.insert("1.0", table)
        self._result_box.configure(state="disabled")

    # -- actions ---------------------------------------------------------
    def _copy_result(self) -> None:
        """Copy the currently rendered table text to the clipboard."""
        text = self._result_box.get("1.0", "end").rstrip("\n")
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)

    def _export_result(self) -> None:
        """Write the currently rendered table to a .txt file under config.EXPORT_DIR."""
        if self._selected_id is None:
            return
        row = next((r for r in self._rows if r["id"] == self._selected_id), None)
        if row is None:
            return
        config.ensure_dirs()
        safe_name = re.sub(r"[^\w\- ]+", "", row["name"]).strip() or "roster"
        filename = f"{safe_name} {row['start_date']}.txt"
        path = config.EXPORT_DIR / filename
        text = self._result_box.get("1.0", "end").rstrip("\n")
        path.write_text(text, encoding="utf-8")
        messagebox.showinfo("Rosterm8", f"Exported to:\n{path}")

    def _delete_selected(self) -> None:
        """Delete the selected roster after confirmation, then refresh the list."""
        if self._selected_id is None:
            return
        if not dialogs.confirm(self, "Delete roster",
                               "Delete this saved roster? This cannot be undone."):
            return
        self.app.db.delete_roster(self._selected_id)
        self.refresh()

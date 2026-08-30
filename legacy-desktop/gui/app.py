"""Main application window: header, organization switcher, tabs, update check.

The header owns the current organization. Every tab reads ``app.org_id`` and
implements ``refresh()``; changing the org in the dropdown simply refreshes all
of them, which is what keeps the two data layers (organization -> people) from
leaking into the individual tabs.
"""
from __future__ import annotations

import customtkinter as ctk
from tkinter import messagebox

from core import updater
from core.database import Database
from core.settings_store import Settings
from gui import theme
from gui.about_dialog import AboutWindow
from gui.build_tab import BuildTab
from gui.dialogs import prompt_text
from gui.history_tab import HistoryTab
from gui.settings_window import SettingsWindow
from gui.shifts_tab import ShiftsTab
from gui.staff_tab import StaffTab
from gui.theme import C, FONT_TAGLINE, FONT_UI, FONT_WORDMARK, accent_button
from gui.update_dialog import UpdateDialog
from version import APP_VERSION

#: Shown under the wordmark; the app has no status to report at rest.
_TAGLINE = "staff roster builder"


class App(ctk.CTk):
    """Top-level window. Owns the database, settings and all tabs."""

    def __init__(self, db: Database, settings: Settings) -> None:
        """Build the window and tabs, then select the last-used organization."""
        super().__init__()
        self.db = db
        self.settings = settings
        self.org_id: int | None = None

        self.title(f"Rosterm8  v{APP_VERSION}")
        self.geometry("1120x740")
        self.minsize(940, 620)
        self.configure(fg_color=C["bg"])
        theme.dark_titlebar(self)
        theme.apply_icon(self)

        self._settings_win: ctk.CTkToplevel | None = None
        self._about_win: ctk.CTkToplevel | None = None
        self._update_shown = False

        self._build_header()
        self._build_tabs()
        self._reload_orgs(select=self.settings.get("last.org_id"))

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Auto-update check (no-ops when running from source or when disabled).
        updater.start_check()
        self.after(4000, self._poll_update)

    # -- header ----------------------------------------------------------
    def _build_header(self) -> None:
        """Top bar: wordmark, tagline, organization switcher, Settings button."""
        bar = ctk.CTkFrame(self, fg_color=C["panel"], corner_radius=0, height=54)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        wordmark = ctk.CTkLabel(bar, text="ROSTERM8", font=FONT_WORDMARK,
                                text_color=C["text"], cursor="hand2")
        wordmark.pack(side="left", padx=(16, 4))
        wordmark.bind("<Button-1>", lambda _e: self.open_about())

        tagline = ctk.CTkLabel(bar, text=_TAGLINE, font=FONT_TAGLINE,
                               text_color=C["dim"], cursor="hand2")
        tagline.pack(side="left", padx=4)
        tagline.bind("<Button-1>", lambda _e: self.open_about())

        # Right-aligned, packed right-to-left.
        accent_button(ctk, bar, "Settings", self._open_settings,
                      colour=C["btn_off"], width=90).pack(side="right", padx=(4, 12))
        accent_button(ctk, bar, "+ Organization", self._add_org,
                      colour=theme.ACCENT, width=130).pack(side="right", padx=4)

        self._org_menu = ctk.CTkOptionMenu(
            bar, values=["(no organizations)"], command=self._on_org_selected,
            font=FONT_UI, width=220)
        self._org_menu.pack(side="right", padx=4)
        ctk.CTkLabel(bar, text="Organization", font=FONT_UI,
                     text_color=C["dim"]).pack(side="right", padx=(4, 2))

    # -- tabs ------------------------------------------------------------
    def _build_tabs(self) -> None:
        """Create the four working tabs inside a bordered frame."""
        frame = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=8,
                             border_width=2, border_color=C["border"])
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.tabs = ctk.CTkTabview(frame, fg_color=C["panel"])
        self.tabs.pack(fill="both", expand=True, padx=3, pady=3)
        for name in ("Staff", "Shifts", "Build Roster", "History"):
            self.tabs.add(name)

        self.staff_tab = StaffTab(self.tabs.tab("Staff"), self)
        self.shifts_tab = ShiftsTab(self.tabs.tab("Shifts"), self)
        self.build_tab = BuildTab(self.tabs.tab("Build Roster"), self)
        self.history_tab = HistoryTab(self.tabs.tab("History"), self)
        self.tabs.set("Build Roster")

    # -- organizations ---------------------------------------------------
    def _reload_orgs(self, select: str | int | None = None) -> None:
        """Repopulate the org dropdown and select ``select`` (or the first org)."""
        self._orgs = self.db.organizations()
        names = [o.name for o in self._orgs] or ["(no organizations)"]
        self._org_menu.configure(values=names)

        wanted = None
        if select not in (None, ""):
            wanted = next((o for o in self._orgs if str(o.id) == str(select)), None)
        target = wanted or (self._orgs[0] if self._orgs else None)

        self.org_id = target.id if target else None
        self._org_menu.set(target.name if target else "(no organizations)")
        if target:
            self.settings.set("last.org_id", target.id)
        self.refresh_all()

    def _on_org_selected(self, name: str) -> None:
        """Switch the working organization from the dropdown."""
        org = next((o for o in self._orgs if o.name == name), None)
        if org is None or org.id == self.org_id:
            return
        self.org_id = org.id
        self.settings.set("last.org_id", org.id)
        self.refresh_all()

    def _add_org(self) -> None:
        """Prompt for a name and create a new organization."""
        name = prompt_text(self, "New organization", "Organization name")
        if not name:
            return
        if any(o.name.lower() == name.lower() for o in self._orgs):
            messagebox.showerror("Rosterm8", f"'{name}' already exists.", parent=self)
            return
        new_id = self.db.add_organization(name)
        self._reload_orgs(select=new_id)

    def refresh_all(self) -> None:
        """Re-read the database into every tab. Called on any structural change."""
        for tab in (self.staff_tab, self.shifts_tab, self.build_tab, self.history_tab):
            tab.refresh()

    # -- windows ---------------------------------------------------------
    def _open_settings(self) -> None:
        """Open (or focus) the Settings window."""
        if self._settings_win is not None and self._settings_win.winfo_exists():
            self._settings_win.lift()
            self._settings_win.focus()
            return
        self._settings_win = SettingsWindow(self)

    def open_about(self) -> None:
        """Open (or focus) the About window."""
        if self._about_win is not None and self._about_win.winfo_exists():
            self._about_win.lift()
            self._about_win.focus()
            return
        self._about_win = AboutWindow(self)

    def _poll_update(self) -> None:
        """Show the update dialog once the background check finds a new version."""
        if self._update_shown:
            return
        info = updater.pending_update()
        if info:
            self._update_shown = True
            UpdateDialog(self, info)
            return
        self.after(4000, self._poll_update)

    def _on_close(self) -> None:
        """Close the database and tear the window down."""
        self.db.close()
        self.destroy()

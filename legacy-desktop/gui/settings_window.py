"""Settings window: organization admin, AI assist config, and update checks."""
from __future__ import annotations

import threading
from tkinter import messagebox

import customtkinter as ctk

from core import ai_parse, updater
from gui import dialogs
from gui.theme import C, FONT_UI, FONT_UI_BOLD, accent_button, apply_icon, dark_titlebar


class SettingsWindow(ctk.CTkToplevel):
    """Modal-ish settings window covering Organization, AI assist and Updates."""

    def __init__(self, app) -> None:
        """Build the window and every section, sized to fit the screen."""
        super().__init__(app)
        self.app = app

        self.title("Rosterm8 - Settings")
        self.configure(fg_color=C["bg"])
        dark_titlebar(self)
        apply_icon(self)
        self.transient(app)

        # Cap the height to the screen so the pinned footer stays visible even
        # on a small display.
        height = min(640, self.winfo_screenheight() - 80)
        self.geometry(f"620x{height}")
        self.minsize(560, 420)

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.grid(row=0, column=0, sticky="nsew", padx=16, pady=(16, 0))

        self._build_organization(body)
        self._build_ai(body)
        self._build_updates(body)
        self._build_footer()

        self.after(50, self._grab_and_focus)

    def _grab_and_focus(self) -> None:
        """Take input focus once the window is fully mapped, then hold the grab."""
        self.grab_set()
        self.focus_set()

    # -- Organization ------------------------------------------------------
    def _build_organization(self, parent) -> None:
        """Rename or delete the current organization."""
        section = self._section(parent, "Organization")

        if self.app.org_id is None:
            ctk.CTkLabel(section, text="No organization selected.", font=FONT_UI,
                        text_color=C["dim"]).pack(anchor="w", padx=12, pady=(0, 12))
            return

        org = next((o for o in self.app.db.organizations() if o.id == self.app.org_id), None)
        org_name = org.name if org else ""

        row = ctk.CTkFrame(section, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 8))
        self._org_entry = ctk.CTkEntry(row, width=280)
        self._org_entry.insert(0, org_name)
        self._org_entry.pack(side="left")
        ctk.CTkButton(row, text="Save", width=80,
                      command=self._rename_org).pack(side="left", padx=8)

        ctk.CTkButton(section, text="Delete organization", fg_color=C["red"],
                     hover_color=C["warn"], command=self._delete_org).pack(
            anchor="w", padx=12, pady=(0, 12))

    def _rename_org(self) -> None:
        """Persist the organization's new name and refresh the org switcher."""
        name = self._org_entry.get().strip()
        if not name:
            return
        self.app.db.rename_organization(self.app.org_id, name)
        self.app._reload_orgs(select=self.app.org_id)

    def _delete_org(self) -> None:
        """Delete the organization and everything in it, after explicit confirmation."""
        if not dialogs.confirm(
            self, "Delete organization",
            "Delete this organization? Its staff, shift types and saved "
            "rosters will all be deleted too. This cannot be undone.",
        ):
            return
        org_id = self.app.org_id
        self.app.db.delete_organization(org_id)
        self.app._reload_orgs()
        self.destroy()

    # -- AI assist -----------------------------------------------------------
    def _build_ai(self, parent) -> None:
        """Provider/model/API-key configuration for the optional AI assist."""
        section = self._section(parent, "AI assist")

        ctk.CTkLabel(
            section, font=FONT_UI, text_color=C["dim"], justify="left", wraplength=560,
            text=("Used only to read free-text availability notes on the Build "
                  "Roster tab and turn them into structured rules for your review. "
                  "The scheduler that actually builds the roster is deterministic "
                  "and never calls the AI - it only helps with data entry."),
        ).pack(anchor="w", padx=12, pady=(0, 10), fill="x")

        settings = self.app.settings
        providers = sorted(ai_parse.PROVIDERS)
        current_provider = settings.get("ai.provider")
        if current_provider not in providers:
            current_provider = providers[0]

        row1 = ctk.CTkFrame(section, fg_color="transparent")
        row1.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkLabel(row1, text="Provider", font=FONT_UI, text_color=C["text"],
                     width=90, anchor="w").pack(side="left")
        self._provider_menu = ctk.CTkOptionMenu(
            row1, values=providers, command=self._on_provider_changed, width=200)
        self._provider_menu.set(current_provider)
        self._provider_menu.pack(side="left")

        row2 = ctk.CTkFrame(section, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkLabel(row2, text="Model", font=FONT_UI, text_color=C["text"],
                     width=90, anchor="w").pack(side="left")
        self._model_entry = ctk.CTkEntry(row2, width=200)
        self._model_entry.insert(0, settings.get("ai.model"))
        self._model_entry.pack(side="left")
        self._apply_model_placeholder(current_provider)

        row3 = ctk.CTkFrame(section, fg_color="transparent")
        row3.pack(fill="x", padx=12, pady=(0, 4))
        ctk.CTkLabel(row3, text="API key", font=FONT_UI, text_color=C["text"],
                     width=90, anchor="w").pack(side="left")
        self._key_entry = ctk.CTkEntry(row3, width=200, show="*")
        self._key_entry.insert(0, settings.api_key())
        self._key_entry.pack(side="left")
        self._show_key_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(row3, text="Show", variable=self._show_key_var,
                        command=self._toggle_key_visibility, width=60).pack(side="left", padx=8)

        ctk.CTkLabel(
            section, text="The key is stored in the Windows Credential Manager, "
                         "never in the database.",
            font=FONT_UI, text_color=C["dim"]).pack(anchor="w", padx=12, pady=(0, 8))

        ctk.CTkButton(section, text="Save AI settings",
                      command=self._save_ai).pack(anchor="w", padx=12, pady=(0, 12))

    def _apply_model_placeholder(self, provider: str) -> None:
        """Show that provider's default model as the entry's placeholder text."""
        _, default_model = ai_parse.PROVIDERS.get(provider, ("", ""))
        self._model_entry.configure(placeholder_text=default_model)

    def _on_provider_changed(self, provider: str) -> None:
        """Update the model placeholder when the provider selection changes."""
        self._apply_model_placeholder(provider)

    def _toggle_key_visibility(self) -> None:
        """Flip the API key entry between masked and plain text."""
        self._key_entry.configure(show="" if self._show_key_var.get() else "*")

    def _save_ai(self) -> None:
        """Persist provider, model and API key; report failure if the key can't be stored."""
        settings = self.app.settings
        settings.set("ai.provider", self._provider_menu.get())
        settings.set("ai.model", self._model_entry.get().strip())
        if not settings.set_api_key(self._key_entry.get().strip()):
            messagebox.showerror("Rosterm8", "Could not save the API key to the "
                                             "Windows Credential Manager.", parent=self)
            return
        messagebox.showinfo("Rosterm8", "AI settings saved.", parent=self)

    # -- Updates -----------------------------------------------------------
    def _build_updates(self, parent) -> None:
        """Auto-check switch, manual check button, and the running version."""
        section = self._section(parent, "Updates")

        frozen = updater.is_frozen()
        if not frozen:
            ctk.CTkLabel(
                section, font=FONT_UI, text_color=C["dim"],
                text="Updates only apply to installed builds - this is a source run.",
            ).pack(anchor="w", padx=12, pady=(0, 8))

        self._auto_var = ctk.BooleanVar(value=updater.is_enabled() if frozen
                                        else updater.auto_check_pref())
        switch = ctk.CTkSwitch(section, text="Check for updates automatically",
                               variable=self._auto_var, command=self._toggle_auto_check,
                               font=FONT_UI)
        switch.pack(anchor="w", padx=12, pady=(0, 8))

        self._check_button = ctk.CTkButton(section, text="Check for updates now",
                                           command=self._check_now)
        self._check_button.pack(anchor="w", padx=12, pady=(0, 6))

        self._update_status = ctk.CTkLabel(section, text="", font=FONT_UI, text_color=C["dim"])
        self._update_status.pack(anchor="w", padx=12, pady=(0, 4))

        ctk.CTkLabel(section, text=f"Current version: {updater.current_version()}",
                    font=FONT_UI, text_color=C["dim"]).pack(anchor="w", padx=12, pady=(0, 12))

        if not frozen:
            switch.configure(state="disabled")
            self._check_button.configure(state="disabled")

    def _toggle_auto_check(self) -> None:
        """Persist the auto-check-on-launch preference."""
        updater.set_enabled(self._auto_var.get())

    def _check_now(self) -> None:
        """Run an update check on a background thread; report the result on the GUI thread."""
        self._check_button.configure(state="disabled")
        self._update_status.configure(text="Checking...")

        def _work() -> None:
            """Background-thread body: hit the Releases API and marshal the result back."""
            info = updater.check_now()
            self.after(0, lambda: self._check_done(info))

        threading.Thread(target=_work, daemon=True).start()

    def _check_done(self, info) -> None:
        """GUI-thread callback: show the outcome of a manual update check."""
        self._check_button.configure(state="normal")
        if info is None:
            self._update_status.configure(text="You are up to date.")
        else:
            self._update_status.configure(text=f"Update available: v{info.version}")

    # -- shared layout ---------------------------------------------------
    def _section(self, parent, title: str) -> ctk.CTkFrame:
        """A titled panel; sections stack top to bottom in the scrollable body."""
        frame = ctk.CTkFrame(parent, fg_color=C["panel"])
        frame.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(frame, text=title, font=FONT_UI_BOLD,
                    text_color=C["text"]).pack(anchor="w", padx=12, pady=(12, 8))
        return frame

    def _build_footer(self) -> None:
        """Pinned Close button, always visible regardless of scroll position."""
        footer = ctk.CTkFrame(self, fg_color=C["bg"])
        footer.grid(row=1, column=0, sticky="ew", padx=16, pady=12)
        accent_button(ctk, footer, "Close", self.destroy,
                     colour=C["btn_off"]).pack(side="right")

"""Small reusable modal dialogs shared across tabs.

Every dialog here is a CTkToplevel that blocks the caller via ``wait_window``
and hands back a plain value (str/bool/tuple) rather than exposing its own
widgets, so call sites never need to know how the dialog is built.
"""
from __future__ import annotations

from datetime import date

import customtkinter as ctk

from gui.theme import C, FONT_UI, accent_button, apply_icon, dark_titlebar


def _center_on_master(win: ctk.CTkToplevel, master, width: int, height: int) -> None:
    """Position ``win`` centred over ``master`` before it is shown."""
    master.update_idletasks()
    mx, my = master.winfo_rootx(), master.winfo_rooty()
    mw, mh = master.winfo_width(), master.winfo_height()
    x = mx + (mw - width) // 2
    y = my + (mh - height) // 2
    win.geometry(f"{width}x{height}+{max(x, 0)}+{max(y, 0)}")


def _make_modal(master, title: str, width: int, height: int) -> ctk.CTkToplevel:
    """Build a themed, centred, modal CTkToplevel shell for a dialog."""
    win = ctk.CTkToplevel(master)
    win.title(title)
    win.configure(fg_color=C["bg"])
    dark_titlebar(win)
    apply_icon(win)
    win.resizable(False, False)
    _center_on_master(win, master, width, height)
    win.transient(master)
    win.grab_set()
    return win


def prompt_text(master, title: str, label: str, initial: str = "") -> str | None:
    """Single-line text entry dialog. Returns the stripped text, or None if cancelled/empty."""
    win = _make_modal(master, title, 360, 150)
    result: list[str | None] = [None]

    ctk.CTkLabel(win, text=label, font=FONT_UI, text_color=C["text"]).pack(
        anchor="w", padx=16, pady=(16, 4))
    entry = ctk.CTkEntry(win, width=328)
    entry.insert(0, initial)
    entry.pack(padx=16)
    entry.focus_set()
    entry.select_range(0, "end")

    def _ok(_event=None) -> None:
        """Commit the entry's text as the result and close."""
        text = entry.get().strip()
        result[0] = text or None
        win.destroy()

    def _cancel() -> None:
        """Discard the dialog without setting a result."""
        win.destroy()

    entry.bind("<Return>", _ok)
    win.bind("<Escape>", lambda _e: _cancel())

    btns = ctk.CTkFrame(win, fg_color="transparent")
    btns.pack(pady=16)
    accent_button(ctk, btns, "OK", _ok, colour=C["blue"], width=90).pack(side="left", padx=4)
    ctk.CTkButton(btns, text="Cancel", command=_cancel, width=90).pack(side="left", padx=4)

    win.wait_window()
    return result[0]


def confirm(master, title: str, message: str) -> bool:
    """Yes/no confirmation dialog, styled red for destructive actions. Returns the choice."""
    win = _make_modal(master, title, 360, 140)
    result = [False]

    ctk.CTkLabel(win, text=message, font=FONT_UI, text_color=C["text"],
                 wraplength=320, justify="left").pack(padx=16, pady=(20, 8), fill="x")

    def _yes() -> None:
        """Record confirmation and close."""
        result[0] = True
        win.destroy()

    def _no() -> None:
        """Discard the dialog without confirming."""
        win.destroy()

    win.bind("<Escape>", lambda _e: _no())

    btns = ctk.CTkFrame(win, fg_color="transparent")
    btns.pack(pady=16)
    accent_button(ctk, btns, "Yes", _yes, colour=C["red"], width=90).pack(side="left", padx=4)
    ctk.CTkButton(btns, text="Cancel", command=_no, width=90).pack(side="left", padx=4)

    win.wait_window()
    return result[0]


def prompt_date_range(master, title: str) -> tuple[date, date, str] | None:
    """Start/end date + optional reason dialog for adding a blackout.

    Dates are validated with date.fromisoformat and any error is shown inline
    rather than raised. Leaving end blank reuses the start date.
    """
    win = _make_modal(master, title, 360, 260)
    result: list[tuple[date, date, str] | None] = [None]

    ctk.CTkLabel(win, text="Start date (YYYY-MM-DD)", font=FONT_UI,
                 text_color=C["text"]).pack(anchor="w", padx=16, pady=(16, 2))
    start_entry = ctk.CTkEntry(win, width=328, placeholder_text="YYYY-MM-DD")
    start_entry.pack(padx=16)

    ctk.CTkLabel(win, text="End date (YYYY-MM-DD, optional)", font=FONT_UI,
                 text_color=C["text"]).pack(anchor="w", padx=16, pady=(10, 2))
    end_entry = ctk.CTkEntry(win, width=328, placeholder_text="YYYY-MM-DD")
    end_entry.pack(padx=16)

    ctk.CTkLabel(win, text="Reason (optional)", font=FONT_UI,
                 text_color=C["text"]).pack(anchor="w", padx=16, pady=(10, 2))
    reason_entry = ctk.CTkEntry(win, width=328)
    reason_entry.pack(padx=16)

    error_label = ctk.CTkLabel(win, text="", font=FONT_UI, text_color=C["red"])
    error_label.pack(padx=16, pady=(6, 0), anchor="w")

    def _ok() -> None:
        """Validate both dates and, if they parse, set the result and close."""
        start_text = start_entry.get().strip()
        end_text = end_entry.get().strip()
        if not start_text:
            error_label.configure(text="Start date is required.")
            return
        try:
            start = date.fromisoformat(start_text)
            end = date.fromisoformat(end_text) if end_text else start
        except ValueError:
            error_label.configure(text="Dates must look like 2026-06-05.")
            return
        result[0] = (start, end, reason_entry.get().strip())
        win.destroy()

    def _cancel() -> None:
        """Discard the dialog without setting a result."""
        win.destroy()

    win.bind("<Escape>", lambda _e: _cancel())

    btns = ctk.CTkFrame(win, fg_color="transparent")
    btns.pack(pady=16)
    accent_button(ctk, btns, "OK", _ok, colour=C["blue"], width=90).pack(side="left", padx=4)
    ctk.CTkButton(btns, text="Cancel", command=_cancel, width=90).pack(side="left", padx=4)

    win.wait_window()
    return result[0]

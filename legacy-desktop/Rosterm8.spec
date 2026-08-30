# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for Rosterm8.

Produces a single windowed executable: dist/Rosterm8.exe

Notes:
* CustomTkinter ships theme JSON + fonts as package data - collected below.
* Rosterm8 has no COM / Outlook / MYOB integrations, so nothing needs
  hiddenimports named explicitly.
* AI providers (optional availability parsing) are called over plain REST
  (requests) - no vendor SDKs to bundle.
"""
import os

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []


def _bundle(pkg: str, optional: bool = False) -> None:
    """Add a package's data/binaries/submodules, skipping missing optionals."""
    if optional:
        try:
            __import__(pkg)
        except Exception:
            print(f"[Rosterm8.spec] optional package not installed, skipping: {pkg}")
            return
    d, b, h = collect_all(pkg)
    datas.extend(d)
    binaries.extend(b)
    hiddenimports.extend(h)


# Required.
_bundle("customtkinter")

# Ship the changelog so the in-app About window can show it offline.
if os.path.exists("CHANGELOG.md"):
    datas.append(("CHANGELOG.md", "."))

# The window/taskbar icon must exist at runtime too, not just be stamped into
# the exe header - iconbitmap() reads the actual file.
if os.path.exists("assets/icon.ico"):
    datas.append(("assets/icon.ico", "assets"))

# Optional feature libraries - bundled only if present at build time.
for _pkg in ("keyring.backends.Windows",):
    _bundle(_pkg, optional=True)

_icon = "assets/icon.ico" if os.path.exists("assets/icon.ico") else None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter.test", "test", "unittest", "pydoc_data"],
    noarchive=False,
)

pyz = PYZ(a.pure)

# Single-file build: pass binaries + datas straight into EXE, no COLLECT.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Rosterm8",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,              # UPX-packed exes trip AV heuristics; keep it off
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # windowed - no console pops up
    disable_windowed_traceback=False,
    icon=_icon,
)

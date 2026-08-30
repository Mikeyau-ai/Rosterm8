"""Generate assets/icon.ico and assets/logo.png for Rosterm8.

One source of truth for both: PyInstaller stamps the .ico into Rosterm8.exe and
the GUI calls iconbitmap() with the same file, so the taskbar icon and the
executable never drift apart.

Design: a purple tile (the app's signature colour - RamBo is red, InvoiceM8 is
blue) carrying a white roster grid with three cells filled in the palette green,
reading as "days assigned". Drawn at 1024 and downsampled with LANCZOS; drawing
straight at 16/32px gives jagged edges, drawing large and resizing does not.

Run after changing the artwork:  python make_icon.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parent / "assets"
ICO_OUT = ASSETS / "icon.ico"
PNG_OUT = ASSETS / "logo.png"

# Matches gui.theme.C - the family palette these tools share. At 16px the tile
# colour is most of what the eye gets, so the icon has to be recognisable by
# colour alone in a crowded taskbar.
BG = (176, 110, 216)       # purple #b06ed8
EDGE = (110, 64, 138)      # darker purple, for the grid rules
PAGE = (245, 247, 250)     # near-white page
ACCENT = (76, 175, 80)     # green   #4caf50 - a filled (rostered) cell
HEADER = (110, 64, 138)    # calendar header band

#: Windows picks the nearest size; 16 and 32 are what the taskbar actually uses.
SIZES = [16, 24, 32, 48, 64, 128, 256]

#: Which grid cells are drawn as "rostered". Chosen to sit on both rows and to
#: stay visually balanced once the icon is scaled down to 16px.
FILLED = {(0, 0), (1, 1), (2, 0), (2, 2)}


def _draw(size: int = 1024) -> Image.Image:
    """Render the icon at a large size for clean downscaling."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = size / 1024.0                      # scale helper: coords authored at 1024

    # Rounded purple tile.
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(180 * u), fill=BG)

    # Calendar body.
    left, top, right, bottom = int(190 * u), int(240 * u), int(834 * u), int(830 * u)
    d.rounded_rectangle([left, top, right, bottom], radius=int(46 * u), fill=PAGE)

    # Header band across the top of the page, with two binder rings above it.
    band_h = int(120 * u)
    d.rounded_rectangle([left, top, right, top + band_h + int(46 * u)],
                        radius=int(46 * u), fill=HEADER)
    d.rectangle([left, top + band_h, right, top + band_h + int(30 * u)], fill=HEADER)
    for rx in (int(340 * u), int(684 * u)):
        d.rounded_rectangle([rx - int(26 * u), int(160 * u),
                             rx + int(26 * u), int(300 * u)],
                            radius=int(26 * u), fill=PAGE)

    # 3x3 cell grid below the header - the roster itself.
    gx0, gy0 = left + int(56 * u), top + band_h + int(78 * u)
    cell, gap = int(150 * u), int(28 * u)
    for row in range(3):
        for col in range(3):
            x = gx0 + col * (cell + gap)
            y = gy0 + row * (cell + gap)
            if y + cell > bottom - int(30 * u):
                continue                    # keep the last row inside the page
            d.rounded_rectangle([x, y, x + cell, y + cell], radius=int(30 * u),
                                fill=ACCENT if (col, row) in FILLED else EDGE)
    return img


def main() -> int:
    """Write the multi-resolution .ico plus a 512px PNG for docs/releases."""
    ASSETS.mkdir(parents=True, exist_ok=True)
    master = _draw()
    frames = [master.resize((s, s), Image.LANCZOS) for s in SIZES]
    frames[-1].save(ICO_OUT, format="ICO",
                    sizes=[(s, s) for s in SIZES], append_images=frames[:-1])
    master.resize((512, 512), Image.LANCZOS).save(PNG_OUT, format="PNG")
    print(f"Wrote {ICO_OUT} ({', '.join(f'{s}x{s}' for s in SIZES)})")
    print(f"Wrote {PNG_OUT} (512x512)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Generate the PWA icon set from the Rosterm8 calendar mark.

Same artwork as the retired desktop app, re-rendered at the sizes a browser and
a home-screen install actually ask for. The maskable variant carries extra
padding so Android can crop it to a circle without clipping the calendar.

Run after changing the artwork:  python make_icons.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

ICONS = Path(__file__).resolve().parent / "icons"

BG = (176, 110, 216)       # purple #b06ed8 - the app's signature colour
EDGE = (110, 64, 138)      # darker purple, for the grid and header band
PAGE = (245, 247, 250)     # near-white page
ACCENT = (76, 175, 80)     # green - a filled (rostered) cell

#: Cells drawn as "rostered", chosen to stay balanced when scaled right down.
FILLED = {(0, 0), (1, 1), (2, 0), (2, 2)}


def draw(size: int = 1024, pad: float = 0.0, rounded: bool = True) -> Image.Image:
    """Render the mark at `size`, insetting by `pad` (a fraction) for maskable use."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    inset = int(size * pad)
    box = size - 2 * inset
    u = box / 1024.0                       # geometry below is authored at 1024

    def X(v):
        """Map an authored coordinate into the padded box."""
        return inset + v * u

    # Tile.
    if rounded:
        d.rounded_rectangle([inset, inset, inset + box - 1, inset + box - 1],
                            radius=int(180 * u), fill=BG)
    else:
        d.rectangle([0, 0, size, size], fill=BG)

    # Calendar body.
    left, top, right, bottom = X(190), X(240), X(834), X(830)
    d.rounded_rectangle([left, top, right, bottom], radius=int(46 * u), fill=PAGE)

    # Header band plus two binder rings.
    band_h = int(120 * u)
    d.rounded_rectangle([left, top, right, top + band_h + int(46 * u)],
                        radius=int(46 * u), fill=EDGE)
    d.rectangle([left, top + band_h, right, top + band_h + int(30 * u)], fill=EDGE)
    for rx in (X(340), X(684)):
        d.rounded_rectangle([rx - int(26 * u), X(160), rx + int(26 * u), X(300)],
                            radius=int(26 * u), fill=PAGE)

    # 3x3 grid of day cells.
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
    """Write every icon the manifest and iOS reference."""
    ICONS.mkdir(exist_ok=True)
    master = draw()

    # Standard "any" icons plus the iOS touch icon.
    for size in (180, 192, 512):
        master.resize((size, size), Image.LANCZOS).save(ICONS / f"icon-{size}.png")

    # Maskable: padded and full-bleed so Android's circle crop keeps the art.
    maskable = draw(1024, pad=0.10, rounded=False)
    maskable.resize((512, 512), Image.LANCZOS).save(ICONS / "icon-512-maskable.png")

    # Favicon for the browser tab.
    frames = [master.resize((s, s), Image.LANCZOS) for s in (16, 32, 48)]
    frames[-1].save(ICONS / "favicon.ico", format="ICO",
                    sizes=[(16, 16), (32, 32), (48, 48)], append_images=frames[:-1])

    print("Wrote:", ", ".join(sorted(p.name for p in ICONS.iterdir())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

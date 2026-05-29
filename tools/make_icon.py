"""Generate the app icon (assets/icon.png) — a white "sync" glyph on a diagonal
gradient from iGPSPORT red to intervals.icu blue (the two services it bridges).

Run it with Pillow available, e.g.:

    uv run --with pillow python tools/make_icon.py

flet build turns assets/icon.png into the Windows .ico and Android launcher
icons automatically.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

SS = 4  # supersample factor for smooth (anti-aliased) edges
SIZE = 1024 * SS
OUT = Path(__file__).resolve().parent.parent / "assets" / "icon.png"

IGP_RED = (228, 0, 43)        # iGPSPORT brand red  #E4002B
INTERVALS_BLUE = (30, 136, 229)  # intervals.icu blue  #1E88E5
WHITE = (255, 255, 255, 255)


def _lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _draw_arc_arrow(draw, cx, cy, r, start, end, width):
    """Draw a thick arc from `start`→`end` (clockwise) with an arrowhead at end."""
    draw.arc([cx - r, cy - r, cx + r, cy + r], start, end, fill=WHITE, width=width)

    th = math.radians(end)
    px, py = cx + r * math.cos(th), cy + r * math.sin(th)
    tangent = (-math.sin(th), math.cos(th))  # clockwise travel direction
    radial = (math.cos(th), math.sin(th))
    length, half = width * 1.5, width * 1.15
    tip = (px + tangent[0] * length, py + tangent[1] * length)
    b1 = (px + radial[0] * half, py + radial[1] * half)
    b2 = (px - radial[0] * half, py - radial[1] * half)
    draw.polygon([tip, b1, b2], fill=WHITE)


def main() -> None:
    # Diagonal gradient iGPSPORT-red (top-left) → intervals.icu-blue (bottom-right).
    # Built small per-pixel then upscaled (fast + smooth).
    g = 256
    small = Image.new("RGB", (g, g))
    px = small.load()
    for y in range(g):
        for x in range(g):
            px[x, y] = _lerp(IGP_RED, INTERVALS_BLUE, (x + y) / (2 * (g - 1)))
    bg = small.resize((SIZE, SIZE), Image.BILINEAR)

    # Rounded-square mask.
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, SIZE - 1, SIZE - 1], radius=int(SIZE * 0.18), fill=255
    )

    icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    icon.paste(bg, (0, 0), mask)

    draw = ImageDraw.Draw(icon)
    cx = cy = SIZE // 2
    r = int(SIZE * 0.28)
    w = int(SIZE * 0.085)
    _draw_arc_arrow(draw, cx, cy, r, 200, 340, w)  # top arrow
    _draw_arc_arrow(draw, cx, cy, r, 20, 160, w)   # bottom arrow

    OUT.parent.mkdir(parents=True, exist_ok=True)
    icon.resize((1024, 1024), Image.LANCZOS).save(OUT)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()

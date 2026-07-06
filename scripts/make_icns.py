#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "zxlive" / "icons" / "logo.png"
DST = ROOT / "zxlive" / "icons" / "logo.icns"

# Leaves a small margin
FILL = 0.92
# Base logical size, @1x filename, @2x filename
SIZES = [16, 32, 128, 256, 512]


def square_master(src: Image.Image, size: int) -> Image.Image:
    """
    Scale `src` to fit within `size`*FILL and center it on a transparent square.

    :param src: image to scale
    :param size: size in pixels
    :return: scaled image
    """
    target = int(size * FILL)

    scaled = src.copy()
    scaled.thumbnail((target, target), Image.LANCZOS)

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    x = (size - scaled.width) // 2
    y = (size - scaled.height) // 2
    canvas.paste(scaled, (x, y), scaled)

    return canvas


def main() -> None:
    src = Image.open(SRC).convert("RGBA")

    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "logo.iconset"
        iconset.mkdir()

        for base in SIZES:
            square_master(src, base).save(iconset / f"icon_{base}x{base}.png")
            square_master(src, base * 2).save(iconset / f"icon_{base}x{base}@2x.png")

        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(DST)],
            check=True,
        )

    print(f"Wrote {DST} ({DST.stat().st_size} bytes)")


if __name__ == "__main__":
    main()

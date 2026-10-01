#!/usr/bin/env python3
"""Round the corners of provider logos that carry a full-bleed plate.

18 files in assets/providers/ have an opaque plate filling all 100% of the
frame (they were supplied as square artwork with their own background). Drawn
inside `.pv-icon` — a 28x28 well with an 8px radius — the plate shows its own
square corners on top of the rounded well, so those logos read as sharp squares
while transparent logos (Alibaba and friends) read as rounded.

Fix: give every full-bleed logo the SAME corner radius as the well, by masking
it to a rounded square at a fixed radius. Transparent logos are left untouched —
their shape already comes from the artwork and they need no clipping.

The radius is expressed against the well's own ratio so it stays correct at any
display size: 8px on a 28px well == 36.57/128 at 128px.
"""
import pathlib
from PIL import Image, ImageDraw

ROOT = pathlib.Path("/data/data/com.termux/files/home/zeline-frontend")
SRC = ROOT / "assets" / "providers"

# 8px radius on the 28px well the list renders.
WELL_PX = 28.0
RADIUS_PX = 8.0
SS = 4  # supersample factor for a clean curve


def plate_fill(im):
    """Fraction of the frame that is opaque, and how many corners are opaque."""
    w, h = im.size
    corners = [im.getpixel(p)[3] > 200 for p in
               [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]]
    opaque = 0
    total = 0
    for y in range(0, h, 4):
        for x in range(0, w, 4):
            total += 1
            if im.getpixel((x, y))[3] > 200:
                opaque += 1
    return opaque / total, sum(corners)


def main():
    changed = []
    skipped = []
    for path in sorted(SRC.glob("*.png")):
        im = Image.open(path).convert("RGBA")
        fill, corners = plate_fill(im)
        # Only touch artwork that is an opaque plate corner-to-corner.
        if not (fill > 0.97 and corners == 4):
            skipped.append(path.name)
            continue

        w, h = im.size
        radius = round(w * (RADIUS_PX / WELL_PX))

        # Build the mask at high resolution, then downsample for a smooth arc.
        mask = Image.new("L", (w * SS, h * SS), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, w * SS - 1, h * SS - 1], radius=radius * SS, fill=255)
        mask = mask.resize((w, h), Image.LANCZOS)

        # Apply the mask to alpha only, so RGB is untouched.
        alpha = im.getchannel("A")
        alpha = Image.composite(alpha, Image.new("L", (w, h), 0), mask)
        out = im.copy()
        out.putalpha(alpha)
        out.save(path, "PNG", optimize=True)
        changed.append((path.name, rounding := radius))

    print(f"rounded corners on {len(changed)} full-bleed logos:")
    for name, r in changed:
        print(f"   {name:24s} radius {r}px (@{128}px art)")
    print(f"\nleft untouched (transparent artwork): {len(skipped)}")
    for n in skipped:
        print(f"   {n}")


if __name__ == "__main__":
    main()

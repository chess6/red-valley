#!/usr/bin/env python3
"""Lay out images on one labelled contact sheet. Pure compositing, no
generation or editing of pixel content -- just arranging existing images
into a grid with a caption strip under each.

  python3 tools/assetgen/contact_sheet.py --out sheet.png img1.png img2.png ...
  python3 tools/assetgen/contact_sheet.py --out sheet.png "a.png::A seed1" "b.png::B seed2"
"""
import argparse
import sys

from PIL import Image, ImageDraw, ImageFont

CELL = 512
PAD = 16
LABEL_H = 28


def build(pairs, columns, cell):
    cols = columns or min(4, len(pairs)) or 1
    rows = (len(pairs) + cols - 1) // cols
    sheet_w = cols * (cell + PAD) + PAD
    sheet_h = rows * (cell + LABEL_H + PAD) + PAD
    sheet = Image.new("RGB", (sheet_w, sheet_h), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 16)
    except Exception:
        font = ImageFont.load_default()

    for i, (path, label) in enumerate(pairs):
        r, c = divmod(i, cols)
        x = PAD + c * (cell + PAD)
        y = PAD + r * (cell + LABEL_H + PAD)
        img = Image.open(path).convert("RGB")
        img.thumbnail((cell, cell))
        ox = x + (cell - img.width) // 2
        oy = y + (cell - img.height) // 2
        sheet.paste(img, (ox, oy))
        draw.rectangle([x, y, x + cell, y + cell], outline=(90, 90, 90))
        text = label if label else path.split("/")[-1]
        draw.text((x + 4, y + cell + 4), text, fill=(230, 230, 230), font=font)
    return sheet


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--columns", type=int, default=0)
    ap.add_argument("--cell", type=int, default=CELL)
    ap.add_argument("images", nargs="+", help="path or path::label")
    args = ap.parse_args(argv)

    pairs = []
    for item in args.images:
        if "::" in item:
            path, label = item.split("::", 1)
        else:
            path, label = item, None
        pairs.append((path, label))
    sheet = build(pairs, args.columns, args.cell)
    sheet.save(args.out)
    print(f"wrote {args.out} ({sheet.width}x{sheet.height}, {len(pairs)} cells)")


if __name__ == "__main__":
    sys.exit(main())

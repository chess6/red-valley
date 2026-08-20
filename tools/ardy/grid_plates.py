"""Overlay a labelled mm grid on the ortho hand plates.

Positions are then read off the plate directly instead of eyeballed, which is
what "align explicitly from orthographic renders" needs to be defensible.
Grid coordinates are millimetres from `centre` along the plate's own right/up
axes, so a reading converts straight through hand_ortho_mapping.json.
"""
import json, os, sys
from PIL import Image, ImageDraw, ImageFont

D = "art/animation/rigify"
M = json.load(open(os.path.join(D, "hand_ortho_mapping.json")))
try:
    FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
except Exception:
    FONT = ImageFont.load_default()

for name in ("palm", "edge"):
    m = M[name]
    RES, S = m["resolution"], m["ortho_scale_m"]
    px_per_m = RES / S
    im = Image.open(os.path.join(D, "hand_%s.png" % name)).convert("RGB")
    d = ImageDraw.Draw(im)
    # grid every 10 mm, minor every 5 mm, centred on the plate centre
    for mm in range(-70, 71, 5):
        off = mm / 1000.0 * px_per_m
        x = RES / 2 + off
        y = RES / 2 - off
        major = (mm % 10 == 0)
        col = (255, 90, 60) if mm == 0 else ((90, 200, 255) if major else (60, 90, 110))
        w = 2 if mm == 0 else (1 if major else 1)
        if 0 <= x < RES: d.line([(x, 0), (x, RES)], fill=col, width=w)
        if 0 <= y < RES: d.line([(0, y), (RES, y)], fill=col, width=w)
        if major and mm != 0:
            if 0 <= x < RES: d.text((x + 3, RES - 26), "%+d" % mm, fill=(90, 200, 255), font=FONT)
            if 0 <= y < RES: d.text((6, y + 3), "%+d" % mm, fill=(90, 200, 255), font=FONT)
    lbl = {"palm": "PALM  right=+bar(mm)  up=+fing(mm)",
           "edge": "EDGE  right=+nrm(mm)  up=+fing(mm)"}[name]
    d.rectangle([0, 0, 720, 34], fill=(15, 18, 22))
    d.text((8, 6), lbl, fill=(255, 220, 120), font=FONT)
    out = os.path.join(D, "hand_%s_grid.png" % name)
    im.save(out)
    print("GRID", out, "px_per_mm=%.3f" % (px_per_m / 1000.0))

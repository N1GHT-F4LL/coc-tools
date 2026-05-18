"""
Probe an existing template against the live screen and show match confidence.
Also lets you crop a new template by specifying pixel coordinates.

Usage:
  # Show where an existing template matches (and how confident):
  python scripts/probe_and_crop.py probe icon_dark_elixir_drill_full

  # Crop a new template from the live screen and save it:
  python scripts/probe_and_crop.py crop x1 y1 x2 y2 output_name
  # e.g.: python scripts/probe_and_crop.py crop 720 480 780 560 icon_dark_elixir_drill_full_1600x900

Run from repo root.
"""
import sys
import os
import cv2
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from coc_bot.core.device import Device
from coc_bot.core.vision import vision

DEBUG_DIR = "coc_bot/logs/debug"
ASSETS_DIR = "coc_bot/assets"


def get_screen():
    device = Device()
    if not device.available:
        print("ERROR: adb not available.")
        return None
    device._check_connection()
    screen = device.get_screen()
    if screen is None:
        print("ERROR: Could not capture screen. Is the emulator running?")
    return screen


def probe(template_name):
    screen = get_screen()
    if screen is None:
        return

    vision.load_assets(ASSETS_DIR)
    if template_name not in vision.cache:
        print(f"ERROR: '{template_name}' not found in asset cache.")
        print("Available keys containing that string:")
        for k in sorted(vision.cache):
            if template_name.lower() in k.lower():
                print(f"  {k}")
        return

    template = vision.cache[template_name]
    screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    th, tw = template.shape[:2]
    sh, sw = screen_gray.shape[:2]
    print(f"Screen: {sw}x{sh}  Template '{template_name}': {tw}x{th}")

    best_val = -1.0
    best_loc = None
    best_scale = None
    scales = (1.0, 0.75, 1.25, 0.5, 1.5, 0.6, 0.85)
    for s in scales:
        nh, nw = int(th * s), int(tw * s)
        if nh < 8 or nw < 8 or nh > sh or nw > sw:
            continue
        if s == 1.0:
            scaled = template
        else:
            interp = cv2.INTER_AREA if s < 1.0 else cv2.INTER_CUBIC
            scaled = cv2.resize(template, (nw, nh), interpolation=interp)
        res = cv2.matchTemplate(screen_gray, scaled, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if max_val > best_val:
            best_val = max_val
            best_loc = max_loc
            best_scale = s

    print(f"Best confidence: {best_val:.3f}  (threshold=0.7)  at {best_loc}  scale={best_scale}")

    # Draw match rectangle on debug image
    if best_loc:
        nh = int(th * best_scale)
        nw = int(tw * best_scale)
        x, y = best_loc
        cx, cy = x + nw // 2, y + nh // 2
        debug_img = screen.copy()
        color = (0, 255, 0) if best_val >= 0.7 else (0, 0, 255)
        cv2.rectangle(debug_img, (x, y), (x + nw, y + nh), color, 2)
        cv2.putText(debug_img, f"{best_val:.3f}", (x, max(0, y - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        os.makedirs(DEBUG_DIR, exist_ok=True)
        out = os.path.join(DEBUG_DIR, f"probe_{template_name}.png")
        cv2.imwrite(out, debug_img)
        print(f"Debug image saved: {out}  (green=match, red=below threshold)")
        print(f"Center of best match: ({cx}, {cy})")
        print()
        if best_val < 0.7:
            print("Tip: confidence below threshold. Open the debug image to see where it's looking.")
            print("     If the location looks wrong, crop a fresh template:")
            print(f"     python scripts/probe_and_crop.py crop x1 y1 x2 y2 {template_name}_1600x900")


def crop_template(x1, y1, x2, y2, output_name):
    screen = get_screen()
    if screen is None:
        return

    if not output_name.endswith('.png'):
        output_name += '.png'

    cropped = screen[y1:y2, x1:x2]
    if cropped.size == 0:
        print(f"ERROR: Empty crop from ({x1},{y1}) to ({x2},{y2}).")
        return

    out_path = os.path.join(ASSETS_DIR, output_name)
    cv2.imwrite(out_path, cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY))
    print(f"Saved template: {out_path}  size={cropped.shape[1]}x{cropped.shape[0]} (wxh)")

    # Self-match verification
    gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
    res = cv2.matchTemplate(gray, gray, cv2.TM_CCOEFF_NORMED)
    _, self_conf, _, _ = cv2.minMaxLoc(res)
    print(f"Self-match confidence: {self_conf:.3f}  (should be 1.000)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "probe" and len(sys.argv) >= 3:
        probe(sys.argv[2])
    elif cmd == "crop" and len(sys.argv) >= 7:
        try:
            x1, y1, x2, y2 = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
        except ValueError:
            print("ERROR: coordinates must be integers.")
            sys.exit(1)
        crop_template(x1, y1, x2, y2, sys.argv[6])
    else:
        print(__doc__)
        sys.exit(1)

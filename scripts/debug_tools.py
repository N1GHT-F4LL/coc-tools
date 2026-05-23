import os
import sys
import json
import cv2
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "coc_bot"))

from core.device import Device
from core.vision import vision
from core.logging_utils import setup_logging

logger = logging.getLogger(__name__)


def _load_settings():
    try:
        with open("coc_bot/settings.json") as f:
            return json.load(f)
    except Exception:
        return {}


def capture_live_screen():
    """Capture and save the current device screen for debugging."""
    settings = _load_settings()
    serial = settings.get("device", {}).get("serial")
    device = Device(serial=serial)

    if not device.available:
        print("ERROR: adb not available")
        return

    screen = device.get_screen()

    if screen is None:
        print("ERROR: Could not capture screen")
        return

    debug_dir = os.path.join('coc_bot', 'logs', 'debug')
    os.makedirs(debug_dir, exist_ok=True)

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_path = os.path.join(debug_dir, f"live_screen_{ts}.png")

    cv2.imwrite(out_path, screen)
    print(f"[OK] Screen captured: {out_path}")
    print(f"[OK] Resolution: {screen.shape[1]}x{screen.shape[0]} (width x height)")


def list_loaded_assets(filter_keyword=None):
    """List all assets loaded in the vision cache."""
    vision.load_assets("coc_bot/assets")

    print(f"\n[OK] Total assets loaded: {len(vision.cache)}")

    if filter_keyword:
        filtered = {k: v for k, v in sorted(vision.cache.items()) if filter_keyword.lower() in k.lower()}
        print(f"\n[OK] Assets matching '{filter_keyword}':")
        for i, key in enumerate(filtered.keys(), 1):
            print(f"  {i:3d}. {key}")
    else:
        print(f"\nAsset keys (sorted, showing all {len(vision.cache)} assets):")
        for i, key in enumerate(sorted(vision.cache.keys()), 1):
            print(f"  {i:3d}. {key}")


if __name__ == "__main__":
    setup_logging(logging.INFO)

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python scripts/debug_tools.py capture          - Capture current screen")
        print("  python scripts/debug_tools.py assets           - List all loaded assets")
        print("  python scripts/debug_tools.py assets <keyword> - List assets matching keyword")
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "capture":
        capture_live_screen()
    elif cmd == "assets":
        keyword = sys.argv[2] if len(sys.argv) > 2 else None
        list_loaded_assets(filter_keyword=keyword)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)

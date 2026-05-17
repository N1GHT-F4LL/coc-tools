import cv2
import numpy as np
from core.device import device

def test_match():
    print("Capturing screen...")
    screen = device.get_screen()
    if screen is None:
        print("Failed to get screen.")
        return

    # Try both Attack and Shop buttons
    for img_name in ['coc_bot/assets/buildings/icon_attack.png', 'coc_bot/assets/ui/btn_shop.png']:
        print(f"\nTesting {img_name}...")
        template = cv2.imread(img_name, cv2.IMREAD_GRAYSCALE)
        if template is None:
            print("  Image file not found.")
            continue
            
        screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        
        # Test 1: Exact size match
        res = cv2.matchTemplate(screen_gray, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)
        print(f"  Exact size match score: {max_val:.3f} (needs 0.700 to pass)")
        
        # Test 2: If score is low, maybe the asset is a different size. Let's test resizing the template.
        if max_val < 0.7:
            print("  Score too low. Testing different scales...")
            best_scale = 1.0
            best_val = max_val
            for scale in [0.5, 0.75, 0.9, 1.1, 1.25, 1.5]:
                try:
                    w = int(template.shape[1] * scale)
                    h = int(template.shape[0] * scale)
                    resized = cv2.resize(template, (w, h))
                    res = cv2.matchTemplate(screen_gray, resized, cv2.TM_CCOEFF_NORMED)
                    _, val, _, _ = cv2.minMaxLoc(res)
                    if val > best_val:
                        best_val = val
                        best_scale = scale
                except: pass
            print(f"  Best scaled match score: {best_val:.3f} at scale {best_scale}x")

if __name__ == "__main__":
    test_match()
import cv2
import os

def auto_crop_anchor():
    img_path = "coc_bot/logs/debug/live_screen.png"
    if not os.path.exists(img_path):
        print("live_screen.png not found.")
        return

    img = cv2.imread(img_path)
    if img is None:
        print("Failed to load image.")
        return

    h, w = img.shape[:2]
    
    # CoC Attack button is usually bottom-left. 
    # Let's crop a box 10% from bottom, 5% from left.
    # Adjust these ratios if it misses.
    crop_w = int(w * 0.15)
    crop_h = int(h * 0.15)
    
    x1 = int(w * 0.02) # 2% from left
    y1 = int(h * 0.75) # 75% down (bottom quarter)
    x2 = x1 + crop_w
    y2 = y1 + crop_h

    attack_crop = img[y1:y2, x1:x2]
    
    out_path = "coc_bot/assets/buildings/icon_attack.png"
    cv2.imwrite(out_path, attack_crop)
    print(f"Auto-cropped bottom-left region and saved to {out_path}.")
    print("Run `python coc_bot/main.py` now.")

if __name__ == "__main__":
    auto_crop_anchor()
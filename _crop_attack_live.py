import cv2
from pathlib import Path

img_path = Path(r'd:/coc-tools/coc_bot/logs/debug/live_screen.png')
out_path = Path(r'd:/coc-tools/coc_bot/assets_v2/buttons/attack/btn_attack.png')
img = cv2.imread(str(img_path))
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

# Green attack button mask
mask = cv2.inRange(hsv, (35, 60, 60), (95, 255, 255))
mask = cv2.medianBlur(mask, 5)
num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
H, W = img.shape[:2]

cands = []
for i in range(1, num):
    x, y, w, h, area = stats[i]
    ar = w / float(h) if h else 0
    if area < 5000:
        continue
    # likely large green button around lower-right area
    if x > W * 0.55 and y > H * 0.65 and 1.4 <= ar <= 4.5:
        cands.append((area, x, y, w, h, ar))

if not cands:
    raise SystemExit('No attack button candidate found')

cands.sort(reverse=True)
_, x, y, w, h, ar = cands[0]
pad = 10
x1 = max(0, x - pad)
y1 = max(0, y - pad)
x2 = min(W, x + w + pad)
y2 = min(H, y + h + pad)

crop = img[y1:y2, x1:x2]
out_path.parent.mkdir(parents=True, exist_ok=True)
cv2.imwrite(str(out_path), crop)
print('saved', out_path)
print('screen', img.shape, 'crop', crop.shape, 'box', (x1,y1,x2,y2))

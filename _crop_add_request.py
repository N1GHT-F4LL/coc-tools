import cv2
from pathlib import Path
img=cv2.imread(r'd:/coc-tools/coc_bot/logs/debug/live_screen.png')
out=Path(r'd:/coc-tools/coc_bot/assets_v2/buttons/attack')
out.mkdir(parents=True, exist_ok=True)
# Detected boxes from green mask
boxes={
 'btn_add_available.png': (1262,694,141,61),
 'btn_request_clan_castle_available.png': (1424,695,141,60),
}
for name,(x,y,w,h) in boxes.items():
 pad=10
 x1=max(0,x-pad); y1=max(0,y-pad); x2=min(img.shape[1],x+w+pad); y2=min(img.shape[0],y+h+pad)
 crop=img[y1:y2,x1:x2]
 cv2.imwrite(str(out/name),crop)
 print(name,crop.shape)

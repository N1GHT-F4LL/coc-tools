import cv2
from pathlib import Path
img=cv2.imread(r'd:/coc-tools/coc_bot/logs/debug/live_screen.png')
# detected button box
x,y,w,h = 1263,773,302,61
pad=12
x1=max(0,x-pad); y1=max(0,y-pad); x2=min(img.shape[1],x+w+pad); y2=min(img.shape[0],y+h+pad)
crop=img[y1:y2,x1:x2]
out=Path(r'd:/coc-tools/coc_bot/assets_v2/buttons/attack/btn_attack.png')
out.parent.mkdir(parents=True, exist_ok=True)
cv2.imwrite(str(out), crop)
print('saved', out, 'shape', crop.shape)

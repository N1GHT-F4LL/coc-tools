import cv2
from pathlib import Path
base=Path(r'd:/coc-tools/coc_bot')
img=cv2.imread(str(base/'logs/debug/live_screen_trash.png'))
# top-left from match + template size
x,y,w,h = 1205,410,36,42
pad=8
x1=max(0,x-pad); y1=max(0,y-pad); x2=min(img.shape[1],x+w+pad); y2=min(img.shape[0],y+h+pad)
crop=img[y1:y2,x1:x2]
out=base/'assets_v2/buttons/attack/btn_delete_troop.png'
cv2.imwrite(str(out),crop)
print('saved',out,'shape',crop.shape)

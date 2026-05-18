import cv2
from pathlib import Path
base=Path(r'd:/coc-tools/coc_bot')
img=cv2.imread(str(base/'logs/debug/live_screen.png'))
# located from match: top-left (1328,579), shape (121,258)
x,y,w,h=1328,579,258,121
pad=8
x1=max(0,x-pad); y1=max(0,y-pad); x2=min(img.shape[1],x+w+pad); y2=min(img.shape[0],y+h+pad)
crop=img[y1:y2,x1:x2]
out=base/'assets_v2/buttons/attack/btn_next_enemy.png'
cv2.imwrite(str(out),crop)
print('wrote',out,'shape',crop.shape)

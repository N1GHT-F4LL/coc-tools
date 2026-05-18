import cv2, numpy as np
from pathlib import Path
base=Path(r'd:/coc-tools')
img=cv2.imread(str(base/'coc_bot/logs/debug/timeout_btn_find_a_match_20260518_115017.png'))
hsv=cv2.cvtColor(img,cv2.COLOR_BGR2HSV)
# orange/yellow button mask
mask=cv2.inRange(hsv,(10,80,120),(40,255,255))
mask=cv2.medianBlur(mask,5)
num,labels,stats,cent=cv2.connectedComponentsWithStats(mask,8)
H,W=img.shape[:2]
cands=[]
for i in range(1,num):
    x,y,w,h,area=stats[i]
    if area<5000: continue
    ar=w/float(h)
    # Find-a-match button expected in lower-left quadrant and wide rectangle
    if x < W*0.55 and y > H*0.45 and 1.8 <= ar <= 4.5 and h>40 and w>120:
        cands.append((area,x,y,w,h,ar))
print('cands',len(cands))
for c in sorted(cands, reverse=True)[:10]:
    print(c)
if not cands:
    raise SystemExit('no candidate')
# choose largest candidate and pad a little
_,x,y,w,h,_=sorted(cands, reverse=True)[0]
pad=8
x1=max(0,x-pad); y1=max(0,y-pad); x2=min(W,x+w+pad); y2=min(H,y+h+pad)
crop=img[y1:y2,x1:x2]
out=base/'coc_bot/assets/btn_find_a_match.png'
cv2.imwrite(str(out),crop)
print('wrote',out,'shape',crop.shape,'box',x1,y1,x2,y2)

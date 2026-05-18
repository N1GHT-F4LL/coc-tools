import cv2, numpy as np
from pathlib import Path
base=Path(r'd:/coc-tools')
sg=cv2.imread(str(base/'coc_bot/logs/debug/timeout_btn_find_a_match_20260518_115017.png'),cv2.IMREAD_GRAYSCALE)
tg=cv2.imread(str(base/'coc_bot/assets/btn_find_a_match.png'),cv2.IMREAD_GRAYSCALE)
ts=cv2.resize(tg,(int(tg.shape[1]*1.5),int(tg.shape[0]*1.5)),interpolation=cv2.INTER_CUBIC)
r=cv2.matchTemplate(sg,ts,cv2.TM_CCOEFF_NORMED)
res=[]
rm=r.copy()
for i in range(8):
    _,mv,_,ml=cv2.minMaxLoc(rm)
    if mv<0.2: break
    res.append((float(mv),ml))
    x,y=ml
    h,w=ts.shape[:2]
    rm[max(0,y-40):min(rm.shape[0],y+h+40),max(0,x-40):min(rm.shape[1],x+w+40)] = -1
print('top matches:')
for v,(x,y) in res:
    print(f'{v:.4f} at ({x},{y})')

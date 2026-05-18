import cv2
from pathlib import Path
base=Path(r'd:/coc-tools/coc_bot')
s=cv2.imread(str(base/'logs/debug/live_screen_trash.png'),cv2.IMREAD_GRAYSCALE)
t=cv2.imread(str(base/'assets/Smart_Auto_train/trash_icon.png'),cv2.IMREAD_GRAYSCALE)
best=(-1,None,None)
for sc in [1.0,0.75,1.25,0.5,1.5,0.6,0.85]:
    h,w=t.shape[:2]
    nh,nw=int(h*sc),int(w*sc)
    if nh<8 or nw<8 or nh>s.shape[0] or nw>s.shape[1]:
        continue
    ts=t if sc==1.0 else cv2.resize(t,(nw,nh),interpolation=cv2.INTER_AREA if sc<1 else cv2.INTER_CUBIC)
    r=cv2.matchTemplate(s,ts,cv2.TM_CCOEFF_NORMED)
    _,mv,_,ml=cv2.minMaxLoc(r)
    if mv>best[0]: best=(mv,ml,ts.shape)
print(best)

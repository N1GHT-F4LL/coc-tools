import cv2
from pathlib import Path
base=Path(r'd:/coc-tools')
s=cv2.imread(str(base/'coc_bot/logs/debug/timeout_btn_find_a_match_20260518_115017.png'),cv2.IMREAD_GRAYSCALE)
t=cv2.imread(str(base/'coc_bot/assets/btn_find_a_match.png'),cv2.IMREAD_GRAYSCALE)
for scale in [1.0,0.75,1.25,0.5,1.5,0.6,0.85]:
    h,w=t.shape[:2]
    nh,nw=int(h*scale),int(w*scale)
    if nh<8 or nw<8 or nh>s.shape[0] or nw>s.shape[1]:
        continue
    ts=t if scale==1.0 else cv2.resize(t,(nw,nh),interpolation=cv2.INTER_AREA if scale<1 else cv2.INTER_CUBIC)
    r=cv2.matchTemplate(s,ts,cv2.TM_CCOEFF_NORMED)
    _,mv,_,ml=cv2.minMaxLoc(r)
    print(scale,round(float(mv),4),ml,ts.shape)

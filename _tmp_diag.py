import cv2, numpy as np
from pathlib import Path
base=Path(r'd:/coc-tools')
screen=cv2.imread(str(base/'coc_bot/logs/debug/timeout_btn_find_a_match_20260518_115017.png'))
tpl=cv2.imread(str(base/'coc_bot/assets/btn_find_a_match.png'))
sg=cv2.cvtColor(screen,cv2.COLOR_BGR2GRAY)
tg=cv2.cvtColor(tpl,cv2.COLOR_BGR2GRAY)
scales=[1.0,0.75,1.25,0.5,1.5,0.6,0.85]
best=(-1,None,None,None)
for s in scales:
    h,w=tg.shape[:2]
    nh,nw=int(h*s),int(w*s)
    if nh<8 or nw<8 or nh>sg.shape[0] or nw>sg.shape[1]:
        continue
    ts=tg if s==1.0 else cv2.resize(tg,(nw,nh),interpolation=cv2.INTER_AREA if s<1 else cv2.INTER_CUBIC)
    r=cv2.matchTemplate(sg,ts,cv2.TM_CCOEFF_NORMED)
    _,mv,_,ml=cv2.minMaxLoc(r)
    if mv>best[0]:
        best=(mv,s,ml,ts.shape)
print('best',best)
score,s,ml,shape=best
h,w=shape
x,y=ml
crop=screen[y:y+h,x:x+w]
vis=screen.copy()
cv2.rectangle(vis,(x,y),(x+w,y+h),(0,0,255),2)
out=base/'coc_bot/logs/debug/_diagnose_find_match_overlay.png'
cv2.imwrite(str(out),vis)
print('overlay',out)
print('tpl_shape',tpl.shape,'match_shape',crop.shape)
print('mean_absdiff',float(np.mean(cv2.absdiff(cv2.resize(tpl,(w,h)),crop))))

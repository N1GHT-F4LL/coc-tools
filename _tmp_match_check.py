import cv2, glob, os
screen = cv2.imread(r'd:\\coc-tools\\coc_bot\\logs\\debug\\timeout_btn_find_a_match_20260518_114345.png', cv2.IMREAD_GRAYSCALE)
assets = glob.glob(r'd:\\coc-tools\\coc_bot\\assets\\*.png')
cands = [p for p in assets if any(k in os.path.basename(p).lower() for k in ['start','next','attack','end','return','button'])]
rows=[]
for p in cands:
    t=cv2.imread(p, cv2.IMREAD_GRAYSCALE)
    if t is None:
        continue
    h,w=t.shape[:2]
    sh,sw=screen.shape[:2]
    best=-1.0
    for s in [1.0,0.75,1.25,0.5,1.5,0.6,0.85]:
        nh,nw=int(h*s),int(w*s)
        if nh<8 or nw<8 or nh>sh or nw>sw:
            continue
        tt=t if s==1.0 else cv2.resize(t,(nw,nh),interpolation=cv2.INTER_AREA if s<1 else cv2.INTER_CUBIC)
        r=cv2.matchTemplate(screen,tt,cv2.TM_CCOEFF_NORMED)
        _,mv,_,_=cv2.minMaxLoc(r)
        if mv>best:
            best=mv
    rows.append((best, os.path.basename(p)))
rows.sort(reverse=True)
for score,name in rows[:20]:
    print('{:.4f}\t{}'.format(score,name))

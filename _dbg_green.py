import cv2
from pathlib import Path
img=cv2.imread(r'd:/coc-tools/coc_bot/logs/debug/live_screen.png')
print('shape',img.shape)
hsv=cv2.cvtColor(img,cv2.COLOR_BGR2HSV)
mask=cv2.inRange(hsv,(30,40,40),(100,255,255))
num,_,stats,_=cv2.connectedComponentsWithStats(mask,8)
rows=[]
for i in range(1,num):
 x,y,w,h,a=stats[i]
 if a>1000:
  rows.append((a,x,y,w,h,w/float(h)))
rows=sorted(rows, reverse=True)[:20]
for r in rows: print(r)

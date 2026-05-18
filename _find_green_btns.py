import cv2
img=cv2.imread(r'd:/coc-tools/coc_bot/logs/debug/live_screen.png')
hsv=cv2.cvtColor(img,cv2.COLOR_BGR2HSV)
mask=cv2.inRange(hsv,(30,40,40),(100,255,255))
num,_,stats,_=cv2.connectedComponentsWithStats(mask,8)
H,W=img.shape[:2]
rows=[]
for i in range(1,num):
 x,y,w,h,a=stats[i]
 if a<1500: continue
 if x>W*0.45 and y>H*0.45:
  rows.append((a,x,y,w,h,w/float(h)))
for r in sorted(rows, reverse=True)[:20]:
 print(r)
print('shape',img.shape)

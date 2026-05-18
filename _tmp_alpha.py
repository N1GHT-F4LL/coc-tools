import cv2
p=r'd:/coc-tools/coc_bot/assets/btn_find_a_match.png'
a=cv2.imread(p,cv2.IMREAD_UNCHANGED)
print('shape',a.shape,'dtype',a.dtype)
if len(a.shape)==3 and a.shape[2]==4:
    alpha=a[:,:,3]
    print('alpha min/max/nonzero',int(alpha.min()),int(alpha.max()),int((alpha>0).sum()),'/',alpha.size)

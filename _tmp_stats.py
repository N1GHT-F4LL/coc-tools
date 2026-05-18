import cv2, numpy as np
p=r'd:/coc-tools/coc_bot/assets/btn_find_a_match.png'
i=cv2.imread(p)
print('mean',i.mean(axis=(0,1)),'std',i.std(axis=(0,1)),'min',i.min(),'max',i.max())

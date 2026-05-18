from pathlib import Path
import csv
from PIL import Image
root = Path(r'd:/coc-tools/coc_bot/assets_v2')
out = root / 'asset_review_checklist.csv'
rows=[]
for p in sorted(root.rglob('*.png')):
    rel=p.relative_to(root).as_posix()
    parts=rel.split('/')
    cat=parts[0] if parts else ''
    sub=parts[1] if len(parts)>1 else ''
    with Image.open(p) as im:
        w,h=im.size
    rows.append([rel,cat,sub,p.stem,w,h,''])
with out.open('w',newline='',encoding='utf-8') as f:
    wr=csv.writer(f); wr.writerow(['path','category','subcategory','filename_stem','width','height','notes']); wr.writerows(rows)
print('updated',out,'rows',len(rows))

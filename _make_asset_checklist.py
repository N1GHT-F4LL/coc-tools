from pathlib import Path
import csv
from PIL import Image

root = Path(r'd:/coc-tools/coc_bot/assets_v2')
out = root / 'asset_review_checklist.csv'

rows = []
for p in sorted(root.rglob('*.png')):
    rel = p.relative_to(root).as_posix()
    parts = rel.split('/')
    category = parts[0] if parts else ''
    subcategory = parts[1] if len(parts) > 1 else ''
    try:
        with Image.open(p) as im:
            w, h = im.size
    except Exception:
        w, h = '', ''
    rows.append([rel, category, subcategory, p.stem, w, h, ''])

with out.open('w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['path', 'category', 'subcategory', 'filename_stem', 'width', 'height', 'notes'])
    writer.writerows(rows)

print(f'WROTE={out}')
print(f'TOTAL_IMAGES={len(rows)}')

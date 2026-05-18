import re
from pathlib import Path

root = Path(r'd:/coc-tools/coc_bot/assets_v2')


def norm(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r'[^a-z0-9]+', '_', s)
    s = re.sub(r'_+', '_', s).strip('_')
    return s

renamed = []
for p in sorted(root.rglob('*')):
    if not p.is_file():
        continue
    stem = norm(p.stem)
    ext = p.suffix.lower()
    if not stem:
        continue
    new_name = stem + ext
    if new_name == p.name:
        continue

    target = p.with_name(new_name)
    i = 1
    while target.exists() and target.resolve() != p.resolve():
        target = p.with_name(f"{stem}_{i}{ext}")
        i += 1

    p.rename(target)
    renamed.append((str(p), str(target)))

print(f'RENAMED={len(renamed)}')
for old, new in renamed[:120]:
    print(f'{old} -> {new}')
if len(renamed) > 120:
    print(f'... {len(renamed)-120} more')

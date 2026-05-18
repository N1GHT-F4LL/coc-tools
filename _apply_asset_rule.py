import re
from pathlib import Path

root = Path(r'd:/coc-tools/coc_bot/assets_v2')

# 1) global: drop common resolution suffix patterns
res_pat = re.compile(r'_(\d{3,4}x\d{3,4})$')

renamed = []
for p in sorted(root.rglob('*.png')):
    stem = p.stem
    new_stem = res_pat.sub('', stem)
    if new_stem != stem:
        target = p.with_name(new_stem + p.suffix)
        i = 1
        while target.exists() and target.resolve() != p.resolve():
            target = p.with_name(f"{new_stem}_{i}{p.suffix}")
            i += 1
        p.rename(target)
        renamed.append((str(p), str(target)))

# 2) buttons folder context cleanup
button_rules = {
    'attack': ['_attack'],
    'home': ['_home'],
    'battle': ['_results', '_battle'],
    'popup': ['_popup'],
}

for sub, suffixes in button_rules.items():
    d = root / 'buttons' / sub
    if not d.exists():
        continue
    for p in sorted(d.glob('*.png')):
        stem = p.stem
        new_stem = stem
        changed = True
        while changed:
            changed = False
            for s in suffixes:
                if new_stem.endswith(s):
                    new_stem = new_stem[: -len(s)]
                    changed = True
        new_stem = re.sub(r'_+', '_', new_stem).strip('_')
        if new_stem != stem and new_stem:
            target = p.with_name(new_stem + p.suffix)
            i = 1
            while target.exists() and target.resolve() != p.resolve():
                target = p.with_name(f"{new_stem}_{i}{p.suffix}")
                i += 1
            p.rename(target)
            renamed.append((str(p), str(target)))

print(f'RENAMED={len(renamed)}')
for old, new in renamed[:120]:
    print(f'{old} -> {new}')
if len(renamed) > 120:
    print(f'... {len(renamed)-120} more')

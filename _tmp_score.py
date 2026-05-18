import cv2
from pathlib import Path

base = Path(r'd:/coc-tools')
screen_path = base / 'coc_bot/logs/debug/timeout_btn_find_a_match_20260518_115017.png'
asset_dir = base / 'coc_bot/assets'

candidates = [
    'btn_find_a_match',
    'start_button',
    'start_button_2',
    'home_attack_button_1600x900',
    'next_button',
]

scales = (1.0, 0.75, 1.25, 0.5, 1.5, 0.6, 0.85)

screen = cv2.imread(str(screen_path), cv2.IMREAD_GRAYSCALE)
print('screen:', screen_path, 'shape=', None if screen is None else screen.shape)

for name in candidates:
    p = asset_dir / f'{name}.png'
    t = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
    if t is None:
        print(name, 'MISSING')
        continue
    sh, sw = screen.shape[:2]
    th, tw = t.shape[:2]
    best = -1.0
    best_scale = None
    best_loc = None
    for s in scales:
        nh, nw = int(th*s), int(tw*s)
        if nh < 8 or nw < 8 or nh > sh or nw > sw:
            continue
        ts = t if s == 1.0 else cv2.resize(t, (nw, nh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
        r = cv2.matchTemplate(screen, ts, cv2.TM_CCOEFF_NORMED)
        _, mv, _, ml = cv2.minMaxLoc(r)
        if mv > best:
            best = mv
            best_scale = s
            best_loc = ml
    print(f'{name}: best={best:.4f} scale={best_scale} loc={best_loc} tpl={t.shape}')

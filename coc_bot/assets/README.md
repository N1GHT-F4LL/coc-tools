# Asset Layout

Core runtime templates are organized by screen domain and should be referenced by relative key (path without `.png`) to avoid basename collisions.

- `ui/home/`: home-screen anchors
- `ui/attack/`: attack flow buttons
- `ui/battle/`: post-battle / return buttons
- `buildings/`: building/resource icons

Example template keys in code:
- `ui/home/home_attack_button_1600x900`
- `ui/attack/btn_find_a_match`
- `buildings/icon_gold_mine_full`

Rules:
1. Use lowercase snake_case filenames.
2. Prefer `ui/<screen>/<name>.png` for interactive buttons.
3. Avoid duplicate basenames across folders unless code uses full relative keys.

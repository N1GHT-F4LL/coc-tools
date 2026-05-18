# assets_v2

Naming convention:
- lowercase snake_case
- suffix with resolution if resolution-specific: `_1600x900`
- button prefix: `btn_`
- icon prefix: `icon_`

Examples:
- `buttons/home/btn_attack_1600x900.png`
- `buttons/attack/btn_find_a_match_1600x900.png`
- `buildings/resource_collectors/icon_gold_mine_full.png`

Collection rules:
1. Crop tight around target UI element.
2. Avoid large background area.
3. Keep one canonical asset per meaning per resolution.
4. Put raw screenshots in `debug/samples/` before cropping.

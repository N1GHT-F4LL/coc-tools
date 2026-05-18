#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PATHS = [
    ROOT / "REQUIREMENT.md",
    ROOT / "coc_bot" / "main.py",
    ROOT / "coc_bot" / "core" / "device.py",
    ROOT / "coc_bot" / "core" / "vision.py",
    ROOT / "coc_bot" / "core" / "logging_utils.py",
    ROOT / "coc_bot" / "settings.json",
]

DISALLOWED_REQUIREMENT_FILES = [
    ROOT / "REQUIREMENTS.md",
    ROOT / "REQUIREMENTS_UNIFIED.md",
    ROOT / "coc_bot" / "ASSET_NAMING_REQUIREMENTS.md",
    ROOT / "coc_bot" / "REPO_REVIEW_NOTES.md",
]

SNAKE_RE = re.compile(r"^[a-z0-9_]+$")


def fail(msg: str):
    print(f"[ERROR] {msg}")


def warn(msg: str):
    print(f"[WARNING] {msg}")


def info(msg: str):
    print(f"[INFO] {msg}")


def check_required_files(errors):
    for p in REQUIRED_PATHS:
        if not p.exists():
            errors.append(f"Missing required path: {p.relative_to(ROOT)}")


def check_single_requirement_source(errors):
    missing = not (ROOT / "REQUIREMENT.md").exists()
    if missing:
        errors.append("REQUIREMENT.md is missing")


def check_no_legacy_requirement_files(errors):
    for p in DISALLOWED_REQUIREMENT_FILES:
        if p.exists():
            errors.append(f"Legacy requirement file must be removed: {p.relative_to(ROOT)}")


def check_settings_contract(errors):
    settings_path = ROOT / "coc_bot" / "settings.json"
    if not settings_path.exists():
        errors.append("settings.json missing")
        return
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"settings.json is invalid JSON: {exc}")
        return

    def require(path):
        cur = data
        for key in path:
            if not isinstance(cur, dict) or key not in cur:
                errors.append(f"Missing settings key: {'.'.join(path)}")
                return
            cur = cur[key]

    for path in [
        ["device", "profile"],
        ["device", "endpoint"],
        ["device", "serial"],
        ["device", "auto_select_single"],
        ["farm", "min_gold"],
        ["farm", "min_elixir"],
        ["farm", "min_dark_elixir"],
        ["delays", "short_min"],
        ["delays", "short_max"],
        ["delays", "long_min"],
        ["delays", "long_max"],
        ["jitter", "radius"],
    ]:
        require(path)


def iter_asset_pngs():
    assets_dir = ROOT / "coc_bot" / "assets"
    if not assets_dir.exists():
        return []
    return list(assets_dir.rglob("*.png"))


def check_asset_naming(warnings, strict_errors):
    files = iter_asset_pngs()
    invalid = []
    with_spaces = []
    with_special = []
    basename_dups = {}

    for p in files:
        name = p.stem
        if " " in p.name:
            with_spaces.append(p)
        if not SNAKE_RE.match(name):
            invalid.append(p)
        if "." in name or "-" in name or "'" in name or "!" in name:
            with_special.append(p)
        basename_dups.setdefault(name, []).append(p)

    dup_items = {k: v for k, v in basename_dups.items() if len(v) > 1}

    if invalid:
        warnings.append(f"Asset basename not snake_case/lowercase: {len(invalid)} files")
    if with_spaces:
        warnings.append(f"Asset filenames with spaces: {len(with_spaces)} files")
    if dup_items:
        warnings.append(f"Duplicate asset basenames detected: {len(dup_items)} keys")

    # Strict mode upgrades warnings to errors.
    if invalid:
        strict_errors.append("Strict assets: invalid asset naming detected")
    if with_spaces:
        strict_errors.append("Strict assets: filenames with spaces detected")
    if dup_items:
        strict_errors.append("Strict assets: duplicate basenames detected")


def check_gitignore_for_logs(errors):
    p = ROOT / ".gitignore"
    if not p.exists():
        errors.append(".gitignore missing")
        return
    content = p.read_text(encoding="utf-8", errors="ignore")
    if "coc_bot/logs/" not in content:
        errors.append(".gitignore must include coc_bot/logs/")


def main():
    parser = argparse.ArgumentParser(description="Requirement gate checks")
    parser.add_argument("--strict-assets", action="store_true", help="Fail on legacy asset naming/duplicates")
    args = parser.parse_args()

    errors = []
    warnings = []
    strict_asset_errors = []

    check_required_files(errors)
    check_single_requirement_source(errors)
    check_no_legacy_requirement_files(errors)
    check_settings_contract(errors)
    check_gitignore_for_logs(errors)
    check_asset_naming(warnings, strict_asset_errors)

    for w in warnings:
        warn(w)

    if args.strict_assets:
        errors.extend(strict_asset_errors)

    if errors:
        for e in errors:
            fail(e)
        fail("Requirement gate: FAILED")
        return 1

    info("Requirement gate: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())

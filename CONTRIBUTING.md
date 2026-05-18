# Contributing

## Source of Truth

- Technical requirements: `REQUIREMENT.md`
- Dependency manifest: `requirements.txt`

## Required Workflow

1. Implement your change.
2. Run requirement gate locally:
   - `python scripts/requirement_check.py`
3. If you are cleaning legacy assets and want strict enforcement:
   - `python scripts/requirement_check.py --strict-assets`
4. Ensure your PR description maps changes to requirement sections.

## PR Merge Policy

- PR must pass CI requirement gate.
- No legacy requirement files should be reintroduced.
- Runtime artifacts under `coc_bot/logs/` must remain ignored.

## Asset Naming Policy

- Follow `REQUIREMENT.md` section "Asset Naming Convention".
- Current repository contains legacy assets; gate warns by default.
- Use `--strict-assets` mode when doing asset cleanup/refactor.

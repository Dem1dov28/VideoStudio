# Project Documentation Map

This folder contains project documentation and operational notes.

## Core Guides

- `MODE_CREATION_GUIDE.md` — how to add and wire new generation modes.
- `MODE5_PARALLELISM_AND_PROVIDER_LIMITS.md` — Mode 5 parallel knobs vs VoiceAPI/FastGen limits (read before tuning `.env`).
- `STYLE_PLAN.md` — styling and UI/UX guidance.

## Root Notes Archive

Moved from project root to reduce clutter:

- `root-notes/ANALYSIS_LOADING.md`
- `root-notes/PROJECT_STRUCTURE.md`
- `root-notes/RATE_LIMIT_GUIDE.md`
- `root-notes/plan.md`

## Related Runtime Data

- Generated runtime outputs remain outside `docs` (for example `MyVideo/` and `output/`).
- Tests were moved to `tests/` and grouped by domain.

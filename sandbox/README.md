# 🧪 ZERO Sandbox

A scratch + reference zone for the ZERO project. Nothing in here is imported by
the engine — this folder holds **research, competitive analysis, experiment
notes, and design proposals** so future sessions (human or AI) can pick up
context without re-doing the research.

## Layout

```text
sandbox/
├── README.md                  # this file
└── research/
    └── 2026-08-05-zero-competitive-landscape.md   # project analysis + suggested upgrades
```

## Conventions

1. **Date-prefix research notes**: `YYYY-MM-DD-topic.md` inside `research/`.
2. **Read-only safety**: engine code (`engine/`, `data/`, `app.py`) never imports from `sandbox/`.
3. **Promotion path**: when a proposal here gets implemented, mark it `[PROMOTED → engine/<file>.py]` at the top of the note instead of deleting it — keeps the decision trail.
4. **Experiments**: throwaway scripts go in `sandbox/experiments/` (create as needed); keep them self-contained.

## Current contents

| Note | Summary |
|---|---|
| `research/2026-08-05-zero-competitive-landscape.md` | Full breakdown of what ZERO is, gap analysis vs TradingAgents / FinRobot / Kronos / Chronos-2 / AlgoTest / Streak, and a prioritized upgrade roadmap. |

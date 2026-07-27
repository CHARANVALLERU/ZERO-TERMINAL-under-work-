---
tags: [integration, obsidian, zero-engine]
---
# Claude Obsidian Integration Plan

## Bidirectional Knowledge Flow
1. **Engine to Obsidian**: `engine/obsidian_sync.py` automatically writes daily predictions to `01_Daily_Logs/YYYY-MM-DD.md`.
2. **Obsidian to Engine**: `engine/zero_engine_kb.py` reads user notes from `02_Mental_Models`, `03_Cognitive_Biases`, `04_Quantitative_Strategies`, and `05_AI_Memory` into Gemini AI system context.
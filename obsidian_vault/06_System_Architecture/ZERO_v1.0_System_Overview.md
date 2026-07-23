---
tags: [architecture, zero-v1]
---
# ZERO v1.0 System Overview

ZERO is built on 4 core layers:
1. **Ingestion Layer** (`data/`): Options chain, news sentiment, historical statistics.
2. **Quantitative Engine Core** (`engine/`): Nautilus order engine, Fincept platform, QuantDinger, Walk-Forward backtester, Calibrator.
3. **AI Brain & Knowledge Layer** (`engine/zero_engine_kb.py` & `obsidian_vault/`): Dynamic RAG system.
4. **Streamlit UI Terminal** (`app.py` & `ui/`): Digital core dashboard.
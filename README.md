<div align="center">
  
# ⚡ ZERO V1.0 
**Adaptive Market Intelligence & Quantum Trading Terminal**

[![Status](https://img.shields.io/badge/Status-Operational-E50914?style=for-the-badge&logo=appveyor)](https://github.com/CHARANVALLERU/ZERO-TERMINAL-under-work-)
[![Version](https://img.shields.io/badge/Version-1.0-D4AF37?style=for-the-badge)](https://github.com/CHARANVALLERU/ZERO-TERMINAL-under-work-)
[![Python](https://img.shields.io/badge/Python-3.10+-white?style=for-the-badge&logo=python)](https://python.org)
[![Core deps](https://img.shields.io/badge/Core-NumPy%20%7C%20Pandas-00ff88?style=for-the-badge)](https://numpy.org)
[![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)](LICENSE)

*An institutional-grade, pre-market OHLC prediction, automated YouTube knowledge ingestion, live index ticker, and AI-powered chart analysis engine for Indian & Global Markets.*

</div>

---

## 📖 Table of Contents
- [Overview](#-overview)
- [What's New in V1.0](#-whats-new-in-v10)
- [ZERO AGI — AI Chart Analysis Engine](#-zero-agi--ai-chart-analysis-engine)
- [Live Price Ticker](#-live-price-ticker-sub-100ms-updates)
- [Automated YouTube Knowledge Pipeline](#-automated-youtube-knowledge-pipeline)
- [Dynamic RAG & Human-Like Memory](#-dynamic-rag--human-like-memory)
- [Dual-Vault Architecture & Backup Protocol](#-dual-vault-architecture--backup-protocol)
- [The Quant Engines](#-the-quant-engines)
- [Core Architecture](#-core-architecture)
- [Getting Started & Installation](#-getting-started--installation)
- [CLI Operations](#-cli-operations)
- [Obsidian Second Brain Integration](#-obsidian-second-brain-integration)
- [Security & Privacy](#-security--privacy)
- [Disclaimer](#-disclaimer)

---

## 🚀 Overview

**ZERO** fuses overnight global cues, NSE options chain data, financial-news sentiment, and automated video transcript knowledge into highly accurate daily market predictions. Built on top of optimized `numpy` and `pandas` routines, ZERO runs natively without requiring heavy deep-learning frameworks.

In **V1.0**, ZERO features a complete **Quantum Trading Terminal** with walk-forward backtesting, multi-agent consensus, automated bracket order generation, live UI progress tracking, AI multimodal chart analysis (ZERO AGI), and a dynamic RAG AI reasoning core.

---

## 🔥 What's New in V1.0

| Feature | Status |
|---|---|
| **ZERO AGI** — AI chart analysis with Entry, SL, TP1, TP2, R:R | ✅ Live |
| **Live Index Ticker** — NIFTY / BANKNIFTY / SENSEX at sub-100ms | ✅ Live |
| **Dynamic Strategy KB Dropdown** — auto-scans all YouTube & mental model notes | ✅ Live |
| **Offline ZERO Brain Engine** — full trade setups with zero API cost | ✅ Live |
| **YouTube Knowledge Ingestion Pipeline** | ✅ Live |
| **Dynamic RAG Context Retrieval (unlimited memory)** | ✅ Live |
| **Streamlit Deprecated API Removal** (`use_container_width`, `st.components.v1.html`) | ✅ Done |
| **Dual-Vault Backup Protocol** (`ZERO.md` ↔ `second zero.md`) | ✅ Live |
| **Walk-Forward Backtester with zero lookahead bias** | ✅ Live |

---

## 🤖 ZERO AGI — AI Chart Analysis Engine

ZERO AGI is an on-device multimodal trading assistant accessible from the **left sidebar → 🤖 ZERO AGI** button.

### Features
- **📸 Chart Image Input**: Upload a screenshot, paste from clipboard, or capture your screen directly.
- **📚 Dynamic Knowledge Base Dropdown**: Automatically scanned from all ingested YouTube videos and ZERO Brain mental models — updates instantly whenever new knowledge is imported. No manual refresh needed.
- **💬 Dialogue Box**: Input any custom strategy directive or pick from the knowledge base.
- **⚡ Offline ZERO Brain Engine**: When no Gemini API key is configured (or rate limits hit), ZERO AGI falls back to a full local inference engine using:
  - Chart pixel momentum analysis (green vs red candle cluster detection with recent candles weighted 2×)
  - Live NIFTY/BANKNIFTY/SENSEX price feed
  - ZERO Brain RAG (ICT rules, SMC rules, candlestick patterns, mental models)

### Trade Setup Output
Every analysis produces a complete, directionally-correct trade plan:

| Field | Description |
|---|---|
| **Directional Bias** | LONG / SHORT / NEUTRAL with confidence % |
| **Entry Zone** | Exact CMP-based entry level |
| **Stop Loss (SL)** | BELOW entry for LONG, ABOVE entry for SHORT. Always shows `Risk: N pts`. |
| **Take Profit 1 (TP1)** | ABOVE entry for LONG, BELOW entry for SHORT. Always shows `Reward: +N pts | R:R 1:2` |
| **Take Profit 2 (TP2)** | Extended target. Always shows `Reward: +N pts | R:R 1:4` |
| **Risk:Reward** | `1:2 (TP1) / 1:4 (TP2)` |
| **Key Structures** | Strategy-specific: OB zones, FVG targets, CHoCH levels, liquidity pools |
| **Invalidation** | Exact candle-close level that kills the thesis |

### Strategy-Aware Level Calculation

The offline engine picks SL/TP multipliers based on which strategy you select:

| Strategy | SL % | TP1 % | TP2 % | R:R |
|---|---|---|---|---|
| ICT Order Block & FVG | 0.45% | 0.90% | 1.80% | 1:2 / 1:4 |
| SMC CHoCH / Premium–Discount | 0.60% | 1.20% | 2.40% | 1:2 / 1:4 |
| Breakout & Retest | 0.40% | 1.20% | 2.40% | 1:3 / 1:6 |
| Candlestick Reversal Patterns | 0.50% | 1.00% | 2.00% | 1:2 / 1:4 |
| ZERO Brain Discipline / Mental Model | 0.50% | 1.00% | 2.00% | 1:2 / 1:4 |

---

## 📈 Live Price Ticker (Sub-100ms Updates)

ZERO runs a **local HTTP price server** (`engine/live_price_server.py`) on `http://127.0.0.1:7701` in a background daemon thread when the Streamlit app starts.

- **Source hierarchy**: BSE India API → NSE India API → yfinance fallback
- **Update rate**: Every 100ms in the browser (JS `setInterval` loop inside an iframe)
- **No page refresh required**: Uses `st.iframe` pointing to a persistent localhost URL — the iframe DOM node is never torn down by Streamlit reruns
- **Displayed data**: Open (locked at 9:15 AM), High, Low, Close (locked at 3:30 PM), Live CMP, Change %, Day range bar

### Open / Close Lock Rules
| Time | Action |
|---|---|
| `09:15:01 AM` | Open price is locked and stored |
| `09:15 AM – 03:30 PM` | High & Low track dynamically in real-time |
| `03:30:01 PM` | Close price is locked |

---

## 📺 Automated YouTube Knowledge Pipeline

ZERO automatically processes YouTube videos and playlists into structured notes:

1. **CLI & Terminal Ingestion:**
   ```bash
   python convert_playlist.py --url "https://www.youtube.com/watch?v=YOUR_VIDEO_ID"
   ```
2. **Native Transcript Extraction:** Uses `youtube-transcript-api` to fetch 100% of video captions with zero truncation.
3. **Graph Connectivity:** Automatically links generated notes to `ZERO Brain Engine.md` and `04_YouTube_Knowledge/Index.md`.
4. **Hot-Reload:** Emits a `.kb_reload.flag` signal to update the running AI engine live without a server restart.
5. **ZERO AGI Dropdown Auto-Update:** When a new video is ingested, it **automatically appears** in the ZERO AGI strategy dropdown — no code change required.

---

## 🧠 Dynamic RAG & Human-Like Memory

- **Unlimited Storage:** Knowledge stored permanently across `obsidian_vault/` and `db/brain/entries.json`.
- **Query-Driven RAG:** `ZeroEngineKB.get_relevant_knowledge()` dynamically ranks matching sections across all transcripts.
- **Dynamic Strategy Discovery:** `ZeroEngineKB.get_dynamic_knowledge_strategies()` scans `04_YouTube_Knowledge/` and `02_Mental_Models/` at runtime — new imports appear in the ZERO AGI dropdown instantly.
- **Continuous Learning:** AI engine learns from new YouTube content and mental model notes.

---

## 🛡️ Dual-Vault Architecture & Backup Protocol

- **`ZERO.md` (Active Master):** Primary entry point for all new updates, features, and knowledge graph links.
- **`second zero.md` (Core Backup):** Modifications made to `ZERO.md` automatically sync to `second zero.md` after **24 hours** of verified stability via `engine/zero_backup_service.py`.

---

## 🧠 The Quant Engines

### 1. Nautilus Order Engine
* **Event-Driven Execution:** Simulates deterministic multi-venue routing (NSE, BSE, MCX, GIFT) with exact slippage modeling.
* **TIF Matrix:** Native support for `IOC`, `FOK`, `GTC`, `GTD`, `DAY`, `POST_ONLY`, and `REDUCE_ONLY` execution instructions.
* **Contingency Chains:** Advanced bracket structures including `OCO` (One-Cancels-Other), `OTO` (One-Triggers-Other), and `OUO` (One-Updates-Other).

### 2. Fincept Developer Platform
* **Quant Team Orchestrator:** Simulates a multi-analyst consensus desk to debate and merge market outlooks into a single Unified Trade Thesis.
* **Options Flow & Sentiment:** Identifies dark pool hedging and institutional sweeps based on PCR and open interest concentration.
* **Derivatives & Macro:** Includes a pure-math Black-Scholes Greeks calculator (Delta, Gamma, Theta, Vega) and cross-asset inter-market correlation signals.

### 3. QuantDinger Strategy Engine
* **Regime Classification:** Automatically classifies the market into states like `VOLATILE_RANGEBOUND`, `TRENDING_BULLISH`, `MACRO_SHOCK`, or `LOW_VOL_SQUEEZE`.
* **Dynamic Strategies:** Outputs fully calculated quantitative setups with precise Risk:Reward ratios, Win Probabilities, and dynamic position sizing.

### 4. Advanced Walk-Forward Backtester
* **Zero Lookahead Bias:** Pure `numpy`-based backtesting engine ensuring strict walk-forward validation.
* **Institutional Analytics:** Computes Sharpe, Sortino, Calmar, Max Drawdown, Profit Factor, and trade expectancy natively.

### 5. ZERO AGI Brain Engine
* **Multimodal Chart Vision:** Analyzes uploaded/captured chart screenshots using Gemini Vision API or local pixel momentum inference.
* **Local Offline Engine:** Full trade setups (Entry, SL, TP1, TP2) generated with zero API cost using ZERO Brain RAG + live price feed.
* **Knowledge Base Integration:** Directly ingests ICT, SMC, candlestick, and mental model knowledge from all YouTube and Obsidian vault notes.

---

## 🏗️ Core Architecture

```text
ZERO/
├── app.py                     # Streamlit Quantum Terminal (entry point & fast splash)
├── cli.py                     # Headless CLI: predict / train / backtest / update
├── convert_playlist.py        # YouTube Video & Playlist Ingestion pipeline
├── config.py                  # Tickers, weights, ML + calibration parameters
│
├── data/                      # Ingestion layer (network I/O, caches, feature store)
│   ├── live_index_service.py  #   Live NIFTY/BANKNIFTY/SENSEX price scraper (3-tier fallback)
│   ├── options_chain.py       #   NSE OI walls, PCR, max-pain
│   ├── market_news.py         #   News feeds + NLP sentiment
│   └── historical.py          #   Prior OHLC, ATR, VWAP
│
├── engine/                    # Quantitative Core (V1.0)
│   ├── live_price_server.py   #   Local HTTP server on :7701 — sub-100ms live ticker
│   ├── zero_agi_engine.py     #   ZERO AGI multimodal chart analysis (Gemini + offline)
│   ├── zero_engine_kb.py      #   Dynamic RAG Knowledge Base Orchestrator
│   ├── nautilus_order_engine.py # Advanced TIF/Contingency order execution
│   ├── fincept_platform.py    #   Quant team thesis, derivatives Greeks, inter-market
│   ├── quant_dinge_engine.py  #   Regime classification & strategy setups
│   ├── advanced_backtest.py   #   Walk-forward validation & analytics
│   ├── zero_backup_service.py #   Dual-vault sync manager (ZERO.md <-> second zero.md)
│   ├── obsidian_sync.py       #   Automated daily note sync with Obsidian Vault
│   ├── brain_engine.py        #   JSON knowledge chunking & SHA1 deduplication
│   ├── calibrator.py          #   Adaptive calibration learning layer
│   └── learning_service.py    #   Daily autonomous feedback loop
│
├── obsidian_vault/            # 🧠 Native Obsidian Second Brain Vault
│   ├── .obsidian/             #   Graph view & plugin configs
│   ├── ZERO.md                #   Master Graph Root Node & Map of Content
│   ├── second zero.md         #   Backup Graph Node (Synced after 24h)
│   ├── 01_Daily_Logs/         #   Auto-synced daily pre-market predictions
│   ├── 02_Mental_Models/      #   First Principles, Probabilistic Thinking
│   ├── 03_Cognitive_Biases/   #   FOMO, Loss Aversion, Psychology framework
│   ├── 04_YouTube_Knowledge/  #   YouTube Ingested Knowledge & Index
│   └── 05_AI_Memory/          #   Executable AI capabilities & skills
│
├── ui/                        # Visual layer (Fincept/Bloomberg-style cards)
│   └── components.py          #   All Streamlit UI components (ticker, ZERO AGI modal, etc.)
└── db/                        # SQLite, feedback logs, ZERO Brain JSON stores
```

---

## 🛠️ Getting Started & Installation

### 1. Prerequisites
- **Python 3.10+**
- Internet access (for live scraping of market data & YouTube transcript API)
- **Gemini API Key** *(Optional — ZERO AGI works fully offline without one)*

### 2. Installation
Clone the repository from GitHub and install dependencies:
```bash
git clone https://github.com/CHARANVALLERU/ZERO-TERMINAL-under-work-.git
cd ZERO-TERMINAL-under-work-
pip install -r requirements.txt
```

### 3. Running the Terminal
Launch the complete UI with Streamlit:
```bash
streamlit run app.py
```
*(On Windows, you can alternatively run `run.bat`).*

### 4. ZERO AGI Setup (Optional)
ZERO AGI works fully offline with no API key required (uses local ZERO Brain inference engine).
For Gemini Vision API enhanced analysis, add your key in the ZERO AGI modal → ⚙ API KEY SETTINGS.

---

## 💻 CLI Operations

```bash
# Ingest YouTube Video or Playlist into Brain Engine & Obsidian Graph
# (Auto-updates ZERO AGI strategy dropdown after import)
python convert_playlist.py --url "https://www.youtube.com/watch?v=YOUR_VIDEO_ID"

# Print today's prediction matrix as JSON
python cli.py predict         

# Retrain the calibration layer on historical logs
python cli.py train           

# Run a walk-forward accuracy report on existing models
python cli.py backtest        

# Execute full daily cycle: fetch actuals -> log -> retrain
python cli.py update          
```

---

## 🧠 Obsidian Second Brain Integration

1. Open **Obsidian** → Click **"Open folder as vault"**.
2. Select the `obsidian_vault` directory inside `ZERO-TERMINAL-under-work-`.
3. Open `ZERO.md` and press `Ctrl + G` (or `Cmd + G`) to view the interactive **Knowledge Graph**!

---

## 🔒 Security & Privacy

ZERO is designed to be **local-first**. All data scraping, quantitative analysis, strategy prediction, chart vision inference, and walk-forward backtesting run **entirely on your local machine**. No data is sent to external servers when using the offline ZERO Brain engine.

---

## ⚠️ Disclaimer

*For quantitative research and educational use only. Market predictions are probabilistic. Trading involves substantial financial risk; consult a licensed financial advisor before acting on any output generated by this software.*

<div align="center">
  <b>ZERO V1.0 // Renaissance of Market Predictions</b>
</div>


---

## 📖 Table of Contents
- [Overview](#-overview)
- [What's New in V1.0](#-whats-new-in-v10)
- [Automated YouTube Knowledge Pipeline](#-automated-youtube-knowledge-pipeline)
- [Dynamic RAG & Human-Like Memory](#-dynamic-rag--human-like-memory)
- [Dual-Vault Architecture & Backup Protocol](#-dual-vault-architecture--backup-protocol)
- [The Quant Engines](#-the-quant-engines)
- [Core Architecture](#-core-architecture)
- [Getting Started & Installation](#-getting-started--installation)
- [CLI Operations](#-cli-operations)
- [Obsidian Second Brain Integration](#-obsidian-second-brain-integration)
- [Security & Privacy](#-security--privacy)
- [Disclaimer](#-disclaimer)

---

## 🚀 Overview

**ZERO** fuses overnight global cues, NSE options chain data, financial-news sentiment, and automated video transcript knowledge into highly accurate daily market predictions. Built on top of optimized `numpy` and `pandas` routines, ZERO runs natively without requiring heavy deep-learning frameworks.

In **V1.0**, ZERO features a complete **Quantum Trading Terminal** with walk-forward backtesting, multi-agent consensus, automated bracket order generation, live UI progress tracking, and a dynamic RAG AI reasoning core.

---

## 🔥 What's New in V1.0

- **Automated YouTube Knowledge Ingestion Pipeline:** Convert any YouTube playlist or video URL directly into structured Obsidian Markdown notes with timestamps and automated Obsidian Graph View connectivity.
- **Dynamic RAG Context Retrieval:** Unlimited knowledge memory retrieval powered by semantic paragraph ranking across all ingested transcripts and mental models.
- **Instant Cache-First Bootup & Fast Load:** Fast app bootup that displays the splash sequence instantly from memory cache while hydrating heavy knowledge bases asynchronously in background daemon threads.
- **Dual-Vault & Backup Protocol (`ZERO.md` & `second zero.md`):** All updates land in `ZERO.md` first; verified changes auto-sync to `second zero.md` after 24 hours of issue-free execution.
- **Live Background Progress Tracker:** Real-time UI progress updates (`Step 1/3` to `COMPLETED`) with auto-expiring status toasts.

---

## 📺 Automated YouTube Knowledge Pipeline

ZERO automatically processes YouTube videos and playlists into structured notes:

1. **CLI & Terminal Ingestion:**
   ```bash
   python convert_playlist.py --url "https://www.youtube.com/watch?v=YOUR_VIDEO_ID"
   ```
2. **Native Transcript Extraction:** Uses `youtube-transcript-api` to fetch 100% of video captions from start to finish (`[00:00]` through completion) with zero truncation.
3. **Graph Connectivity:** Automatically links generated notes to `ZERO Brain Engine.md` and `04_YouTube_Knowledge/Index.md`.
4. **Hot-Reload:** Emits a `.kb_reload.flag` signal to update the running AI engine live in Streamlit without requiring a server restart.

---

## 🧠 Dynamic RAG & Human-Like Memory

- **Unlimited Storage:** Knowledge is stored permanently across `obsidian_vault/` and `db/brain/entries.json`.
- **Query-Driven RAG:** `ZeroEngineKB.get_relevant_knowledge()` dynamically ranks matching sections across all transcripts and injects relevant context into the Gemini AI system prompt per query.
- **Continuous Learning:** The AI engine learns from new YouTube content and mental model notes, providing answers grounded in actual ingested material.

---

## 🛡️ Dual-Vault Architecture & Backup Protocol

- **`ZERO.md` (Active Master):** Primary entry point for all new updates, features, and knowledge graph links.
- **`second zero.md` (Core Backup):** Renamed backup vault. Modifications made to `ZERO.md` automatically sync to `second zero.md` after **24 hours** of verified stability via `engine/zero_backup_service.py`.

---

## 🧠 The Quant Engines

### 1. Nautilus Order Engine
* **Event-Driven Execution:** Simulates deterministic multi-venue routing (NSE, BSE, MCX, GIFT) with exact slippage modeling.
* **TIF Matrix:** Native support for `IOC`, `FOK`, `GTC`, `GTD`, `DAY`, `POST_ONLY`, and `REDUCE_ONLY` execution instructions.
* **Contingency Chains:** Advanced bracket structures including `OCO` (One-Cancels-Other), `OTO` (One-Triggers-Other), and `OUO` (One-Updates-Other).

### 2. Fincept Developer Platform
* **Quant Team Orchestrator:** Simulates a multi-analyst consensus desk to debate and merge market outlooks into a single Unified Trade Thesis.
* **Options Flow & Sentiment:** Identifies dark pool hedging and institutional sweeps based on PCR and open interest concentration.
* **Derivatives & Macro:** Includes a pure-math Black-Scholes Greeks calculator (Delta, Gamma, Theta, Vega) and cross-asset inter-market correlation signals (US Futures, Crude, DXY, VIX).

### 3. QuantDinger Strategy Engine
* **Regime Classification:** Automatically classifies the market into states like `VOLATILE_RANGEBOUND`, `TRENDING_BULLISH`, `MACRO_SHOCK`, or `LOW_VOL_SQUEEZE`.
* **Dynamic Strategies:** Outputs fully calculated quantitative setups (e.g., "Breakout Momentum Ride") with precise Risk:Reward ratios, Win Probabilities, and dynamic position sizing (using Kelly criterion limits).

### 4. Advanced Walk-Forward Backtester
* **Zero Lookahead Bias:** Pure `numpy`-based backtesting engine ensuring strict walk-forward validation (train/test splits) to prevent overfitting.
* **Institutional Analytics:** Computes Sharpe, Sortino, Calmar, Max Drawdown, Profit Factor, and trade expectancy natively.

### 5. ZERO AI Brain & Obsidian Vault
* **Local RAG & Skill Ingestion:** Integrates the `zero_engine_kb.py` module to dynamically load human cognitive biases, market psychology, candlestick encyclopedias, and AI system capabilities.
* **Conversational Console:** Built-in Streamlit side-panel acting as a live quantitative assistant, cross-referencing market state with personal Obsidian Vault knowledge.

---

## 🏗️ Core Architecture

```text
ZERO/
├── app.py                     # Streamlit Quantum Terminal (entry point & fast splash)
├── cli.py                     # Headless CLI: predict / train / backtest / update
├── convert_playlist.py        # YouTube Video & Playlist Ingestion pipeline
├── config.py                  # Tickers, weights, ML + calibration parameters
│
├── data/                      # Ingestion layer (network I/O, caches, feature store)
│   ├── options_chain.py       #   NSE OI walls, PCR, max-pain
│   ├── market_news.py         #   News feeds + NLP sentiment
│   └── historical.py          #   Prior OHLC, ATR, VWAP
│
├── engine/                    # Quantitative Core (V1.0)
│   ├── nautilus_order_engine.py # Advanced TIF/Contingency order execution
│   ├── fincept_platform.py    # Quant team thesis, derivatives Greeks, inter-market
│   ├── quant_dinge_engine.py  # Regime classification & strategy setups
│   ├── advanced_backtest.py   # Walk-forward validation & analytics
│   ├── zero_engine_kb.py      # Dynamic RAG Knowledge Base Orchestrator
│   ├── zero_backup_service.py # Dual-vault sync manager (ZERO.md <-> second zero.md)
│   ├── obsidian_sync.py       # Automated daily note sync with Obsidian Vault
│   ├── brain_engine.py        # JSON knowledge chunking & SHA1 deduplication
│   ├── calibrator.py          # Adaptive calibration learning layer
│   └── learning_service.py    # Daily autonomous feedback loop
│
├── obsidian_vault/            # 🧠 Native Obsidian Second Brain Vault
│   ├── .obsidian/             #   Graph view & plugin configs
│   ├── ZERO.md                #   Master Graph Root Node & Map of Content
│   ├── second zero.md         #   Backup Graph Node (Synced after 24h)
│   ├── 01_Daily_Logs/         #   Auto-synced daily pre-market predictions
│   ├── 02_Mental_Models/      #   First Principles, Probabilistic Thinking
│   ├── 03_Cognitive_Biases/   #   FOMO, Loss Aversion, Psychology framework
│   ├── 04_YouTube_Knowledge/  #   YouTube Ingested Knowledge & Index
│   └── 05_AI_Memory/          #   Executable AI capabilities & skills
│
├── ui/                        # Visual layer (Fincept/Bloomberg-style cards)
└── db/                        # SQLite, feedback logs, ZERO Brain JSON stores
```

---

## 🛠️ Getting Started & Installation

### 1. Prerequisites
- **Python 3.10+**
- Internet access (for live scraping of market data & YouTube transcript API)
- **Gemini API Key** (Required for the ZERO AI Brain interface)

### 2. Installation
Clone the repository from GitHub and install dependencies:
```bash
git clone https://github.com/CHARANVALLERU/ZERO-TERMINAL-under-work-.git
cd ZERO-TERMINAL-under-work-
pip install -r requirements.txt
```

### 3. Running the Terminal
Launch the complete UI with Streamlit:
```bash
streamlit run app.py
```
*(On Windows, you can alternatively run `run.bat`).*

---

## 💻 CLI Operations

```bash
# Ingest YouTube Video or Playlist into Brain Engine & Obsidian Graph
python convert_playlist.py --url "https://www.youtube.com/watch?v=YOUR_VIDEO_ID"

# Print today's prediction matrix as JSON
python cli.py predict         

# Retrain the calibration layer on historical logs
python cli.py train           

# Run a walk-forward accuracy report on existing models
python cli.py backtest        

# Execute full daily cycle: fetch actuals -> log -> retrain
python cli.py update          
```

---

## 🧠 Obsidian Second Brain Integration

1. Open **Obsidian** $\rightarrow$ Click **"Open folder as vault"**.
2. Select the `obsidian_vault` directory inside `ZERO-TERMINAL-under-work-`.
3. Open `ZERO.md` and press `Ctrl + G` (or `Cmd + G`) to view the interactive **Knowledge Graph**!

---

## 🔒 Security & Privacy

ZERO is designed to be **local-first**. All data scraping, quantitative analysis, strategy prediction, and walk-forward backtesting run **entirely on your local machine**.

---

## ⚠️ Disclaimer

*For quantitative research and educational use only. Market predictions are probabilistic. Trading involves substantial financial risk; consult a licensed financial advisor before acting on any output generated by this software.*

<div align="center">
  <b>ZERO V1.0 // Renaissance of Market Predictions</b>
</div>

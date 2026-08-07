

# ⚡ ZERO V1.1

**Adaptive Market Intelligence & Quantum Trading Terminal**

[Status](https://github.com/CHARANVALLERU/ZERO-TERMINAL-under-work-)
[Version](https://github.com/CHARANVALLERU/ZERO-TERMINAL-under-work-)
[Python](https://python.org)
[Core deps](https://numpy.org)
[License](LICENSE)

*An institutional-grade, pre-market OHLC prediction, automated YouTube knowledge ingestion, live index ticker, and AI-powered chart analysis engine for Indian & Global Markets.*



---

## 📖 Table of Contents

- [Overview](#-overview)
- [What's New in V1.1](#-whats-new-in-v11)
- [ZERO AGI — AI Chart Analysis Engine](#-zero-agi--ai-chart-analysis-engine)
- [Live Price Ticker](#-live-price-ticker-sub-100ms-updates)
- [Automated YouTube Knowledge Pipeline](#-automated-youtube-knowledge-pipeline)
- [Dynamic RAG & Human-Like Memory](#-dynamic-rag--human-like-memory)
- [Dual-Vault Architecture & Backup Protocol](#-dual-vault-architecture--backup-protocol)
- [The Quant Engines](#-the-quant-engines)
- [KRONOS ENGINE — K-Line Foundation Model](#-kronos-engine--k-line-foundation-model)
- [ZERO AITE — Automated Intelligent Trading Environment](#-zero-aite--automated-intelligent-trading-environment)
- [The V1.1 Intelligence Layer](#-the-v11-intelligence-layer)
- [Core Architecture](#-core-architecture)
- [Getting Started & Installation](#-getting-started--installation)
- [CLI Operations](#-cli-operations)
- [Obsidian Second Brain Integration](#-obsidian-second-brain-integration)
- [Security & Privacy](#-security--privacy)
- [Disclaimer](#-disclaimer)

---

## 🚀 Overview

**ZERO** fuses overnight global cues, NSE options chain data, financial-news sentiment, and automated video transcript knowledge into highly accurate daily market predictions. Built on top of optimized `numpy` and `pandas` routines, ZERO runs natively without requiring heavy deep-learning frameworks.

In **V1.1**, ZERO adds a full institutional intelligence layer: GARCH/India-VIX-driven volatility forecasting, time-series foundation model (TSFM) ensemble support, a TradingAgents-style LLM debate engine, options intelligence (OI-change, IV smile, multi-leg strategies), Indian transaction-cost realism, Diebold–Mariano/PSR/DSR statistical validation, a health-scored data provider registry, safety-gated broker adapters, and a deterministic daily IC memo written straight into the Obsidian vault.

Every new subsystem follows ZERO's core law: **optional dependencies degrade gracefully** — the engine runs cold with nothing but `numpy`, `pandas`, and `requests`.

---

## 🔥 What's New in V1.1


| Feature                                                                                                                                                                                | Status                 |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------- |
| **KRONOS ENGINE Tab** — vendored K-line foundation model (AAAI 2026, 45+ exchanges) with forecast console, probabilistic paths, rolling backtests, finetuning CLI & prediction history | ✅ Live (opt-in torch)  |
| **ZERO AITE Tab** — autonomous strategy breeding, OOS exam, 10–40 bot portfolio, paper/MT5 deploy, 08:45 IST premarket, 24/7 daemon                                                    | ✅ Live (opt-in MT5)    |
| **Session-IV Volatility Layer** — EGARCH/GJR-GARCH → EWMA → ATR fallback, blended with live India VIX (replaces hardcoded IV=15)                                                       | ✅ Live                 |
| **TSFM Ensemble Leg** — Chronos-2 (covariate-informed) / Kronos / TimesFM adapters, no-op safe                                                                                         | ✅ Live (opt-in deps)   |
| **Agent Debate Engine** — bull vs bear researchers → risk manager → PM verdict, Gemini-backed with deterministic offline fallback, decision log                                        | ✅ Live                 |
| **Options Intelligence** — chain snapshots, OI-change vectors, buildup classification, IV smile & term structure, max-pain drift, multi-leg strategy metrics with POP                  | ✅ Live                 |
| **Indian Cost Model** — STT / txn / GST / SEBI / stamp / brokerage / slippage per segment, net PnL & breakeven solver                                                                  | ✅ Live                 |
| **Backtest Statistics** — Diebold–Mariano vs naive baseline, Probabilistic & Deflated Sharpe, embargo-purged walk-forward                                                              | ✅ Live                 |
| **Provider Registry** — NSE → BSE → yfinance health-scored failover (`data/providers/`)                                                                                                | ✅ Live                 |
| **Broker Adapters** — paper default; Dhan / Fyers / Kite / Angel One REST adapters, dual-layer armed gate + audit log                                                                  | ✅ Live (paper default) |
| **Daily IC Memo** — deterministic FinRobot-style memo auto-written to `obsidian_vault/01_Daily_Logs/`                                                                                  | ✅ Live                 |


**Carried over from V1.0:** ZERO AGI chart analysis · live sub-100ms ticker · dynamic strategy KB dropdown · offline ZERO Brain engine · YouTube ingestion pipeline · dynamic RAG · dual-vault backup · walk-forward backtester · multi-agent consensus · Nautilus order engine · QuantDinger regimes · Fincept platform.

---

## 🤖 ZERO AGI — AI Chart Analysis Engine

ZERO AGI is an on-device multimodal trading assistant accessible from the **left sidebar → 🤖 ZERO AGI** button.

### Features

- **📸 Chart Image Input**: Upload a screenshot, paste from clipboard, or capture your screen directly.
- **📚 Dynamic Knowledge Base Dropdown**: Automatically scanned from all ingested YouTube videos and ZERO Brain mental models — updates instantly whenever new knowledge is imported.
- **💬 Dialogue Box**: Input any custom strategy directive or pick from the knowledge base.
- **⚡ Offline ZERO Brain Engine**: When no Gemini API key is configured (or rate limits hit), ZERO AGI falls back to a full local inference engine using chart pixel momentum analysis, the live index price feed, and ZERO Brain RAG (ICT rules, SMC rules, candlestick patterns, mental models).

### Trade Setup Output

Every analysis produces a complete, directionally-correct trade plan: directional bias (LONG/SHORT/NEUTRAL + confidence), entry zone, stop loss (with risk in points), TP1/TP2 (with reward + R:R), key structures (OB zones, FVG targets, CHoCH levels, liquidity pools), and an exact invalidation level.

### Strategy-Aware Level Calculation

The offline engine picks SL/TP multipliers based on the selected strategy (ICT Order Block & FVG, SMC CHoCH, Breakout & Retest, Candlestick Reversal, ZERO Brain Mental Model) with R:R from 1:2 / 1:4 up to 1:3 / 1:6 on breakout setups.

---

## 📈 Live Price Ticker (Sub-100ms Updates)

ZERO runs a **local HTTP price server** (`engine/live_price_server.py`) on `http://127.0.0.1:7701` in a background daemon thread when the Streamlit app starts.

- **Source hierarchy**: BSE India API → NSE India API → yfinance fallback
- **Update rate**: Every 100ms in the browser (JS `setInterval` inside an iframe that Streamlit reruns never tear down)
- **Displayed data**: Open (locked 9:15 AM), High, Low, Close (locked 3:30 PM), live CMP, change %, day range bar

---

## 📺 Automated YouTube Knowledge Pipeline

1. **CLI ingestion:** `python convert_playlist.py --url "https://www.youtube.com/watch?v=YOUR_VIDEO_ID"`
2. **Native transcript extraction** via `youtube-transcript-api` — 100% of captions, zero truncation.
3. **Graph connectivity** — auto-links notes to `ZERO Brain Engine.md` and `04_YouTube_Knowledge/Index.md`.
4. **Hot-reload** — emits `.kb_reload.flag` to update the running engine without restart.
5. **ZERO AGI dropdown auto-update** — new videos appear in the strategy dropdown with no code change.

---

## 🧠 Dynamic RAG & Human-Like Memory

- **Unlimited storage** across `obsidian_vault/` and `db/brain/entries.json`.
- **Query-driven RAG** — `ZeroEngineKB.get_relevant_knowledge()` ranks matching sections per query.
- **Dynamic strategy discovery** — runtime scan of `04_YouTube_Knowledge/` and `02_Mental_Models/`.
- **Continuous learning** — the engine grounds answers in newly ingested material.

---

## 🛡️ Dual-Vault Architecture & Backup Protocol

All meaningful engine writes go through `engine/vault_sync.py`:

1. **Immediate → ZERO vault** (`OBSIDIAN_VAULT_PATH`, default `obsidian_vault/`)
  Daily forecasts, IC memos, brain notes, YouTube knowledge, AITE activity, and premarket briefs land here first. `ZERO.md` gets a changelog bullet for each update.
2. **After ≥24 hours → SECOND ZERO** (`SECOND_ZERO_VAULT_PATH`, default `second_zero_vault/`)
  A background sweeper (started with Streamlit / AITE daemon) copies queued files only when they are at least 24h old. Idempotent (content-hash); skips gracefully if the SECOND ZERO path is missing/unwritable.
3. **In-vault MOC backup:** `second zero.md` remains a delayed mirror of `ZERO.md` for Obsidian graph continuity.

Queue state persists in `db/vault_sync_queue.json`. Override paths via env: `OBSIDIAN_VAULT_PATH`, `SECOND_ZERO_VAULT_PATH`, `VAULT_BACKUP_DELAY_HOURS`.

---

## 🧠 The Quant Engines

### 1. Nautilus Order Engine

Event-driven multi-venue routing simulation (NSE, BSE, MCX, GIFT) with exact slippage modeling; full TIF matrix (`IOC`, `FOK`, `GTC`, `GTD`, `DAY`, `POST_ONLY`, `REDUCE_ONLY`) and contingency chains (`OCO`, `OTO`, `OUO`).

### 2. Fincept Developer Platform

Multi-analyst consensus desk merging outlooks into a Unified Trade Thesis; options flow & sentiment (PCR, OI concentration); pure-math Black-Scholes Greeks; cross-asset inter-market signals (US futures, crude, DXY, VIX).

### 3. QuantDinger Strategy Engine

Regime classification (`VOLATILE_RANGEBOUND`, `TRENDING_BULLISH`, `MACRO_SHOCK`, `LOW_VOL_SQUEEZE`) and fully calculated quantitative setups with R:R, win probabilities, and Kelly-limited position sizing.

### 4. Advanced Walk-Forward Backtester

Zero-lookahead `numpy` backtesting with Sharpe, Sortino, Calmar, max drawdown, profit factor, expectancy — **V1.1 adds** Diebold–Mariano significance vs a naive baseline, Probabilistic/Deflated Sharpe ratios (López de Prado), embargo-purged train/test splits, and an optional Indian-cost hook for net-of-costs PnL.

### 5. ZERO AGI Brain Engine

Multimodal chart vision (Gemini Vision API or local pixel-momentum inference), full offline trade setups, and direct ingestion of ICT/SMC/candlestick/mental-model knowledge.

---

## 🔮 KRONOS ENGINE — K-Line Foundation Model

ZERO now ships a fully **vendored** port of **[Kronos](https://github.com/shiyu-coder/Kronos)** — the first open-source **foundation model for financial candlesticks (K-lines)**, accepted at **AAAI 2026** and pre-trained on data from **45+ global exchanges** ([paper: arXiv 2508.02739](https://arxiv.org/abs/2508.02739) · MIT license · `NeoQuasar` model family — full credit to the upstream authors). The port is upstream-faithful, hardened to ZERO's core law: every piece is lazy-imported, never raises, and degrades gracefully.

### What was integrated


| Module                | Path                                                      | Purpose                                                                                                                                                                                   |
| --------------------- | --------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Vendored core**     | `engine/kronos/`                                          | Faithful port of the model + tokenizer + predictor (`Kronos`, `KronosTokenizer`, `KronosPredictor`)                                                                                       |
| **Inference service** | `engine/kronos_service.py`                                | Lazy singleton `get_kronos_service()` — `status()` / `load()` / `forecast()` / `forecast_batch()`, P10/P50/P90 bands, volatility amplification, never raises                              |
| **Data adapter**      | `data/kronos_adapter.py`                                  | 10-symbol catalog (NIFTY · BANKNIFTY · SENSEX · BTC · ETH · Gold · USDINR · RELIANCE · TCS · HDFCBANK), 5m→1d intervals, NSE-session (09:15–15:30) & holiday-aware future timestamp grids |
| **Charts**            | `ui/kronos_charts.py`                                     | Candles + gold forecast pair + P10–P90 band + NOW divider + volume subplot; probabilistic path fans; backtest equity charts — ZERO dark theme                                             |
| **Terminal panel**    | `ui/kronos_panel.py`                                      | The full KRONOS ENGINE tab console (`render_kronos_terminal_panel`)                                                                                                                       |
| **Backtester**        | `engine/kronos_backtest.py`                               | Rolling-origin walk-forward: direction hit-rates, MAE/MAPE/RMSE, envelope coverage, strategy-vs-buy&hold equity curves                                                                    |
| **Finetuning**        | `engine/kronos_finetune/`                                 | Two-stage (tokenizer → predictor) finetuning pipeline, YAML configs, CLI runner                                                                                                           |
| **Results store**     | `engine/kronos_results_store.py`                          | Atomic file-per-prediction history with 200-file self-prune                                                                                                                               |
| **Tests + fixtures**  | `tests/test_kronos_integration.py` + `tests/data/kronos/` | 16-test integration suite + byte-identical upstream regression fixtures                                                                                                                   |


### Where it lives in the UI

The main tab bar gains a dedicated sixth tab, right after TRADING TERMINAL:

`NIFTY 50 · BANKNIFTY · SENSEX · GLOBAL NEWS · TRADING TERMINAL ·` `**▶ KRONOS ENGINE ◀**` `· ZERO AITE · LEARNING LAB · PREDICTION HISTORY`

Inside the **KRONOS ENGINE** tab, top to bottom:

1. **Status strip** — `ONLINE` (weights loaded) / `STANDBY` (deps OK → shows **⚡ LOAD MODEL** button) / `OFFLINE` (torch missing → shows the pip hint).
2. **Controls** — symbol picker + free-text ticker override, interval (5m/15m/30m/60m/1d), lookback 64–512 bars, prediction length 1–120 bars.
3. **⚙️ Advanced sampling** *(expander)* — temperature `T`, nucleus `top-p`, sample count (>1 unlocks probabilistic bands), volatility amplification.
4. **🔮 RUN KRONOS FORECAST** — fetch history → prepare inputs → sample future K-lines.
5. **Metrics row** — predicted close (+Δ%), direction, predicted high/low, model latency + device.
6. **🌫️ Probabilistic paths** *(expander)* — Monte-Carlo close paths + P10/P50/P90 readout.
7. **🧪 HISTORICAL BACKTEST** *(expander)* — rolling-window hit-rate, close MAPE, P10–P90 coverage + equity curves.
8. **🗂️ PREDICTION HISTORY** *(expander)* — saved-runs table, reload any prior forecast.

### Enabling full model inference

The tab is always visible; actual forecasting needs the torch stack:

```bash
pip install torch torchvision einops huggingface_hub safetensors
```

`torchvision` is **required** for a quiet Streamlit + `transformers` stack — install a build that matches your `torch` variant (CPU↔CPU / CUDA↔CUDA; e.g. `torch 2.13.0+cpu` with `torchvision 0.28.0+cpu`). The first **⚡ LOAD MODEL** click downloads `**NeoQuasar/Kronos-small`** (~100 MB) plus its tokenizer from Hugging Face into the local HF cache. Public NeoQuasar models work **without** a token; `HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN` is **optional** and only raises anonymous Hub rate limits (`set HF_TOKEN=hf_...` on Windows, or `export HF_TOKEN=hf_...` on Unix — `run.bat` passes an existing token through and has a commented example). Environment overrides:


| Variable                              | Default                           | Meaning                                                                                                            |
| ------------------------------------- | --------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN` | *(unset)*                         | Optional Hub token — public NeoQuasar models need none; raises rate limits when set (`config.HF_TOKEN` also works) |
| `KRONOS_MODEL_ID`                     | `NeoQuasar/Kronos-small`          | Hugging Face model id (swap in Kronos-mini/base)                                                                   |
| `KRONOS_TOKENIZER_ID`                 | `NeoQuasar/Kronos-Tokenizer-base` | Hugging Face tokenizer id                                                                                          |
| `KRONOS_DEVICE`                       | `auto`                            | `cuda` if available, else `cpu`                                                                                    |
| `KRONOS_MAX_CONTEXT`                  | `512`                             | Max context bars fed to the model                                                                                  |


**Graceful degradation (ZERO core law):** without torch the tab sits in `OFFLINE` mode with an install hint; with deps but no weights it sits in `STANDBY`; a missing sibling module downgrades only its own section to an info notice. The rest of the terminal is never affected.

### Troubleshooting


| Symptom                                                                                            | Cause                                                                                                     | Fix                                                                                                                                |
| -------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Console spam `ModuleNotFoundError: No module named 'torchvision'` after Kronos / transformers load | Streamlit's file watcher probes `transformers` vision modules; torchvision missing or mismatched vs torch | `pip install torchvision` matching your torch CPU/CUDA build; prefer `**run.bat**` (sets poll watcher + quiet HF env)              |
| File-watcher / path-notify noise on Windows                                                        | Watchdog + large `.venv` / site-packages trees                                                            | Non-fatal. `.streamlit/config.toml` sets `fileWatcherType = "poll"`; `run.bat` also sets `STREAMLIT_SERVER_FILE_WATCHER_TYPE=poll` |
| Hub rate-limit / unauthenticated warnings on first LOAD MODEL                                      | Anonymous Hugging Face downloads                                                                          | Optional: set `HF_TOKEN` or `HUGGING_FACE_HUB_TOKEN`; warm local HF cache loads offline on later runs                              |


### Finetuning quickstart

```bash
python -m engine.kronos_finetune.run_sequential --config engine/kronos_finetune/configs/example_nifty_daily.yaml
```

Runs the two upstream-faithful stages sequentially (tokenizer → predictor) with checkpoints and logs under `db/kronos_finetune/`.

### Data on disk


| Location                 | Contents                                                     |
| ------------------------ | ------------------------------------------------------------ |
| `db/kronos_predictions/` | Saved forecast runs (override with `KRONOS_PREDICTIONS_DIR`) |
| `db/kronos_backtests/`   | Saved backtest reports (JSON)                                |
| `db/kronos_finetune/`    | Finetuning checkpoints & outputs                             |


---

## 🏦 ZERO AITE — Automated Intelligent Trading Environment

ZERO AITE is ZERO's **native ALGORY-style agentic trading loop** — not a pip install of a proprietary ALGORY binary. There is **no installable open-source package named ALGORY** that provides this hedge-fund automation surface; the implementation **is** `engine/aite/` (capability clone: breed → exam → portfolio → deploy → daemon). Streamlit console: `ui/aite/`.

### How the agentic loop works

```text
idea / seed genomes
        ↓
  genetic BREED  (default full cycle: population ≈ 1000 candidates)
        ↓
  OOS EXAM + walk-forward backtest
        ↓
  survivors (10–40 bots) + correlation cull
        ↓
  paper fund allocation  (default ₹10L via ZERO_AITE_PAPER_FUND)
        ↓
  deploy (local paper · optional MT5 paper)
        ↓
  24/7 daemon ticks  ·  08:45 IST premarket brief
```

Agent roles (breeder / risk / researcher / execution) keep writing under `db/aite/` even when the UI is closed, as long as the daemon process is alive.

### Open the tab

```bash
streamlit run app.py
# or run.bat on Windows
```

In the main tab bar, open **ZERO AITE** (immediately after KRONOS ENGINE):

`NIFTY 50 · BANKNIFTY · SENSEX · GLOBAL NEWS · TRADING TERMINAL · KRONOS ENGINE ·` `**▶ ZERO AITE ◀**` `· LEARNING LAB · PREDICTION HISTORY`

Inside: 3D bot graph (custom canvas JS — **no three.js package / no CDN three.js**), backtest flow, activity logs, agent automation, and controls (fund / daemon / breed / squad / paper deploy / idea→agent / brief).

### Daemon 24/7

The AITE daemon is a **non-blocking background thread** (same pattern as the live price server). It auto-starts when `app.py` loads. For a process that **survives Streamlit close**:

```bash
python -m engine.aite.daemon
```

```python
from engine.aite import start_daemon, stop_daemon, get_daemon_status
start_daemon()
```

Ticks every ~30s (`DAEMON_TICK_SECONDS`), re-breeds on interval (`BREED_INTERVAL_HOURS`), and fires the **08:45 IST** premarket research pass once per session day.

### Breed ≈ 1000 + paper fund


| Knob                         | Default               | Where                                                |
| ---------------------------- | --------------------- | ---------------------------------------------------- |
| Full generation population   | **1000**              | `run_generation_cycle(n_population=1000)`            |
| Quick / CLI smoke population | **48**                | `python -m engine.aite.runner` / `run_quick_cycle()` |
| Survivor book                | **10–40** (target 20) | `ZERO_AITE_TARGET_BOTS` / `MIN_BOTS`–`MAX_BOTS`      |
| Paper fund                   | **₹10,00,000**        | `ZERO_AITE_PAPER_FUND` (see `.env.example`)          |


```bash
# Quick offline-friendly cycle (pop=48, survivors=10)
python -m engine.aite.runner

# Full ALGORY-scale breed (1000 candidates → survivors)
python -c "from engine.aite import run_generation_cycle; print(run_generation_cycle(n_population=1000))"
```

State persists under `db/aite/` (`bots.json`, `portfolio.json`, `fund.json`, `daemon_state.json`, JSONL logs).

### Dependencies (daemon / runner)

Already covered by `pip install -r requirements.txt` core + live-data lines:

- **Required for daemon/runner:** `numpy`, `pandas`, `requests`, `yfinance`, `pytz`
- **UI tab:** `streamlit`, `plotly` (3D graph is in-repo canvas JS — **do not** add `three` / three.js to pip)
- **Optional MT5:** `pip install MetaTrader5` (Windows + MT5 terminal; lazy-imported)

### MT5 paper steps (India brokers)

MT5 is **off by default**. AITE stays on local paper / simulated fills unless all of the following hold:

1. Install the package: `pip install MetaTrader5`
2. Open the MetaTrader 5 terminal, log into a **demo/paper** account, and **enable AutoTrading** (toolbar / Tools → Options → Expert Advisors).
3. Confirm index symbols in Market Watch match your broker (names vary by India CFD broker).
4. Map ZERO UI labels → Market Watch strings via env (see `engine/aite/config.py` → `MT5_SYMBOL_MAP`):


| ZERO UI symbol | Env var(s)                                       | Default MT5 name |
| -------------- | ------------------------------------------------ | ---------------- |
| `NIFTY 50`     | `ZERO_AITE_MT5_NIFTY` or `ZERO_AITE_MT5_NIFTY50` | `NIFTY`          |
| `BANKNIFTY`    | `ZERO_AITE_MT5_BANKNIFTY`                        | `BANKNIFTY`      |
| `SENSEX`       | `ZERO_AITE_MT5_SENSEX`                           | `SENSEX`         |


```bash
# Windows PowerShell
$env:ZERO_AITE_MT5="1"
$env:ZERO_AITE_MT5_NIFTY="NIFTY50"   # example — use your broker's exact name
$env:ZERO_AITE_PAPER_FUND="1000000"

# Unix
export ZERO_AITE_MT5=1
export ZERO_AITE_MT5_NIFTY=NIFTY50
export ZERO_AITE_PAPER_FUND=1000000
```

Copy `.env.example` → `.env` for a full checklist. **Live cash MT5 trading is intentionally out of scope** — without `ZERO_AITE_MT5=1` + a connected terminal, AITE never leaves local paper sim.

### Honesty: ALGORY vs ZERO AITE


| Claim                             | Reality                                                                                                                           |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| "Install ALGORY via pip"          | **False** — no proprietary ALGORY binary / official `algory` PyPI package is wired here                                           |
| Open-source "ALGORY-like" drop-in | **Not found** as a fitting dependency (searched PyPI/GitHub); unrelated MT5 wrappers exist but are not this loop                  |
| What ZERO ships                   | `**engine/aite/` is the implementation** — genetic breed, OOS exam, portfolio, paper/MT5 deploy, 24/7 daemon, 08:45 IST premarket |


### Module map


| Path                     | Role                                                                    |
| ------------------------ | ----------------------------------------------------------------------- |
| `engine/aite/`           | Breeding, exam, portfolio, deploy, daemon, premarket, briefs, orderflow |
| `engine/aite/config.py`  | Paper fund, breed knobs, IST schedule, `MT5_SYMBOL_MAP`                 |
| `engine/aite/service.py` | Lazy singleton `get_aite_service()` for UI                              |
| `ui/aite/`               | Streamlit panel (`from ui.aite import render_aite_panel`)               |
| `tests/test_aite_*.py`   | Core + daemon smoke tests                                               |
| `.env.example`           | Documented `ZERO_AITE_*` env vars                                       |


---

## 🧬 The V1.1 Intelligence Layer

### Session-IV Volatility Layer (`engine/volatility_forecast.py` + `data/india_vix.py`)

Replaces the legacy hardcoded `iv = 15.0`. Fetches **India VIX** (NSE → yfinance `^INDIAVIX`, 15-min cache + last-good persistence) and blends it with a model forecast: **EGARCH(1,1) → GJR-GARCH(1,1)** (optional `arch` package) → **EWMA** (RiskMetrics λ=0.94, pure numpy) → **ATR%** fallback. Every prediction now reports `iv_used`, `vol_method`, and `india_vix`.

### TSFM Ensemble Leg (`engine/tsfm_predictor.py`)

Optional time-series foundation model forecasts alongside the calibrated envelope: **Chronos-2** (covariate-informed — GIFT premium, VIX, PCR, sentiment feed in as covariates), **Kronos** (finance K-line foundation model, CPU-friendly), **TimesFM 2.5**. Returns P10/P50/P90 quantiles plus `compare_vs_point` disagreement metrics. Fully no-op safe: `status: 'unavailable'` when no backend is installed.

### Agent Debate Engine (`engine/agent_debate.py`)

TradingAgents-style deliberation on every prediction: **Bull Researcher** argues the move, **Bear Researcher** rebuts, **Risk Manager** grades the risk, **Portfolio Manager** issues a structured verdict (`action`, `conviction`, `kill_condition`, `position_size_hint_pct`). Gemini-backed when `GEMINI_API_KEY` is set; deterministic factor-based debate otherwise. Every verdict is appended to `db/agent_decisions.jsonl` for future accuracy scoring.

### Options Intelligence (`engine/options_analytics.py` + chain snapshots)

- **Snapshots**: `snapshot_option_chain()` persists timestamped chains to `db/options_snapshots/` (parquet or JSONL).
- **OI-change vectors** + buildup classification (`LONG_BUILDUP`, `SHORT_COVERING`, …).
- **IV smile** (quadratic fit, ATM IV, 25Δ skew proxy) and **ATM IV term structure**.
- **Max-pain drift** across intraday snapshots.
- **Multi-leg strategies**: straddle / strangle / iron condor / bull-call-spread builders, vectorized expiry payoff, breakevens, and **POP estimates** from ZERO's calibrated bands.

### Indian Transaction-Cost Model (`engine/india_costs.py`)

STT (delivery/intraday/futures/options/exercise), NSE txn charges, 18% GST on brokerage+txn, SEBI charges, stamp duty (buy-side, segment-aware), flat ₹20-style brokerage, and slippage bps. `net_pnl()`, `apply_to_trades()`, and an exact `breakeven_points()` solver. Rates are dataclass fields — verify against the latest Union Budget.

### Provider Registry (`data/providers/`)

Unified `get_ohlc()` / `get_quote()` with health-scored failover across NSE → BSE → yfinance, rolling success-rate persistence (`db/provider_health.json`), and a `status_report()` for the UI. Wraps the existing scrapers — nothing re-implemented, nothing broken.

### Broker Adapters (`engine/broker/`)

Paper broker by default. Live REST adapters for **Dhan, Fyers, Zerodha Kite, Angel One** behind a **dual-layer safety gate**: every live order requires both `armed=True` *and* `ZERO_BROKER_ARMED=1` in the environment, credentials come only from env vars, and all actions append to `db/broker_audit.jsonl`. Live trading is impossible to trigger accidentally.

### Daily IC Memo (`engine/report_generator.py`)

Deterministic, FinRobot-style Investment Committee memo rendered from the prediction matrix: executive summary, per-index table with conformal bands, evidence & drivers, agent consensus & strategy, debate verdict, risk & kill conditions, disclaimer. Auto-written to `obsidian_vault/01_Daily_Logs/<date>-ZERO-Memo.md` by the daily updater and via `python cli.py memo`.

---

## 🏗️ Core Architecture

```text
ZERO/
├── app.py                     # Streamlit Quantum Terminal (entry point & fast splash)
├── cli.py                     # Headless CLI: predict / train / backtest / update / accuracy / memo
├── convert_playlist.py        # YouTube Video & Playlist ingestion pipeline
├── config.py                  # Tickers, weights, ML + calibration parameters
│
├── data/                      # Ingestion layer (network I/O, caches, feature store)
│   ├── live_index_service.py  #   Live NIFTY/BANKNIFTY/SENSEX price scraper (3-tier fallback)
│   ├── india_vix.py           #   India VIX fetch (NSE → yfinance, cache + last-good)      [V1.1]
│   ├── kronos_adapter.py      #   Kronos symbol catalog, K-line fetch, session grids     [KRONOS]
│   ├── options_chain.py       #   NSE OI walls, PCR, max-pain + intraday snapshots        [V1.1 +]
│   ├── providers/             #   Health-scored failover registry (NSE→BSE→yfinance)      [V1.1]
│   ├── market_news.py         #   News feeds (WorldMonitor + RSS) + NLP sentiment
│   └── historical.py          #   Prior OHLC, ATR, VWAP
│
├── engine/                    # Quantitative Core
│   ├── live_price_server.py   #   Local HTTP server on :7701 — sub-100ms live ticker
│   ├── zero_agi_engine.py     #   ZERO AGI multimodal chart analysis (Gemini + offline)
│   ├── zero_engine_kb.py      #   Dynamic RAG Knowledge Base orchestrator
│   ├── prediction_matrix.py   #   Master per-index OHLC prediction pipeline
│   ├── volatility_forecast.py #   EGARCH/GJR → EWMA → ATR session-IV layer               [V1.1]
│   ├── tsfm_predictor.py      #   Chronos-2 / Kronos / TimesFM ensemble leg              [V1.1]
│   ├── kronos/                #   Vendored Kronos K-line foundation model (MIT)          [KRONOS]
│   ├── kronos_service.py      #   Kronos load/forecast lazy singleton (never raises)     [KRONOS]
│   ├── kronos_backtest.py     #   Rolling-origin Kronos walk-forward backtester          [KRONOS]
│   ├── kronos_finetune/       #   Two-stage finetuning pipeline + YAML configs           [KRONOS]
│   ├── kronos_results_store.py #  Forecast history store (db/kronos_predictions/)       [KRONOS]
│   ├── agent_debate.py        #   Bull/bear → risk → PM verdict + decision log           [V1.1]
│   ├── options_analytics.py   #   OI-change, IV smile, multi-leg strategies + POP        [V1.1]
│   ├── india_costs.py         #   Indian transaction-cost model (STT/GST/stamp/…)        [V1.1]
│   ├── report_generator.py    #   Deterministic daily IC memo → Obsidian                 [V1.1]
│   ├── broker/                #   Paper + Dhan/Fyers/Kite/Angel adapters (armed-gated)   [V1.1]
│   ├── nautilus_order_engine.py # Advanced TIF/Contingency order execution
│   ├── fincept_platform.py    #   Quant team thesis, derivatives Greeks, inter-market
│   ├── quant_dinge_engine.py  #   Regime classification & strategy setups
│   ├── multi_agent_consensus.py # 4-agent heuristic consensus
│   ├── advanced_backtest.py   #   Walk-forward + DM/PSR/DSR + embargo                    [V1.1 +]
│   ├── xgboost_predictor.py   #   Multi-timeframe %-change XGBoost
│   ├── monte_carlo.py         #   Ruin-probability risk gate
│   ├── genetic_mutator.py     #   StrategyQuant-style evolutionary rules
│   ├── aite/                  #   ZERO AITE: breed→exam→portfolio→daemon/MT5   [AITE]
│   ├── zero_backup_service.py #   Dual-vault sync manager
│   ├── obsidian_sync.py       #   Automated daily note sync
│   ├── brain_engine.py        #   JSON knowledge chunking & SHA1 dedup
│   ├── calibrator.py          #   Adaptive calibration learning layer
│   └── learning_service.py    #   Daily autonomous feedback loop
│
├── obsidian_vault/            # 🧠 Native Obsidian Second Brain Vault
│   ├── ZERO.md                #   Master graph root node & map of content
│   ├── second zero.md         #   Backup graph node (synced after 24h)
│   ├── 01_Daily_Logs/         #   Auto-synced daily predictions + IC memos               [V1.1 +]
│   ├── 02_Mental_Models/      #   First principles, probabilistic thinking
│   ├── 03_Cognitive_Biases/   #   FOMO, loss aversion, psychology framework
│   ├── 04_YouTube_Knowledge/  #   YouTube ingested knowledge & index
│   └── 05_AI_Memory/          #   Executable AI capabilities & skills
│
├── ui/                        # Visual layer (Fincept/Bloomberg-style cards)
├── sandbox/                   # Research notes & competitive analysis (non-runtime)      [V1.1]
└── db/                        # SQLite, feedback logs, ZERO Brain JSON, decision/audit logs
```

---

## 🛠️ Getting Started & Installation

### 1. Prerequisites

- **Python 3.10+**
- Internet access (live scraping & YouTube transcript API)
- **Gemini API Key** *(optional — ZERO AGI and the debate engine work fully offline without one)*

### 2. Installation

```bash
git clone https://github.com/CHARANVALLERU/ZERO-TERMINAL-under-work-.git
cd ZERO-TERMINAL-under-work-
pip install -r requirements.txt
```

### 3. Running the Terminal

```bash
streamlit run app.py
```

**Prefer `run.bat` on Windows** — it activates `.venv`, sets `TOKENIZERS_PARALLELISM=false`, `HF_HUB_DISABLE_TELEMETRY=1`, and `STREAMLIT_SERVER_FILE_WATCHER_TYPE=poll`, and passes through an existing `HF_TOKEN` (commented example in the bat). You can still run `streamlit run app.py` after activating the venv.

**Clean relaunch (Windows):** close any prior Streamlit window, then double-click `run.bat` (or from the repo root: `.venv\Scripts\activate` → `streamlit run app.py`). Optional: `set HF_TOKEN=hf_...` (or `HUGGING_FACE_HUB_TOKEN`) before launch for higher Hugging Face Hub rate limits — not required for public NeoQuasar/Kronos weights.

**Streamlit watcher / torchvision spam:** Streamlit may probe `transformers` vision modules and log `ModuleNotFoundError: torchvision` when torchvision is absent — **non-fatal**, but noisy. Install a matching `torchvision`, prefer `run.bat`, and use the shipped `.streamlit/config.toml` (`fileWatcherType = "poll"`, `.venv` blacklisted).

### 4. Optional power-ups (V1.1)

All optional — every feature degrades gracefully without them:

```bash
pip install arch                  # EGARCH/GJR-GARCH volatility forecasts
pip install chronos-forecasting   # Chronos-2 TSFM leg (pulls torch)
pip install "timesfm[torch]"      # TimesFM 2.5 leg
pip install torch torchvision einops huggingface_hub safetensors  # KRONOS ENGINE (torchvision must match torch build; quiets Streamlit+transformers)
pip install MetaTrader5           # ZERO AITE MT5 paper path (Windows + MT5 terminal; see ZERO AITE section)
```

### 5. Broker adapters (paper by default)

Live adapters stay inert unless **both** conditions hold: `armed=True` in code **and** `ZERO_BROKER_ARMED=1` in the environment, plus broker credentials (`DHAN_`*, `KITE_*`, `FYERS_*`, `ANGEL_*`). Without them, `get_broker()` returns the paper broker.

---

## 💻 CLI Operations

```bash
# Ingest YouTube Video or Playlist into Brain Engine & Obsidian Graph
python convert_playlist.py --url "https://www.youtube.com/watch?v=YOUR_VIDEO_ID"

# Print today's prediction matrix as JSON (now with iv_used, TSFM, debate keys)
python cli.py predict

# Retrain the calibration layer on historical logs
python cli.py train

# Walk-forward accuracy report (now with DM / PSR / DSR significance)
python cli.py backtest

# Baseline accuracy report from the log
python cli.py accuracy

# Execute full daily cycle: fetch actuals -> log -> retrain -> IC memo
python cli.py update

# Write today's IC memo to the Obsidian vault
python cli.py memo
```

---

## 🧠 Obsidian Second Brain Integration

1. Open **Obsidian** → Click **"Open folder as vault"**.
2. Select the `obsidian_vault` directory inside `ZERO-TERMINAL-under-work-`.
3. Open `ZERO.md` and press `Ctrl + G` (or `Cmd + G`) to view the interactive **Knowledge Graph**!
4. Daily IC memos land in `01_Daily_Logs/` automatically after each update cycle.

---

## 🔒 Security & Privacy

ZERO is designed to be **local-first**. All data scraping, quantitative analysis, strategy prediction, chart vision inference, and walk-forward backtesting run **entirely on your local machine**. No data is sent to external servers when using the offline ZERO Brain engine. Broker credentials are read only from environment variables, are never logged, and live order paths are sealed behind a dual-layer armed gate with a full audit trail.

---

## ⚠️ Disclaimer

*For quantitative research and educational use only. Market predictions are probabilistic. Trading involves substantial financial risk; consult a licensed financial advisor before acting on any output generated by this software.*

**ZERO V1.1 // Renaissance of Market Predictions**
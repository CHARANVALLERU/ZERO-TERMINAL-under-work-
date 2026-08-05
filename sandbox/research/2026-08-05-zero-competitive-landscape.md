# ZERO — Competitive Landscape & Upgrade Roadmap
**Date:** 2026-08-05 · **Scope:** `D:\ZERO_FRESH` (engine, data, ui, db, obsidian_vault) · **Status:** Reference

> **UPDATE 2026-08-05 (same day):** items 1–10 below were **PROMOTED** in a 9-agent
> build wave and shipped as ZERO V1.1. See `sandbox/research/2026-08-05-v11-build-report.md`
> for the agent roster, file ownership map, and verification results.

---

## 1. What ZERO actually is (code-verified, not README-verified)

**ZERO V1.0** is a **local-first, Streamlit-based Indian-market intelligence terminal**.
One sentence: it predicts the day's OHLC envelope for NIFTY 50 / BANKNIFTY / SENSEX
before the 9:15 open, then layers multi-agent reasoning, order suggestions, chart-vision
AI, and an Obsidian "second brain" on top.

### Pipeline (as implemented)

```
data/ (scrapers)                    engine/ (quant core)
──────────────────────              ──────────────────────────────────
global_feeds (US close, VIX)   ──▶  opening_predictor  → gap estimate
gift_nifty (GIFT premium)      ──▶  range_predictor    → ATR envelopes
adr_tracker (ADR delta)        ──▶  prediction_matrix  → per-index OHLC
options_chain (PCR, OI walls)  ──▶  calibrator         → ridge residual fix + conformal bands
market_news (VADER sentiment)  ──▶  news_impact        → breaking-news overlay shift
live_index_service (BSE→NSE→yfinance)  xgboost_predictor → MTF % -change targets (intraday+weekly)
                                ──▶  multi_agent_consensus (4 heuristic agents, TradingAgents-style)
                                ──▶  quant_dinge_engine (regime classifier + setups)
                                ──▶  fincept_platform (BS Greeks, intermarket, quant team)
                                ──▶  nautilus_order_engine (paper IOC/FOK/GTC/OCO brackets)
                                ──▶  monte_carlo (ruin prob gate) + genetic_mutator (StrategyQuant-style)
                                ──▶  zero_agi_engine (Gemini Vision / offline pixel-momentum chart AI)
                                ──▶  zero_engine_kb + brain_engine (RAG over Obsidian + YouTube)
ui/ + live_price_server (:7701) ──▶ Streamlit terminal, sub-100ms ticker iframe
db/                           ──▶ feedback_log, calibrator.json, xgb models, brain JSON
obsidian_vault/               ──▶ ZERO.md ⇄ second zero.md (24h-delayed backup sync)
```

### Verified strengths
- **Strict no-lookahead discipline**: stationarized %-change XGBoost targets, walk-forward
  folds, week-static weekly features, calibrator committed per leg.
- **Graceful degradation everywhere**: every optional dep (xgboost, sklearn, Gemini,
  Streamlit, pyarrow) has a numpy/pure-python fallback. Runs cold with zero API keys.
- **Calibration-first philosophy**: conformal-style P10/P90 bands + residual correction —
  most retail tools never touch this.
- **Genuinely unique combo**: YouTube→Obsidian knowledge graph feeding a chart-vision
  trade-setup generator. No comparable open-source project does this.

### Verified weaknesses
- `multi_agent_consensus.py` is **keyword-counting heuristics**, not LLM agents
  (no debate, no structured output, no memory of past verdicts).
- **No real broker bridge** — Nautilus engine is paper-only.
- Options analytics stop at PCR / max-OI walls / single ATM Greeks (no IV surface,
  no OI-change time series, no multi-leg strategies, no expiry-day models).
- Volatility input is a hardcoded `iv = 15.0` in `prediction_matrix.py` — no GARCH,
  no India VIX fetch.
- Backtester lacks Indian transaction-cost modeling (STT, stamp duty, impact) and
  significance testing vs a random-walk baseline.
- `README.md` is **duplicated** — the entire document repeats from ~line 290. Quick fix.

---

## 2. What the niche looks like (Aug 2026, web-verified)

| Project | What it does better than ZERO today |
|---|---|
| **TradingAgents v0.3.x** (TauricResearch) | Real LLM agents: structured-output Research Manager / Trader / Portfolio Manager, bull-vs-bear **researcher debate**, LangGraph checkpoint resume, **persistent decision log**, multi-provider LLM registry, look-ahead-filtered data contract. |
| **FinRobot** (AI4Finance) | Strict split of **deterministic compute vs LLM narration** with numeric provenance; 7 data providers with automatic failover; IC-memo style 13-chapter reports; Desktop app packaging. |
| **Kronos** (NeoQuasar, AAAI 2026) | Open-source **K-line foundation model** (12B candles, 45 exchanges). `Kronos-mini` (4.1M) / `Kronos-small` (24.7M) run on CPU; zero-shot OHLC forecasts + volatility forecasts + synthetic data generation. |
| **Chronos-2** (Amazon, Oct 2025) | Zero-shot **multivariate + covariate-informed** forecasting with native quantile outputs — GIFT premium, VIX, PCR can be fed as covariates. 120M params. |
| **TimesFM 2.5** (Google) | 200M params, 16k context, continuous **quantile head** (P10/P50/P90) — philosophically identical to ZERO's conformal bands. |
| **AlgoTest / Streak / Opstra / Sensibull** (India retail algo) | Multi-leg options strategy builder + payoff curves, 7.5y options backtests, OI-change analytics, **30+ broker integrations** for one-click live deployment, NSE F&O margin calculator. |
| **arXiv 2606.27100** (TSFM benchmark, 2026) | Reality check: TSFMs beat naive baselines only *sparsely* — Diebold–Mariano significance is the honesty bar. Local supervised models still win on some assets/regimes. |

---

## 3. Suggested updates / additions (prioritized)

### P0 — Cheap, high-value, zero new deps

1. **Fix `README.md` duplication** — delete the repeated half (~lines 290-494).
2. **Replace hardcoded `iv = 15.0` with India VIX + GARCH**
   - Fetch India VIX from NSE (same scrape pattern as `options_chain.py`).
   - Optional `arch` package → EGARCH/GJR-GARCH 1-day vol forecast to scale the
     ATR envelope. Falls back to current ATR path when absent (matches ZERO's
     graceful-degradation convention).
3. **Statistical honesty in `advanced_backtest.py`**
   - Add **Diebold–Mariano test vs random-walk/naive baseline** and
     **Probabilistic/Deflated Sharpe Ratio** (López de Prado) to the report.
   - Add **embargo periods** to the walk-forward splits (purged K-fold) — tiny change,
     closes the last leakage edge between train/test boundaries.
4. **Indian cost model in the backtester** — STT (0.1% both sides delivery / 0.025% sell
   intraday / 0.0125% options sell on premium), exchange txn, GST, stamp duty, SEBI fees,
   + configurable impact bps. Without this every Sharpe number is optimistic by a wide margin.

### P1 — Biggest capability jumps

5. **LLM-backed agent debate layer** (`engine/agent_debate.py`, new)
   - Keep the heuristic 4-agent engine as the offline floor; add an **optional** Gemini
     layer mirroring TradingAgents v0.3: bull researcher vs bear researcher argue the
     prediction-matrix output, a Risk Manager and a "Portfolio Manager" verdict gate it.
   - **Structured outputs only** (JSON schema: bias, confidence, kill-condition) so the
     QuantDinger/Nautilus legs can consume it programmatically.
   - Persist every debate to `db/agent_decisions.jsonl` → gives you a decision log you can
     later score against actuals (closes the learning loop the calibrator already started).
6. **TSFM ensemble leg** (`engine/tsfm_predictor.py`, new)
   - **Chronos-2** first: covariate-informed zero-shot forecast — feed close-price history
     as target, GIFT premium / VIX / PCR / sentiment as covariates → quantile paths.
     Compare its P50 against the calibrator output; log disagreement as a feature.
   - **Kronos-small** as the finance-native alternative (CPU-friendly, K-line tokenizer,
     also gives a **volatility forecast** that feeds suggestion #2).
   - Blend as a third leg next to geometric-envelope + XGBoost (weight by rolling
     out-of-sample DM-test winner — the arXiv benchmark warns TSFMs don't always win).
7. **Options intelligence upgrade** (`data/options_chain.py` + new `engine/options_analytics.py`)
   - **Snapshot the chain intraday** (every 5–15 min into parquet) → OI-change vectors,
     OI buildup classification (long buildup / short covering etc.), max-pain drift.
   - **IV smile/skew per expiry** + ATM IV term structure → replace the `vix*1.2` IV proxy
     in the Greeks module.
   - **Multi-leg strategy presets** (straddle/strangle/iron condor/bull-call-spread) with
     payoff-diagram data + POP estimate from the calibrated bands — this is the
     AlgoTest/Sensibull table-stakes ZERO currently lacks.
   - **Expiry-day regime**: special handling for weekly expiry sessions (gamma effects
     near max-pain) in QuantDinger's regime classifier.

### P2 — Structural / product-level

8. **Provider registry with failover** (`data/providers/`, new)
   - FinRobot-style abstraction: `get_ohlc(symbol)` → tries NSE → BSE → yfinance →
     OpenBB (optional) with per-provider health scores. ZERO already has 3-tier fallback
     in `live_index_service.py` — generalize that pattern to *all* data legs.
9. **Broker bridge behind Nautilus** (`engine/broker/`, new)
   - `paper_brokerage.py` already defines the interface; add **Dhan / Fyers / Zerodha Kite
     / Angel One SmartAPI** adapters (all have free REST APIs; Dhan even offers free
     historical intraday data). Ship disabled-by-default with explicit armed flag.
10. **Daily IC-memo report** (`engine/report_generator.py`, new)
    - FinRobot-style: deterministic numbers from the prediction matrix + Gemini narration,
    - auto-written to `obsidian_vault/01_Daily_Logs/` — extends the existing
      `obsidian_sync.py` from raw sync → authored narrative with evidence links.
11. **Regime-conditioned ensembling** — QuantDinger already classifies regimes; log
    per-leg (geometric / XGBoost / TSFM) MAE **per regime** and re-weight the blend
    per regime instead of globally. This is where the arXiv TSFM paper says local
    models claw back wins.
12. **Optional RL sandbox, not production** — FinRL-style policy learning belongs in
    `sandbox/experiments/` only; daily-index OHLC prediction has too little signal for RL
    to beat the calibrated ensemble honestly.

---

## 4. Effort × impact map

```
high impact │  5 LLM debate        6 TSFM leg          9 broker bridge
            │  3 DM-test honesty   7 options intel     10 IC memo
────────────┼─────────────────────────────────────────────────────────
low impact  │  1 README fix        2 GARCH/India VIX   4 cost model
            │                      8 provider registry  12 RL (skip)
              low effort ──────────────────────────────▶ high effort
```
Recommended order: **1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 10 → 9** (skip 12).

---

## 5. Sources

- TradingAgents — https://github.com/TauricResearch/TradingAgents (v0.3.1, Jul 2026)
- FinRobot — https://github.com/ai4finance-foundation/finrobot
- Kronos — https://github.com/shiyu-coder/Kronos · arXiv 2508.02739 (AAAI 2026)
- Chronos-2 — https://github.com/amazon-science/chronos-forecasting · arXiv 2510.15821
- TimesFM 2.5 — https://github.com/google-research/timesfm
- TSFM benchmark — arXiv 2606.27100 "Pretrained Time-Series Foundation Models for Financial Return Forecasting"
- AlgoTest — https://algotest.in · AlgoTest vs Streak (Feb 2026) — https://algotest.in/blog/algotest-vs-streak/
- Streak — https://streak.zerodha.com · free-options backtesting roundup — https://algotest.in/blog/free-options-backtesting/

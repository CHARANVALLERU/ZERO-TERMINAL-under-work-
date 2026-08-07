"""
ZERO AITE premarket research — observational 8-section brief.

Covers NIFTY 50 / BANKNIFTY / SENSEX with prior-day 1H context and day
predictions via ``generate_prediction_matrix`` when available.

NEVER emits buy/sell recommendations — research / scenario language only.
Persists to ``db/aite/premarket/YYYY-MM-DD.json``.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Section keys (exactly 8). Aliases accepted on read for "S/R" / "no-trade".
SECTION_KEYS = (
    "context",
    "trend",
    "support_resistance",
    "bull",
    "bear",
    "invalidation",
    "no_trade",
    "questions",
)

_BANNED = re.compile(
    r"\b(buy|sell|long|short|accumulate|reduce|enter|exit|call to action)\b",
    re.IGNORECASE,
)


def _today_ist() -> str:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
    except Exception:
        return (datetime.utcnow() + timedelta(hours=5, minutes=30)).date().isoformat()


def _premarket_dir() -> Path:
    from engine.aite import config as cfg

    d = cfg.AITE_DB_DIR / "premarket"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sanitize(text: str) -> str:
    """Strip directive trade verbs; keep observational wording."""
    if not text:
        return text

    def _repl(m: re.Match) -> str:
        w = m.group(0).lower()
        mapping = {
            "buy": "upside interest",
            "sell": "downside interest",
            "long": "upside bias",
            "short": "downside bias",
            "accumulate": "build exposure gradually",
            "reduce": "lighten exposure",
            "enter": "engage",
            "exit": "stand down",
            "call to action": "observation",
        }
        return mapping.get(w, "observe")

    return _BANNED.sub(_repl, text)


def _empty_sections(msg: str = "Data unavailable; sections deferred.") -> Dict[str, str]:
    return {k: _sanitize(msg) for k in SECTION_KEYS}


def _load_daily_frame(symbol: str, bars: int = 80):
    """Lazy market frame — never raises."""
    try:
        from engine.aite.exam import load_market_frame

        return load_market_frame(symbol, bars=bars)
    except Exception:
        return None


def _prior_day_1h_context(symbol: str) -> Dict[str, Any]:
    """
    Prior-session 1H context. Tries hourly Yahoo bars; falls back to daily
    OHLC summarized as a pseudo-session. No network until called.
    """
    out: Dict[str, Any] = {
        "symbol": symbol,
        "source": "none",
        "bars": 0,
        "prior_high": None,
        "prior_low": None,
        "prior_close": None,
        "prior_open": None,
        "range_pts": None,
        "note": "",
    }

    # 1) Try yfinance 1h (lazy)
    try:
        import yfinance as yf  # type: ignore

        ticker = {
            "NIFTY 50": "^NSEI",
            "BANKNIFTY": "^NSEBANK",
            "SENSEX": "^BSESN",
        }.get(symbol, symbol)
        df = yf.download(
            ticker,
            period="5d",
            interval="1h",
            progress=False,
            auto_adjust=True,
        )
        if df is not None and len(df) >= 4:
            if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
                df.columns = [c[0].lower() for c in df.columns]
            else:
                df.columns = [str(c).lower() for c in df.columns]
            # Last completed calendar day group
            idx = df.index
            if hasattr(idx, "tz_localize") or getattr(idx, "tz", None) is not None:
                try:
                    from zoneinfo import ZoneInfo

                    idx_local = idx.tz_convert(ZoneInfo("Asia/Kolkata")) if idx.tz else idx
                except Exception:
                    idx_local = idx
            else:
                idx_local = idx
            days = sorted({d.date() if hasattr(d, "date") else d for d in idx_local})
            if len(days) >= 2:
                prior = days[-2]
            else:
                prior = days[-1]
            mask = [
                (d.date() if hasattr(d, "date") else d) == prior for d in idx_local
            ]
            session = df.loc[mask]
            if len(session) >= 1:
                o = float(session["open"].iloc[0])
                h = float(session["high"].max())
                l = float(session["low"].min())
                c = float(session["close"].iloc[-1])
                out.update(
                    {
                        "source": "yfinance_1h",
                        "bars": int(len(session)),
                        "prior_open": round(o, 2),
                        "prior_high": round(h, 2),
                        "prior_low": round(l, 2),
                        "prior_close": round(c, 2),
                        "range_pts": round(h - l, 2),
                        "session_date": str(prior),
                        "note": f"{len(session)} hourly bars on {prior}",
                    }
                )
                return out
    except Exception as exc:
        out["note"] = f"1h fetch skipped: {exc}"

    # 2) Daily frame fallback (exam synthetic / historical)
    try:
        df = _load_daily_frame(symbol, bars=40)
        if df is not None and len(df) >= 2:
            cols = {str(c).lower(): c for c in df.columns}
            def col(name: str):
                c = cols.get(name)
                return df[c] if c is not None else None

            o_s, h_s, l_s, c_s = col("open"), col("high"), col("low"), col("close")
            if c_s is not None:
                # Prior completed day = second-to-last bar
                i = -2 if len(df) >= 2 else -1
                o = float(o_s.iloc[i]) if o_s is not None else float(c_s.iloc[i])
                h = float(h_s.iloc[i]) if h_s is not None else o
                l = float(l_s.iloc[i]) if l_s is not None else o
                c = float(c_s.iloc[i])
                out.update(
                    {
                        "source": "daily_fallback",
                        "bars": 1,
                        "prior_open": round(o, 2),
                        "prior_high": round(h, 2),
                        "prior_low": round(l, 2),
                        "prior_close": round(c, 2),
                        "range_pts": round(h - l, 2),
                        "note": "Derived from prior daily bar (1H unavailable).",
                    }
                )
                return out
    except Exception as exc:
        out["note"] = f"daily fallback failed: {exc}"

    out["note"] = out.get("note") or "No prior-day context available."
    return out


def _safe_prediction_matrix() -> Dict[str, Any]:
    """Lazy call into existing prediction pipeline; degrade to {}."""
    try:
        from engine.prediction_matrix import generate_prediction_matrix

        matrix = generate_prediction_matrix()
        return matrix if isinstance(matrix, dict) else {}
    except Exception:
        return {}


def _pred_slice(matrix: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    raw = matrix.get(symbol) if matrix else None
    if not isinstance(raw, dict) or "error" in raw:
        return {"available": False, "error": (raw or {}).get("error", "missing")}
    keys = (
        "prev_close",
        "pred_open",
        "pred_high",
        "pred_low",
        "pred_close",
        "atr",
        "iv_used",
        "vol_method",
    )
    slim = {k: raw.get(k) for k in keys if k in raw}
    slim["available"] = True
    return slim


def _trend_from_frame(symbol: str) -> Tuple[str, str]:
    """Return (regime, narrative) using AITE indicators when possible."""
    try:
        from engine.aite.indicators import compute_features, regime_label

        df = _load_daily_frame(symbol, bars=120)
        if df is None or getattr(df, "empty", True):
            return "UNKNOWN", "Insufficient history for trend classification."
        feats = compute_features(df)
        if feats.empty:
            return "UNKNOWN", "Feature matrix empty."
        regime = regime_label(feats)
        mom = float(feats["mom_20"].iloc[-1]) if "mom_20" in feats else 0.0
        adx = float(feats["adx"].iloc[-1]) if "adx" in feats else 0.0
        narrative = (
            f"Regime={regime}; 20-bar momentum {mom:+.2f}%; ADX≈{adx:.1f}. "
            "Classification is descriptive, not a trade directive."
        )
        return regime, narrative
    except Exception as exc:
        return "UNKNOWN", f"Trend unavailable ({exc})."


def _sr_levels(ctx: Dict[str, Any], pred: Dict[str, Any]) -> str:
    parts = []
    if ctx.get("prior_high") is not None:
        parts.append(f"Prior session high {ctx['prior_high']}")
    if ctx.get("prior_low") is not None:
        parts.append(f"Prior session low {ctx['prior_low']}")
    if ctx.get("prior_close") is not None:
        parts.append(f"Prior close {ctx['prior_close']}")
    if pred.get("available"):
        if pred.get("pred_high") is not None:
            parts.append(f"Model day high envelope {pred['pred_high']}")
        if pred.get("pred_low") is not None:
            parts.append(f"Model day low envelope {pred['pred_low']}")
    if not parts:
        return "Support/resistance levels unavailable for this session."
    return "S/R markers: " + "; ".join(parts) + ". Levels are reference zones only."


def _build_sections(
    symbol: str,
    ctx: Dict[str, Any],
    pred: Dict[str, Any],
    regime: str,
    trend_note: str,
) -> Dict[str, str]:
    pc = ctx.get("prior_close")
    rng = ctx.get("range_pts")
    ctx_txt = (
        f"{symbol}: prior-day 1H context via {ctx.get('source', 'none')} "
        f"({ctx.get('note', '')}). "
        f"O={ctx.get('prior_open')} H={ctx.get('prior_high')} "
        f"L={ctx.get('prior_low')} C={pc}; range={rng} pts."
    )
    if pred.get("available"):
        ctx_txt += (
            f" Day model: open≈{pred.get('pred_open')}, "
            f"close≈{pred.get('pred_close')}, "
            f"envelope [{pred.get('pred_low')} … {pred.get('pred_high')}]"
            f" (vol={pred.get('vol_method', 'n/a')})."
        )
    else:
        ctx_txt += " Day prediction matrix unavailable; context is price-structure only."

    bull = (
        f"Bull case for {symbol}: acceptance above prior high "
        f"{ctx.get('prior_high')} with model high {pred.get('pred_high')} as "
        f"stretch marker; regime currently {regime}. Scenario only — not a directive."
    )
    bear = (
        f"Bear case for {symbol}: rejection below prior low "
        f"{ctx.get('prior_low')} with model low {pred.get('pred_low')} as "
        f"stretch marker; regime currently {regime}. Scenario only — not a directive."
    )
    invalidation = (
        f"Thesis invalidation: sustained trade outside the prior range "
        f"[{ctx.get('prior_low')} … {ctx.get('prior_high')}] "
        f"and beyond model envelope [{pred.get('pred_low')} … {pred.get('pred_high')}] "
        "would retire today's structural map."
    )
    no_trade = (
        f"No-trade / stand-aside windows: overlapping event risk, "
        f"regime={regime} with unclear momentum, or price locked inside a "
        f"sub-ATR coil near {pc}. Prefer observation over engagement when "
        "structure is two-sided and unresolved."
    )
    questions = (
        f"Open questions — {symbol}: Does GIFT / global cue confirm the "
        f"model open {pred.get('pred_open')}? Is prior value ({pc}) defended "
        "in the first hour? Which scenario (bull/bear) prints first without "
        "violating invalidation?"
    )

    sections = {
        "context": ctx_txt,
        "trend": trend_note,
        "support_resistance": _sr_levels(ctx, pred),
        "bull": bull,
        "bear": bear,
        "invalidation": invalidation,
        "no_trade": no_trade,
        "questions": questions,
    }
    return {k: _sanitize(v) for k, v in sections.items()}


def build_symbol_brief(
    symbol: str,
    matrix: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """One-symbol 8-section research block."""
    ctx = _prior_day_1h_context(symbol)
    pred = _pred_slice(matrix or {}, symbol)
    regime, trend_note = _trend_from_frame(symbol)
    sections = _build_sections(symbol, ctx, pred, regime, trend_note)
    return {
        "symbol": symbol,
        "regime": regime,
        "prior_day_1h": ctx,
        "prediction": pred,
        "sections": sections,
    }


def run_premarket_brief(
    symbols: Optional[List[str]] = None,
    persist: bool = True,
    date_str: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build premarket research for index set. Returns PremarketReport-shaped dict.

    Never recommends buy/sell. Graceful when data / prediction matrix missing.
    """
    try:
        from engine.aite import config as cfg

        symbols = list(symbols or cfg.DEFAULT_SYMBOLS)
    except Exception:
        symbols = symbols or ["NIFTY 50", "BANKNIFTY", "SENSEX"]

    date_str = date_str or _today_ist()
    matrix = _safe_prediction_matrix()

    per_symbol: Dict[str, Any] = {}
    merged_sections: Dict[str, str] = {k: "" for k in SECTION_KEYS}
    predictions: Dict[str, Any] = {}

    for sym in symbols:
        try:
            block = build_symbol_brief(sym, matrix=matrix)
        except Exception as exc:
            block = {
                "symbol": sym,
                "regime": "UNKNOWN",
                "prior_day_1h": {"note": str(exc)},
                "prediction": {"available": False},
                "sections": _empty_sections(f"{sym}: brief failed ({exc})."),
            }
        per_symbol[sym] = block
        predictions[sym] = block.get("prediction") or {}
        secs = block.get("sections") or _empty_sections()
        for k in SECTION_KEYS:
            piece = secs.get(k, "")
            merged_sections[k] = (
                (merged_sections[k] + "\n\n" if merged_sections[k] else "")
                + f"### {sym}\n{piece}"
            )

    # Ensure exactly 8 keys, sanitized
    sections = {k: _sanitize(merged_sections.get(k, "")) for k in SECTION_KEYS}

    report: Dict[str, Any] = {
        "date": date_str,
        "symbols": symbols,
        "sections": sections,
        "predictions": predictions,
        "per_symbol": per_symbol,
        "generated_at": time.time(),
        "disclaimer": (
            "Observational research only. No buy/sell recommendations. "
            "Scenarios describe structure, not instructions to trade."
        ),
    }

    if persist:
        _persist_report(report)

    return report


def _persist_report(report: Dict[str, Any]) -> None:
    """Write dated JSON + append JSONL via store (best-effort)."""
    try:
        from engine.aite import store

        path = _premarket_dir() / f"{report.get('date', _today_ist())}.json"
        store.write_json(path, report)
        # Slim row for jsonl index
        store.save_premarket(
            {
                "date": report.get("date"),
                "symbols": report.get("symbols"),
                "generated_at": report.get("generated_at"),
                "path": str(path),
            }
        )
        store.log_event("INFO", f"Premarket brief saved {path.name}")
        # Immediate Obsidian ZERO vault note + 24h SECOND ZERO queue
        try:
            from engine.vault_sync import sync_premarket_brief
            sync_premarket_brief(report)
        except Exception:
            pass
    except Exception:
        pass


def load_premarket_brief(date_str: Optional[str] = None) -> Dict[str, Any]:
    date_str = date_str or _today_ist()
    try:
        from engine.aite import store

        path = _premarket_dir() / f"{date_str}.json"
        data = store.read_json(path, {})
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

"""
ZERO // KRONOS K-LINE FOUNDATION MODEL — KRONOS ENGINE tab console
==================================================================

Flagship panel that ports the open-source Kronos project's web console
(https://github.com/shiyu-coder/Kronos, MIT license — "NeoQuasar" model
family) into the ZERO terminal's dedicated KRONOS ENGINE tab, restyled
for the digital-core theme (gold titles, dark cards).

Kronos webui features replicated here:
  - model status display + load-model workflow
  - symbol / timeframe selection (+ free-text ticker override)
  - lookback & prediction-length controls
  - sampling controls: temperature T, nucleus top-p, sample count
  - volatility amplification option
  - run-forecast workflow with progress spinner
  - candlestick chart with predicted region (+ volume)
  - prediction summary stats (last vs predicted close, change %,
    direction, predicted high/low range, latency + device)
  - probabilistic sample paths with P10 / P50 / P90 readout
  - historical backtest (hit-rate, MAPE, interval coverage)
  - prediction history (save / list / reload)

Sibling modules (engine.kronos_service, data.kronos_adapter,
ui.kronos_charts, engine.kronos_backtest, engine.kronos_results_store)
are imported LAZILY inside functions. When one is missing or broken the
panel degrades to st.info notices — it must never crash the terminal.
"""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import streamlit as st

# ── Fallback catalogs (used only while sibling modules are still landing) ──
_FALLBACK_SYMBOLS = {
    "NIFTY 50": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "SENSEX": "^BSESN",
    "BTC-USD": "BTC-USD",
    "ETH-USD": "ETH-USD",
    "Gold Futures": "GC=F",
}
_FALLBACK_INTERVALS = {"1d": "1d", "1h": "1h", "30m": "30m", "15m": "15m", "5m": "5m"}

_INSTALL_HINT = "pip install torch einops huggingface_hub safetensors"
_TORCHVISION_HINT = (
    "torchvision optional — without it Streamlit may log non-fatal "
    "transformers vision-module noise after other backends load; "
    "Kronos forecasts still work. Quiet with: pip install torchvision"
)


# ── Lazy sibling-module accessors (never raise) ─────────────────────────────

def _get_service():
    """engine.kronos_service.get_kronos_service() or None."""
    try:
        from engine.kronos_service import get_kronos_service
        return get_kronos_service()
    except Exception:
        return None


def _get_adapter():
    """data.kronos_adapter module or None."""
    try:
        from data import kronos_adapter
        return kronos_adapter
    except Exception:
        return None


def _get_charts():
    """ui.kronos_charts module or None."""
    try:
        from ui import kronos_charts
        return kronos_charts
    except Exception:
        return None


def _get_backtest():
    """engine.kronos_backtest.run_kronos_backtest or None."""
    try:
        from engine.kronos_backtest import run_kronos_backtest
        return run_kronos_backtest
    except Exception:
        return None


def _get_store():
    """engine.kronos_results_store module or None."""
    try:
        from engine import kronos_results_store
        return kronos_results_store
    except Exception:
        return None


# ── Small pure helpers ──────────────────────────────────────────────────────

def _to_float(value: Any) -> Optional[float]:
    try:
        f = float(value)
        if pd.isna(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _fmt_price(value: Any) -> str:
    f = _to_float(value)
    return f"{f:,.2f}" if f is not None else "—"


def _rate_str(value: Any) -> str:
    """Format a rate/error metric that may arrive as a fraction or percent."""
    f = _to_float(value)
    if f is None:
        return "—"
    if 0.0 <= abs(f) <= 1.0:
        f *= 100.0
    return f"{f:.1f}%"


def _direction_label(last_close: Optional[float], pred_close: Optional[float]) -> str:
    if not last_close or pred_close is None:
        return "FLAT"
    chg = (pred_close / last_close - 1.0) * 100.0
    if chg > 0.05:
        return "UP"
    if chg < -0.05:
        return "DOWN"
    return "FLAT"


def _terminal_value(values: Any) -> Optional[float]:
    """Last element of an array-like (or the scalar itself)."""
    if values is None:
        return None
    try:
        arr = np.asarray(values, dtype=float).ravel()
        if arr.size == 0:
            return None
        return float(arr[-1])
    except Exception:
        return _to_float(values)


def _has_paths(sample_paths: Any) -> bool:
    if sample_paths is None:
        return False
    try:
        return len(sample_paths) > 0
    except Exception:
        return True


def _metric_pct_str(metrics: Dict[str, Any], *keys: str) -> str:
    """Format the first present metric as a percentage string.

    Keys ending in ``_pct`` (the engine.kronos_backtest convention) are
    already percentages and pass through unscaled; other keys go through
    the fraction-vs-percent heuristic in :func:`_rate_str`.
    """
    for k in keys:
        if k in metrics and metrics[k] is not None:
            f = _to_float(metrics[k])
            if f is None:
                return "—"
            if k.endswith("_pct"):
                return f"{f:.1f}%"
            return _rate_str(f)
    return "—"


def _json_safe_records(df: Any) -> List[Dict[str, Any]]:
    """DataFrame -> list of JSON-serialisable dicts (timestamps become ISO strings)."""
    try:
        out = df.copy()
        try:
            if not isinstance(out.index, pd.RangeIndex):
                out = out.reset_index()
        except Exception:
            pass
        records: List[Dict[str, Any]] = []
        for rec in out.to_dict("records"):
            clean: Dict[str, Any] = {}
            for k, v in rec.items():
                if v is None:
                    clean[str(k)] = None
                elif hasattr(v, "isoformat"):
                    clean[str(k)] = v.isoformat()
                elif isinstance(v, (bool, np.bool_)):
                    clean[str(k)] = bool(v)
                else:
                    try:
                        clean[str(k)] = float(v)
                    except (TypeError, ValueError):
                        clean[str(k)] = str(v)
            records.append(clean)
        return records
    except Exception:
        return []


def _safe_status(service: Any) -> Dict[str, Any]:
    try:
        status = service.status()
        return status if isinstance(status, dict) else {}
    except Exception:
        return {}


def _service_state(status: Dict[str, Any]) -> str:
    """ONLINE (weights loaded) / STANDBY (deps ok) / OFFLINE (torch missing)."""
    if status.get("model_loaded"):
        return "ONLINE"
    if status.get("torch_available") and status.get("package_available"):
        return "STANDBY"
    return "OFFLINE"


def _torchvision_missing(status: Dict[str, Any]) -> bool:
    """True when torchvision is absent (non-fatal for Kronos)."""
    if "torchvision_available" in status:
        return not bool(status.get("torchvision_available"))
    try:
        import importlib.util
        return importlib.util.find_spec("torchvision") is None
    except Exception:
        return True


def _render_load_side_notes(status: Dict[str, Any], state: str) -> None:
    """HF auth caption + non-fatal torchvision note (status strip only)."""
    if status.get("error"):
        st.caption(f"Engine note: {status.get('error')}")
    caption = status.get("hf_auth_caption")
    if caption and state == "STANDBY" and not status.get("hf_token_set"):
        st.caption(str(caption))
    if state in ("STANDBY", "ONLINE") and _torchvision_missing(status):
        st.caption(_TORCHVISION_HINT)


def _fallback_status_badge(state: str, status: Dict[str, Any]) -> str:
    """House-styled status pill used when ui.kronos_charts is unavailable."""
    color = {"ONLINE": "#00E676", "STANDBY": "#D4AF37", "OFFLINE": "#E50914"}.get(state, "#666")
    if state == "ONLINE":
        detail = f"{status.get('model_id') or 'kronos'} · {status.get('device') or '?'}"
    elif state == "STANDBY":
        detail = "DEPS OK — WEIGHTS NOT LOADED"
    else:
        detail = "TORCH STACK MISSING"
    return (
        f"<div style='display:inline-flex;align-items:center;gap:10px;"
        f"background:rgba(0,0,0,0.45);border:1px solid {color}55;border-radius:6px;"
        f"padding:8px 14px;margin:2px 0 10px 0;'>"
        f"<span style='width:9px;height:9px;border-radius:50%;background:{color};"
        f"box-shadow:0 0 8px {color};display:inline-block;'></span>"
        f"<span style=\"font-family:'Orbitron',sans-serif;font-size:0.68rem;font-weight:900;"
        f"letter-spacing:2px;color:{color};\">KRONOS {state}</span>"
        f"<span style='font-size:0.6rem;color:#888;letter-spacing:1px;'>{detail}</span>"
        f"</div>"
    )


def _fallback_forecast_chart(hist_df: Any, pred_df: Any, symbol: str):
    """Minimal close-line view used when ui.kronos_charts is unavailable."""
    import plotly.graph_objects as go

    fig = go.Figure()
    if hist_df is not None and "close" in getattr(hist_df, "columns", []):
        hx = hist_df["timestamps"] if "timestamps" in hist_df.columns else hist_df.index
        fig.add_trace(go.Scatter(
            x=hx, y=hist_df["close"], name="History (close)",
            line=dict(color="#888", width=1.6),
        ))
    if pred_df is not None and "close" in getattr(pred_df, "columns", []):
        px_ = pred_df["timestamps"] if "timestamps" in pred_df.columns else pred_df.index
        fig.add_trace(go.Scatter(
            x=px_, y=pred_df["close"], name="Kronos forecast",
            line=dict(color="#E50914", width=2.2, dash="dash"),
        ))
    fig.update_layout(
        title=dict(text=f"{symbol} — fallback view (ui.kronos_charts pending)", font=dict(size=12)),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0.01)",
        font={"color": "#777", "family": "Inter"},
        height=420, margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(orientation="h"),
        xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#111", zeroline=False),
    )
    return fig


# ── Section renderers ───────────────────────────────────────────────────────

def _resolve_interval_code(interval_label: str, intervals: Dict[str, Any]) -> str:
    """Map the Interval selectbox value to a fetchable interval code.

    ``data.kronos_adapter.SUPPORTED_INTERVALS`` maps code → metadata dict
    (``{'yf': '1d', ...}``). Older panel code passed that dict straight into
    ``fetch_kline_history``, which made every forecast/backtest return empty
    history. Prefer the selectbox key; only follow string values (fallback
    catalogs map label → code).
    """
    label = str(interval_label or "").strip()
    raw = intervals.get(label, label) if isinstance(intervals, dict) else label
    if isinstance(raw, dict):
        yf = raw.get("yf") or raw.get("interval")
        if isinstance(yf, str) and yf.strip():
            return yf.strip()
        return label
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return label


def _pred_display_frame(pred_df: Any) -> Optional[pd.DataFrame]:
    """Kronos-webui style prediction table: timestamps + OHLCV(A)."""
    if pred_df is None or not isinstance(pred_df, pd.DataFrame) or len(pred_df) == 0:
        return None
    try:
        out = pred_df.copy()
        if "timestamps" not in out.columns:
            if isinstance(out.index, pd.DatetimeIndex) or out.index.name in (
                "timestamps", "timestamp", "date", "datetime", None,
            ):
                out = out.reset_index()
                first = str(out.columns[0])
                if first.lower() in ("timestamps", "timestamp", "date", "datetime", "index"):
                    out = out.rename(columns={out.columns[0]: "timestamps"})
        cols = [c for c in ("timestamps", "open", "high", "low", "close", "volume", "amount")
                if c in out.columns]
        if not cols:
            return out
        show = out[cols].copy()
        for c in cols:
            if c == "timestamps":
                continue
            show[c] = pd.to_numeric(show[c], errors="coerce")
        return show
    except Exception:
        return None


def _render_status_strip() -> None:
    """ONLINE / STANDBY / OFFLINE strip + LOAD MODEL / install hint actions."""
    service = _get_service()
    if service is None:
        st.info("Kronos engine module pending (engine.kronos_service unavailable) — "
                "status strip offline; the console stays browsable.")
        return

    status = _safe_status(service)
    state = _service_state(status)

    badge_html = None
    charts = _get_charts()
    if charts is not None:
        try:
            badge_fn = getattr(charts, "kronos_status_badge_html", None)
            if callable(badge_fn):
                badge_html = badge_fn(status)
        except Exception:
            badge_html = None
    if not badge_html:
        badge_html = _fallback_status_badge(state, status)

    s1, s2 = st.columns([2.2, 1])
    with s1:
        st.markdown(badge_html, unsafe_allow_html=True)
        _render_load_side_notes(status, state)
    with s2:
        if state == "STANDBY":
            if st.button("⚡ LOAD MODEL", key="kronos_load_model", width='stretch'):
                ok, err = False, None
                with st.spinner("Loading Kronos weights (first run downloads from Hugging Face)..."):
                    try:
                        # Idempotent singleton — skips Hub/transformers if already loaded.
                        ok = bool(service.load())
                    except Exception as exc:
                        err = str(exc)
                post = _safe_status(service)
                if ok and _service_state(post) == "ONLINE":
                    st.success(
                        f"Kronos ONLINE — {post.get('model_id') or 'model'} on "
                        f"{post.get('device') or '?'} (weights kept in process singleton)."
                    )
                    st.rerun()
                elif err:
                    st.error(f"Model load failed: {err}")
                else:
                    detail = post.get("error") or "load did not complete"
                    st.error(f"Model load did not reach ONLINE — {detail}")
        elif state == "OFFLINE":
            st.markdown("<p class='label-grey'>PyTorch stack missing — enable with:</p>",
                        unsafe_allow_html=True)
            st.code(_INSTALL_HINT, language="bash")
            st.caption("The terminal keeps running without it; Kronos simply stays offline.")
        else:  # ONLINE — no re-load; predictor lives on the module singleton
            st.markdown(
                f"<p class='label-grey'>MODEL {status.get('model_id') or '—'}<br/>"
                f"DEVICE {status.get('device') or '—'} · ONLINE</p>",
                unsafe_allow_html=True,
            )


def _render_controls() -> Dict[str, Any]:
    """Symbol / interval / lookback / pred_len row + advanced sampling expander."""
    adapter = _get_adapter()
    symbols: Dict[str, str] = {}
    intervals: Dict[str, str] = {}
    if adapter is not None:
        try:
            symbols = dict(getattr(adapter, "SUPPORTED_SYMBOLS", {}) or {})
            intervals = dict(getattr(adapter, "SUPPORTED_INTERVALS", {}) or {})
        except Exception:
            symbols, intervals = {}, {}
    if not symbols:
        symbols = dict(_FALLBACK_SYMBOLS)
    if not intervals:
        intervals = dict(_FALLBACK_INTERVALS)
    if adapter is None:
        st.info("Data adapter module pending (data.kronos_adapter unavailable) — "
                "symbol catalog running on fallback defaults.")

    c1, c2, c3, c4 = st.columns([1.35, 0.95, 1.1, 1.1])
    with c1:
        symbol_name = st.selectbox("Symbol", list(symbols.keys()), key="kronos_symbol")
        override = st.text_input(
            "Ticker override", key="kronos_ticker_override",
            placeholder="Optional — e.g. AAPL, BTC-USD",
            help="Free-text ticker passed straight to the data adapter, bypassing the preset list.",
        )
    with c2:
        interval_labels = list(intervals.keys())
        default_idx = interval_labels.index("1d") if "1d" in interval_labels else 0
        interval_label = st.selectbox("Interval", interval_labels, index=default_idx,
                                      key="kronos_interval")
    with c3:
        lookback = st.slider("Lookback (bars)", 64, 512, 400, 16, key="kronos_lookback",
                             help="Historical context window fed to the model.")
    with c4:
        pred_len = st.slider("Prediction length (bars)", 1, 120, 24, 1, key="kronos_pred_len",
                             help="How many future K-lines to sample.")

    with st.expander("⚙️ Advanced sampling", expanded=False):
        a1, a2, a3, a4 = st.columns(4)
        temperature = a1.slider("Temperature (T)", 0.1, 2.0, 1.0, 0.05, key="kronos_temperature",
                                help="Higher = more diverse candles, lower = more conservative.")
        top_p = a2.slider("Nucleus top-p", 0.1, 1.0, 0.9, 0.05, key="kronos_top_p",
                          help="Probability mass considered at each sampling step.")
        sample_count = a3.slider("Sample count", 1, 10, 1, 1, key="kronos_sample_count",
                                 help="Monte-Carlo paths blended into the forecast "
                                      "(>1 enables probabilistic bands).")
        vol_amp = a4.slider("Volatility amplification", 0.5, 3.0, 1.0, 0.1, key="kronos_vol_amp",
                            help="Scales the amplitude of predicted moves around the last close.")

    override = (override or "").strip()
    ticker = override or symbols.get(symbol_name) or symbol_name
    interval_code = _resolve_interval_code(interval_label, intervals)
    # Prefer adapter.normalize_interval when available (aliases / defense).
    if adapter is not None:
        try:
            norm = getattr(adapter, "normalize_interval", None)
            if callable(norm):
                resolved = norm(interval_code) or norm(interval_label)
                if resolved:
                    interval_code = resolved
        except Exception:
            pass
    return {
        "symbol_name": override if override else symbol_name,
        "ticker": ticker,
        "interval_label": interval_label,
        "interval": interval_code,
        "lookback": int(lookback),
        "pred_len": int(pred_len),
        "T": float(temperature),
        "top_p": float(top_p),
        "sample_count": int(sample_count),
        "vol_amp": float(vol_amp),
    }


def _persist_run(run: Dict[str, Any]) -> str:
    """Save the finished run to engine.kronos_results_store; tolerate absence."""
    store = _get_store()
    if store is None:
        return "Results store pending (engine.kronos_results_store) — run not persisted."
    record = {
        "symbol": str(run.get("symbol_name") or ""),
        "ticker": str(run.get("ticker") or ""),
        "interval": str(run.get("interval_label") or ""),
        "interval_code": str(run.get("interval_code") or ""),
        "params": dict(run.get("params") or {}),
        "last_close": run.get("last_close"),
        "predicted_close": run.get("predicted_close"),
        "predicted_high": run.get("predicted_high"),
        "predicted_low": run.get("predicted_low"),
        "direction": run.get("direction"),
        "change_pct": run.get("change_pct"),
        "pred_rows": run.get("pred_rows") or [],
        "created_at": run.get("created_at"),
        "elapsed_s": run.get("elapsed_s"),
        "model_id": run.get("model_id"),
        "device": run.get("device"),
    }
    try:
        saved_path = store.save_prediction(record)  # returns file path, '' on failure
    except Exception as exc:
        return f"Could not persist run: {exc}"
    if not saved_path:
        return "Could not persist run — results store rejected the record."
    import os
    return f"Saved to prediction history ({os.path.basename(str(saved_path))})."


def _run_forecast(controls: Dict[str, Any]) -> None:
    """Fetch history → prepare inputs → service.forecast → stash in session state."""
    adapter = _get_adapter()
    if adapter is None:
        st.info("Cannot run yet — data adapter module pending (data.kronos_adapter unavailable).")
        return
    service = _get_service()
    if service is None:
        st.info("Cannot run yet — engine module pending (engine.kronos_service unavailable).")
        return
    if _service_state(_safe_status(service)) == "OFFLINE":
        st.info(f"Kronos is OFFLINE — install the model stack first: `{_INSTALL_HINT}`. "
                "The terminal keeps running without it.")
        return

    ticker = controls["ticker"]
    interval = controls["interval"]
    with st.spinner(f"KRONOS // sampling {controls['pred_len']} future K-lines for "
                    f"{ticker} ({interval})..."):
        try:
            hist_df = adapter.fetch_kline_history(ticker, interval, controls["lookback"])
        except Exception as exc:
            st.error(f"History fetch failed for {ticker}: {exc}")
            return
        if hist_df is None or len(hist_df) == 0:
            detail = ""
            try:
                err_fn = getattr(adapter, "get_last_fetch_error", None)
                if callable(err_fn):
                    detail = (err_fn() or "").strip()
            except Exception:
                detail = ""
            msg = f"No K-line history returned for {ticker} @ {interval}."
            if detail:
                msg = f"{msg} ({detail})"
            st.info(msg)
            return

        try:
            prep = adapter.prepare_kronos_inputs(
                hist_df, controls["lookback"], controls["pred_len"],
                interval, ticker,
            )
        except Exception as exc:
            st.error(f"Kronos input preparation failed: {exc}")
            return
        if not isinstance(prep, dict) or prep.get("error") or "x_df" not in prep:
            reason = prep.get("error") if isinstance(prep, dict) else "unexpected adapter result"
            st.info(f"Kronos input preparation: {reason}")
            return

        # STANDBY → auto-load once so the first forecast doesn't just bounce.
        status = _safe_status(service)
        if _service_state(status) == "STANDBY":
            with st.spinner("Loading Kronos weights (first run downloads from Hugging Face)..."):
                try:
                    service.load()
                except Exception as exc:
                    st.error(f"Model load failed: {exc}")
                    return
            if _service_state(_safe_status(service)) != "ONLINE":
                err = _safe_status(service).get("error") or "load did not complete"
                st.info(f"Kronos model unavailable — use LOAD MODEL in the status strip. ({err})")
                return

        try:
            result = service.forecast(
                prep["x_df"], prep["x_timestamp"], prep["y_timestamp"], controls["pred_len"],
                T=controls["T"], top_p=controls["top_p"],
                sample_count=controls["sample_count"], vol_amp=controls["vol_amp"],
            )
        except Exception as exc:
            st.error(f"Kronos forecast failed: {exc}")
            return

    r_status = getattr(result, "status", "error") if result is not None else "error"
    pred_df = getattr(result, "pred_df", None) if result is not None else None
    if r_status != "ok" or pred_df is None or len(pred_df) == 0:
        err = (getattr(result, "error", None) if result is not None else None) or "no prediction returned"
        if r_status == "unavailable":
            st.info(f"Kronos model unavailable — load it from the status strip above. ({err})")
        else:
            st.error(f"Kronos forecast error: {err}")
        return

    last_close = _to_float(hist_df["close"].iloc[-1]) if "close" in hist_df.columns else None
    pred_close = _to_float(pred_df["close"].iloc[-1]) if "close" in pred_df.columns else None
    pred_high = _to_float(pred_df["high"].max()) if "high" in pred_df.columns else pred_close
    pred_low = _to_float(pred_df["low"].min()) if "low" in pred_df.columns else pred_close
    change_pct = ((pred_close / last_close - 1.0) * 100.0) if (last_close and pred_close is not None) else None

    run: Dict[str, Any] = {
        "symbol_name": controls["symbol_name"],
        "ticker": ticker,
        "interval_label": controls["interval_label"],
        "interval_code": controls["interval"],
        "params": {k: controls[k] for k in ("lookback", "pred_len", "T", "top_p",
                                            "sample_count", "vol_amp")},
        "hist_df": hist_df,
        "pred_df": pred_df,
        "sample_paths": getattr(result, "sample_paths", None),
        "close_p10_last": _terminal_value(getattr(result, "close_p10", None)),
        "close_p50_last": _terminal_value(getattr(result, "close_p50", None)),
        "close_p90_last": _terminal_value(getattr(result, "close_p90", None)),
        "last_close": last_close,
        "predicted_close": pred_close,
        "predicted_high": pred_high,
        "predicted_low": pred_low,
        "change_pct": change_pct,
        "direction": _direction_label(last_close, pred_close),
        "elapsed_s": _to_float(getattr(result, "elapsed_s", None)),
        "model_id": getattr(result, "model_id", None),
        "device": getattr(result, "device", None),
        "pred_rows": _json_safe_records(pred_df),
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    st.session_state["kronos_last_run"] = run
    st.session_state["kronos_save_note"] = _persist_run(run)


def _render_results() -> None:
    """Chart + metrics + probabilistic-paths expander for the latest run."""
    last = st.session_state.get("kronos_last_run")
    if not last:
        st.markdown("<p class='label-grey' style='margin-top:6px;'>Awaiting first Kronos run — "
                    "configure the sampler and hit RUN KRONOS FORECAST.</p>",
                    unsafe_allow_html=True)
        return

    hist_df, pred_df = last.get("hist_df"), last.get("pred_df")
    charts = _get_charts()

    fig = None
    if charts is not None:
        try:
            chart_fn = getattr(charts, "kronos_forecast_chart", None)
            if callable(chart_fn):
                fig = chart_fn(
                    hist_df, pred_df, sample_paths=last.get("sample_paths"),
                    symbol=str(last.get("symbol_name") or ""),
                    interval=str(last.get("interval_label") or ""),
                    show_volume=True,
                )
        except Exception as exc:
            st.info(f"Kronos chart helper failed ({exc}) — using built-in fallback view.")
    elif charts is None:
        st.info("Chart module pending (ui.kronos_charts unavailable) — using built-in fallback view.")
    if fig is None:
        try:
            fig = _fallback_forecast_chart(hist_df, pred_df, str(last.get("symbol_name") or ""))
        except Exception:
            fig = None
    if fig is not None:
        _pcfg = getattr(charts, "KRONOS_PLOTLY_CONFIG", None) if charts else None
        st.plotly_chart(
            fig, width='stretch', key="kronos_forecast_chart_fig",
            config=_pcfg or dict(
                scrollZoom=True, displayModeBar=True, displaylogo=False,
            ),
        )

    chg = last.get("change_pct")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Predicted close", _fmt_price(last.get("predicted_close")),
              f"{chg:+.2f}%" if chg is not None else None)
    m2.metric("Direction", last.get("direction") or "—",
              f"vs last close {_fmt_price(last.get('last_close'))}", delta_color="off")
    m3.metric("Predicted high / low",
              f"{_fmt_price(last.get('predicted_high'))} / {_fmt_price(last.get('predicted_low'))}")
    lat = last.get("elapsed_s")
    m4.metric("Model latency", f"{lat:.2f} s" if lat is not None else "—",
              str(last.get("device") or "—"), delta_color="off")

    params = last.get("params") or {}
    st.caption(
        f"{last.get('created_at', '—')} · {last.get('ticker', '?')} @ {last.get('interval_label', '?')} · "
        f"model {last.get('model_id') or '—'} · "
        + " · ".join(f"{k}={params.get(k)}" for k in ("lookback", "pred_len", "T", "top_p",
                                                      "sample_count", "vol_amp"))
    )
    save_note = st.session_state.get("kronos_save_note")
    if save_note:
        st.caption(f"💾 {save_note}")

    # Kronos-webui style predicted OHLC table (open/high/low/close/volume/amount).
    pred_table = _pred_display_frame(pred_df)
    if pred_table is not None:
        with st.expander("📋 Predicted K-lines (OHLCV)", expanded=True):
            st.dataframe(pred_table, hide_index=True, width='stretch')

    sample_paths = last.get("sample_paths")
    if _has_paths(sample_paths):
        with st.expander("🌫️ Probabilistic paths", expanded=False):
            pfig = None
            if charts is not None:
                try:
                    paths_fn = getattr(charts, "kronos_close_paths_chart", None)
                    if callable(paths_fn):
                        pred_ts = None
                        try:
                            if pred_df is not None:
                                pred_ts = (pred_df["timestamps"]
                                           if "timestamps" in pred_df.columns else pred_df.index)
                        except Exception:
                            pred_ts = None
                        pfig = paths_fn(hist_df, sample_paths, pred_timestamps=pred_ts,
                                        symbol=str(last.get("symbol_name") or ""))
                except Exception as exc:
                    st.info(f"Paths chart failed: {exc}")
            else:
                st.info("Chart module pending (ui.kronos_charts unavailable) — "
                        "path fan chart not rendered.")
            if pfig is not None:
                _pcfg = getattr(charts, "KRONOS_PLOTLY_CONFIG", None) if charts else None
                st.plotly_chart(
                    pfig, width='stretch', key="kronos_paths_chart_fig",
                    config=_pcfg or dict(
                        scrollZoom=True, displayModeBar=True, displaylogo=False,
                    ),
                )
            q1, q2, q3 = st.columns(3)
            q1.metric("Close P10", _fmt_price(last.get("close_p10_last")))
            q2.metric("Close P50", _fmt_price(last.get("close_p50_last")))
            q3.metric("Close P90", _fmt_price(last.get("close_p90_last")))


def _run_backtest(controls: Dict[str, Any], n_windows: int, bt_pred_len: int) -> None:
    run_bt = _get_backtest()
    if run_bt is None:
        st.info("Backtest engine module pending (engine.kronos_backtest unavailable).")
        return
    adapter = _get_adapter()
    if adapter is None:
        st.info("Data adapter module pending (data.kronos_adapter unavailable).")
        return
    service = _get_service()
    if service is None:
        st.info("Cannot run backtest — engine module pending (engine.kronos_service unavailable).")
        return

    state = _service_state(_safe_status(service))
    if state == "OFFLINE":
        st.info(f"Kronos is OFFLINE — install the model stack first: `{_INSTALL_HINT}`.")
        return
    if state == "STANDBY":
        with st.spinner("Loading Kronos weights for backtest..."):
            try:
                ok = bool(service.load())
            except Exception as exc:
                st.error(f"Model load failed: {exc}")
                return
        if not ok or _service_state(_safe_status(service)) != "ONLINE":
            err = _safe_status(service).get("error") or "load did not complete"
            st.info(f"Kronos model unavailable — use LOAD MODEL in the status strip. ({err})")
            return

    ticker = controls["ticker"]
    interval = controls["interval"]
    bars_needed = controls["lookback"] + n_windows * bt_pred_len + bt_pred_len
    with st.spinner(f"KRONOS // walking {n_windows} historical windows on "
                    f"{ticker} @ {interval}..."):
        try:
            df = adapter.fetch_kline_history(ticker, interval, bars_needed)
        except Exception as exc:
            st.error(f"History fetch failed for {ticker}: {exc}")
            return
        if df is None or len(df) == 0:
            detail = ""
            try:
                err_fn = getattr(adapter, "get_last_fetch_error", None)
                if callable(err_fn):
                    detail = (err_fn() or "").strip()
            except Exception:
                detail = ""
            msg = f"No K-line history returned for {ticker} @ {interval}."
            if detail:
                msg = f"{msg} ({detail})"
            st.info(msg)
            return
        try:
            # Tag the frame so reports/charts show the symbol.
            try:
                df = df.copy()
                df.attrs["symbol"] = controls.get("symbol_name") or ticker
                df.attrs["ticker"] = ticker
            except Exception:
                pass
            result = run_bt(
                df, pred_len=bt_pred_len, window=controls["lookback"], n_windows=n_windows,
                T=controls["T"], top_p=controls["top_p"], sample_count=3,
                service=service,
            )
        except Exception as exc:
            st.error(f"Kronos backtest failed: {exc}")
            return

    if not isinstance(result, dict):
        st.info("Backtest returned an unexpected result — engine.kronos_backtest may still be landing.")
        return
    st.session_state["kronos_backtest_result"] = result
    status = str(result.get("status") or "").lower()
    if status not in ("ok", "success", "completed", "done"):
        why = result.get("error") or result.get("reason") or "see engine logs"
        st.warning(f"Backtest finished with status={result.get('status')}: {why}")
    else:
        m = result.get("metrics") or {}
        st.success(
            f"Backtest complete — {m.get('n_windows_evaluated', '?')}/"
            f"{m.get('n_windows_requested', n_windows)} windows · "
            f"hit-rate {_metric_pct_str(m, 'direction_hit_rate_pct', 'hit_rate')} · "
            f"MAPE {_metric_pct_str(m, 'close_mape_pct', 'mape')}"
        )


def _render_backtest_section(controls: Dict[str, Any]) -> None:
    with st.expander("🧪 HISTORICAL BACKTEST — KRONOS ROLLING WINDOWS", expanded=False):
        st.markdown("<p class='label-grey'>Walk-forward re-forecasts on past windows of the "
                    "selected symbol; measures directional hit-rate, close MAPE and "
                    "P10–P90 interval coverage.</p>", unsafe_allow_html=True)
        b1, b2 = st.columns(2)
        n_windows = b1.slider("Backtest windows", 3, 12, 6, 1, key="kronos_bt_windows")
        bt_pred_len = b2.slider("Backtest horizon (bars per window)", 1, 60, 10, 1,
                                key="kronos_bt_pred_len")
        if st.button("🚀 RUN KRONOS BACKTEST", key="kronos_run_backtest"):
            _run_backtest(controls, int(n_windows), int(bt_pred_len))

        result = st.session_state.get("kronos_backtest_result")
        if not result:
            st.caption("No backtest run yet in this session.")
            return

        status = str(result.get("status") or "ok").lower()
        if status not in ("ok", "success", "completed", "done"):
            why = result.get("error") or result.get("reason") or "see engine logs"
            st.info(f"Backtest status: {result.get('status')} — {why}")
            if status in ("unavailable",):
                st.caption("Load the Kronos model from the status strip (LOAD MODEL), then re-run.")
            return

        metrics = result.get("metrics") or {}
        m1, m2, m3 = st.columns(3)
        m1.metric("Hit-rate (direction)",
                  _metric_pct_str(metrics, "direction_hit_rate_pct",
                                  "hit_rate", "hitrate", "directional_accuracy"))
        m2.metric("MAPE (close)",
                  _metric_pct_str(metrics, "close_mape_pct",
                                  "mape", "close_mape", "mape_pct"))
        m3.metric("P10–P90 coverage",
                  _metric_pct_str(metrics, "envelope_coverage_pct",
                                  "coverage", "interval_coverage", "coverage_p10_p90"))

        s1, s2, s3 = st.columns(3)
        s1.metric("Strategy return",
                  _metric_pct_str(metrics, "strategy_total_return_pct"))
        s2.metric("Buy & hold",
                  _metric_pct_str(metrics, "benchmark_total_return_pct"))
        s3.metric("Max drawdown",
                  _metric_pct_str(metrics, "strategy_max_drawdown_pct"))

        charts = _get_charts()
        bt_fig = None
        if charts is not None:
            try:
                bt_fn = getattr(charts, "kronos_backtest_chart", None)
                if callable(bt_fn):
                    bt_fig = bt_fn(result)
            except Exception as exc:
                st.info(f"Backtest chart failed: {exc}")
        else:
            st.info("Chart module pending (ui.kronos_charts unavailable) — backtest chart not rendered.")
        if bt_fig is not None:
            _pcfg = getattr(charts, "KRONOS_PLOTLY_CONFIG", None) if charts else None
            st.plotly_chart(
                bt_fig, width='stretch', key="kronos_bt_chart_fig",
                config=_pcfg or dict(
                    scrollZoom=True, displayModeBar=True, displaylogo=False,
                ),
            )

        windows = result.get("windows") or []
        if windows:
            with st.expander("Per-window backtest detail", expanded=False):
                try:
                    st.dataframe(pd.DataFrame(windows), hide_index=True, width='stretch')
                except Exception:
                    st.json(windows[:20])


def _render_history_record(rec: Dict[str, Any]) -> None:
    sym = rec.get("symbol") or rec.get("ticker") or "?"
    itv = rec.get("interval") or "?"
    last_close = _to_float(rec.get("last_close"))
    rows = rec.get("pred_rows") or rec.get("predicted_rows") or rec.get("prediction_rows") or []
    pred_close = _to_float(rec.get("predicted_close"))
    if pred_close is None and rows:
        try:
            pred_close = _to_float(rows[-1].get("close"))
        except Exception:
            pred_close = None
    direction = rec.get("direction") or _direction_label(last_close, pred_close)
    chg = ((pred_close / last_close - 1.0) * 100.0) if (last_close and pred_close is not None) else None

    h1, h2, h3 = st.columns(3)
    h1.metric("Saved last close", _fmt_price(last_close))
    h2.metric("Saved predicted close", _fmt_price(pred_close),
              f"{chg:+.2f}%" if chg is not None else None)
    h3.metric("Direction", str(direction))
    params = rec.get("params") or {}
    st.caption(f"Saved {rec.get('created_at', '—')} · {sym} @ {itv}"
               + (" · " + ", ".join(f"{k}={v}" for k, v in params.items()) if params else ""))
    if rows:
        try:
            closes = [c for c in (_to_float(r.get("close")) for r in rows) if c is not None]
            if closes:
                st.line_chart(pd.DataFrame({"Predicted close": closes}),
                              color="#E50914", height=200)
        except Exception:
            pass


def _render_history_section() -> None:
    with st.expander("🗂️ PREDICTION HISTORY — SAVED KRONOS RUNS", expanded=False):
        store = _get_store()
        if store is None:
            st.info("Results store module pending (engine.kronos_results_store unavailable).")
            return
        try:
            preds = store.list_predictions(limit=50) or []
        except Exception as exc:
            st.info(f"Could not list saved predictions: {exc}")
            return
        if not preds:
            st.info("No Kronos predictions saved yet — run a forecast to create the first record.")
            return

        table_rows: List[Dict[str, Any]] = []
        labels: List[str] = ["— select a saved run —"]
        ids: List[Any] = [None]
        for i, p in enumerate(preds):
            if not isinstance(p, dict):
                continue
            pid = p.get("id") or p.get("pred_id") or p.get("prediction_id")
            created = str(p.get("created_at") or p.get("timestamp") or "")[:19].replace("T", " ")
            sym = p.get("symbol") or p.get("ticker") or "?"
            itv = p.get("interval") or p.get("interval_label") or "?"
            pred_close = _to_float(p.get("predicted_close"))
            if pred_close is None:
                rows = p.get("pred_rows") or p.get("predicted_rows") or []
                if rows:
                    try:
                        pred_close = _to_float(rows[-1].get("close"))
                    except Exception:
                        pred_close = None
            direction = p.get("direction") or "—"
            table_rows.append({
                "Time": created or "—",
                "Symbol": sym,
                "Interval": itv,
                "Predicted close": _fmt_price(pred_close),
                "Direction": direction,
            })
            labels.append(f"#{i + 1} · {created or 'n/a'} · {sym} ({itv})")
            ids.append(pid)

        if table_rows:
            st.dataframe(pd.DataFrame(table_rows), hide_index=True, width='stretch')

        selection = st.selectbox("Reload saved forecast", labels, key="kronos_history_select")
        idx = labels.index(selection) if selection in labels else 0
        if idx > 0:
            pid = ids[idx]
            if pid is None:
                st.info("This record has no id — cannot reload it.")
                return
            rec = None
            try:
                rec = store.load_prediction(pid)
            except Exception as exc:
                st.info(f"Could not load prediction {pid}: {exc}")
            if isinstance(rec, dict):
                _render_history_record(rec)
            elif rec is None:
                st.info("Could not load the selected prediction record.")


# ── Public entry point ──────────────────────────────────────────────────────

def _render_panel_body() -> None:
    st.markdown("<h2 class='gold-title'>KRONOS // K-LINE FOUNDATION MODEL</h2>",
                unsafe_allow_html=True)
    st.markdown(
        "<p class='label-grey' style='margin-bottom: 20px;'>"
        "Foundation-model candlestick forecasting — vendored from the open-source "
        "<b>Kronos</b> project (MIT license, NeoQuasar model family).</p>",
        unsafe_allow_html=True,
    )

    _render_status_strip()
    controls = _render_controls()

    if st.button("🔮 RUN KRONOS FORECAST", key="kronos_run_forecast",
                 type="primary", width='stretch'):
        _run_forecast(controls)

    _render_results()
    _render_backtest_section(controls)
    _render_history_section()


def render_kronos_terminal_panel() -> None:
    """Render the full Kronos console inside its host tab (KRONOS ENGINE). Never raises."""
    try:
        _render_panel_body()
    except Exception as exc:
        st.warning(f"KRONOS console contained an unexpected error and stood down safely: {exc}")

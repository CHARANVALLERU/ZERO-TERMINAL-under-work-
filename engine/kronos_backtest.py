"""
ZERO Kronos Backtest — rolling-origin evaluation of the Kronos K-line model
============================================================================

Ports the backtesting workflows that ship with the Kronos foundation model
(MIT licensed, github.com/shiyu-coder/Kronos) into ZERO house style:

* ``examples/run_backtest_kronos.py``  — threshold long/flat signal from the
  predicted horizon return, strategy equity curve vs a buy&hold benchmark,
  total return / max drawdown / win rate / trade count.
* ``examples/yuce/historical_backtest.py`` — rolling-origin ("walk forward
  through history") evaluation: at many anchor points, feed ``window`` bars
  of context, predict ``pred_len`` bars, score against the actual future
  (MAPE, bar-to-bar direction accuracy, within-5% rate, pred/actual
  correlation) and run the threshold strategy on the predictions.
* ``finetune/qlib_test.py``           — sliding lookback/predict windows with
  a hard ``max_context`` cap (512) and T / top_p / sample_count inference
  parameters; signals derived from predicted close vs last context close.

Inference itself is delegated to ``engine.kronos_service`` (lazy import —
the module, torch, or the model weights may be missing, in which case every
public function degrades to a graceful ``'unavailable'`` / ``'error'``
result instead of raising).

SCHEMA CONTRACT: the dict returned by :func:`run_kronos_backtest` feeds the
UI chart function ``kronos_backtest_chart``. The top-level keys

    'status', 'symbol_hint', 'generated_at', 'params', 'metrics',
    'windows', 'dates', 'actual_close', 'predicted_close',
    'strategy_curve', 'benchmark_curve'

must keep exactly these names. The five array keys are aligned lists;
``predicted_close`` is NaN outside predicted spans.

Run:  ``python -m engine.kronos_backtest``   (synthetic random-walk demo;
reports 'unavailable' when torch / the service is absent — by design).
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

__all__ = ["run_kronos_backtest", "save_backtest_report", "summarize_backtest"]

MAX_CONTEXT: int = 512
"""Hard context cap, mirroring Kronos's ``max_context`` (qlib_test.py)."""

MIN_CONTEXT: int = 16
"""Smallest context we will ever hand to the model for one window."""

DEFAULT_THRESHOLD: float = 0.001
"""Strategy entry threshold on the predicted horizon return (0.1%)."""

_MAX_LEADING_FAILURES: int = 3
"""Abort the window loop after this many consecutive failures with zero
successes (dead/broken service) instead of burning every remaining call."""

_TS_ALIASES = ("timestamps", "timestamp", "date", "datetime", "time")
"""Accepted names for the timestamp column (contract name first)."""

_OHLCVA = ("open", "high", "low", "close", "volume", "amount")


# ─────────────────────────────────────────────
#  Small never-raise helpers
# ─────────────────────────────────────────────

def _notify(cb: Optional[Callable[[float, str], None]], frac: float, msg: str) -> None:
    """Invoke the caller's progress callback; swallow every callback error."""
    if cb is None:
        return
    try:
        cb(float(max(0.0, min(1.0, frac))), str(msg))
    except Exception:
        pass


def _iso(t: Any) -> str:
    try:
        return pd.Timestamp(t).isoformat()
    except Exception:
        return str(t)


def _fmt_num(x: Any, nd: int = 4) -> str:
    try:
        v = float(x)
        if not np.isfinite(v):
            return "n/a"
        return f"{v:,.{nd}f}"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_pct(x: Any) -> str:
    try:
        v = float(x)
        if not np.isfinite(v):
            return "n/a"
        return f"{v:.2f}%"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_signed(x: Any) -> str:
    try:
        v = float(x)
        if not np.isfinite(v):
            return "n/a"
        return f"{v:+.2f}%"
    except (TypeError, ValueError):
        return "n/a"


def _jsonable(obj: Any) -> Any:
    """Recursively convert a result dict into strict-JSON-safe types.

    numpy scalars -> python, NaN/inf -> None, timestamps -> str.
    """
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [_jsonable(v) for v in obj.tolist()]
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        obj = float(obj)
    if isinstance(obj, float):
        return obj if np.isfinite(obj) else None
    if obj is None or isinstance(obj, (str, int, bool)):
        return obj
    return str(obj)


def _symbol_hint(df: Any) -> str:
    """Best-effort symbol name from df.attrs or a symbol/ticker column."""
    try:
        if isinstance(df, pd.DataFrame):
            attrs = getattr(df, "attrs", {}) or {}
            for key in ("symbol", "symbol_hint", "ticker", "name"):
                if attrs.get(key):
                    return str(attrs[key])
            for col in ("symbol", "ticker"):
                if col in df.columns and len(df) > 0:
                    return str(df[col].iloc[0])
    except Exception:
        pass
    return ""


def _skeleton(status: str, reason: str = "", error: str = "",
              symbol_hint: str = "", params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Full-schema result dict so every exit path honours the UI contract."""
    from datetime import datetime, timezone  # lazy (stdlib)
    out: Dict[str, Any] = {
        "status": status,
        "symbol_hint": symbol_hint,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "params": params or {},
        "metrics": {},
        "windows": [],
        "dates": [],
        "actual_close": [],
        "predicted_close": [],
        "strategy_curve": [],
        "benchmark_curve": [],
    }
    if reason:
        out["reason"] = reason
    if error:
        out["error"] = error
    return out


# ─────────────────────────────────────────────
#  Data preparation & window placement
# ─────────────────────────────────────────────

def _prepare_df(df: Any) -> Tuple[Optional[pd.DataFrame], str]:
    """Normalise the input frame to sorted, numeric, NaN-free OHLCVA bars."""
    if df is None or not isinstance(df, pd.DataFrame) or len(df) == 0:
        return None, "input dataframe is empty or not a DataFrame"
    d = df.copy()
    d.columns = [str(c).strip().lower() for c in d.columns]

    ts_col = next((c for c in _TS_ALIASES if c in d.columns), None)
    if ts_col is None:
        return None, "missing 'timestamps' column"
    if ts_col != "timestamps":
        d = d.rename(columns={ts_col: "timestamps"})

    for col in ("open", "high", "low", "close"):
        if col not in d.columns:
            return None, f"missing required column '{col}'"
    for col in ("volume", "amount"):
        if col not in d.columns:
            d[col] = 0.0

    ts = pd.to_datetime(d["timestamps"], errors="coerce")
    if ts.isna().all():                       # unparseable stamps: synthesise
        ts = pd.Series(pd.date_range("2000-01-01", periods=len(d), freq="D"),
                       index=d.index)
    d["timestamps"] = ts
    d = d.dropna(subset=["timestamps"])

    for col in _OHLCVA:
        d[col] = pd.to_numeric(d[col], errors="coerce")
    d = d.dropna(subset=["close"])
    for col in ("open", "high", "low"):
        d[col] = d[col].fillna(d["close"])
    d[["volume", "amount"]] = d[["volume", "amount"]].fillna(0.0)

    d = (d.sort_values("timestamps")
          .drop_duplicates(subset="timestamps", keep="last")
          .reset_index(drop=True))
    if len(d) < MIN_CONTEXT + 1:
        return None, f"not enough usable bars ({len(d)}; need >= {MIN_CONTEXT + 1})"
    return d[["timestamps", *_OHLCVA]], ""


def _pick_anchors(n_bars: int, pred_len: int, step: Optional[int],
                  n_windows: int) -> List[int]:
    """Rolling-origin anchor indices (context ends at anchor, exclusive).

    Anchors are evenly spaced (constant ``step``) working backwards from the
    end of the data so the prediction spans tile the tail of the frame; the
    default ``step = pred_len`` makes them contiguous and non-overlapping,
    like the ``test_points`` grid in historical_backtest.py.
    """
    last = n_bars - pred_len
    if last < MIN_CONTEXT:
        return []
    stride = pred_len if (step is None or step <= 0) else int(step)
    anchors: List[int] = []
    a = last
    while a >= MIN_CONTEXT and len(anchors) < n_windows:
        anchors.append(a)
        a -= stride
    anchors.reverse()
    return anchors


# ─────────────────────────────────────────────
#  Service access (lazy — module may not exist yet)
# ─────────────────────────────────────────────

def _resolve_service(service: Any) -> Tuple[Optional[Any], str]:
    """Return (service, '') or (None, reason). Never raises."""
    if service is not None:
        return service, ""
    try:
        from engine.kronos_service import get_kronos_service  # lazy heavy import
    except Exception as exc:
        return None, f"engine.kronos_service not importable: {exc}"
    try:
        svc = get_kronos_service()
    except Exception as exc:
        return None, f"get_kronos_service() failed: {exc}"
    if svc is None:
        return None, "get_kronos_service() returned None"
    return svc, ""


def _forecast_window(svc: Any, ctx: pd.DataFrame, y_ts: pd.Series, pred_len: int,
                     T: float, top_p: float, sample_count: int,
                     ) -> Tuple[Optional[pd.DataFrame], str, str]:
    """One service call. Returns (pred_df|None, status, error)."""
    try:
        feats = ctx[list(_OHLCVA)].reset_index(drop=True)
        x_ts = pd.Series(ctx["timestamps"].values)
        res = svc.forecast(df=feats, x_timestamp=x_ts,
                           y_timestamp=y_ts.reset_index(drop=True),
                           pred_len=pred_len, T=T, top_p=top_p,
                           sample_count=sample_count)
    except Exception as exc:
        return None, "error", f"forecast raised: {type(exc).__name__}: {exc}"
    status = str(getattr(res, "status", "error") or "error")
    if status != "ok":
        err = str(getattr(res, "error", "") or f"forecast status={status}")
        return None, status, err
    pred = getattr(res, "pred_df", None)
    if not isinstance(pred, pd.DataFrame) or len(pred) == 0:
        return None, "error", "forecast returned empty/invalid pred_df"
    pred = pred.reset_index(drop=True)
    pred.columns = [str(c).strip().lower() for c in pred.columns]
    if "close" not in pred.columns:
        return None, "error", "pred_df missing 'close' column"
    return pred, "ok", ""


# ─────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────

def run_kronos_backtest(df: Any, pred_len: int = 10, window: int = 400,
                        step: Optional[int] = None, n_windows: int = 8,
                        T: float = 1.0, top_p: float = 0.9, sample_count: int = 3,
                        service: Any = None,
                        progress_cb: Optional[Callable[[float, str], None]] = None,
                        threshold: float = DEFAULT_THRESHOLD,
                        allow_short: bool = False) -> Dict[str, Any]:
    """Rolling-origin Kronos backtest over ``df``. Never raises.

    ``df`` needs columns ['timestamps','open','high','low','close','volume',
    'amount']. For each of ``n_windows`` anchors, ``window`` bars of context
    (capped at 512) are fed to the Kronos service to predict ``pred_len``
    bars, which are scored against the actual future bars. A threshold
    long/flat strategy (short optional) is simulated on the predictions and
    compared with buy&hold over the same spans.

    Returns the UI-contract dict (see module docstring); ``status`` is
    'ok', 'unavailable' (service/torch missing) or 'error'.
    """
    try:
        pred_len = max(1, int(pred_len))
        window = int(np.clip(int(window), MIN_CONTEXT, MAX_CONTEXT))
        n_windows = max(1, int(n_windows))
        step_i = None if step is None else max(1, int(step))
        thr = abs(float(threshold))
        params: Dict[str, Any] = {
            "pred_len": pred_len, "window": window,
            "step": step_i if step_i is not None else pred_len,
            "n_windows": n_windows, "T": float(T), "top_p": float(top_p),
            "sample_count": int(sample_count), "threshold": thr,
            "allow_short": bool(allow_short), "max_context": MAX_CONTEXT,
        }
        sym = _symbol_hint(df)

        data, err = _prepare_df(df)
        if data is None:
            return _skeleton("error", error=err, symbol_hint=sym, params=params)
        n = len(data)

        anchors = _pick_anchors(n, pred_len, step_i, n_windows)
        if not anchors:
            return _skeleton(
                "error", symbol_hint=sym, params=params,
                error=(f"not enough data for one window (bars={n}; need "
                       f">= {MIN_CONTEXT} context + {pred_len} future bars)"))

        svc, why = _resolve_service(service)
        if svc is None:
            return _skeleton("unavailable", reason=why, symbol_hint=sym, params=params)
        try:
            if hasattr(svc, "available") and not svc.available():
                reason = getattr(svc, "error", None) or \
                    "Kronos model unavailable (torch / weights not installed)"
                return _skeleton("unavailable", reason=str(reason),
                                 symbol_hint=sym, params=params)
        except Exception as exc:
            return _skeleton("unavailable", symbol_hint=sym, params=params,
                             reason=f"service availability check failed: {exc}")

        closes = data["close"].to_numpy(dtype=float)
        highs = data["high"].to_numpy(dtype=float)
        lows = data["low"].to_numpy(dtype=float)
        ts_all = data["timestamps"]

        windows_out: List[Dict[str, Any]] = []
        signal_at = np.full(n, np.nan)       # per-bar strategy signal
        pred_close_at = np.full(n, np.nan)   # chart overlay (NaN outside spans)
        pool_pred: List[float] = []          # pooled predicted closes
        pool_act: List[float] = []           # pooled actual closes
        pool_bar_hits: List[bool] = []       # pooled per-bar direction hits
        pool_env: List[bool] = []            # pooled envelope membership
        horizon_hits: List[bool] = []
        hi_apes: List[float] = []
        lo_apes: List[float] = []
        trade_rets: List[float] = []         # compounded return per traded window
        last_err = ""
        n_ok = 0
        fail_streak = 0
        n_total = len(anchors)

        _notify(progress_cb, 0.0, f"kronos backtest: {n_total} windows queued")

        for k, a in enumerate(anchors):
            ctx_lo = max(0, a - window)
            ctx = data.iloc[ctx_lo:a]
            m = min(pred_len, n - a)
            actual = data.iloc[a:a + m]
            y_ts = pd.Series(actual["timestamps"].values)

            wrec: Dict[str, Any] = {
                "window_index": k,
                "anchor_index": int(a),
                "context_start": _iso(ts_all.iloc[ctx_lo]),
                "context_end": _iso(ts_all.iloc[a - 1]),
                "pred_start": _iso(ts_all.iloc[a]),
                "pred_end": _iso(ts_all.iloc[a + m - 1]),
                "context_bars": int(len(ctx)),
                "horizon_bars": int(m),
            }

            pred, st, ferr = _forecast_window(svc, ctx, y_ts, m, T, top_p, sample_count)
            if st == "unavailable":           # model vanished mid-run: abort
                out = _skeleton("unavailable", symbol_hint=sym, params=params,
                                reason=ferr or "service became unavailable mid-run")
                out["windows"] = windows_out
                return out
            if pred is None:
                last_err = ferr
                wrec.update({"status": "error", "error": ferr})
                windows_out.append(wrec)
                _notify(progress_cb, (k + 1) / n_total,
                        f"window {k + 1}/{n_total} failed: {ferr[:80]}")
                fail_streak += 1
                if n_ok == 0 and fail_streak >= _MAX_LEADING_FAILURES and k + 1 < n_total:
                    last_err = (f"{last_err} (aborted after {fail_streak} consecutive "
                                f"failures; {n_total - k - 1} windows skipped)")
                    break
                continue

            mm = min(m, len(pred))
            p_close_raw = pred["close"].to_numpy(dtype=float)[:mm]
            a_close = closes[a:a + mm]
            p_high = pred["high"].to_numpy(dtype=float)[:mm] if "high" in pred.columns else None
            p_low = pred["low"].to_numpy(dtype=float)[:mm] if "low" in pred.columns else None
            origin = float(closes[a - 1])     # last context close (qlib_test.py)

            both = np.isfinite(p_close_raw) & np.isfinite(a_close)
            if origin <= 0 or not both.any():
                last_err = "non-finite predictions or bad origin price"
                wrec.update({"status": "error", "error": last_err})
                windows_out.append(wrec)
                _notify(progress_cb, (k + 1) / n_total,
                        f"window {k + 1}/{n_total} failed: {last_err}")
                fail_streak += 1
                if n_ok == 0 and fail_streak >= _MAX_LEADING_FAILURES and k + 1 < n_total:
                    last_err = (f"{last_err} (aborted after {fail_streak} consecutive "
                                f"failures; {n_total - k - 1} windows skipped)")
                    break
                continue
            pc, ac = p_close_raw[both], a_close[both]

            # ── prediction-accuracy metrics (historical_backtest.py) ──
            e = pc - ac
            w_mae = float(np.mean(np.abs(e)))
            w_mape = float(np.mean(np.abs(e) / np.maximum(np.abs(ac), 1e-12)) * 100)
            w_rmse = float(np.sqrt(np.mean(e ** 2)))

            pred_seq = np.concatenate(([origin], pc))
            act_seq = np.concatenate(([origin], ac))
            bar_hits = np.sign(np.diff(pred_seq)) == np.sign(np.diff(act_seq))
            w_bar_hit = float(np.mean(bar_hits)) * 100 if bar_hits.size else None

            pred_ret = float(pc[-1] / origin - 1.0)
            act_ret = float(ac[-1] / origin - 1.0)
            dir_hit = bool(np.sign(pred_ret) == np.sign(act_ret))

            # ── predicted [low, high] envelope vs actual closes ──
            env_cov = None
            if p_high is not None and p_low is not None:
                em = np.isfinite(p_high) & np.isfinite(p_low) & np.isfinite(a_close)
                if em.any():
                    lo_b = np.minimum(p_low[em], p_high[em])
                    hi_b = np.maximum(p_low[em], p_high[em])
                    inside = (a_close[em] >= lo_b) & (a_close[em] <= hi_b)
                    env_cov = float(np.mean(inside)) * 100
                    pool_env.extend(bool(x) for x in inside)

            # ── extreme (max-high / min-low) absolute % errors ──
            hi_ape = lo_ape = None
            if p_high is not None and np.isfinite(p_high).any():
                act_hi = float(np.max(highs[a:a + mm]))
                if act_hi > 0:
                    hi_ape = abs(float(np.nanmax(p_high)) - act_hi) / act_hi * 100
                    hi_apes.append(hi_ape)
            if p_low is not None and np.isfinite(p_low).any():
                act_lo = float(np.min(lows[a:a + mm]))
                if act_lo > 0:
                    lo_ape = abs(float(np.nanmin(p_low)) - act_lo) / act_lo * 100
                    lo_apes.append(lo_ape)

            # ── threshold strategy (run_backtest_kronos.py) ──
            if pred_ret > thr:
                sig = 1
            elif allow_short and pred_ret < -thr:
                sig = -1
            else:
                sig = 0
            for i in range(a, a + mm):        # first covering window wins
                if np.isnan(signal_at[i]):
                    signal_at[i] = sig
            bar_r = np.diff(act_seq) / act_seq[:-1]
            w_strat_ret = float(np.prod(1.0 + sig * bar_r) - 1.0)
            if sig != 0:
                trade_rets.append(w_strat_ret)

            # chart overlay: only finite predicted bars
            span = pred_close_at[a:a + mm]
            fin = np.isfinite(p_close_raw)
            span[fin] = p_close_raw[fin]

            pool_pred.extend(pc.tolist())
            pool_act.extend(ac.tolist())
            pool_bar_hits.extend(bool(x) for x in bar_hits)
            horizon_hits.append(dir_hit)

            wrec.update({
                "status": "ok",
                "last_close": round(origin, 6),
                "predicted_return_pct": round(pred_ret * 100, 4),
                "actual_return_pct": round(act_ret * 100, 4),
                "direction_hit": dir_hit,
                "bar_hit_rate_pct": round(w_bar_hit, 2) if w_bar_hit is not None else None,
                "close_mae": round(w_mae, 6),
                "close_mape_pct": round(w_mape, 4),
                "close_rmse": round(w_rmse, 6),
                "envelope_coverage_pct": round(env_cov, 2) if env_cov is not None else None,
                "high_extreme_ape_pct": round(hi_ape, 4) if hi_ape is not None else None,
                "low_extreme_ape_pct": round(lo_ape, 4) if lo_ape is not None else None,
                "signal": int(sig),
                "strategy_return_pct": round(w_strat_ret * 100, 4),
            })
            windows_out.append(wrec)
            n_ok += 1
            fail_streak = 0
            _notify(progress_cb, (k + 1) / n_total,
                    f"window {k + 1}/{n_total} ok ({wrec['pred_start'][:10]})")

        ok_windows = [w for w in windows_out if w.get("status") == "ok"]
        if not ok_windows:
            out = _skeleton("error", symbol_hint=sym, params=params,
                            error=(f"all {len(windows_out)} attempted windows failed; "
                                   f"last error: {last_err}"))
            out["windows"] = windows_out
            return out

        # ── aggregate accuracy metrics (pooled across all scored bars) ──
        pa = np.asarray(pool_pred, dtype=float)
        aa = np.asarray(pool_act, dtype=float)
        e_all = pa - aa
        ape_all = np.abs(e_all) / np.maximum(np.abs(aa), 1e-12)
        corr = None
        if pa.size >= 2 and float(np.std(pa)) > 0 and float(np.std(aa)) > 0:
            corr = float(np.corrcoef(pa, aa)[0, 1])

        # ── equity curves over the evaluated spans (chart contract) ──
        first_a, last_a = anchors[0], anchors[-1]
        chart_lo = max(0, first_a - window)
        chart_hi = min(n, last_a + pred_len)
        span_n = chart_hi - chart_lo
        strat = np.full(span_n, np.nan)
        bench = np.full(span_n, np.nan)
        s_eq = b_eq = 1.0
        started = False
        for i in range(chart_lo, chart_hi):
            sig_i = signal_at[i]
            if not np.isnan(sig_i) and i > 0 and closes[i - 1] > 0:
                r = closes[i] / closes[i - 1] - 1.0
                s_eq *= (1.0 + float(sig_i) * r)
                b_eq *= (1.0 + r)
                started = True
            if started:                       # flat carry between windows
                strat[i - chart_lo] = s_eq
                bench[i - chart_lo] = b_eq

        s_fin = strat[np.isfinite(strat)]
        b_fin = bench[np.isfinite(bench)]
        strat_total = float(s_fin[-1] - 1.0) * 100 if s_fin.size else 0.0
        bench_total = float(b_fin[-1] - 1.0) * 100 if b_fin.size else 0.0
        if s_fin.size:
            runmax = np.maximum.accumulate(s_fin)
            max_dd = float(np.min(s_fin / runmax - 1.0)) * 100
        else:
            max_dd = 0.0
        n_trades = len(trade_rets)
        win_rate = (round(sum(1 for r in trade_rets if r > 0) / n_trades * 100, 2)
                    if n_trades else None)

        metrics: Dict[str, Any] = {
            "n_windows_requested": n_windows,
            "n_windows_evaluated": len(ok_windows),
            "n_bars_scored": int(pa.size),
            "direction_hit_rate_pct": round(float(np.mean(horizon_hits)) * 100, 2),
            "bar_direction_hit_rate_pct": (round(float(np.mean(pool_bar_hits)) * 100, 2)
                                           if pool_bar_hits else None),
            "close_mae": round(float(np.mean(np.abs(e_all))), 6),
            "close_mape_pct": round(float(np.mean(ape_all)) * 100, 4),
            "close_rmse": round(float(np.sqrt(np.mean(e_all ** 2))), 6),
            "close_within_5pct_rate": round(float(np.mean(ape_all < 0.05)) * 100, 2),
            "pred_actual_corr": round(corr, 4) if corr is not None else None,
            "envelope_coverage_pct": (round(float(np.mean(pool_env)) * 100, 2)
                                      if pool_env else None),
            "high_extreme_mape_pct": round(float(np.mean(hi_apes)), 4) if hi_apes else None,
            "low_extreme_mape_pct": round(float(np.mean(lo_apes)), 4) if lo_apes else None,
            "strategy_total_return_pct": round(strat_total, 4),
            "benchmark_total_return_pct": round(bench_total, 4),
            "excess_return_pct": round(strat_total - bench_total, 4),
            "strategy_max_drawdown_pct": round(max_dd, 4),
            "strategy_win_rate_pct": win_rate,
            "n_trades": n_trades,
        }

        out = _skeleton("ok", symbol_hint=sym, params=params)
        out["metrics"] = metrics
        out["windows"] = windows_out
        out["dates"] = [_iso(t) for t in ts_all.iloc[chart_lo:chart_hi]]
        out["actual_close"] = [round(float(v), 6) for v in closes[chart_lo:chart_hi]]
        out["predicted_close"] = [round(float(v), 6) if np.isfinite(v) else float("nan")
                                  for v in pred_close_at[chart_lo:chart_hi]]
        out["strategy_curve"] = [round(float(v), 6) if np.isfinite(v) else float("nan")
                                 for v in strat]
        out["benchmark_curve"] = [round(float(v), 6) if np.isfinite(v) else float("nan")
                                  for v in bench]
        _notify(progress_cb, 1.0, "kronos backtest complete")
        return out

    except Exception as exc:
        try:
            return _skeleton("error", error=f"{type(exc).__name__}: {exc}")
        except Exception:
            return {"status": "error", "error": "kronos backtest failed",
                    "symbol_hint": "", "generated_at": "", "params": {},
                    "metrics": {}, "windows": [], "dates": [],
                    "actual_close": [], "predicted_close": [],
                    "strategy_curve": [], "benchmark_curve": []}


def save_backtest_report(result: Dict[str, Any], symbol: str) -> str:
    """Persist a backtest result dict as JSON under ``db/kronos_backtests``.

    Filename: ``backtest_<symbol>_<UTCtimestamp>.json`` (symbol sanitised for
    the filesystem, NaN scrubbed to null). Returns the path, or '' on any
    failure — never raises.
    """
    try:
        import json
        import os
        import re
        from datetime import datetime, timezone

        if not isinstance(result, dict):
            return ""
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(symbol or "")).strip("._-") or "UNKNOWN"
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        out_dir = os.path.join(root, "db", "kronos_backtests")
        os.makedirs(out_dir, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = os.path.join(out_dir, f"backtest_{safe}_{stamp}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(_jsonable(result), fh, indent=2, default=str)
        return path
    except Exception:
        return ""


def summarize_backtest(result: Dict[str, Any]) -> str:
    """Compact multi-line human-readable summary for terminal display."""
    try:
        if not isinstance(result, dict):
            return "KRONOS BACKTEST: no result"
        status = str(result.get("status", "error"))
        sym = str(result.get("symbol_hint") or "?")
        lines = [f"KRONOS BACKTEST  [{sym}]  status={status}"]
        if status != "ok":
            why = result.get("reason") or result.get("error") or "unknown"
            lines.append(f"  -> {why}")
            return "\n".join(lines)
        p = result.get("params") or {}
        m = result.get("metrics") or {}
        lines.append(
            f"  windows   : {m.get('n_windows_evaluated', 0)}/{m.get('n_windows_requested', 0)}"
            f" evaluated | horizon {p.get('pred_len')} bars | context {p.get('window')} bars"
            f" | T={p.get('T')} top_p={p.get('top_p')} samples={p.get('sample_count')}")
        lines.append(
            f"  direction : horizon hit {_fmt_pct(m.get('direction_hit_rate_pct'))}"
            f" | per-bar hit {_fmt_pct(m.get('bar_direction_hit_rate_pct'))}")
        lines.append(
            f"  close err : MAE {_fmt_num(m.get('close_mae'))}"
            f" | MAPE {_fmt_pct(m.get('close_mape_pct'))}"
            f" | RMSE {_fmt_num(m.get('close_rmse'))}"
            f" | corr {_fmt_num(m.get('pred_actual_corr'))}"
            f" | within-5% {_fmt_pct(m.get('close_within_5pct_rate'))}")
        lines.append(
            f"  envelope  : {_fmt_pct(m.get('envelope_coverage_pct'))} of closes inside"
            f" predicted [low, high] | high-ext APE {_fmt_pct(m.get('high_extreme_mape_pct'))}"
            f" | low-ext APE {_fmt_pct(m.get('low_extreme_mape_pct'))}")
        lines.append(
            f"  strategy  : total {_fmt_signed(m.get('strategy_total_return_pct'))}"
            f" vs B&H {_fmt_signed(m.get('benchmark_total_return_pct'))}"
            f" (excess {_fmt_signed(m.get('excess_return_pct'))})"
            f" | maxDD {_fmt_signed(m.get('strategy_max_drawdown_pct'))}"
            f" | trades {m.get('n_trades', 0)}"
            f" win {_fmt_pct(m.get('strategy_win_rate_pct'))}")
        lines.append(f"  generated : {result.get('generated_at', '')}")
        return "\n".join(lines)
    except Exception as exc:
        return f"KRONOS BACKTEST: summary failed ({exc})"


# ─────────────────────────────────────────────
#  Demo
# ─────────────────────────────────────────────

def _demo_dataframe(n_bars: int = 700, seed: int = 42) -> pd.DataFrame:
    """Synthetic random-walk OHLCV frame in the input contract shape."""
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0003, 0.015, n_bars)
    close = 100.0 * np.exp(np.cumsum(rets))
    open_ = np.empty(n_bars)
    open_[0] = 100.0
    open_[1:] = close[:-1] * (1.0 + rng.normal(0, 0.003, n_bars - 1))
    wick = np.abs(rng.normal(0, 0.006, n_bars))
    high = np.maximum(open_, close) * (1.0 + wick)
    low = np.minimum(open_, close) * (1.0 - wick)
    volume = np.round(rng.lognormal(13, 0.4, n_bars))
    df = pd.DataFrame({
        "timestamps": pd.date_range("2023-01-02", periods=n_bars, freq="B"),
        "open": open_, "high": high, "low": low, "close": close,
        "volume": volume, "amount": volume * close,
    })
    df.attrs["symbol"] = "SYNTH"
    return df


if __name__ == "__main__":
    print("ZERO Kronos backtest - synthetic random-walk demo")
    demo = _demo_dataframe()
    print(f"synthetic bars: {len(demo)}  "
          f"span: {demo['timestamps'].iloc[0].date()} -> {demo['timestamps'].iloc[-1].date()}")

    def _cb(frac: float, msg: str) -> None:
        print(f"  [{frac * 100:5.1f}%] {msg}")

    res = run_kronos_backtest(demo, pred_len=10, window=400, n_windows=8,
                              progress_cb=_cb)
    print()
    print(summarize_backtest(res))
    if res.get("status") == "ok":
        saved = save_backtest_report(res, "SYNTH")
        print(f"\nreport saved: {saved or '(save failed)'}")
    else:
        print("\n(no report saved - service unavailable/errored; this still "
              "validates the graceful no-op contract)")

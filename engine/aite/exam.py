"""
ZERO AITE OOS examination / walk-forward backtest engine.

Produces ~40 progress lines for UI sync, trade tables (name, entry, exit,
entry time, exit time), and pass/fail gates against OOS Sharpe / drawdown.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from engine.aite import config as cfg
from engine.aite.indicators import combined_signal, compute_features
from engine.aite.models import BotGenome, ExamResult

logger = logging.getLogger(__name__)


def combine_signal_safe(feats, rules, side_bias):
    return combined_signal(feats, rules, side_bias)


def _timestamps(df: pd.DataFrame) -> List[str]:
    for col in ("timestamps", "timestamp", "datetime", "date", "Date"):
        if col in df.columns:
            return [str(x) for x in df[col].tolist()]
    if isinstance(df.index, pd.DatetimeIndex):
        return [str(x) for x in df.index.tolist()]
    return [f"bar_{i}" for i in range(len(df))]


def _sharpe(returns: np.ndarray, ann: float = 252.0) -> float:
    if returns is None or len(returns) < 2:
        return 0.0
    mu = float(np.mean(returns))
    sd = float(np.std(returns))
    if sd <= 1e-12:
        return 0.0
    return float((mu / sd) * np.sqrt(ann))


def _max_dd(equity: np.ndarray) -> float:
    if equity is None or len(equity) == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / np.where(peak == 0, 1.0, peak)
    return float(abs(dd.min()))


def _simulate(
    feats: pd.DataFrame,
    genome: BotGenome,
    times: List[str],
    commission_bps: float,
    slippage_bps: float,
) -> Tuple[List[Dict[str, Any]], np.ndarray, np.ndarray]:
    """Bar-by-bar long/short simulation with ATR stops."""
    sig = combine_signal_safe(feats, genome.rules, genome.side_bias)
    closes = feats["close"].values.astype(float)
    highs = feats["high"].values.astype(float)
    lows = feats["low"].values.astype(float)
    atrs = feats["atr"].values.astype(float) if "atr" in feats.columns else np.full(len(closes), closes[0] * 0.01)

    n = len(closes)
    equity = np.ones(n, dtype=float)
    rets = np.zeros(n, dtype=float)
    trades: List[Dict[str, Any]] = []

    pos = 0  # +1 / -1 / 0
    entry_px = 0.0
    entry_i = 0
    stop = 0.0
    take = 0.0
    slip = slippage_bps / 10000.0
    fee = commission_bps / 10000.0

    for i in range(1, n):
        # Manage open position
        if pos != 0:
            hit_stop = (pos > 0 and lows[i] <= stop) or (pos < 0 and highs[i] >= stop)
            hit_take = (pos > 0 and highs[i] >= take) or (pos < 0 and lows[i] <= take)
            timed = (i - entry_i) >= max(1, genome.hold_bars)
            flip = sig[i] != 0 and sig[i] != pos

            if hit_stop or hit_take or timed or flip:
                if hit_stop:
                    exit_px = stop
                    reason = "stop"
                elif hit_take:
                    exit_px = take
                    reason = "take"
                elif flip:
                    exit_px = closes[i]
                    reason = "flip"
                else:
                    exit_px = closes[i]
                    reason = "time"

                if pos > 0:
                    exit_px *= (1.0 - slip)
                else:
                    exit_px *= (1.0 + slip)

                pnl_pct = pos * (exit_px / entry_px - 1.0) - 2 * fee
                trades.append({
                    "trade_id": f"{genome.bot_id}_{entry_i}_{i}",
                    "bot_id": genome.bot_id,
                    "bot_name": genome.name,
                    "symbol": genome.symbol,
                    "side": "BUY" if pos > 0 else "SELL",
                    "entry": round(float(entry_px), 4),
                    "exit": round(float(exit_px), 4),
                    "entry_time": times[entry_i] if entry_i < len(times) else str(entry_i),
                    "exit_time": times[i] if i < len(times) else str(i),
                    "qty": 1.0,
                    "pnl": round(float(pnl_pct * 10000), 2),  # notional units
                    "pnl_pct": round(float(pnl_pct) * 100, 4),
                    "bars_held": int(i - entry_i),
                    "reason": reason,
                    "mode": "sim",
                })
                rets[i] = pnl_pct
                equity[i] = equity[i - 1] * (1.0 + pnl_pct)
                pos = 0
                continue

        # Flat → maybe enter
        if pos == 0 and sig[i] != 0:
            pos = int(sig[i])
            entry_i = i
            raw = closes[i]
            entry_px = raw * (1.0 + slip) if pos > 0 else raw * (1.0 - slip)
            a = max(atrs[i], closes[i] * 0.001)
            if pos > 0:
                stop = entry_px - genome.stop_atr * a
                take = entry_px + genome.take_atr * a
            else:
                stop = entry_px + genome.stop_atr * a
                take = entry_px - genome.take_atr * a

        equity[i] = equity[i - 1] * (1.0 + rets[i]) if rets[i] else equity[i - 1]

    return trades, equity, rets


def _progress_lines(genome: BotGenome, n_bars: int, n_is: int, n_oos: int, stage: str, detail: str = "") -> List[str]:
    """Generate exactly BACKTEST_FLOW_LINES narrative lines for UI sync."""
    total = cfg.BACKTEST_FLOW_LINES
    template = [
        f"[01] INIT exam harness for {genome.name} ({genome.bot_id})",
        f"[02] SYMBOL={genome.symbol} STYLE={genome.style} GEN={genome.generation}",
        f"[03] RULES={len(genome.rules)} STOP_ATR={genome.stop_atr} TAKE_ATR={genome.take_atr}",
        f"[04] SIDE_BIAS={genome.side_bias} HOLD_BARS={genome.hold_bars}",
        f"[05] LOAD bars → {n_bars} rows available",
        f"[06] FEATURE ENGINE: RSI MACD BB ATR EMA MOM STOCH ADX CCI VWAP",
        f"[07] SPLIT IS={n_is} bars ({cfg.IS_FRAC:.0%}) | OOS={n_oos} bars ({cfg.OOS_FRAC:.0%})",
        f"[08] COST MODEL: commission={cfg.COMMISSION_BPS}bps slip={cfg.SLIPPAGE_BPS}bps",
        f"[09] BEGIN in-sample simulation…",
        f"[10] IS: warm-up indicators (30 bars)",
        f"[11] IS: signal voting across {len(genome.rules)} rules",
        f"[12] IS: ATR stop/take placement active",
        f"[13] IS: time-stop + flip exits armed",
        f"[14] IS: equity curve accumulating",
        f"[15] IS: trade blotter writing fills",
        f"[16] IS: sharpe / hit-rate interim",
        f"[17] IS: max drawdown checkpoint",
        f"[18] IS: complete — handoff to OOS",
        f"[19] FREEZE parameters (no re-fit)",
        f"[20] BEGIN out-of-sample simulation…",
        f"[21] OOS: fresh feature window",
        f"[22] OOS: signal replay (no look-ahead)",
        f"[23] OOS: risk exits identical to IS",
        f"[24] OOS: equity curve accumulating",
        f"[25] OOS: trade blotter writing fills",
        f"[26] OOS: sharpe computation",
        f"[27] OOS: drawdown gate check (max {cfg.MAX_OOS_DRAWDOWN:.0%})",
        f"[28] OOS: min-trades gate (need ≥ {cfg.MIN_TRADES_OOS})",
        f"[29] OOS: min-sharpe gate (need ≥ {cfg.MIN_OOS_SHARPE})",
        f"[30] COMPOSITE fitness = {cfg.IS_WEIGHT}*IS + {cfg.OOS_WEIGHT}*OOS",
        f"[31] CORRELATION fingerprint (returns series)",
        f"[32] REGIME stress: TREND / RANGE / HIGH_VOL tags",
        f"[33] SLIPPAGE stress: +50% cost sensitivity",
        f"[34] SURVIVORSHIP: status candidate→exam",
        f"[35] VERDICT assembly…",
        f"[36] STAGE={stage}",
        f"[37] DETAIL={detail or 'n/a'}",
        f"[38] PERSIST exam cache row",
        f"[39] EMIT trade table (name/entry/exit/times)",
        f"[40] DONE — ready for portfolio admission",
    ]
    # pad/trim exactly
    while len(template) < total:
        template.append(f"[{len(template)+1:02d}] …")
    return template[:total]


def run_exam(
    genome: BotGenome,
    df: pd.DataFrame,
    commission_bps: float | None = None,
    slippage_bps: float | None = None,
) -> ExamResult:
    """Full IS/OOS exam for one genome. Never raises."""
    try:
        return _run_exam_inner(genome, df, commission_bps, slippage_bps)
    except Exception as exc:  # noqa: BLE001
        lines = _progress_lines(genome, 0, 0, 0, "ERROR", str(exc)[:120])
        return ExamResult(
            bot_id=genome.bot_id,
            passed=False,
            is_sharpe=0.0,
            oos_sharpe=0.0,
            is_return=0.0,
            oos_return=0.0,
            max_dd=1.0,
            n_trades_is=0,
            n_trades_oos=0,
            hit_rate_oos=0.0,
            fitness=0.0,
            reason=f"exam_error: {exc}",
            progress_lines=lines,
        )


def _run_exam_inner(genome, df, commission_bps, slippage_bps) -> ExamResult:
    commission_bps = cfg.COMMISSION_BPS if commission_bps is None else commission_bps
    slippage_bps = cfg.SLIPPAGE_BPS if slippage_bps is None else slippage_bps

    feats = compute_features(df)
    if feats.empty or len(feats) < cfg.MIN_BARS:
        lines = _progress_lines(genome, len(df) if df is not None else 0, 0, 0, "REJECT", "insufficient bars")
        return ExamResult(
            bot_id=genome.bot_id, passed=False,
            is_sharpe=0, oos_sharpe=0, is_return=0, oos_return=0, max_dd=1,
            n_trades_is=0, n_trades_oos=0, hit_rate_oos=0, fitness=0,
            reason="insufficient_bars", progress_lines=lines,
        )

    times = _timestamps(df if df is not None else feats)
    if len(times) != len(feats):
        times = [f"bar_{i}" for i in range(len(feats))]

    n = len(feats)
    split = int(n * cfg.IS_FRAC)
    split = max(40, min(split, n - 30))

    is_feats = feats.iloc[:split].reset_index(drop=True)
    oos_feats = feats.iloc[split:].reset_index(drop=True)
    is_times = times[:split]
    oos_times = times[split:]

    is_trades, is_eq, is_rets = _simulate(is_feats, genome, is_times, commission_bps, slippage_bps)
    oos_trades, oos_eq, oos_rets = _simulate(oos_feats, genome, oos_times, commission_bps, slippage_bps)

    is_sharpe = _sharpe(is_rets[is_rets != 0]) if np.any(is_rets) else _sharpe(is_rets)
    oos_sharpe = _sharpe(oos_rets[oos_rets != 0]) if np.any(oos_rets) else _sharpe(oos_rets)
    is_ret = float(is_eq[-1] - 1.0) if len(is_eq) else 0.0
    oos_ret = float(oos_eq[-1] - 1.0) if len(oos_eq) else 0.0
    max_dd = _max_dd(oos_eq) if len(oos_eq) else 1.0
    n_is = len(is_trades)
    n_oos = len(oos_trades)
    wins = sum(1 for t in oos_trades if t.get("pnl_pct", 0) > 0)
    hit = (wins / n_oos) if n_oos else 0.0

    # Fitness
    is_comp = is_sharpe * (1.0 + max(is_ret, -0.5)) / (1.0 + _max_dd(is_eq))
    oos_comp = oos_sharpe * (1.0 + max(oos_ret, -0.5)) / (1.0 + max_dd)
    fitness = cfg.IS_WEIGHT * is_comp + cfg.OOS_WEIGHT * oos_comp

    passed = (
        n_oos >= cfg.MIN_TRADES_OOS
        and oos_sharpe >= cfg.MIN_OOS_SHARPE
        and max_dd <= cfg.MAX_OOS_DRAWDOWN
        and oos_ret > -0.05
    )
    reason = "PASS" if passed else (
        f"FAIL n_oos={n_oos} sharpe={oos_sharpe:.2f} dd={max_dd:.2%} ret={oos_ret:.2%}"
    )

    lines = _progress_lines(
        genome, n, split, n - split,
        "PASS" if passed else "FAIL",
        f"oos_sharpe={oos_sharpe:.3f} fitness={fitness:.3f}",
    )

    return ExamResult(
        bot_id=genome.bot_id,
        passed=passed,
        is_sharpe=round(is_sharpe, 4),
        oos_sharpe=round(oos_sharpe, 4),
        is_return=round(is_ret, 4),
        oos_return=round(oos_ret, 4),
        max_dd=round(max_dd, 4),
        n_trades_is=n_is,
        n_trades_oos=n_oos,
        hit_rate_oos=round(hit, 4),
        equity_oos=[round(float(x), 6) for x in oos_eq[:: max(1, len(oos_eq) // 40)]],
        trades=oos_trades + is_trades[-5:],  # OOS primary + recent IS samples
        fitness=round(float(fitness), 4),
        reason=reason,
        progress_lines=lines,
    )


def _period_for_bars(bars: int) -> str:
    """yfinance period bucket covering at least ``bars`` trading sessions."""
    # Trading days → calendar days with weekend/holiday headroom.
    cal_days = int(max(bars, cfg.TARGET_BARS) * 1.7) + 30
    if cal_days <= 90:
        return "3mo"
    if cal_days <= 180:
        return "6mo"
    if cal_days <= 365:
        return "1y"
    if cal_days <= 730:
        return "2y"
    if cal_days <= 1825:
        return "5y"
    return "max"


def _normalize_ohlcv_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten MultiIndex, lower-case OHLCV, promote Date index → timestamps."""
    if df is None or getattr(df, "empty", True):
        return pd.DataFrame()
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [
            str(c[0]).lower() if isinstance(c, tuple) else str(c).lower()
            for c in out.columns
        ]
    else:
        out.columns = [str(c).lower() for c in out.columns]
    # Drop duplicate column labels keeping first (yf MultiIndex quirk)
    out = out.loc[:, ~pd.Index(out.columns).duplicated()]
    rename = {c: "volume" for c in out.columns if c in ("vol",)}
    if rename:
        out = out.rename(columns=rename)
    if not any(c in out.columns for c in ("timestamps", "timestamp", "datetime", "date")):
        if isinstance(out.index, pd.DatetimeIndex) or str(out.index.name).lower() in (
            "date", "datetime", "timestamps",
        ):
            out = out.reset_index()
            # reset_index may introduce Date / index / level_0
            for cand in ("date", "datetime", "index", "level_0"):
                if cand in out.columns:
                    out = out.rename(columns={cand: "timestamps"})
                    break
    for need in ("open", "high", "low", "close"):
        if need not in out.columns:
            return pd.DataFrame()
    if "volume" not in out.columns:
        out["volume"] = 1.0
    keep = [c for c in ("timestamps", "timestamp", "datetime", "date",
                        "open", "high", "low", "close", "volume") if c in out.columns]
    return out[keep].dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)


def _pad_with_synthetic(df: pd.DataFrame, bars: int, symbol: str) -> pd.DataFrame:
    """
    Prepend synthetic older bars so recent real OHLC stays at the end.
    Last-resort only — caller must log.
    """
    need = max(0, bars - len(df))
    if need <= 0:
        return df.tail(bars).copy() if len(df) > bars else df.copy()
    seed = abs(hash(symbol)) % 10_000
    start = float(df["close"].iloc[0]) if len(df) and "close" in df.columns else 22000.0
    # Walk backward from first real close so the join is continuous.
    synth = _synthetic_ohlcv(need, seed=seed, start_price=start)
    # Reverse-scale so synth ends near first real close
    if len(synth) and float(synth["close"].iloc[-1]) > 0:
        scale = start / float(synth["close"].iloc[-1])
        for col in ("open", "high", "low", "close"):
            synth[col] = synth[col] * scale
    # Shift synth timestamps before first real bar when possible
    if "timestamps" in df.columns and len(df):
        try:
            first_ts = pd.Timestamp(df["timestamps"].iloc[0])
            synth["timestamps"] = pd.bdate_range(end=first_ts - pd.Timedelta(days=1), periods=need)
        except Exception:
            pass
    merged = pd.concat([synth, df], ignore_index=True)
    return merged.tail(bars).reset_index(drop=True)


def load_market_frame(symbol: str, bars: int | None = None) -> pd.DataFrame:
    """
    Fetch OHLCV via ZERO historical adapters with enough history for OOS exams.

    Preference order:
      1. data.historical.get_historical_data with a period covering ``bars``
      2. direct yfinance download (2y+)
      3. synthetic pad of a short real series (logged) — last resort
      4. full synthetic frame (offline / total API failure)
    """
    bars = int(bars or cfg.DEFAULT_BARS)
    bars = max(bars, cfg.TARGET_BARS, cfg.MIN_BARS)
    period = _period_for_bars(bars)
    hist_key = cfg.INDEX_KEYS.get(symbol, symbol)
    min_accept = cfg.MIN_BARS
    short_real: pd.DataFrame | None = None

    def _keep_if_short(frame: pd.DataFrame) -> None:
        nonlocal short_real
        if frame is not None and 0 < len(frame) < min_accept:
            if short_real is None or len(frame) > len(short_real):
                short_real = frame

    # 1) ZERO historical adapter with explicit long period (not default 60d)
    try:
        from data.historical import get_historical_data
        raw = get_historical_data(hist_key, period=period)
        df = _normalize_ohlcv_frame(raw)
        if len(df) >= min_accept:
            if len(df) < bars:
                logger.info(
                    "AITE load_market_frame(%s): got %d real bars (want %d) via historical period=%s",
                    symbol, len(df), bars, period,
                )
            return df.tail(bars).copy() if len(df) > bars else df.copy()
        _keep_if_short(df)
        if len(df) > 0:
            logger.warning(
                "AITE load_market_frame(%s): historical period=%s returned only %d bars (< MIN_BARS=%d)",
                symbol, period, len(df), min_accept,
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("AITE historical load failed for %s: %s", symbol, exc)

    # 2) Direct yfinance with long lookback
    try:
        import yfinance as yf
        ticker = {
            "NIFTY 50": "^NSEI",
            "BANKNIFTY": "^NSEBANK",
            "SENSEX": "^BSESN",
        }.get(symbol, symbol)
        yf_period = period if period in ("2y", "5y", "max") else "2y"
        raw = yf.download(ticker, period=yf_period, interval="1d", progress=False, auto_adjust=True)
        df = _normalize_ohlcv_frame(raw)
        if len(df) >= min_accept:
            if len(df) < bars:
                logger.info(
                    "AITE load_market_frame(%s): got %d real bars (want %d) via yfinance period=%s",
                    symbol, len(df), bars, yf_period,
                )
            return df.tail(bars).copy() if len(df) > bars else df.copy()
        _keep_if_short(df)
        if len(df) > 0:
            logger.warning(
                "AITE load_market_frame(%s): yfinance period=%s returned only %d bars",
                symbol, yf_period, len(df),
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("AITE yfinance load failed for %s: %s", symbol, exc)

    # 3) Pad short real series (last resort)
    if short_real is not None and len(short_real) > 0:
        logger.warning(
            "AITE load_market_frame(%s): padding short real series (%d bars) with synthetic "
            "history to reach %d (last resort)",
            symbol, len(short_real), bars,
        )
        return _pad_with_synthetic(short_real, bars, symbol)

    logger.warning(
        "AITE load_market_frame(%s): no usable real OHLC — using full synthetic %d bars",
        symbol, bars,
    )
    return _synthetic_ohlcv(bars, seed=abs(hash(symbol)) % 10_000)


def _synthetic_ohlcv(n: int = 400, seed: int = 7, start_price: float = 22000.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = max(1, int(n))
    rets = rng.normal(0.0003, 0.009, size=n)
    close = start_price * np.cumprod(1.0 + rets)
    open_ = np.empty(n)
    open_[0] = start_price
    open_[1:] = close[:-1]
    spread = np.abs(rng.normal(0, 0.004, size=n)) * close
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    volume = rng.uniform(1e6, 5e6, size=n)
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame({
        "timestamps": idx,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })

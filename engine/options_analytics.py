"""Institutional options analytics: OI-change tracking, IV smile,
term structure, max-pain drift, and multi-leg strategies with
vectorized expiry payoff + probability-of-profit.

Consumes snapshot records produced by
``data.options_chain.snapshot_option_chain``::

    {'ts', 'symbol', 'spot', 'pcr', 'max_pain', 'expiry',
     'strikes': [{'strike', 'ce_oi', 'pe_oi', 'ce_iv', 'pe_iv',
                  'ce_ltp', 'pe_ltp'}, ...]}

Leg shape (multi-leg strategies)::

    {'right': 'CE'|'PE', 'strike': float, 'side': 'buy'|'sell',
     'qty': int, 'premium': float}

Conventions (ZERO shared): numpy/pandas only, no network at import,
importable without Streamlit, public functions never raise — error
payloads carry a 'status' key. Constants are env-overridable.
"""
from __future__ import annotations

import datetime as _dt
import math as _math
import os as _os

import numpy as np

# --- Env-overridable constants ---------------------------------------------
GRID_POINTS = int(_os.environ.get('ZERO_OA_GRID_POINTS', '4001'))
# Log-moneyness offsets used as the 25-delta proxy for smile skew.
SKEW_MONEYNESS_STEP = float(_os.environ.get('ZERO_OA_SKEW_STEP', '0.05'))
MIN_SMILE_POINTS = int(_os.environ.get('ZERO_OA_MIN_SMILE_POINTS', '5'))

# Quantile anchors recognised in a calibrated band dict, lowest to highest.
# ZERO's prediction band uses {'low_lo', 'high_hi'}; some callers pass
# {'p10', 'p90'}. All four are supported and may be combined.
_BAND_ANCHORS = (('low_lo', 0.05), ('p10', 0.10), ('p90', 0.90), ('high_hi', 0.95))


# --- Small helpers (never raise) --------------------------------------------
def _f(value, default: float = 0.0) -> float:
    """Best-effort float coercion."""
    try:
        if value is None:
            return default
        v = float(value)
        if _math.isnan(v) or _math.isinf(v):
            return default
        return v
    except Exception:
        return default


def _strikes_map(chain: dict | None) -> dict[float, dict]:
    """Map strike -> strike-row from a snapshot/processed chain dict."""
    out: dict[float, dict] = {}
    try:
        for row in (chain or {}).get('strikes') or []:
            k = _f((row or {}).get('strike'), default=-1.0)
            if k >= 0:
                out[k] = row
    except Exception:
        pass
    return out


def _prem(premiums: dict | None, *keys: str) -> float:
    """Fetch the first present numeric premium among alias keys."""
    for key in keys:
        try:
            val = (premiums or {}).get(key)
            if val is not None:
                return _f(val, 0.0)
        except Exception:
            continue
    return 0.0


# --- OI-change tracking ------------------------------------------------------
def compute_oi_change(current: dict, previous: dict) -> dict:
    """Per-strike CE/PE OI deltas between two snapshots + aggregate classification.

    'current'/'previous' are snapshot records (need a 'strikes' list).
    Returns {'status', 'per_strike': [{strike, ce_oi, pe_oi, ce_oi_prev,
    pe_oi_prev, ce_oi_chg, pe_oi_chg}], 'total_ce_oi_chg', 'total_pe_oi_chg',
    'net_call_writing', 'net_put_writing', 'classification'}.
    Positive total OI change => writing (fresh short positions); negative
    => unwinding. Never raises.
    """
    out = {
        'status': 'insufficient',
        'per_strike': [],
        'total_ce_oi_chg': 0.0,
        'total_pe_oi_chg': 0.0,
        'net_call_writing': False,
        'net_put_writing': False,
        'classification': 'NO_DATA',
    }
    try:
        cur = _strikes_map(current)
        prev = _strikes_map(previous)
        if not cur or not prev:
            return out
        rows = []
        tot_ce = 0.0
        tot_pe = 0.0
        for strike in sorted(set(cur) | set(prev)):
            c = cur.get(strike) or {}
            p = prev.get(strike) or {}
            ce_now = _f(c.get('ce_oi'))
            pe_now = _f(c.get('pe_oi'))
            ce_prev = _f(p.get('ce_oi'))
            pe_prev = _f(p.get('pe_oi'))
            ce_chg = ce_now - ce_prev
            pe_chg = pe_now - pe_prev
            tot_ce += ce_chg
            tot_pe += pe_chg
            rows.append({
                'strike': strike,
                'ce_oi': ce_now,
                'pe_oi': pe_now,
                'ce_oi_prev': ce_prev,
                'pe_oi_prev': pe_prev,
                'ce_oi_chg': ce_chg,
                'pe_oi_chg': pe_chg,
            })
        out.update({
            'status': 'ok',
            'per_strike': rows,
            'total_ce_oi_chg': tot_ce,
            'total_pe_oi_chg': tot_pe,
            'net_call_writing': tot_ce > 0,
            'net_put_writing': tot_pe > 0,
            'classification': (
                ('CALL_WRITING' if tot_ce > 0 else 'CALL_UNWINDING')
                + '_'
                + ('PUT_WRITING' if tot_pe > 0 else 'PUT_UNWINDING')
            ),
        })
    except Exception:
        pass
    return out


def classify_buildup(price_chg: float, oi_chg: float) -> str:
    """Classify futures/options buildup from price & OI change.

    price up + OI up -> LONG_BUILDUP; price down + OI up -> SHORT_BUILDUP;
    price down + OI down -> LONG_UNWINDING; price up + OI down ->
    SHORT_COVERING. Zero counts as 'up'. Never raises.
    """
    try:
        p = _f(price_chg)
        o = _f(oi_chg)
        if o >= 0:
            return 'LONG_BUILDUP' if p >= 0 else 'SHORT_BUILDUP'
        return 'SHORT_COVERING' if p >= 0 else 'LONG_UNWINDING'
    except Exception:
        return 'LONG_BUILDUP'


# --- Volatility surface ------------------------------------------------------
def iv_smile(strikes: list[float], ivs: list[float], spot: float) -> dict:
    """Quadratic smile fit on log-moneyness.

    Fits iv = a*k^2 + b*k + c with k = ln(strike/spot) over valid
    (strike > 0, iv > 0) pairs. Returns {'atm_iv', 'skew_25d_proxy',
    'curvature', 'status', 'n_points'}:
      - atm_iv: fitted IV at k=0 (the constant term).
      - skew_25d_proxy: fit(-SKEW_MONEYNESS_STEP) - fit(+SKEW_MONEYNESS_STEP);
        positive values indicate classic downside put skew.
      - curvature: second derivative 2a (smile convexity).
    Needs >= MIN_SMILE_POINTS valid pairs else status 'insufficient'.
    IV units are pass-through (NSE reports percent). Never raises.
    """
    out = {'atm_iv': None, 'skew_25d_proxy': None, 'curvature': None,
           'status': 'insufficient', 'n_points': 0}
    try:
        s = _f(spot, -1.0)
        if s <= 0:
            out['status'] = 'invalid_spot'
            return out
        pairs = []
        for k_raw, v_raw in zip(strikes or [], ivs or []):
            k = _f(k_raw, -1.0)
            v = _f(v_raw, -1.0)
            if k > 0 and v > 0:
                pairs.append((k, v))
        if len(pairs) < MIN_SMILE_POINTS:
            return out
        ks = np.array([p[0] for p in pairs], dtype=float)
        ys = np.array([p[1] for p in pairs], dtype=float)
        x = np.log(ks / s)
        a, b, c = np.polyfit(x, ys, 2)
        fit = lambda m: float(a * m * m + b * m + c)  # noqa: E731
        out.update({
            'atm_iv': float(c),
            'skew_25d_proxy': fit(-SKEW_MONEYNESS_STEP) - fit(SKEW_MONEYNESS_STEP),
            'curvature': float(2.0 * a),
            'status': 'ok',
            'n_points': len(pairs),
        })
    except Exception:
        pass
    return out


def _expiry_sort_key(expiry: str):
    """Sort key for NSE-style expiry strings ('05-Aug-2026'); falls back
    to the raw string so unknown formats still sort deterministically."""
    for fmt in ('%d-%b-%Y', '%d-%B-%Y', '%Y-%m-%d'):
        try:
            return (0, _dt.datetime.strptime(str(expiry), fmt))
        except Exception:
            continue
    return (1, str(expiry))


def atm_iv_term_structure(chain_by_expiry: dict[str, dict]) -> list[dict]:
    """ATM IV per expiry, sorted nearest-first.

    chain_by_expiry maps expiry string -> chain dict with 'strikes'
    (snapshot strike rows) and optionally 'spot'/'underlyingValue'.
    ATM = strike nearest spot (median strike when spot absent); ATM IV is
    the mean of whichever of ce_iv/pe_iv is present there. Expiries with
    no usable IV are skipped. Never raises.
    """
    out: list[dict] = []
    try:
        for expiry, chain in (chain_by_expiry or {}).items():
            try:
                rows = (chain or {}).get('strikes') or []
                if not rows:
                    continue
                spot = _f((chain or {}).get('spot',
                          (chain or {}).get('underlyingValue')), -1.0)
                strikes = sorted(_f(r.get('strike'), -1.0) for r in rows
                                 if _f(r.get('strike'), -1.0) >= 0)
                if not strikes:
                    continue
                target = spot if spot > 0 else strikes[len(strikes) // 2]
                best = min(
                    rows,
                    key=lambda r: abs(_f(r.get('strike'), target) - target),
                )
                ivs = [v for v in (_f(best.get('ce_iv'), -1.0),
                                   _f(best.get('pe_iv'), -1.0)) if v > 0]
                if not ivs:
                    continue
                out.append({
                    'expiry': expiry,
                    'atm_iv': sum(ivs) / len(ivs),
                    'atm_strike': _f(best.get('strike')),
                })
            except Exception:
                continue
        out.sort(key=lambda r: _expiry_sort_key(r.get('expiry')))
    except Exception:
        pass
    return out


def max_pain_drift(snapshots: list[dict]) -> list[dict]:
    """Max-pain time series from snapshots: [{'ts', 'max_pain'}], newest-last.

    Snapshots missing 'max_pain' are skipped. Never raises.
    """
    out: list[dict] = []
    try:
        for snap in snapshots or []:
            try:
                mp = (snap or {}).get('max_pain')
                if mp is None:
                    continue
                out.append({'ts': snap.get('ts'), 'max_pain': _f(mp)})
            except Exception:
                continue
    except Exception:
        pass
    return out


# --- Multi-leg strategy builders ---------------------------------------------
def _leg(right: str, strike: float, side: str, premium: float, qty: int = 1) -> dict:
    return {'right': right, 'strike': round(_f(strike), 2), 'side': side,
            'qty': int(qty), 'premium': _f(premium)}


def long_straddle(spot: float, atm_premium_ce: float, atm_premium_pe: float,
                  strike: float | None = None) -> list[dict]:
    """Buy 1 CE + 1 PE at the same strike (defaults to spot). [] on error."""
    try:
        k = _f(strike if strike is not None else spot)
        return [_leg('CE', k, 'buy', atm_premium_ce),
                _leg('PE', k, 'buy', atm_premium_pe)]
    except Exception:
        return []


def long_strangle(spot: float, width_pct: float, prem_ce: float,
                  prem_pe: float) -> list[dict]:
    """Buy OTM CE at spot*(1+width_pct) + OTM PE at spot*(1-width_pct).

    width_pct is a per-side fractional offset (0.02 = +/-2%). [] on error.
    """
    try:
        s = _f(spot)
        w = abs(_f(width_pct))
        return [_leg('CE', s * (1.0 + w), 'buy', prem_ce),
                _leg('PE', s * (1.0 - w), 'buy', prem_pe)]
    except Exception:
        return []


def iron_condor(spot: float, wing_width: float, premiums: dict) -> list[dict]:
    """Sell body at spot +/- wing_width, buy wings one width further out.

    premiums keys (aliases accepted): sell_pe/pe_short, buy_pe/pe_long,
    sell_ce/ce_short, buy_ce/ce_long. Missing premiums default 0. [] on error.
    """
    try:
        s = _f(spot)
        w = abs(_f(wing_width))
        return [
            _leg('PE', s - 2.0 * w, 'buy', _prem(premiums, 'buy_pe', 'pe_long', 'long_pe')),
            _leg('PE', s - w, 'sell', _prem(premiums, 'sell_pe', 'pe_short', 'short_pe')),
            _leg('CE', s + w, 'sell', _prem(premiums, 'sell_ce', 'ce_short', 'short_ce')),
            _leg('CE', s + 2.0 * w, 'buy', _prem(premiums, 'buy_ce', 'ce_long', 'long_ce')),
        ]
    except Exception:
        return []


def bull_call_spread(spot: float, width: float, prem_long: float,
                     prem_short: float) -> list[dict]:
    """Buy CE at spot, sell CE at spot + width. [] on error."""
    try:
        s = _f(spot)
        w = abs(_f(width))
        return [_leg('CE', s, 'buy', prem_long),
                _leg('CE', s + w, 'sell', prem_short)]
    except Exception:
        return []


# --- Payoff & metrics ---------------------------------------------------------
def payoff_at_expiry(legs: list[dict], spot_range: np.ndarray) -> np.ndarray:
    """Vectorized expiry PnL per unit, net of premiums.

    Buy: sign=+1 -> qty * (intrinsic - premium); sell mirrors. Unknown legs
    are skipped. Returns a float array aligned with spot_range; an empty
    zeros array on error (never raises).
    """
    try:
        s = np.asarray(spot_range, dtype=float)
        pnl = np.zeros_like(s, dtype=float)
        for leg in legs or []:
            try:
                right = str((leg or {}).get('right', '')).upper()
                k = _f(leg.get('strike'))
                prem = _f(leg.get('premium'))
                qty = _f(leg.get('qty', 1), 1.0)
                sign = 1.0 if str(leg.get('side', 'buy')).lower() == 'buy' else -1.0
                if right == 'CE':
                    intrinsic = np.maximum(s - k, 0.0)
                elif right == 'PE':
                    intrinsic = np.maximum(k - s, 0.0)
                else:
                    continue
                pnl += sign * qty * (intrinsic - prem)
            except Exception:
                continue
        return pnl
    except Exception:
        try:
            return np.zeros(len(spot_range), dtype=float)
        except Exception:
            return np.zeros(0, dtype=float)


def _band_cdf_points(band: dict) -> tuple[list[float], list[float]]:
    """Sorted (value, cumulative-prob) anchors from a calibrated band dict.

    Recognises low_lo/p10/p90/high_hi. Returns ([], []) when fewer than two
    usable anchors exist.
    """
    pts: list[tuple[float, float]] = []
    for key, q in _BAND_ANCHORS:
        try:
            val = (band or {}).get(key)
            if val is not None:
                v = _f(val, -1.0)
                if v >= 0:
                    pts.append((v, q))
        except Exception:
            continue
    pts.sort(key=lambda t: t[0])
    if len(pts) < 2:
        return [], []
    return [p[0] for p in pts], [p[1] for p in pts]


def _band_prob_between(xs: list[float], qs: list[float], lo: float, hi: float) -> float:
    """CDF(hi) - CDF(lo) under piecewise-linear interpolation; the CDF
    clamps to 0 below the first anchor and 1 above the last."""
    try:
        c_lo = float(np.interp(lo, xs, qs, left=0.0, right=1.0))
        c_hi = float(np.interp(hi, xs, qs, left=0.0, right=1.0))
        return max(0.0, c_hi - c_lo)
    except Exception:
        return 0.0


def strategy_metrics(legs: list[dict], spot: float,
                     band: dict | None = None) -> dict:
    """Max profit/loss, breakevens, and probability-of-profit for a strategy.

    Evaluates the expiry payoff on a dense grid [0, max(3*spot,
    1.5*max_strike)]. Breakevens are linear-interpolated sign-change roots
    of the payoff curve, sorted ascending. pop_estimate integrates the
    calibrated band ('low_lo'/'p10'/'p90'/'high_hi' anchors, piecewise-linear
    CDF) over the regions where payoff > 0 — between breakevens for
    range-bound strategies, outside them for long-vol ones. None when band
    is absent or unusable. 'max_profit_unbounded'/'max_loss_unbounded' flag
    open-ended tails (grid numbers are then just the grid extremes).
    Never raises.
    """
    out = {
        'status': 'invalid',
        'max_profit': None,
        'max_loss': None,
        'breakevens': [],
        'pop_estimate': None,
        'max_profit_unbounded': False,
        'max_loss_unbounded': False,
    }
    try:
        s = _f(spot, -1.0)
        if not legs or s <= 0:
            return out
        leg_strikes = [_f(l.get('strike')) for l in legs if l]
        hi = max(3.0 * s, (max(leg_strikes) * 1.5) if leg_strikes else 3.0 * s)
        lo = 0.0
        grid = np.linspace(lo, hi, GRID_POINTS)
        pnl = payoff_at_expiry(legs, grid)

        out['max_profit'] = float(np.max(pnl))
        out['max_loss'] = float(np.min(pnl))

        # Unbounded-tail detection from net long optionality at each extreme.
        net_ce = 0.0
        net_pe = 0.0
        for leg in legs:
            try:
                q = _f(leg.get('qty', 1), 1.0) * (
                    1.0 if str(leg.get('side', 'buy')).lower() == 'buy' else -1.0)
                if str(leg.get('right', '')).upper() == 'CE':
                    net_ce += q
                elif str(leg.get('right', '')).upper() == 'PE':
                    net_pe += q
            except Exception:
                continue
        out['max_profit_unbounded'] = net_ce > 0
        out['max_loss_unbounded'] = net_ce < 0 or net_pe < 0

        # Breakevens: exact zeros plus sign-change roots (linear interp).
        bes: list[float] = []
        for i in range(len(grid) - 1):
            y0 = float(pnl[i])
            y1 = float(pnl[i + 1])
            if y0 == 0.0:
                bes.append(float(grid[i]))
            elif y0 * y1 < 0.0:
                root = grid[i] - y0 * (grid[i + 1] - grid[i]) / (y1 - y0)
                bes.append(float(root))
        bes.sort()
        tol = (hi - lo) / max(len(grid) - 1, 1) * 0.5
        deduped: list[float] = []
        for b in bes:
            if not deduped or b - deduped[-1] > tol:
                deduped.append(b)
        out['breakevens'] = deduped

        # POP: probability mass over regions where payoff > 0.
        if band:
            xs, qs = _band_cdf_points(band)
            if xs:
                bounds = [lo] + deduped + [hi]
                prob = 0.0
                for a, b in zip(bounds[:-1], bounds[1:]):
                    if b <= a:
                        continue
                    mid = 0.5 * (a + b)
                    mid_pnl = float(payoff_at_expiry(legs, np.array([mid]))[0])
                    if mid_pnl > 0:
                        prob += _band_prob_between(xs, qs, a, b)
                out['pop_estimate'] = round(min(1.0, max(0.0, prob)), 4)

        out['status'] = 'ok'
    except Exception:
        pass
    return out

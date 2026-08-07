"""ZERO // Kronos visualization layer — pure Plotly chart builders.

Recreates (and upgrades) the Kronos foundation-model web UI charts inside
the ZERO dark terminal:

* Upstream reference 1 — ``Kronos-master/webui/app.py`` + ``templates/index.html``:
  a Plotly candlestick figure with historical candles in one color pair,
  predicted candles in a contrasting pair, timestamps continued past the
  forecast boundary at the inferred bar interval, rangeslider off, date axis.
* Upstream reference 2 — ``Kronos-master/examples/prediction_example.py``:
  a two-panel matplotlib figure (close on top, volume below, shared x) that
  overlays ground truth vs prediction.

House theme tokens are lifted from ``ui/charts.py`` / ``ui/components.py``:

===================  =====================================================
Token                Value
===================  =====================================================
paper/plot bg        ``rgba(0,0,0,0)`` (transparent over #000/#0a0a0a app)
font                 family ``Outfit``, color ``#ffffff``
green (up / buy)     ``#00ff88``
red (down / sell)    ``#E50914``  (alt ``#ff4b4b``)
gold (accent)        ``#D4AF37``
muted text / ticks   ``#888``
grid / borders       ``#333`` / ``#1a1a1a`` (grid ~ rgba(255,255,255,0.06))
margins              compact, ``t=50`` when titled (see sentiment gauge)
===================  =====================================================

Design contract
---------------
* Pure functions: **no streamlit import** — only numpy / pandas / plotly.
* Every public function tolerates ``None`` / empty / malformed input and
  returns an annotated empty dark figure (or a fallback badge string for the
  HTML helper). They never raise.

Public API
----------
- ``kronos_forecast_chart``    — history + forecast candles, NOW divider,
  uncertainty band, optional volume subplot.
- ``kronos_close_paths_chart`` — 'spaghetti' plot of sampled close paths.
- ``kronos_backtest_chart``    — predicted-vs-actual overlay + equity curves.
- ``kronos_status_badge_html`` — inline-styled ONLINE/STANDBY/OFFLINE badge.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ---------------------------------------------------------------------------
# Theme tokens (mirrors ui/charts.py — keep in sync with the house style)
# ---------------------------------------------------------------------------
PAPER_BG = "rgba(0,0,0,0)"
PLOT_BG = "rgba(0,0,0,0)"
FONT_FAMILY = "Outfit"
FONT_COLOR = "#ffffff"

GREEN = "#00ff88"          # ZERO buy / up
RED = "#E50914"            # ZERO sell / down
GOLD = "#D4AF37"           # ZERO accent — forecast "up" candles
YELLOW = "#FFD600"          # forecast "down" candles (distinct from RED)
MUTED = "#888"             # secondary text / ticks
GRID = "rgba(255,255,255,0.06)"
AXIS_LINE = "#333"

GREEN_A = "rgba(0,255,136,0.45)"     # translucent volume up
RED_A = "rgba(229,9,20,0.45)"        # translucent volume down
GOLD_A = "rgba(212,175,55,0.50)"     # muted-gold forecast volume
BAND_FILL = "rgba(212,175,55,0.16)"  # uncertainty band fill
PATH_LINE = "rgba(212,175,55,0.25)"  # spaghetti sample paths
DIVIDER = "rgba(255,255,255,0.45)"   # NOW divider line

# Streamlit ``st.plotly_chart(..., config=...)`` — keep interactive (never
# staticPlot / never hide the modebar). Zoom, pan, box/lasso, scroll-zoom,
# hover, and reset live on the Plotly modebar; scroll wheel zooms in-place.
KRONOS_PLOTLY_CONFIG = dict(
    scrollZoom=True,
    displayModeBar=True,
    displaylogo=False,
    responsive=True,
    # Defaults already include zoom2d / pan2d / select2d / lasso2d /
    # zoomIn2d / zoomOut2d / autoScale2d / resetScale2d — leave them on.
    modeBarButtonsToRemove=["toImage"],  # keep chrome lean; export rarely used here
)

_OHLC_ALIASES = {
    "timestamp": "timestamps", "date": "timestamps", "datetime": "timestamps",
    "time": "timestamps", "ts": "timestamps",
    "o": "open", "h": "high", "l": "low", "c": "close",
    "vol": "volume", "v": "volume",
}

_DEFAULT_STEP = pd.Timedelta(minutes=5)  # Kronos demo data is 5-min bars


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _hoverlabel():
    return dict(
        bgcolor="rgba(10,10,10,0.95)",
        bordercolor=AXIS_LINE,
        font=dict(family=FONT_FAMILY, color=FONT_COLOR, size=11),
    )


def _apply_dark_layout(fig, title="", height=520, legend_top=True, uirevision=None):
    """Apply the ZERO terminal layout (same bg / grid / font as ui/charts.py).

    Interactivity: ``dragmode='pan'`` (TradingView-style; modebar toggles to
    box/lasso zoom), unified hover, gold/muted spike lines, and a stable
    ``uirevision`` so Streamlit reruns do not wipe the user's zoom/pan.
    Rangeslider stays off — the modebar owns zoom/pan/reset.
    """
    fig.update_layout(
        title=dict(
            text=title,
            font=dict(family=FONT_FAMILY, size=13, color=GOLD),
            x=0.01, xanchor="left",
        ) if title else None,
        paper_bgcolor=PAPER_BG,
        plot_bgcolor=PLOT_BG,
        font=dict(family=FONT_FAMILY, color=FONT_COLOR, size=12),
        margin=dict(l=10, r=10, t=50 if title else 30, b=10),
        height=height,
        hovermode="x unified",
        hoverlabel=_hoverlabel(),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="right", x=1.0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=10, color=MUTED),
        ) if legend_top else None,
        # Pan by default; modebar exposes zoom / box / lasso / reset.
        dragmode="pan",
        # Preserve viewport across Streamlit reruns when the series identity
        # is unchanged (symbol / chart family). Fresh data still redraws.
        uirevision=uirevision if uirevision is not None else (title or "kronos"),
        spikedistance=-1,
        hoverdistance=20,
    )
    fig.update_xaxes(
        rangeslider_visible=False,
        showgrid=True, gridcolor=GRID,
        zeroline=False, linecolor=AXIS_LINE, showline=True,
        tickfont=dict(color=MUTED, size=10),
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikecolor=GOLD,
        spikethickness=1,
        spikedash="dot",
    )
    fig.update_yaxes(
        showgrid=True, gridcolor=GRID,
        zeroline=False, linecolor=AXIS_LINE, showline=True,
        tickfont=dict(color=MUTED, size=10),
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikecolor=MUTED,
        spikethickness=1,
        spikedash="dot",
        fixedrange=False,  # allow vertical zoom/pan (trading-chart feel)
    )
    return fig


def _empty_fig(message="NO DATA", height=420):
    """Annotated empty figure in the dark terminal style (graceful fallback)."""
    fig = go.Figure()
    fig.update_layout(
        paper_bgcolor=PAPER_BG,
        plot_bgcolor=PLOT_BG,
        font=dict(family=FONT_FAMILY, color=FONT_COLOR),
        margin=dict(l=10, r=10, t=30, b=10),
        height=height,
        showlegend=False,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    fig.add_annotation(
        x=0.5, y=0.5, xref="paper", yref="paper",
        text=str(message),
        showarrow=False,
        font=dict(family=FONT_FAMILY, size=13, color=MUTED),
    )
    return fig


def _coerce_ohlcv(df):
    """Normalize an OHLCV frame; return None when nothing usable.

    Accepts a DataFrame (or anything ``pd.DataFrame`` can wrap). Column names
    are lower-cased and aliased; a ``timestamps`` column is pulled from the
    index when missing (pred_df often carries timestamps in its index).
    Requires a numeric ``close``; missing open/high/low fall back to close so
    a degraded frame still renders instead of raising.
    """
    if df is None:
        return None
    if not isinstance(df, pd.DataFrame):
        try:
            df = pd.DataFrame(df)
        except Exception:
            return None
    if df.empty:
        return None

    out = df.copy()
    out.columns = [str(c).strip().lower() for c in out.columns]
    out = out.rename(columns=_OHLC_ALIASES)
    # Drop duplicated columns after aliasing (keep first).
    out = out.loc[:, ~out.columns.duplicated()]

    # timestamps: column first, then index (DatetimeIndex or parseable).
    # A numeric index (e.g. RangeIndex) is NOT parsed — pd.to_datetime would
    # silently map 0..N to 1970-epoch stamps; positional x is used instead.
    if "timestamps" in out.columns:
        ts = pd.to_datetime(out["timestamps"], errors="coerce")
    elif isinstance(out.index, pd.DatetimeIndex):
        ts = pd.Series(out.index, index=out.index)
    else:
        idx = pd.Series(out.index, index=out.index)
        if pd.api.types.is_numeric_dtype(idx):
            ts = pd.Series(pd.NaT, index=out.index)
        else:
            ts = pd.to_datetime(idx, errors="coerce")
    out["timestamps"] = ts.values

    if "close" not in out.columns:
        return None
    for col in ("open", "high", "low", "close", "volume"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out[out["close"].notna()]
    if out.empty:
        return None
    for col in ("open", "high", "low"):
        if col not in out.columns or out[col].isna().all():
            out[col] = out["close"]
        else:
            out[col] = out[col].fillna(out["close"])
    if "volume" not in out.columns:
        out["volume"] = np.nan
    return out.reset_index(drop=True)


def _x_axis(df):
    """X values for a coerced frame: real timestamps, else positional ints."""
    ts = df["timestamps"]
    if ts.notna().all():
        return pd.DatetimeIndex(ts)
    return pd.Index(np.arange(len(df)))


def _infer_step(x):
    """Bar interval from the last two x values (mirrors webui/app.py)."""
    try:
        if len(x) >= 2:
            step = x[-1] - x[-2]
            if isinstance(step, pd.Timedelta):
                return step if step > pd.Timedelta(0) else _DEFAULT_STEP
            return step if step > 0 else 1
    except Exception:
        pass
    return _DEFAULT_STEP if isinstance(x, pd.DatetimeIndex) else 1


def _continue_axis(hist_x, n):
    """Synthesize n x-values continuing past hist_x at the inferred interval."""
    if hist_x is None or len(hist_x) == 0:
        return pd.Index(np.arange(n))
    step = _infer_step(hist_x)
    last = hist_x[-1]
    try:
        if isinstance(hist_x, pd.DatetimeIndex):
            return pd.DatetimeIndex([last + step * (i + 1) for i in range(n)])
        return pd.Index([last + step * (i + 1) for i in range(n)])
    except Exception:
        return pd.Index(np.arange(n))


def _forecast_x(hist_x, pred_df):
    """X axis for the forecast segment.

    Uses the prediction's own timestamps when present and compatible with the
    history axis; otherwise continues history at the inferred bar interval
    (exactly what the upstream webui does).
    """
    n = len(pred_df)
    own = pred_df["timestamps"]
    if own.notna().all():
        own_idx = pd.DatetimeIndex(own)
        if hist_x is None or len(hist_x) == 0 or isinstance(hist_x, pd.DatetimeIndex):
            return own_idx
    return _continue_axis(hist_x, n)


def _boundary(hist_x, pred_x):
    """Midpoint between the last historical bar and the first forecast bar."""
    try:
        if hist_x is not None and len(hist_x) and pred_x is not None and len(pred_x):
            return hist_x[-1] + (pred_x[0] - hist_x[-1]) / 2
        if hist_x is not None and len(hist_x):
            return hist_x[-1]
        if pred_x is not None and len(pred_x):
            return pred_x[0]
    except Exception:
        pass
    return None


def _add_now_divider(fig, x):
    """Dashed vertical divider labeled NOW at the forecast boundary."""
    if x is None:
        return
    fig.add_shape(
        type="line", xref="x", yref="paper",
        x0=x, x1=x, y0=0, y1=1,
        line=dict(color=DIVIDER, width=1, dash="dash"),
    )
    fig.add_annotation(
        x=x, y=1.0, xref="x", yref="paper",
        text="NOW", showarrow=False,
        yanchor="bottom", yshift=2,
        font=dict(family=FONT_FAMILY, size=10, color=GOLD),
    )


def _clean_paths(sample_paths):
    """Coerce sample_paths (list of close arrays / 2-D array) to a 2-D float
    matrix truncated to the shortest path. Returns None when unusable."""
    if sample_paths is None:
        return None
    try:
        if isinstance(sample_paths, np.ndarray):
            paths = [sample_paths] if sample_paths.ndim == 1 else list(sample_paths)
        elif isinstance(sample_paths, (list, tuple)):
            paths = list(sample_paths)
        else:
            paths = [sample_paths]
        rows = []
        for p in paths:
            arr = np.asarray(p, dtype="float64").ravel()
            arr = arr[np.isfinite(arr)] if np.isnan(arr).all() else arr
            if arr.size:
                rows.append(arr)
        if not rows:
            return None
        n = min(len(r) for r in rows)
        if n == 0:
            return None
        return np.vstack([r[:n] for r in rows])
    except Exception:
        return None


def _series(values):
    """1-D float array or None."""
    if values is None:
        return None
    try:
        arr = np.asarray(pd.to_numeric(pd.Series(values), errors="coerce"), dtype="float64")
        return arr if arr.size and np.isfinite(arr).any() else None
    except Exception:
        return None


def _title(*parts):
    return "  ·  ".join(str(p).upper() for p in parts if p)


# ---------------------------------------------------------------------------
# 1. Forecast candlestick chart
# ---------------------------------------------------------------------------
def kronos_forecast_chart(hist_df, pred_df, sample_paths=None,
                          symbol="", interval="", show_volume=True):
    """History + Kronos forecast candlesticks in the ZERO terminal style.

    Parameters
    ----------
    hist_df, pred_df : pandas.DataFrame or None
        Columns ``['timestamps','open','high','low','close','volume']``.
        ``pred_df`` may carry its timestamps in the index instead — both are
        handled. Missing forecast timestamps are synthesized by continuing
        history at the inferred bar interval (upstream webui behavior).
    sample_paths : list of array-like, optional
        Sampled forecast *close* paths. With >=4 paths the uncertainty band
        spans p10–p90; with fewer it spans min–max. Without samples a subtle
        band is drawn from the forecast candles' high/low range.
    symbol, interval : str
        Cosmetic labels for the title.
    show_volume : bool
        Adds a volume subplot (row heights ~0.75/0.25, shared x): history
        bars tinted green/red by candle direction, forecast bars muted gold.

    Returns
    -------
    plotly.graph_objects.Figure — never raises; empty/None inputs yield an
    annotated empty dark figure.
    """
    try:
        hist = _coerce_ohlcv(hist_df)
        pred = _coerce_ohlcv(pred_df)
        if hist is None and pred is None:
            return _empty_fig("KRONOS — NO FORECAST DATA")

        hist_x = _x_axis(hist) if hist is not None else None
        pred_x = _forecast_x(hist_x, pred) if pred is not None else None

        has_vol = bool(show_volume) and any(
            df is not None and df["volume"].notna().any() for df in (hist, pred)
        )
        rows = 2 if has_vol else 1
        fig = make_subplots(
            rows=rows, cols=1, shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=[0.75, 0.25] if has_vol else None,
        )

        # --- uncertainty band (under the candles) --------------------------
        band_label = None
        if pred is not None:
            paths = _clean_paths(sample_paths)
            if paths is not None:
                n = min(paths.shape[1], len(pred_x))
                bx = list(pred_x[:n])
                if paths.shape[0] >= 4:
                    lo = np.nanpercentile(paths[:, :n], 10, axis=0)
                    hi = np.nanpercentile(paths[:, :n], 90, axis=0)
                    band_label = "UNCERTAINTY p10–p90"
                else:
                    lo = np.nanmin(paths[:, :n], axis=0)
                    hi = np.nanmax(paths[:, :n], axis=0)
                    band_label = "UNCERTAINTY min–max"
            else:
                bx = list(pred_x)
                lo = pred["low"].to_numpy(dtype="float64")
                hi = pred["high"].to_numpy(dtype="float64")
                band_label = "FORECAST RANGE"
            fig.add_trace(go.Scatter(
                x=bx, y=hi, mode="lines",
                line=dict(width=0), hoverinfo="skip",
                showlegend=False, name="",
            ), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=bx, y=lo, mode="lines",
                line=dict(width=0), fill="tonexty", fillcolor=BAND_FILL,
                hoverinfo="skip", name=band_label, showlegend=True,
            ), row=1, col=1)

        # --- history candles (ZERO green/red) ------------------------------
        if hist is not None:
            fig.add_trace(go.Candlestick(
                x=list(hist_x),
                open=hist["open"], high=hist["high"],
                low=hist["low"], close=hist["close"],
                name="HISTORY",
                increasing=dict(line=dict(color=GREEN, width=1), fillcolor=GREEN),
                decreasing=dict(line=dict(color=RED, width=1), fillcolor=RED),
                whiskerwidth=0.6,
            ), row=1, col=1)

        # --- forecast candles (gold/yellow pair) ----------------------------
        if pred is not None:
            fig.add_trace(go.Candlestick(
                x=list(pred_x),
                open=pred["open"], high=pred["high"],
                low=pred["low"], close=pred["close"],
                name="KRONOS FORECAST",
                increasing=dict(line=dict(color=GOLD, width=1), fillcolor=GOLD),
                decreasing=dict(line=dict(color=YELLOW, width=1), fillcolor=YELLOW),
                whiskerwidth=0.6, opacity=0.9,
            ), row=1, col=1)

        # --- connector: last hist close -> first pred close ----------------
        if hist is not None and pred is not None:
            fig.add_trace(go.Scatter(
                x=[hist_x[-1], pred_x[0]],
                y=[float(hist["close"].iloc[-1]), float(pred["close"].iloc[0])],
                mode="lines",
                line=dict(color=GOLD, width=1.2, dash="dot"),
                hoverinfo="skip", showlegend=False, name="",
            ), row=1, col=1)

        # --- NOW divider ----------------------------------------------------
        _add_now_divider(fig, _boundary(hist_x, pred_x))

        # --- volume subplot --------------------------------------------------
        if has_vol:
            if hist is not None and hist["volume"].notna().any():
                v_colors = [
                    GREEN_A if c >= o else RED_A
                    for o, c in zip(hist["open"], hist["close"])
                ]
                fig.add_trace(go.Bar(
                    x=list(hist_x), y=hist["volume"],
                    marker_color=v_colors, marker_line_width=0,
                    name="VOLUME", showlegend=False,
                ), row=2, col=1)
            if pred is not None and pred["volume"].notna().any():
                fig.add_trace(go.Bar(
                    x=list(pred_x), y=pred["volume"],
                    marker_color=GOLD_A, marker_line_width=0,
                    name="FORECAST VOL", showlegend=False,
                ), row=2, col=1)
            fig.update_yaxes(title_text=None, row=2, col=1)

        _apply_dark_layout(
            fig,
            title=_title(symbol, interval, "KRONOS FORECAST"),
            height=560 if has_vol else 480,
            uirevision=_title(symbol, interval, "KRONOS FORECAST") or "kronos-forecast",
        )
        fig.update_layout(bargap=0.15)
        if pred is None:
            fig.add_annotation(
                x=0.99, y=0.98, xref="paper", yref="paper",
                text="NO FORECAST — SHOWING HISTORY", showarrow=False,
                xanchor="right", font=dict(size=10, color=MUTED),
            )
        return fig
    except Exception as exc:  # pragma: no cover — hard never-raise guarantee
        return _empty_fig(f"KRONOS CHART ERROR — {type(exc).__name__}")


# ---------------------------------------------------------------------------
# 2. Sampled close-paths 'spaghetti' chart
# ---------------------------------------------------------------------------
def kronos_close_paths_chart(hist_df, sample_paths, pred_timestamps=None, symbol=""):
    """'Spaghetti' plot of Monte-Carlo forecast close paths.

    Last ~100 historical closes as a solid green line, every sampled forecast
    close path as a thin translucent gold line, and the cross-path mean as a
    bold gold line — same ZERO dark theme as :func:`kronos_forecast_chart`.

    Parameters
    ----------
    hist_df : pandas.DataFrame or None
        Same OHLCV schema as the forecast chart (only ``close`` is used).
    sample_paths : list of array-like (or 2-D array)
        One close array per sampled forecast path.
    pred_timestamps : array-like, optional
        X values for the forecast paths; synthesized from the history's bar
        interval when omitted or unparseable.
    symbol : str
        Cosmetic label for the title.

    Returns
    -------
    plotly.graph_objects.Figure — never raises.
    """
    try:
        hist = _coerce_ohlcv(hist_df)
        paths = _clean_paths(sample_paths)
        if hist is None and paths is None:
            return _empty_fig("KRONOS — NO SAMPLE PATHS")

        fig = go.Figure()

        hist_x = None
        if hist is not None:
            tail = hist.tail(100)
            hist_x = _x_axis(hist)[-len(tail):]
            fig.add_trace(go.Scatter(
                x=list(hist_x), y=tail["close"],
                mode="lines", name="HISTORY",
                line=dict(color=GREEN, width=1.8),
                hovertemplate="%{y:.4f}<extra>HISTORY</extra>",
            ))

        pred_x = None
        if paths is not None:
            n = paths.shape[1]
            # Resolve forecast x axis: explicit -> parse; else continue hist.
            if pred_timestamps is not None:
                try:
                    raw = pd.Series(list(pred_timestamps))
                    if len(raw) and pd.api.types.is_numeric_dtype(raw):
                        # Numeric x values are kept positional, not epoch-parsed.
                        pred_x = pd.Index(raw.to_numpy())
                    else:
                        px = pd.to_datetime(raw, errors="coerce")
                        pred_x = pd.DatetimeIndex(px) if px.notna().all() else None
                except Exception:
                    pred_x = None
                if pred_x is not None and len(pred_x) < n:
                    n = len(pred_x)
            if pred_x is None:
                pred_x = _continue_axis(hist_x, n)
            pred_x = pred_x[:n]

            for i, row in enumerate(paths):
                fig.add_trace(go.Scatter(
                    x=list(pred_x), y=row[:n],
                    mode="lines",
                    line=dict(color=PATH_LINE, width=1),
                    name="SAMPLED PATHS",
                    legendgroup="paths",
                    showlegend=(i == 0),
                    hoverinfo="skip",
                ))
            mean_path = np.nanmean(paths[:, :n], axis=0)
            fig.add_trace(go.Scatter(
                x=list(pred_x), y=mean_path,
                mode="lines", name="MEAN FORECAST",
                line=dict(color=GOLD, width=2.6),
                hovertemplate="%{y:.4f}<extra>MEAN FORECAST</extra>",
            ))
            # Connector from last hist close to first mean point.
            if hist is not None and len(pred_x):
                fig.add_trace(go.Scatter(
                    x=[hist_x[-1], pred_x[0]],
                    y=[float(hist["close"].iloc[-1]), float(mean_path[0])],
                    mode="lines",
                    line=dict(color=GOLD, width=1.2, dash="dot"),
                    hoverinfo="skip", showlegend=False, name="",
                ))

        _add_now_divider(fig, _boundary(hist_x, pred_x))
        _apply_dark_layout(
            fig,
            title=_title(symbol, "KRONOS CLOSE PATHS"),
            height=420,
            uirevision=_title(symbol, "KRONOS CLOSE PATHS") or "kronos-paths",
        )
        if paths is None:
            fig.add_annotation(
                x=0.99, y=0.98, xref="paper", yref="paper",
                text="NO SAMPLE PATHS", showarrow=False,
                xanchor="right", font=dict(size=10, color=MUTED),
            )
        return fig
    except Exception as exc:  # pragma: no cover
        return _empty_fig(f"KRONOS CHART ERROR — {type(exc).__name__}")


# ---------------------------------------------------------------------------
# 3. Backtest chart
# ---------------------------------------------------------------------------
def kronos_backtest_chart(result):
    """Backtest review: prediction accuracy on top, equity curves below.

    Parameters
    ----------
    result : dict or None
        Expected schema (every key optional — missing/short/None entries are
        handled gracefully and simply omitted)::

            {
                'dates':           array-like of timestamps (x axis),
                'actual_close':    array-like — realized close prices,
                'predicted_close': array-like — Kronos predicted closes,
                'strategy_curve':  array-like — cumulative strategy equity,
                'benchmark_curve': array-like — cumulative buy & hold equity,
            }

        Series lengths may differ; each trace is truncated against the date
        axis independently. When ``dates`` is missing a positional index is
        used.

    Returns
    -------
    plotly.graph_objects.Figure — top panel overlays predicted vs actual
    close, bottom panel overlays cumulative strategy vs buy & hold. Never
    raises; ``None`` / empty / unusable input yields an annotated empty dark
    figure.
    """
    try:
        if not isinstance(result, dict) or not result:
            return _empty_fig("KRONOS — NO BACKTEST DATA")

        actual = _series(result.get("actual_close"))
        predicted = _series(result.get("predicted_close"))
        strategy = _series(result.get("strategy_curve"))
        benchmark = _series(result.get("benchmark_curve"))
        if all(s is None for s in (actual, predicted, strategy, benchmark)):
            return _empty_fig("KRONOS — NO BACKTEST DATA")

        # Date axis (optional).
        dates = None
        raw_dates = result.get("dates")
        if raw_dates is not None:
            try:
                parsed = pd.to_datetime(pd.Series(list(raw_dates)), errors="coerce")
                if parsed.notna().all() and len(parsed):
                    dates = pd.DatetimeIndex(parsed)
            except Exception:
                dates = None

        def _xy(arr):
            """Pair a series with the date axis, truncating to the overlap."""
            if arr is None:
                return None, None
            if dates is not None:
                n = min(len(dates), len(arr))
                return list(dates[:n]), arr[:n]
            return list(range(len(arr))), arr

        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            vertical_spacing=0.08,
            row_heights=[0.55, 0.45],
            subplot_titles=("PREDICTED VS ACTUAL CLOSE", "STRATEGY VS BUY & HOLD"),
        )

        # --- top: predicted vs actual close --------------------------------
        x, y = _xy(actual)
        if x is not None:
            fig.add_trace(go.Scatter(
                x=x, y=y, mode="lines", name="ACTUAL CLOSE",
                line=dict(color="#e8e8e8", width=1.6),
                hovertemplate="%{y:.4f}<extra>ACTUAL</extra>",
            ), row=1, col=1)
        x, y = _xy(predicted)
        if x is not None:
            fig.add_trace(go.Scatter(
                x=x, y=y, mode="lines", name="KRONOS PREDICTED",
                line=dict(color=GOLD, width=1.6, dash="dash"),
                hovertemplate="%{y:.4f}<extra>PREDICTED</extra>",
            ), row=1, col=1)

        # --- bottom: equity curves ------------------------------------------
        x, y = _xy(strategy)
        if x is not None:
            fig.add_trace(go.Scatter(
                x=x, y=y, mode="lines", name="STRATEGY",
                line=dict(color=GREEN, width=1.8),
                fill="tozeroy", fillcolor="rgba(0,255,136,0.06)",
                hovertemplate="%{y:.4f}<extra>STRATEGY</extra>",
            ), row=2, col=1)
        x, y = _xy(benchmark)
        if x is not None:
            fig.add_trace(go.Scatter(
                x=x, y=y, mode="lines", name="BUY & HOLD",
                line=dict(color=MUTED, width=1.4, dash="dash"),
                hovertemplate="%{y:.4f}<extra>BUY & HOLD</extra>",
            ), row=2, col=1)

        if not fig.data:
            return _empty_fig("KRONOS — NO BACKTEST DATA")

        _apply_dark_layout(
            fig,
            title=_title("KRONOS BACKTEST"),
            height=520,
            uirevision="kronos-backtest",
        )
        # Restyle the subplot titles to the muted terminal caption look.
        for ann in fig.layout.annotations:
            if ann.text in ("PREDICTED VS ACTUAL CLOSE", "STRATEGY VS BUY & HOLD"):
                ann.font = dict(family=FONT_FAMILY, size=10, color=MUTED)
        return fig
    except Exception as exc:  # pragma: no cover
        return _empty_fig(f"KRONOS CHART ERROR — {type(exc).__name__}")


# ---------------------------------------------------------------------------
# 4. Model status badge (HTML snippet for st.markdown(..., unsafe_allow_html))
# ---------------------------------------------------------------------------
def kronos_status_badge_html(status):
    """Inline-styled status pill for the Kronos service.

    Parameters
    ----------
    status : dict or None
        Service status flags, e.g. ``{'torch_available': True,
        'model_loaded': False, 'device': 'cpu', ...}``.

    Rules
    -----
    * ``model_loaded``     -> ONLINE  (ZERO green ``#00ff88``)
    * ``torch_available``  -> STANDBY (gold ``#D4AF37``)
    * otherwise            -> OFFLINE (ZERO red ``#E50914``)

    Returns
    -------
    str — a self-contained ``<span>`` (matches the pill styling used across
    the ZERO terminal) safe to pass to ``st.markdown(..., unsafe_allow_html=True)``.
    Never raises; malformed input degrades to OFFLINE.
    """
    try:
        s = status if isinstance(status, dict) else {}
        if s.get("model_loaded"):
            label, color = "ONLINE", GREEN
        elif s.get("torch_available"):
            label, color = "STANDBY", GOLD
        else:
            label, color = "OFFLINE", RED

        # Tooltip: flat key=value summary, sanitized for the title attribute.
        try:
            detail = " | ".join(f"{k}={v}" for k, v in list(s.items())[:8])
        except Exception:
            detail = ""
        detail = (detail.replace("&", "&amp;").replace('"', "&quot;")
                        .replace("<", "&lt;").replace(">", "&gt;"))

        dot = (
            f"<span style='display:inline-block;width:7px;height:7px;"
            f"border-radius:50%;background:{color};box-shadow:0 0 6px {color};'></span>"
        )
        return (
            f'<span title="{detail}" style="display:inline-flex;align-items:center;'
            f"gap:7px;font-family:'Outfit',sans-serif;font-size:0.66rem;font-weight:700;"
            f"letter-spacing:0.12em;color:{color};background:rgba(10,10,10,0.85);"
            f"border:1px solid #222;border-radius:20px;padding:4px 12px;"
            f'white-space:nowrap;">{dot}KRONOS · {label}</span>'
        )
    except Exception:  # pragma: no cover
        return (
            "<span style=\"display:inline-flex;align-items:center;gap:7px;"
            "font-family:'Outfit',sans-serif;font-size:0.66rem;font-weight:700;"
            "letter-spacing:0.12em;color:#E50914;background:rgba(10,10,10,0.85);"
            "border:1px solid #222;border-radius:20px;padding:4px 12px;"
            "white-space:nowrap;\">KRONOS · OFFLINE</span>"
        )


__all__ = [
    "kronos_forecast_chart",
    "kronos_close_paths_chart",
    "kronos_backtest_chart",
    "kronos_status_badge_html",
    "KRONOS_PLOTLY_CONFIG",
]

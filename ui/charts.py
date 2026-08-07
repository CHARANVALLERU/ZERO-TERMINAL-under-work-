import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# ZERO Plotly palette LOCK — black / red / white / gold / yellow / green only.
# No Plotly default blues, no cyan accents. Kronos charts mirror these tokens.
# ---------------------------------------------------------------------------
BLACK = "#000000"
BG_ELEV = "#0a0a0a"
RED = "#E50914"
RED_ALT = "#ff4b4b"
WHITE = "#ffffff"
GOLD = "#D4AF37"
YELLOW = "#FFD600"
GREEN = "#00ff88"
MUTED = "#888888"
AXIS = "#333333"
TICK = "#444444"
PAPER_BG = "rgba(0,0,0,0)"
PLOT_BG = "rgba(0,0,0,0)"
FONT_FAMILY = "Outfit"

# Kill default Plotly colorway (blue-first) on every figure from this module.
_ZERO_COLORWAY = (RED, GOLD, GREEN, YELLOW, WHITE, RED_ALT, MUTED)

# Sign thresholds for the market-mood pulse. Anything inside +/- BUY_THRESHOLD
# is treated as neutral so the sign does not flicker on noise.
_BUY_THRESHOLD = 0.15


def _hoverlabel():
    return dict(
        bgcolor="rgba(10,10,10,0.95)",
        bordercolor=GOLD,
        font=dict(family=FONT_FAMILY, color=WHITE, size=11),
    )


def _apply_zero_plotly_layout(fig, **kwargs):
    """Shared layout that overrides Plotly blue defaults."""
    base = dict(
        paper_bgcolor=PAPER_BG,
        plot_bgcolor=PLOT_BG,
        font=dict(color=WHITE, family=FONT_FAMILY),
        colorway=list(_ZERO_COLORWAY),
        hoverlabel=_hoverlabel(),
        # Neutral template — no plotly / plotly_dark blue accents.
        template="none",
    )
    base.update(kwargs)
    fig.update_layout(**base)
    return fig


# Pure-function helper so it is unit-testable in tests/test_action_sign.py
# without a Streamlit runtime.
def action_sign(score):
    """Return ('BUY'|'SELL'|'NEUTRAL', arrow, colour) for a sentiment score
    in [-1, 1]. Symmetric thresholds so a value just above zero is still
    neutral, not 'BUY'."""
    try:
        s = float(score or 0.0)
    except (TypeError, ValueError):
        s = 0.0
    if s > _BUY_THRESHOLD:
        return "BUY", "\u25b2", GREEN
    if s < -_BUY_THRESHOLD:
        return "SELL", "\u25bc", RED
    return "NEUTRAL", "\u2022", GOLD


def sentiment_gauge_chart(score):
    """Circular gauge for news sentiment.

    The figure carries the numeric dial; the BUY/SELL/NEUTRAL sign is
    rendered separately by the caller so it can sit cleanly under the
    gauge with its own animation.
    """
    # Score is -1 to 1, convert to 0-100 for gauge
    value = (score + 1) * 50

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        domain={"x": [0, 1], "y": [0, 1]},
        title={"text": "Market Sentiment Pulse", "font": {"size": 16, "color": GOLD}},
        number={"font": {"color": WHITE}},
        gauge={
            "axis": {
                "range": [0, 100],
                "tickwidth": 1,
                "tickcolor": TICK,
                "tickfont": {"color": MUTED},
            },
            "bar": {"color": RED},
            "bgcolor": PAPER_BG,
            "borderwidth": 2,
            "bordercolor": AXIS,
            "steps": [
                {"range": [0, 30], "color": "rgba(229, 9, 20, 0.12)"},
                {"range": [30, 70], "color": "rgba(255, 214, 0, 0.12)"},
                {"range": [70, 100], "color": "rgba(0, 255, 136, 0.12)"},
            ],
            "threshold": {
                "line": {"color": WHITE, "width": 4},
                "thickness": 0.75,
                "value": value,
            },
        },
    ))

    _apply_zero_plotly_layout(
        fig,
        margin=dict(l=20, r=20, t=50, b=20),
        height=250,
        transition=dict(duration=420, easing="cubic-in-out"),
    )
    return fig


def ohlc_range_chart(data):
    """Range visualization for predicted High/Low/Open."""
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=[data["pred_low"], data["pred_high"]],
        y=[0, 0],
        mode="lines+markers",
        line=dict(color=AXIS, width=10),
        marker=dict(size=20, color=[RED_ALT, GREEN], line=dict(width=0)),
        name="Range",
        hoverlabel=_hoverlabel(),
    ))

    fig.add_trace(go.Scatter(
        x=[data["pred_open"]],
        y=[0],
        mode="markers",
        marker=dict(size=25, color=GOLD, symbol="diamond", line=dict(width=0)),
        name="Opening",
        hoverlabel=_hoverlabel(),
    ))

    _apply_zero_plotly_layout(
        fig,
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            color=MUTED,
            tickfont=dict(color=MUTED),
            linecolor=AXIS,
        ),
        yaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            color=MUTED,
            linecolor=AXIS,
        ),
        margin=dict(l=10, r=10, t=10, b=10),
        height=100,
        showlegend=False,
    )
    return fig

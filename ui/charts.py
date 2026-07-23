import plotly.graph_objects as go
import streamlit as st

# Sign thresholds for the market-mood pulse. Anything inside ±BUY_THRESHOLD
# is treated as neutral so the sign doesn't flicker on noise.
_BUY_THRESHOLD = 0.15

# Pure-function helper so it's unit-testable in tests/test_action_sign.py
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
        return "BUY", "▲", "#00ff88"
    if s < -_BUY_THRESHOLD:
        return "SELL", "▼", "#E50914"
    return "NEUTRAL", "•", "#D4AF37"


def sentiment_gauge_chart(score):
    """Circular gauge for news sentiment.

    The figure carries the numeric dial; the BUY/SELL/NEUTRAL sign is
    rendered separately by the caller so it can sit cleanly under the
    gauge with its own animation.
    """
    # Score is -1 to 1, convert to 0-100 for gauge
    value = (score + 1) * 50

    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = value,
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': "Market Sentiment Pulse", 'font': {'size': 16, 'color': "#D4AF37"}},
        number = {'font': {'color': "#ffffff"}},
        gauge = {
            'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "#444"},
            'bar': {'color': "#E50914"},
            'bgcolor': "rgba(0,0,0,0)",
            'borderwidth': 2,
            'bordercolor': "#333",
            'steps': [
                {'range': [0, 30], 'color': 'rgba(255, 0, 0, 0.1)'},
                {'range': [30, 70], 'color': 'rgba(255, 255, 0, 0.1)'},
                {'range': [70, 100], 'color': 'rgba(0, 255, 0, 0.1)'}
            ],
            'threshold': {
                'line': {'color': "white", 'width': 4},
                'thickness': 0.75,
                'value': value
            }
        }
    ))

    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font={'color': "#ffffff", 'family': "Outfit"},
        margin=dict(l=20, r=20, t=50, b=20),
        height=250,
        # Smoother dial sweep — was a hard 0-duration cut, now eased.
        transition=dict(duration=420, easing='cubic-in-out'),
    )
    return fig

def ohlc_range_chart(data):
    """Range visualization for predicted High/Low/Open."""
    fig = go.Figure()
    
    # Target Range
    fig.add_trace(go.Scatter(
        x=[data['pred_low'], data['pred_high']],
        y=[0, 0],
        mode='lines+markers',
        line=dict(color='#333', width=10),
        marker=dict(size=20, color=['#ff4b4b', '#00ff88']),
        name="Range"
    ))
    
    # Opening Point
    fig.add_trace(go.Scatter(
        x=[data['pred_open']],
        y=[0],
        mode='markers',
        marker=dict(size=25, color='#D4AF37', symbol='diamond'),
        name="Opening"
    ))
    
    fig.update_layout(
        xaxis=dict(showgrid=False, zeroline=False, color="#888"),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=10, r=10, t=10, b=10),
        height=100,
        showlegend=False
    )
    return fig

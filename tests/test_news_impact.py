"""
Tests for the real-time news-impact engine and breaking-news monitor.

Standalone:  python tests/test_news_impact.py    (numpy-free, no network)
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.news_impact import assess, classify, aggregate_impact, summarize_alert  # noqa: E402


def test_negated_peace_deal_is_bearish():
    """The headline the user cited: a collapsing peace deal must read BEARISH
    and be high-impact, not bullish."""
    a = assess("Breaking: Trump says the Iran peace deal is off, tensions escalate")
    assert a["direction"] == "BEARISH", a
    assert a["category"] == "geopolitical"
    assert a["is_high_impact"] is True
    assert a["per_index"]["NIFTY 50"]["move_pct"] < 0


def test_positive_it_news_is_bullish_and_sector_tilted():
    """IT milestone: bullish, and it should move Nifty/Sensex more than Bank Nifty."""
    a = assess("Indian IT sector hits record export milestone, Infosys TCS rally")
    assert a["direction"] == "BULLISH"
    assert a["category"] == "sector_it"
    nifty = a["per_index"]["NIFTY 50"]["move_pct"]
    banknifty = a["per_index"]["BANKNIFTY"]["move_pct"]
    assert nifty > banknifty  # IT barely touches banks


def test_rate_news_tilts_banknifty():
    a = assess("RBI unexpectedly cuts repo rate by 50 bps to boost growth")
    assert a["category"] == "monetary_policy"
    assert a["direction"] == "BULLISH"
    # Bank Nifty is the most rate-sensitive → larger move than Nifty.
    assert abs(a["per_index"]["BANKNIFTY"]["move_pct"]) >= abs(a["per_index"]["NIFTY 50"]["move_pct"])


def test_neutral_headline_no_alert():
    a = assess("Company reports quarterly earnings in line with estimates")
    assert a["direction"] == "NEUTRAL"
    assert a["is_high_impact"] is False
    assert a["impact_score"] == 0.0 or a["impact_score"] < 45


def test_move_is_clamped():
    a = assess("nuclear war invasion missile attack crash collapse catastrophe default")
    for idx in ("NIFTY 50", "BANKNIFTY", "SENSEX"):
        assert -2.8 <= a["per_index"][idx]["move_pct"] <= 2.8


def test_classify_priorities():
    assert classify("war and missiles over the border")[0] == "geopolitical"
    assert classify("fed rate hike cpi inflation")[0] == "monetary_policy"


def test_points_scale_with_index_level():
    """A given % move should be more points on Sensex than Nifty (higher level)."""
    a = assess("Breaking: markets crash on recession fears, selloff deepens")
    npts = abs(a["per_index"]["NIFTY 50"]["move_points"])
    spts = abs(a["per_index"]["SENSEX"]["move_points"])
    assert spts > npts


def test_aggregate_impact_blends():
    shocks = [
        assess("Iran peace deal collapses, war fears escalate"),
        assess("Global markets selloff on recession fears"),
    ]
    agg = aggregate_impact(shocks)
    assert agg["NIFTY 50"]["move_pct"] < 0
    for idx in ("NIFTY 50", "BANKNIFTY", "SENSEX"):
        assert -2.8 <= agg[idx]["move_pct"] <= 2.8


def test_summary_string():
    s = summarize_alert(assess("Iran peace deal is off, tensions escalate"))
    assert "BEARISH" in s and "Nifty" in s


def test_monitor_dedup_offline():
    """The monitor must alert once, then not re-alert the same story."""
    import data.market_news as mn
    mn.get_global_news = lambda: [
        {"title": "Iran peace deal is off, war fears escalate", "source": "R"},
    ]
    from data import news_monitor as nm
    nm.reset_seen()
    first = nm.check_breaking()
    second = nm.check_breaking()
    assert len(first["breaking"]) == 1
    assert len(second["breaking"]) == 0
    nm.reset_seen()


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn(); print(f"  PASS  {fn.__name__}"); passed += 1
        except AssertionError as e:
            print(f"  FAIL  {fn.__name__}: {e}")
        except Exception as e:
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(fns)} tests passed")
    return passed == len(fns)


if __name__ == "__main__":
    raise SystemExit(0 if _run_all() else 1)

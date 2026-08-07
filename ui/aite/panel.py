"""
ZERO AITE — Streamlit control panel.

Public entry: ``render_aite_panel()``.

Layout:
  1. Top — 3D Obsidian-like bot graph (gold dots / red edges / death blast)
  2. Mid — backtest flow (~40 lines) | success table
  3. Logs — bots / trades / activity from db/aite
  4. Agent automation (Notion-like)
  5. Controls — fund, daemon, breed/exam, squad, paper deploy, idea→agent, brief

All engine imports are lazy with try/except + mock fallbacks.
Does NOT touch app.py — merge agent wires the tab.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from ui.aite.styles import (
    CRIMSON, GOLD, NEON, CYAN, MUTE,
    inject_aite_styles, status_pill,
)
from ui.aite.graph_3d import render_bot_graph_3d
from ui.aite.backtest_flow import render_backtest_flow
from ui.aite.agent_viz import render_agent_automation


# ── Lazy engine accessors (never raise) ─────────────────────────────────────

def _store():
    try:
        from engine.aite import store
        return store
    except Exception:
        return None


def _cfg():
    try:
        from engine.aite import config as cfg
        return cfg
    except Exception:
        return None


def _get_service():
    try:
        from engine.aite import get_aite_service
        return get_aite_service()
    except Exception:
        return None


def _daemon_mod():
    try:
        from engine.aite import daemon
        return daemon
    except Exception:
        return None


def _load_bots() -> List[Dict[str, Any]]:
    store = _store()
    if store:
        try:
            return list(store.load_bots() or [])
        except Exception:
            pass
    return []


def _load_daemon() -> Dict[str, Any]:
    store = _store()
    if store:
        try:
            return dict(store.load_daemon_state() or {})
        except Exception:
            pass
    return {"running": False, "ticks": 0, "started_at": None, "last_tick": None}


def _load_fund() -> Dict[str, Any]:
    store = _store()
    cfg = _cfg()
    default = float(getattr(cfg, "DEFAULT_PAPER_FUND", 1_000_000)) if cfg else 1_000_000.0
    if store:
        try:
            return dict(store.load_fund() or {})
        except Exception:
            pass
    return {"paper_fund": default, "cash": default, "equity": default, "currency": "INR"}


def _load_portfolio() -> Dict[str, Any]:
    store = _store()
    if store:
        try:
            return dict(store.load_portfolio() or {})
        except Exception:
            pass
    return {"bot_ids": [], "allocations": {}, "killed": []}


def _load_trades(limit: int = 100) -> List[Dict[str, Any]]:
    store = _store()
    if store:
        try:
            return list(store.load_trades(limit=limit) or [])
        except Exception:
            pass
    return []


def _load_logs(limit: int = 120) -> List[Dict[str, Any]]:
    store = _store()
    if store:
        try:
            return list(store.load_logs(limit=limit) or [])
        except Exception:
            pass
    return []


def _load_exams() -> List[Dict[str, Any]]:
    store = _store()
    if not store:
        return []
    try:
        cfg = _cfg()
        path = getattr(cfg, "EXAM_CACHE_PATH", None) if cfg else None
        if path:
            data = store.read_json(path, {})
            if isinstance(data, dict):
                exams = data.get("exams") or data.get("results") or []
                if isinstance(exams, list):
                    return exams
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def _log_ui(level: str, message: str, **extra) -> None:
    store = _store()
    if store:
        try:
            store.log_event(level, message, **extra)
            return
        except Exception:
            pass
    # Session fallback
    buf = st.session_state.setdefault("_aite_ui_logs", [])
    buf.append({"ts": time.time(), "level": level, "message": message, **extra})


# ── Control actions ─────────────────────────────────────────────────────────

def _set_fund(amount: float) -> str:
    try:
        from engine.aite.paper_fund import get_paper_fund
        result = get_paper_fund().set_fund_size(float(amount), reset_positions=True)
        if result.get("ok"):
            return f"Fund set to ₹{float(amount):,.0f}"
        return f"Fund save failed: {result.get('error') or 'unknown'}"
    except Exception as exc:
        store = _store()
        if store:
            try:
                fund = store.load_fund()
                fund["paper_fund"] = float(amount)
                fund["cash"] = float(amount)
                fund["equity"] = float(amount)
                store.save_fund(fund)
                store.log_event("INFO", f"Paper fund set to ₹{amount:,.0f}")
                return f"Fund set to ₹{amount:,.0f} (store fallback)"
            except Exception as exc2:
                return f"Fund save failed: {exc2}"
        st.session_state["_aite_fund_override"] = float(amount)
        return f"Fund cached locally ₹{amount:,.0f} ({exc})"


def _start_daemon() -> str:
    svc = _get_service()
    if svc and hasattr(svc, "start_daemon"):
        try:
            svc.start_daemon()
            return "Daemon started via service"
        except Exception as exc:
            return f"Service start failed: {exc}"
    dm = _daemon_mod()
    if dm:
        for name in ("start_daemon", "start", "run_daemon"):
            fn = getattr(dm, name, None)
            if callable(fn):
                try:
                    fn()
                    store = _store()
                    if store:
                        st_ = store.load_daemon_state()
                        st_["running"] = True
                        st_["started_at"] = time.time()
                        store.save_daemon_state(st_)
                    return f"Daemon started via daemon.{name}"
                except Exception as exc:
                    return f"daemon.{name} failed: {exc}"
    # Persist running flag for UI polling even without process
    store = _store()
    if store:
        try:
            st_ = store.load_daemon_state()
            st_["running"] = True
            st_["started_at"] = time.time()
            store.save_daemon_state(st_)
            store.log_event("INFO", "Daemon flag set running (background process may be pending)")
            return "Daemon flag → RUNNING (wire daemon module if needed)"
        except Exception as exc:
            return str(exc)
    return "Daemon module not available — flag not set"


def _stop_daemon() -> str:
    svc = _get_service()
    if svc and hasattr(svc, "stop_daemon"):
        try:
            svc.stop_daemon()
            return "Daemon stopped via service"
        except Exception as exc:
            return f"Service stop failed: {exc}"
    dm = _daemon_mod()
    if dm:
        for name in ("stop_daemon", "stop"):
            fn = getattr(dm, name, None)
            if callable(fn):
                try:
                    fn()
                    break
                except Exception:
                    pass
    store = _store()
    if store:
        try:
            st_ = store.load_daemon_state()
            st_["running"] = False
            store.save_daemon_state(st_)
            store.log_event("INFO", "Daemon stopped")
            return "Daemon stopped"
        except Exception as exc:
            return str(exc)
    return "Daemon stop flagged"


def _run_breed() -> str:
    svc = _get_service()
    if svc and hasattr(svc, "breed"):
        try:
            result = svc.breed()
            n = result.get("n_survivors") if isinstance(result, dict) else None
            return f"Breed complete — survivors={n}"
        except Exception as exc:
            return f"Service breed failed: {exc}"
    try:
        from engine.aite.breeding import breed_strategies
        with st.spinner("Breeding strategies…"):
            result = breed_strategies()
        store = _store()
        if store and isinstance(result, dict):
            survivors = result.get("survivors") or []
            if survivors:
                store.save_bots(survivors)
            store.log_event("INFO", f"Breed finished n={result.get('n_survivors')}")
        return (
            f"Breed OK — survivors={result.get('n_survivors')} "
            f"passed={result.get('n_passed')}"
        )
    except Exception as exc:
        return f"Breed unavailable: {exc}"


def _run_full_cycle(idea: Optional[str] = None) -> str:
    """End-to-end idea→breed→exam→survivors→deploy→monitor via pipeline."""
    svc = _get_service()
    idea = (idea or "").strip() or None
    try:
        with st.spinner("Running full AITE pipeline (idea→breed→exam→deploy→monitor)…"):
            if svc and hasattr(svc, "run_cycle"):
                result = svc.run_cycle(
                    idea=idea,
                    n_population=48,
                    n_survivors=20,
                    generations=1,
                    venue="paper",
                    deploy=True,
                    monitor=True,
                    persist=True,
                )
            else:
                from engine.aite.pipeline import run_pipeline
                result = run_pipeline(
                    idea=idea,
                    n_population=48,
                    n_survivors=20,
                    generations=1,
                    venue="paper",
                    deploy=True,
                    monitor=True,
                    persist=True,
                )
        if not isinstance(result, dict):
            return f"Pipeline returned unexpected: {result!r}"
        if not result.get("ok"):
            return f"Pipeline failed: {result.get('error') or 'unknown'}"
        return (
            f"Pipeline OK — passed_oos={result.get('n_passed')} "
            f"survivors={result.get('n_survivors')} "
            f"deployed={len(result.get('deployed') or [])} "
            f"bars={result.get('bar_counts')} "
            f"({result.get('elapsed_sec')}s)"
        )
    except Exception as exc:
        return f"Pipeline unavailable: {exc}"


def _run_exam_selected(bot_ids: List[str]) -> str:
    bots = _load_bots()
    if not bots:
        return "No bots to exam"
    selected = [b for b in bots if b.get("bot_id") in bot_ids] if bot_ids else bots[:5]
    try:
        from engine.aite.exam import run_exam, load_market_frame
        from engine.aite.models import BotGenome
        results = []
        with st.spinner(f"Examining {len(selected)} bots…"):
            frames: Dict[str, Any] = {}
            for raw in selected:
                g = BotGenome.from_dict(raw)
                if g.symbol not in frames:
                    frames[g.symbol] = load_market_frame(g.symbol)
                ex = run_exam(g, frames[g.symbol])
                results.append(ex.to_dict())
                raw["status"] = "alive" if ex.passed else "candidate"
        store = _store()
        if store:
            store.save_bots(bots)
            cfg = _cfg()
            if cfg and getattr(cfg, "EXAM_CACHE_PATH", None):
                store.write_json(cfg.EXAM_CACHE_PATH, {"exams": results, "ts": time.time()})
            store.log_event("INFO", f"Exam finished n={len(results)}")
        passed = sum(1 for r in results if r.get("passed"))
        st.session_state["_aite_last_exams"] = results
        return f"Exam done — {passed}/{len(results)} passed"
    except Exception as exc:
        return f"Exam failed: {exc}"


def _deploy_paper(bot_ids: List[str]) -> str:
    bots = _load_bots()
    ids = list(bot_ids) if bot_ids else [
        b.get("bot_id") for b in bots
        if str(b.get("status")) == "alive" and b.get("bot_id")
    ]
    ids = [str(x) for x in ids if x]
    if not ids:
        return "No alive bots to deploy"
    try:
        from engine.aite.deploy import deploy_bots
        # Ensure selected ids are on the portfolio book so deploy resolves them
        store = _store()
        if store:
            port = store.load_portfolio()
            existing = [str(x) for x in (port.get("bot_ids") or [])]
            for bid in ids:
                if bid not in existing:
                    existing.append(bid)
            port["bot_ids"] = existing
            store.save_portfolio(port)
        result = deploy_bots(ids, venue="paper", note="ui_deploy")
        if result.get("ok"):
            n = len(result.get("deployed") or [])
            return f"Deployed {n} bots → paper ({result.get('mode', 'sim')})"
        return f"Deploy failed: {result.get('error') or 'unknown'}"
    except Exception as exc:
        store = _store()
        if store:
            try:
                port = store.load_portfolio()
                port["bot_ids"] = ids
                store.save_portfolio(port)
                store.log_event("INFO", f"Paper deploy fallback {len(ids)} bots ({exc})")
                return f"Paper deploy flagged for {len(ids)} bots (fallback)"
            except Exception as exc2:
                return str(exc2)
        return f"Deploy failed: {exc}"


def _submit_idea(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return "Idea text empty"
    try:
        from engine.aite.idea_agent import queue_idea
        rec = queue_idea(text, enqueue_breed=True)
        genome = rec.get("genome") or {}
        name = genome.get("name") or genome.get("bot_id") or rec.get("idea_id")
        return f"Idea queued → {name} (breed job seeded)"
    except Exception as exc:
        _log_ui("WARN", f"queue_idea fail: {exc}")
    store = _store()
    if store:
        try:
            store.save_idea({"text": text, "ts": time.time(), "status": "queued"})
            store.log_event("INFO", f"Idea queued: {text[:80]}")
            return "Idea queued for breeding (fallback)"
        except Exception as exc2:
            return str(exc2)
    return "Idea stored in session only"


def _ask_brief(symbol: str) -> Dict[str, Any]:
    try:
        from engine.aite.brief import ask_brief
        return ask_brief(f"One-shot market brief for {symbol}")
    except Exception as exc:
        try:
            from engine.aite.brief import build_brief
            return build_brief(symbol)
        except Exception as exc2:
            return {
                "symbol": symbol,
                "verdict": "HOLD",
                "rationale": f"Brief unavailable: {exc2 or exc}",
                "price": 0, "momentum": 0, "drawdown": 0, "regime": "UNKNOWN",
            }


# ── Logs pane ───────────────────────────────────────────────────────────────

def _render_logs(
    bots: List[Dict[str, Any]],
    trades: List[Dict[str, Any]],
    logs: List[Dict[str, Any]],
) -> None:
    st.markdown(
        f"<div class='aite-label'>LOGS · BOTS / TRADES / ACTIVITY</div>",
        unsafe_allow_html=True,
    )
    t1, t2, t3 = st.tabs(["BOTS", "TRADES", "ACTIVITY"])
    with t1:
        if bots:
            rows = [{
                "Name": b.get("name"),
                "ID": b.get("bot_id"),
                "Symbol": b.get("symbol"),
                "Status": b.get("status"),
                "Style": b.get("style"),
                "Gen": b.get("generation"),
            } for b in bots]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=220)
        else:
            st.caption("No bots in db/aite yet — run Breed.")
    with t2:
        if trades:
            rows = [{
                "Strategy": t.get("bot_name") or t.get("strategy"),
                "Side": t.get("side"),
                "Entry": t.get("entry") or t.get("fill_price"),
                "Exit": t.get("exit"),
                "PnL%": t.get("pnl_pct"),
                "Mode": t.get("mode"),
                "Entry Time": t.get("entry_time"),
                "Exit Time": t.get("exit_time"),
            } for t in trades[-80:]]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=220)
        else:
            st.caption("No trades logged yet.")
    with t3:
        ui_logs = list(st.session_state.get("_aite_ui_logs") or [])
        merged = list(logs or []) + ui_logs
        if not merged:
            st.caption("No activity yet.")
        else:
            html = ["<div class='aite-log'>"]
            for row in merged[-100:]:
                lvl = str(row.get("level") or "INFO").lower()
                cls = "info" if lvl == "info" else ("warn" if lvl in ("warn", "warning") else ("error" if lvl == "error" else ""))
                ts = row.get("ts")
                try:
                    ts_s = time.strftime("%H:%M:%S", time.localtime(float(ts)))
                except Exception:
                    ts_s = "—"
                msg = str(row.get("message") or "")
                html.append(
                    f"<div class='aite-log-row {cls}'>"
                    f"<span class='ts'>[{ts_s}]</span> "
                    f"{lvl.upper()} · {_esc(msg)}</div>"
                )
            html.append("</div>")
            st.markdown("".join(html), unsafe_allow_html=True)


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ── Controls ────────────────────────────────────────────────────────────────

def _render_controls(bots: List[Dict[str, Any]], daemon: Dict[str, Any], fund: Dict[str, Any]) -> None:
    st.markdown(
        f"<div class='aite-label'>CONTROLS · FUND / DAEMON / BREED / DEPLOY / IDEA / BRIEF</div>",
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns([1.1, 1.0, 1.0, 1.2], gap="small")

    with c1:
        default_fund = float(fund.get("paper_fund") or st.session_state.get("_aite_fund_override") or 1_000_000)
        amount = st.number_input(
            "Paper fund (₹)",
            min_value=10_000.0,
            max_value=1_000_000_000.0,
            value=default_fund,
            step=50_000.0,
            key="aite_fund_input",
        )
        if st.button("SET FUND", key="aite_set_fund", width="stretch"):
            msg = _set_fund(float(amount))
            st.success(msg)
            _log_ui("INFO", msg)

    with c2:
        running = bool(daemon.get("running"))
        st.markdown(
            status_pill("DAEMON ON" if running else "DAEMON OFF", NEON if running else CRIMSON),
            unsafe_allow_html=True,
        )
        b_a, b_b = st.columns(2)
        with b_a:
            if st.button("START", key="aite_daemon_start", width="stretch", type="primary"):
                st.info(_start_daemon())
                st.rerun()
        with b_b:
            if st.button("STOP", key="aite_daemon_stop", width="stretch"):
                st.info(_stop_daemon())
                st.rerun()

    with c3:
        if st.button("FULL CYCLE", key="aite_full_cycle", width="stretch", type="primary"):
            idea_txt = str(st.session_state.get("aite_idea_text") or "").strip()
            st.info(_run_full_cycle(idea_txt or None))
            st.rerun()
        if st.button("BREED ONLY", key="aite_breed", width="stretch"):
            st.info(_run_breed())
            st.rerun()
        alive_ids = [b.get("bot_id") for b in bots if b.get("bot_id")]
        # Session-state only — never pass default= together with key=
        # (avoids StreamlitWarning on aite_squad_pick).
        if "aite_squad_pick" not in st.session_state:
            st.session_state["aite_squad_pick"] = alive_ids[: min(5, len(alive_ids))]
        else:
            cur = list(st.session_state.get("aite_squad_pick") or [])
            valid = [x for x in cur if x in alive_ids]
            # If options emptied/changed and selection is stale, reseed once.
            if not valid and alive_ids:
                valid = alive_ids[: min(5, len(alive_ids))]
            st.session_state["aite_squad_pick"] = valid
        pick = st.multiselect(
            "Exam / squad bots",
            options=alive_ids,
            format_func=lambda bid: next(
                (f"{b.get('name')} ({bid})" for b in bots if b.get("bot_id") == bid),
                str(bid),
            ),
            key="aite_squad_pick",
        )
        e1, e2 = st.columns(2)
        with e1:
            if st.button("RUN EXAM", key="aite_exam", width="stretch"):
                st.info(_run_exam_selected(list(pick)))
                st.rerun()
        with e2:
            if st.button("DEPLOY PAPER", key="aite_deploy", width="stretch"):
                st.info(_deploy_paper(list(pick)))
                st.rerun()

    with c4:
        idea = st.text_area("Idea → agent", height=90, key="aite_idea_text",
                            placeholder="e.g. mean-revert BANKNIFTY when RSI<30 and vol z>1")
        if st.button("SEND IDEA", key="aite_idea_send", width="stretch"):
            st.info(_submit_idea(idea))
        if st.button("IDEA → FULL PIPELINE", key="aite_idea_pipeline", width="stretch", type="primary"):
            st.info(_run_full_cycle(idea))
            st.rerun()
        sym = st.selectbox(
            "Ask brief",
            options=["NIFTY 50", "BANKNIFTY", "SENSEX"],
            key="aite_brief_sym",
        )
        if st.button("ASK BRIEF", key="aite_brief", width="stretch", type="primary"):
            brief = _ask_brief(sym)
            st.session_state["_aite_last_brief"] = brief
            verdict = str(brief.get("verdict") or "HOLD")
            color = CRIMSON if verdict == "DO_NOT_BUY" else (NEON if verdict == "ACCUMULATE" else GOLD)
            st.markdown(
                f"<div class='aite-card'>"
                f"<div class='aite-label'>{_esc(sym)} · "
                f"<span style='color:{color}'>{_esc(verdict)}</span></div>"
                f"<div style='font-family:Share Tech Mono,monospace;font-size:0.75rem;color:#ccc;'>"
                f"px={brief.get('price')} · mom={brief.get('momentum')} · "
                f"dd={brief.get('drawdown')} · regime={brief.get('regime')}<br/>"
                f"{_esc(str(brief.get('rationale') or ''))}</div></div>",
                unsafe_allow_html=True,
            )


# ── Public entry ────────────────────────────────────────────────────────────

def render_aite_panel() -> None:
    """Render the full ZERO AITE cyber console (merge agent wires into app.py)."""
    inject_aite_styles()

    bots = _load_bots()
    daemon = _load_daemon()
    fund = _load_fund()
    portfolio = _load_portfolio()
    trades = _load_trades()
    logs = _load_logs()
    exams = st.session_state.get("_aite_last_exams") or _load_exams()
    killed = list(portfolio.get("killed") or [])
    for b in bots:
        if str(b.get("status", "")).lower() == "dead":
            kid = b.get("bot_id")
            if kid and kid not in killed:
                killed.append(kid)

    running = bool(daemon.get("running"))
    n_alive = sum(1 for b in bots if str(b.get("status", "")).lower() in ("alive", "exam"))
    n_dead = sum(1 for b in bots if str(b.get("status", "")).lower() == "dead")

    st.markdown(
        "<div class='aite-wrap'>"
        "<div class='aite-title'>ZERO AITE</div>"
        "<div class='aite-sub'>Automated Intelligent Trading Environment · "
        "genetic breed · OOS exam · 10–40 bot book</div></div>",
        unsafe_allow_html=True,
    )

    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.markdown(status_pill("DAEMON ON" if running else "DAEMON OFF",
                                NEON if running else MUTE), unsafe_allow_html=True)
    with m2:
        st.markdown(f"<div class='aite-metric'>{n_alive}</div>"
                    f"<div class='aite-label'>ALIVE</div>", unsafe_allow_html=True)
    with m3:
        st.markdown(f"<div class='aite-metric' style='color:{CRIMSON}'>{n_dead}</div>"
                    f"<div class='aite-label'>DEAD</div>", unsafe_allow_html=True)
    with m4:
        eq = float(fund.get("equity") or fund.get("paper_fund") or 0)
        st.markdown(f"<div class='aite-metric' style='color:{GOLD}'>₹{eq:,.0f}</div>"
                    f"<div class='aite-label'>PAPER FUND</div>", unsafe_allow_html=True)
    with m5:
        ticks = int(daemon.get("ticks") or 0)
        st.markdown(f"<div class='aite-metric' style='color:{CYAN}'>{ticks}</div>"
                    f"<div class='aite-label'>TICKS</div>", unsafe_allow_html=True)

    # 1. TOP — live 3D graph (continuous rAF sim inside iframe)
    st.markdown("<div class='aite-label'>BOT CONSTELLATION · LIVE GRAPH</div>",
                unsafe_allow_html=True)
    render_bot_graph_3d(bots=bots, killed_ids=killed, height=580)

    # 2+3. Flow + success table
    render_backtest_flow(bots=bots, exams=exams, daemon=daemon, trades=trades)

    # 4. Logs
    _render_logs(bots, trades, logs)

    # 5. Agent automation
    render_agent_automation()

    # 6. Controls
    _render_controls(bots, daemon, fund)

    # Light auto-refresh when daemon running (polls db/aite)
    if running:
        st.caption("Daemon running — auto-refresh polls db/aite.")
        if st.checkbox("Auto-refresh (8s)", value=False, key="aite_auto_refresh"):
            time.sleep(8)
            st.rerun()

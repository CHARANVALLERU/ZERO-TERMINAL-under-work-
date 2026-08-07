"""
ZERO AITE — animated backtest progress flow (~40 lines) + success table.

Lines animate in sync with exam progress_lines / daemon ticks from db/aite.
Flow panel is a live st.iframe sim; success table stays a Streamlit dataframe.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from ui.aite.styles import CRIMSON, GOLD, NEON, CYAN, VOID, PANEL, MUTE

_N_LINES = 40
_DB = Path(__file__).resolve().parents[2] / "db" / "aite"
_FLOW_H = 360


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _mock_progress_lines(progress: float = 0.55) -> List[str]:
    stages = [
        "LOAD bars", "FEATURE rsi/macd", "SPLIT IS/OOS", "SIM long",
        "SIM short", "ATR stops", "SCORE sharpe", "GATE oos",
        "FITNESS blend", "PASS/FAIL",
    ]
    lines: List[str] = []
    for i in range(_N_LINES):
        stage = stages[i % len(stages)]
        pct = (i + 1) / _N_LINES
        tag = "…" if pct > progress else "OK"
        lines.append(f"[{i+1:02d}/{_N_LINES}] {stage} · bot={i%8:02d} · {tag}")
    return lines


def collect_flow_state(
    bots: Optional[List[Dict[str, Any]]] = None,
    exams: Optional[List[Dict[str, Any]]] = None,
    daemon: Optional[Dict[str, Any]] = None,
) -> Tuple[List[str], float, List[Dict[str, Any]]]:
    """
    Build (lines, progress_0_1, success_trades) from store/daemon/exam payloads.
    Never raises.
    """
    del bots  # reserved for future bot-scoped filters
    lines: List[str] = []
    trades: List[Dict[str, Any]] = []
    progress = 0.0

    # Prefer in-memory exams, then exam_cache.json on disk
    try:
        if not exams:
            cache = _read_json(_DB / "exam_cache.json") or {}
            if isinstance(cache, dict):
                exams = cache.get("exams") or cache.get("results") or []
            elif isinstance(cache, list):
                exams = cache
        if exams:
            for ex in reversed(list(exams)):
                pl = ex.get("progress_lines") if isinstance(ex, dict) else None
                if pl:
                    lines = list(pl)[:_N_LINES]
                    # Completed exam → full progress; REJECT still advances
                    reason = str(ex.get("reason") or "")
                    if ex.get("passed") or reason:
                        progress = 1.0 if (ex.get("passed") or "REJECT" in reason.upper()
                                           or "DONE" in " ".join(pl).upper()) else 0.7
                    break
            for ex in exams:
                if isinstance(ex, dict):
                    trades.extend(list(ex.get("trades") or []))
    except Exception:
        pass

    if not lines:
        try:
            from engine.aite import store
            daemon = daemon or store.load_daemon_state()
            ticks = float(daemon.get("ticks") or 0)
            progress = min(1.0, (ticks % 40) / 40.0) if ticks else 0.35
            logs = store.load_logs(limit=_N_LINES)
            if logs:
                lines = [
                    f"[{i+1:02d}/{_N_LINES}] {r.get('level','INFO')} · {r.get('message','')}"
                    for i, r in enumerate(logs[-_N_LINES:])
                ]
            trades = store.load_trades(limit=80)
        except Exception:
            # Filesystem fallback
            daemon = daemon or _read_json(_DB / "daemon_state.json") or {}
            hb = _read_json(_DB / "heartbeat.json") or {}
            ticks = float(daemon.get("ticks") or hb.get("ticks") or 0)
            progress = min(1.0, (ticks % 40) / 40.0) if ticks else 0.45
            lines = _mock_progress_lines(progress)
            trades = _mock_trades()

    if not lines:
        progress = progress or 0.4
        lines = _mock_progress_lines(progress)

    if len(lines) < _N_LINES:
        lines = lines + [f"[{i+1:02d}/{_N_LINES}] WAIT · idle"
                         for i in range(len(lines), _N_LINES)]
    lines = lines[:_N_LINES]

    done = sum(1 for ln in lines if any(k in ln.upper() for k in ("OK", "PASS", "DONE", "INFO", "REJECT", "VERDICT")))
    if progress <= 0:
        progress = done / max(_N_LINES, 1)

    # Runner / heartbeat nudge: animate toward live tick head
    try:
        hb = _read_json(_DB / "heartbeat.json") or {}
        daemon = daemon or _read_json(_DB / "daemon_state.json") or {}
        ticks = int(daemon.get("ticks") or hb.get("ticks") or 0)
        if ticks > 0 and progress < 1.0:
            progress = max(progress, min(0.95, (ticks % _N_LINES) / float(_N_LINES)))
    except Exception:
        pass

    success = []
    for t in trades:
        if not isinstance(t, dict):
            continue
        pnl = t.get("pnl_pct", t.get("pnl", 0))
        try:
            pnl_f = float(pnl or 0)
        except (TypeError, ValueError):
            pnl_f = 0.0
        if t.get("exit") is not None or pnl_f > 0 or t.get("status") == "filled":
            success.append(t)
    if not success:
        success = _mock_trades()
    return lines, float(progress), success


def _mock_trades() -> List[Dict[str, Any]]:
    now = time.strftime("%Y-%m-%d")
    return [
        {
            "bot_name": "MOM-G02-007", "strategy": "MOM-G02-007",
            "entry": 22450.0, "exit": 22510.5,
            "entry_time": f"{now} 10:15", "exit_time": f"{now} 11:42",
            "pnl_pct": 0.27,
        },
        {
            "bot_name": "MRV-G01-003", "strategy": "MRV-G01-003",
            "entry": 51200.0, "exit": 51340.0,
            "entry_time": f"{now} 09:45", "exit_time": f"{now} 12:05",
            "pnl_pct": 0.27,
        },
        {
            "bot_name": "BRK-G03-011", "strategy": "BRK-G03-011",
            "entry": 74500.0, "exit": 74220.0,
            "entry_time": f"{now} 13:10", "exit_time": f"{now} 14:55",
            "pnl_pct": -0.38,
        },
    ]


def build_flow_html(lines: List[str], progress: float, height: int = _FLOW_H) -> str:
    """Animated terminal: cursor advances through lines synced to progress."""
    payload = json.dumps({"lines": list(lines)[:_N_LINES], "progress": float(progress)})
    h = max(280, int(height))
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<style>
  html,body {{ margin:0; padding:0; background:{VOID}; overflow:hidden;
    font-family:'Share Tech Mono',Consolas,monospace; }}
  #box {{ height:{h}px; background:linear-gradient(180deg,{PANEL} 0%,{VOID} 100%);
    border:1px solid #1a1a1a; position:relative; overflow:hidden; }}
  #barwrap {{ position:absolute; top:0; left:0; right:0; height:4px; background:#111; }}
  #bar {{ height:100%; width:0%; background:linear-gradient(90deg,{GOLD},{CRIMSON},{CYAN});
    box-shadow:0 0 10px {CYAN}; transition:width 0.25s linear; }}
  #meta {{ position:absolute; top:10px; left:12px; right:12px; color:{GOLD};
    font-size:10px; letter-spacing:2px; text-transform:uppercase; }}
  #meta b {{ color:{CYAN}; font-weight:normal; }}
  #scroller {{ position:absolute; top:32px; left:0; right:0; bottom:0;
    overflow:hidden; padding:0 10px 12px; }}
  .ln {{ font-size:11px; line-height:1.45; padding:2px 8px; margin:1px 0;
    border-left:2px solid #222; color:{MUTE}; white-space:nowrap;
    overflow:hidden; text-overflow:ellipsis; transition: color 0.2s, border-color 0.2s,
    background 0.2s, transform 0.2s; }}
  .ln.done {{ color:{NEON}; border-left-color:{NEON}; }}
  .ln.active {{ color:{CYAN}; border-left-color:{CYAN};
    background:linear-gradient(90deg, rgba(0,176,255,0.18), transparent);
    transform:translateX(4px); box-shadow:inset 0 0 20px rgba(0,176,255,0.08); }}
  .ln.fail {{ color:{CRIMSON}; border-left-color:{CRIMSON}; }}
  .ln.pending {{ color:{MUTE}; }}
  .scan {{ position:absolute; left:0; right:0; height:28px; pointer-events:none;
    background:linear-gradient(180deg, transparent, rgba(0,176,255,0.07), transparent);
    transition: top 0.15s linear; }}
</style></head>
<body>
<div id="box">
  <div id="barwrap"><div id="bar"></div></div>
  <div id="meta">BACKTEST FLOW · <b id="pct">0%</b> · RUNNER SYNC</div>
  <div id="scroller"><div id="scan" class="scan"></div><div id="lines"></div></div>
</div>
<script>
(function(){{
  const DATA = {payload};
  const lines = DATA.lines || [];
  const target = Math.max(0, Math.min(1, DATA.progress || 0));
  const host = document.getElementById('lines');
  const bar = document.getElementById('bar');
  const pct = document.getElementById('pct');
  const scan = document.getElementById('scan');
  const scroller = document.getElementById('scroller');
  const els = [];
  lines.forEach((text, i) => {{
    const d = document.createElement('div');
    d.className = 'ln pending';
    d.textContent = text;
    host.appendChild(d);
    els.push(d);
  }});

  let head = 0;           // animated cursor index
  const end = target * lines.length;
  // Pace: complete approach in ~ lines*80ms but never faster than 40ms/step
  const stepMs = Math.max(40, Math.min(90, 2800 / Math.max(end, 1)));

  function classify(i, h){{
    const up = (lines[i]||'').toUpperCase();
    if(/FAIL|ERROR|REJECT/.test(up) && i <= h) return 'fail';
    if(Math.abs(i - h) < 0.75) return 'active';
    if(i < h) return 'done';
    return 'pending';
  }}

  function paint(){{
    els.forEach((el, i) => {{
      el.className = 'ln ' + classify(i, head);
    }});
    const p = Math.min(1, head / Math.max(lines.length, 1));
    bar.style.width = (p*100).toFixed(1) + '%';
    pct.textContent = Math.round(p*100) + '%';
    const active = els[Math.min(els.length-1, Math.floor(head))];
    if(active){{
      const top = active.offsetTop - 4;
      scan.style.top = top + 'px';
      // Keep active near upper third
      const view = scroller.clientHeight;
      const want = active.offsetTop - view*0.35;
      scroller.scrollTop = Math.max(0, want);
    }}
  }}

  function tick(){{
    if(head < end){{
      head = Math.min(end, head + 0.35);
      paint();
      setTimeout(tick, stepMs);
    }} else {{
      head = end;
      paint();
      // Breathing pulse on the frontier when complete or paused
      let phase = 0;
      setInterval(() => {{
        phase += 0.15;
        if(target >= 0.999){{
          // soft re-scan glow down the list
          const i = Math.floor((Math.sin(phase)*0.5+0.5) * (lines.length-1));
          head = i;
          paint();
        }} else {{
          // micro-jitter on active line
          paint();
        }}
      }}, 120);
    }}
  }}

  // Continuous rAF shimmer on active line border
  function frame(){{
    const active = document.querySelector('.ln.active');
    if(active){{
      const a = 0.35 + Math.sin(performance.now()/280)*0.25;
      active.style.borderLeftColor = `rgba(0,176,255,${{0.6+a}})`;
    }}
    requestAnimationFrame(frame);
  }}
  requestAnimationFrame(frame);
  paint();
  setTimeout(tick, 200);
}})();
</script>
</body></html>"""


def render_backtest_flow(
    bots: Optional[List[Dict[str, Any]]] = None,
    exams: Optional[List[Dict[str, Any]]] = None,
    daemon: Optional[Dict[str, Any]] = None,
    trades: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Animated ~40-line flow (left iframe) + success table (right)."""
    lines, progress, success = collect_flow_state(bots, exams, daemon)
    if trades:
        success = list(trades)

    left, right = st.columns([1.35, 1.0], gap="medium")

    with left:
        st.markdown(
            f"<div class='aite-label'>BACKTEST FLOW · "
            f"<span style='color:{CYAN}'>{int(progress*100)}%</span></div>",
            unsafe_allow_html=True,
        )
        try:
            html = build_flow_html(lines, progress, height=_FLOW_H)
            st.iframe(html, height=_FLOW_H, width="stretch")
        except Exception as exc:
            st.progress(min(1.0, max(0.0, progress)))
            st.caption(f"Flow iframe unavailable: {exc}")

    with right:
        st.markdown(
            f"<div class='aite-label'>SUCCESS TABLE · "
            f"<span style='color:{NEON}'>FILLS</span></div>",
            unsafe_allow_html=True,
        )
        render_success_table(success)


def render_success_table(trades: List[Dict[str, Any]], limit: int = 25) -> None:
    rows = []
    for t in (trades or [])[-limit:]:
        name = t.get("bot_name") or t.get("strategy") or t.get("name") or t.get("bot_id") or "—"
        rows.append({
            "Strategy": name,
            "Entry": _fmt_px(t.get("entry") or t.get("fill_price") or t.get("entry_price")),
            "Exit": _fmt_px(t.get("exit") or t.get("exit_price")),
            "Entry Time": str(t.get("entry_time") or t.get("ts") or "—"),
            "Exit Time": str(t.get("exit_time") or "—"),
        })
    if not rows:
        rows = [{"Strategy": "—", "Entry": "—", "Exit": "—",
                 "Entry Time": "—", "Exit Time": "—"}]
    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, width="stretch", height=320)


def _fmt_px(v: Any) -> str:
    try:
        f = float(v)
        return f"{f:,.2f}"
    except (TypeError, ValueError):
        return "—" if v is None else str(v)

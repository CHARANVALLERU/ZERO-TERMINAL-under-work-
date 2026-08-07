"""
ZERO AITE — live Notion-like agent automation visualization.

Animated status cards + handoff edges that light when agents pass work.
Pulls db/aite/agents_state.json + activity.jsonl; renders via st.iframe.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

from ui.aite.styles import CRIMSON, CYAN, GOLD, NEON, MUTE, VOID, PANEL

_DB = Path(__file__).resolve().parents[2] / "db" / "aite"
_VIZ_H = 340

_DEFAULT_SWARM: List[Dict[str, Any]] = [
    {
        "agent_id": "orch",
        "role": "Orchestrator",
        "status": "idle",
        "message": "Awaiting daemon start",
        "parent": None,
        "children": ["breeder", "analyst", "risk", "researcher", "exec"],
    },
    {"agent_id": "breeder", "role": "Breeder Analyst", "status": "idle",
     "message": "Genetic pool ready", "parent": "orch", "children": []},
    {"agent_id": "analyst", "role": "Strategy Analyst", "status": "idle",
     "message": "Watching OOS exams", "parent": "orch", "children": []},
    {"agent_id": "risk", "role": "Risk Officer", "status": "idle",
     "message": "Corr + fade gates armed", "parent": "orch", "children": []},
    {"agent_id": "researcher", "role": "Market Researcher", "status": "idle",
     "message": "Premarket 08:45 IST queued", "parent": "orch", "children": []},
    {"agent_id": "exec", "role": "Execution", "status": "idle",
     "message": "Paper brokerage standby", "parent": "orch", "children": []},
]


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _read_jsonl(path: Path, limit: int = 50) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        if not path.is_file():
            return rows
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except Exception:
        pass
    return rows


def load_agent_nodes() -> List[Dict[str, Any]]:
    """Pull agent graph from store / agents module / filesystem; mock if missing."""
    try:
        from engine.aite import store
        state = store.load_agents()
        nodes = state.get("nodes") if isinstance(state, dict) else None
        if nodes:
            return list(nodes)
    except Exception:
        pass
    try:
        from engine.aite import agents as ag
        if hasattr(ag, "get_swarm_state"):
            state = ag.get_swarm_state()
            if isinstance(state, dict) and state.get("nodes"):
                return list(state["nodes"])
            if isinstance(state, list) and state:
                return state
        if hasattr(ag, "load_agents_state"):
            state = ag.load_agents_state()
            if isinstance(state, dict) and state.get("nodes"):
                return list(state["nodes"])
    except Exception:
        pass

    # Direct filesystem (agents_state.json preferred)
    for name in ("agents_state.json", "agents.json"):
        data = _read_json(_DB / name)
        if isinstance(data, dict) and data.get("nodes"):
            return list(data["nodes"])

    nodes = [dict(n) for n in _DEFAULT_SWARM]
    tick = int(time.time()) % 12
    cycle = ["idle", "thinking", "working", "done", "idle", "thinking"]
    for i, n in enumerate(nodes):
        n["status"] = cycle[(tick + i) % len(cycle)]
        if n["status"] == "thinking":
            n["message"] = "Reasoning over latest bars…"
        elif n["status"] == "working":
            n["message"] = "Executing assigned task…"
        elif n["status"] == "done":
            n["message"] = "Task complete — standing by"
    return nodes


def _load_edges(nodes: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    for name in ("agents_state.json", "agents.json"):
        data = _read_json(_DB / name)
        if isinstance(data, dict) and data.get("edges"):
            return [
                {"from": str(e.get("from") or e.get("source") or ""),
                 "to": str(e.get("to") or e.get("target") or ""),
                 "kind": str(e.get("kind") or "delegates")}
                for e in data["edges"] if isinstance(e, dict)
            ]
    # Derive from parent/children
    edges = []
    for n in nodes:
        aid = str(n.get("agent_id") or "")
        parent = n.get("parent")
        if parent:
            edges.append({"from": str(parent), "to": aid, "kind": "delegates"})
        for kid in (n.get("children") or []):
            edges.append({"from": aid, "to": str(kid), "kind": "delegates"})
    # Dedup
    seen = set()
    out = []
    for e in edges:
        key = (e["from"], e["to"])
        if key in seen or not e["from"] or not e["to"] or e["from"] == e["to"]:
            continue
        seen.add(key)
        out.append(e)
    return out


def _status_color(status: str) -> str:
    return {
        "thinking": CYAN,
        "working": NEON,
        "done": GOLD,
        "error": CRIMSON,
        "idle": MUTE,
    }.get(str(status).lower(), MUTE)


def build_agent_viz_html(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, str]],
    activity: List[Dict[str, Any]],
    height: int = _VIZ_H,
) -> str:
    slim_nodes = []
    for n in nodes:
        slim_nodes.append({
            "id": str(n.get("agent_id") or ""),
            "role": str(n.get("role") or n.get("agent_id") or ""),
            "status": str(n.get("status") or "idle").lower(),
            "message": str(n.get("message") or "—")[:140],
            "parent": str(n.get("parent") or "") if n.get("parent") else None,
            "children": [str(c) for c in (n.get("children") or [])],
        })
    act = []
    for row in activity[-40:]:
        if not isinstance(row, dict):
            continue
        extra = row.get("extra") or {}
        act.append({
            "agent": str(row.get("agent_id") or ""),
            "msg": str(row.get("message") or "")[:100],
            "status": str(extra.get("status") or ""),
            "level": str(row.get("level") or ""),
        })
    payload = json.dumps({"nodes": slim_nodes, "edges": edges, "activity": act})
    h = max(280, int(height))

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<style>
  html,body {{ margin:0; padding:0; background:{VOID}; overflow:hidden;
    font-family:'Inter',system-ui,sans-serif; color:#eee; height:100%; }}
  #board {{ position:relative; width:100%; height:{h}px;
    background: linear-gradient(160deg, {PANEL} 0%, {VOID} 100%); }}
  #svg {{ position:absolute; inset:0; width:100%; height:100%; pointer-events:none; }}
  .card {{ position:absolute; width:148px; min-height:72px;
    background:rgba(10,10,10,0.92); border:1px solid #222; border-radius:4px;
    padding:10px 12px; transition: border-color 0.25s, box-shadow 0.25s, transform 0.35s;
    box-shadow: 0 0 0 0 transparent; }}
  .card .role {{ font-family:Orbitron,sans-serif; font-size:9px; letter-spacing:1.2px;
    text-transform:uppercase; color:{GOLD}; margin-bottom:4px; }}
  .card .st {{ font-family:'Share Tech Mono',monospace; font-size:10px;
    letter-spacing:1px; margin-bottom:6px; }}
  .card .msg {{ font-family:'Share Tech Mono',monospace; font-size:10px;
    color:#aaa; line-height:1.3; max-height:2.6em; overflow:hidden; }}
  .card.thinking {{ border-left:3px solid {CYAN}; box-shadow:0 0 16px rgba(0,176,255,0.22); }}
  .card.working  {{ border-left:3px solid {NEON}; box-shadow:0 0 18px rgba(0,255,136,0.28);
    transform: translateY(-2px); }}
  .card.done     {{ border-left:3px solid {GOLD}; }}
  .card.error    {{ border-left:3px solid {CRIMSON}; box-shadow:0 0 14px rgba(229,9,20,0.3); }}
  .card.idle     {{ border-left:3px solid {MUTE}; opacity:0.78; }}
  .dot {{ display:inline-block; width:7px; height:7px; border-radius:50%;
    margin-right:6px; vertical-align:middle;
    animation: pulseDot 1.2s ease-in-out infinite; }}
  @keyframes pulseDot {{ 0%,100%{{transform:scale(1);opacity:1}} 50%{{transform:scale(0.7);opacity:0.5}} }}
  #banner {{ position:absolute; top:8px; left:12px; right:12px; font-size:10px;
    font-family:'Share Tech Mono',monospace; color:{CYAN}; letter-spacing:1px;
    z-index:3; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  #banner span {{ color:{GOLD}; }}
</style></head>
<body>
<div id="board">
  <div id="banner">AGENT AUTOMATION · <span>LIVE</span> · waiting for handoff…</div>
  <svg id="svg"></svg>
</div>
<script>
(function(){{
  const DATA = {payload};
  const COLORS = {{
    thinking:'{CYAN}', working:'{NEON}', done:'{GOLD}', error:'{CRIMSON}', idle:'{MUTE}'
  }};
  const board = document.getElementById('board');
  const svg = document.getElementById('svg');
  const banner = document.getElementById('banner');
  const nodes = DATA.nodes.map(n => ({{...n}}));
  const byId = {{}};
  nodes.forEach(n => byId[n.id]=n);

  // Layout: root top-center, children in a row
  const roots = nodes.filter(n => !n.parent || !byId[n.parent]);
  const root = roots[0] || nodes[0];
  const kids = nodes.filter(n => n !== root);
  const W = () => board.clientWidth || 640;
  const H = {h};

  function layout(){{
    const w = W();
    if(root){{ root._x = w/2 - 74; root._y = 42; }}
    const n = Math.max(kids.length, 1);
    const gap = Math.min(168, (w - 40) / n);
    const start = (w - gap*(n-1) - 148) / 2;
    kids.forEach((k,i) => {{
      k._x = Math.max(8, start + i*gap);
      k._y = H - 118;
    }});
  }}

  const cards = {{}};
  nodes.forEach(n => {{
    const el = document.createElement('div');
    el.className = 'card ' + (n.status||'idle');
    el.id = 'card_' + n.id;
    el.innerHTML = '<div class="role"></div><div class="st"></div><div class="msg"></div>';
    board.appendChild(el);
    cards[n.id] = el;
  }});

  function paintCard(n){{
    const el = cards[n.id];
    if(!el) return;
    el.style.left = n._x + 'px';
    el.style.top = n._y + 'px';
    el.className = 'card ' + (n.status||'idle');
    const col = COLORS[n.status] || COLORS.idle;
    el.querySelector('.role').textContent = (n.role||n.id).replace(/_/g,' ');
    el.querySelector('.st').innerHTML =
      '<span class="dot" style="background:'+col+';box-shadow:0 0 8px '+col+'"></span>' +
      (n.status||'idle').toUpperCase();
    el.querySelector('.st').style.color = col;
    el.querySelector('.msg').textContent = n.message || '—';
  }}

  // Edge paths
  const edgeEls = [];
  (DATA.edges||[]).forEach(e => {{
    const path = document.createElementNS('http://www.w3.org/2000/svg','path');
    path.setAttribute('fill','none');
    path.setAttribute('stroke','{CRIMSON}');
    path.setAttribute('stroke-width','1.5');
    path.setAttribute('stroke-opacity','0.35');
    path.setAttribute('stroke-dasharray','6 8');
    path.dataset.from = e.from;
    path.dataset.to = e.to;
    svg.appendChild(path);
    const particle = document.createElementNS('http://www.w3.org/2000/svg','circle');
    particle.setAttribute('r','3.5');
    particle.setAttribute('fill','{GOLD}');
    particle.setAttribute('opacity','0');
    svg.appendChild(particle);
    edgeEls.push({{path, particle, from:e.from, to:e.to, lit:0, t:Math.random()}});
  }});

  function edgeGeom(from, to){{
    const a = byId[from], b = byId[to];
    if(!a||!b) return null;
    const x1 = a._x + 74, y1 = a._y + 72;
    const x2 = b._x + 74, y2 = b._y;
    const midY = (y1+y2)/2;
    return {{d:`M${{x1}} ${{y1}} C ${{x1}} ${{midY}}, ${{x2}} ${{midY}}, ${{x2}} ${{y2}}`, x1,y1,x2,y2}};
  }}

  function setStatus(id, status, msg){{
    const n = byId[id];
    if(!n) return;
    n.status = status || n.status;
    if(msg) n.message = msg;
    paintCard(n);
  }}

  // Replay activity as live handoffs
  let actIdx = 0;
  const activity = DATA.activity || [];
  function poll(){{
    if(activity.length){{
      const ev = activity[actIdx % activity.length];
      actIdx++;
      let aid = ev.agent;
      if(!aid || !byId[aid]){{
        // fuzzy match role in message
        const hit = nodes.find(n => ev.msg && ev.msg.toLowerCase().indexOf((n.role||'').split('_')[0])>=0);
        aid = hit ? hit.id : (root && root.id);
      }}
      const st = ev.status || (ev.level==='ERROR'?'error':'working');
      setStatus(aid, st, ev.msg || 'working…');
      // Light edges involving this agent
      edgeEls.forEach(ed => {{
        if(ed.from===aid || ed.to===aid){{
          ed.lit = 1;
          // Handoff: if parent done-ish, child lights
          if(ed.from===aid && byId[ed.to]){{
            setTimeout(() => setStatus(ed.to, 'thinking', 'Handoff received…'), 280);
          }}
        }}
      }});
      banner.innerHTML = 'AGENT AUTOMATION · <span>LIVE</span> · ' +
        (ev.msg||'handoff').replace(/[<>]/g,'');
    }} else {{
      // Synthetic Notion-like cycle
      const order = nodes.map(n=>n.id);
      const i = actIdx % order.length;
      actIdx++;
      const cycle = ['thinking','working','done','idle'];
      setStatus(order[i], cycle[actIdx%cycle.length], 'Autonomous tick…');
      edgeEls.forEach(ed => {{ if(ed.from===order[i]||ed.to===order[i]) ed.lit=1; }});
    }}
  }}
  setInterval(poll, 1100);
  poll();

  // Decay busy → idle slowly
  setInterval(() => {{
    nodes.forEach(n => {{
      if(n.status==='done'){{
        // stay briefly then idle
      }}
    }});
  }}, 4000);

  let dashOffset = 0;
  function frame(){{
    layout();
    nodes.forEach(paintCard);
    dashOffset -= 0.55;
    edgeEls.forEach(ed => {{
      const g = edgeGeom(ed.from, ed.to);
      if(!g) return;
      ed.path.setAttribute('d', g.d);
      ed.lit *= 0.96;
      const hot = ed.lit > 0.15;
      ed.path.setAttribute('stroke', hot ? '{NEON}' : '{CRIMSON}');
      ed.path.setAttribute('stroke-opacity', String(0.3 + ed.lit*0.65));
      ed.path.setAttribute('stroke-width', String(1.4 + ed.lit*2.2));
      ed.path.setAttribute('stroke-dashoffset', String(dashOffset));
      // Particle along cubic approx
      ed.t += 0.008 + ed.lit*0.02;
      if(ed.t>1) ed.t-=1;
      const t=ed.t;
      const mx = g.x1 + (g.x2-g.x1)*t;
      const my = g.y1 + (g.y2-g.y1)*t * (0.3+0.7*Math.sin(t*Math.PI));
      ed.particle.setAttribute('cx', mx);
      ed.particle.setAttribute('cy', my);
      ed.particle.setAttribute('opacity', String(0.25 + ed.lit*0.75));
      ed.particle.setAttribute('fill', hot ? '{NEON}' : '{GOLD}');
    }});
    requestAnimationFrame(frame);
  }}
  requestAnimationFrame(frame);
  window.addEventListener('resize', layout);
}})();
</script>
</body></html>"""


def render_agent_automation(
    nodes: Optional[List[Dict[str, Any]]] = None,
    title: str = "AGENT AUTOMATION",
) -> None:
    """Notion-style live hierarchical agent board (iframe sim)."""
    nodes = nodes if nodes is not None else load_agent_nodes()
    if not nodes:
        nodes = list(_DEFAULT_SWARM)

    edges = _load_edges(nodes)
    activity = _read_jsonl(_DB / "activity.jsonl", limit=50)
    # Prefer engine activity reader when available
    try:
        from engine.aite.activity_log import read_activity
        activity = read_activity(limit=50) or activity
    except Exception:
        pass

    st.markdown(
        f"<div class='aite-label'>{title} · "
        f"<span style='color:{CYAN}'>LIVE</span></div>",
        unsafe_allow_html=True,
    )

    # Compact status strip (static snapshot; iframe carries motion)
    pills = []
    for n in nodes:
        col = _status_color(n.get("status", "idle"))
        role = str(n.get("role") or n.get("agent_id") or "")
        pills.append(
            f"<span style='display:inline-flex;align-items:center;gap:6px;"
            f"margin:2px 8px 8px 0;font-family:Orbitron,sans-serif;"
            f"font-size:0.55rem;letter-spacing:1px;color:{col};'>"
            f"<span style='width:7px;height:7px;border-radius:50%;background:{col};"
            f"box-shadow:0 0 6px {col};'></span>"
            f"{_esc(role)} · {_esc(str(n.get('status') or 'idle').upper())}</span>"
        )
    st.markdown("".join(pills), unsafe_allow_html=True)

    try:
        html = build_agent_viz_html(nodes, edges, activity, height=_VIZ_H)
        st.iframe(html, height=_VIZ_H, width="stretch")
    except Exception as exc:
        st.info(f"Agent viz unavailable: {exc}")


def _esc(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

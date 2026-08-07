"""
ZERO AITE — live 3D bot constellation (canvas rAF simulation).

Gold nodes orbit/pulse, crimson edges carry flow particles, activity spikes
from db/aite/agents_state.json + activity.jsonl. Dead bots explode then vanish.
Rendered via st.iframe (HTML/CSS/JS) — not static Plotly.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

from ui.aite.styles import CRIMSON, GOLD, NEON, VOID, CYAN

_DB = Path(__file__).resolve().parents[2] / "db" / "aite"
_GRAPH_H = 580  # default; panel may pass 520–640


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _read_jsonl(path: Path, limit: int = 80) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        if not path.is_file():
            return rows
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines[-limit:]:
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


def _load_live_feed() -> Dict[str, Any]:
    """Filesystem poll of agents_state + activity (engine-independent)."""
    agents = _read_json(_DB / "agents_state.json") or _read_json(_DB / "agents.json") or {}
    activity = _read_jsonl(_DB / "activity.jsonl", limit=60)
    heartbeat = _read_json(_DB / "heartbeat.json") or {}
    daemon = _read_json(_DB / "daemon_state.json") or {}
    return {
        "agents": agents if isinstance(agents, dict) else {},
        "activity": activity,
        "heartbeat": heartbeat if isinstance(heartbeat, dict) else {},
        "daemon": daemon if isinstance(daemon, dict) else {},
        "polled_at": time.time(),
    }


def _layout_positions(n: int, seed: float = 0.0) -> List[Dict[str, float]]:
    pts: List[Dict[str, float]] = []
    if n <= 0:
        return pts
    golden = math.pi * (3.0 - math.sqrt(5.0))
    for i in range(n):
        y = 1.0 - (i / max(n - 1, 1)) * 2.0
        radius = math.sqrt(max(0.0, 1.0 - y * y))
        theta = golden * i + seed
        x = math.cos(theta) * radius
        z = math.sin(theta) * radius
        pts.append({"x": x * 1.55, "y": y * 1.55, "z": z * 1.55})
    return pts


def _normalize_bots(bots: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    bots = list(bots or [])
    if bots:
        return bots
    mock = []
    styles = ("momentum", "mean_reversion", "breakout", "flow", "mixed")
    for i in range(18):
        status = "alive"
        if i == 4:
            status = "dead"
        elif i == 9:
            status = "fading"
        elif i >= 16:
            status = "candidate"
        mock.append({
            "bot_id": f"mock_{i:02d}",
            "name": f"HYB-G00-{i:03d}",
            "status": status,
            "style": styles[i % len(styles)],
            "symbol": ["NIFTY 50", "BANKNIFTY", "SENSEX"][i % 3],
            "generation": i // 4,
        })
    return mock


def _edges_for(bots: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    edges: List[Dict[str, str]] = []
    by_style: Dict[str, List[str]] = {}
    by_sym: Dict[str, List[str]] = {}
    for b in bots:
        bid = str(b.get("bot_id") or "")
        by_style.setdefault(str(b.get("style") or "mixed"), []).append(bid)
        by_sym.setdefault(str(b.get("symbol") or "?"), []).append(bid)
    for group in list(by_style.values()) + list(by_sym.values()):
        for i in range(len(group) - 1):
            edges.append({"source": group[i], "target": group[i + 1]})
    seen = set()
    out = []
    for e in edges:
        key = tuple(sorted((e["source"], e["target"])))
        if key in seen or key[0] == key[1]:
            continue
        seen.add(key)
        out.append(e)
    return out[: max(10, len(bots) * 2)]


def build_graph_html(
    bots: Optional[List[Dict[str, Any]]] = None,
    killed_ids: Optional[List[str]] = None,
    height: int = _GRAPH_H,
    live: Optional[Dict[str, Any]] = None,
) -> str:
    """Self-contained HTML/JS continuous 3D-ish force graph."""
    bots = _normalize_bots(bots)
    killed = set(str(x) for x in (killed_ids or []) if x)
    for b in bots:
        if str(b.get("status", "")).lower() == "dead":
            killed.add(str(b.get("bot_id")))

    live = live or _load_live_feed()
    positions = _layout_positions(len(bots), seed=time.time() % 7)
    nodes = []
    for i, b in enumerate(bots):
        p = positions[i] if i < len(positions) else {"x": 0, "y": 0, "z": 0}
        status = str(b.get("status") or "alive").lower()
        bid = str(b.get("bot_id") or f"n{i}")
        nodes.append({
            "id": bid,
            "name": str(b.get("name") or f"BOT-{i}"),
            "status": status,
            "style": str(b.get("style") or ""),
            "symbol": str(b.get("symbol") or ""),
            "x": p["x"], "y": p["y"], "z": p["z"],
            "dead": status == "dead" or bid in killed,
            "phase": (i * 0.37) % 6.28,
            "orbit": 0.04 + (i % 5) * 0.012,
        })
    edges = _edges_for(bots)

    # Slim activity for JS (message + agent + bot hints)
    act_slim = []
    for row in (live.get("activity") or [])[-40:]:
        if not isinstance(row, dict):
            continue
        extra = row.get("extra") or {}
        act_slim.append({
            "msg": str(row.get("message") or "")[:120],
            "agent": str(row.get("agent_id") or ""),
            "bot": str(extra.get("bot_id") or ""),
            "level": str(row.get("level") or "INFO"),
            "status": str(extra.get("status") or ""),
        })

    agent_nodes = []
    ag = live.get("agents") or {}
    for n in (ag.get("nodes") or []):
        if isinstance(n, dict):
            agent_nodes.append({
                "id": str(n.get("agent_id") or ""),
                "status": str(n.get("status") or "idle"),
                "role": str(n.get("role") or ""),
            })

    payload = json.dumps({
        "nodes": nodes,
        "edges": edges,
        "killed": list(killed),
        "activity": act_slim,
        "agents": agent_nodes,
        "daemon_running": bool((live.get("daemon") or {}).get("running")
                               or (live.get("heartbeat") or {}).get("status") == "alive"),
        "ticks": int((live.get("daemon") or {}).get("ticks")
                     or (live.get("heartbeat") or {}).get("ticks") or 0),
    })

    h = max(520, min(640, int(height)))

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<style>
  html,body {{ margin:0; padding:0; background:{VOID}; overflow:hidden;
    font-family:'Share Tech Mono',Consolas,monospace; height:100%; }}
  #wrap {{ position:relative; width:100%; height:{h}px; }}
  #c {{ display:block; width:100%; height:{h}px; background:
    radial-gradient(ellipse at 50% 42%, #141414 0%, #0a0a0a 45%, {VOID} 78%);
    cursor:grab; }}
  #c:active {{ cursor:grabbing; }}
  #hud {{ position:absolute; left:14px; top:12px; color:{GOLD}; font-size:11px;
    letter-spacing:2px; text-transform:uppercase; pointer-events:none;
    text-shadow:0 0 10px rgba(212,175,55,0.55); z-index:2; }}
  #hud b {{ color:{NEON}; font-weight:normal; }}
  #feed {{ position:absolute; left:14px; bottom:12px; right:14px; color:#888;
    font-size:10px; pointer-events:none; z-index:2; white-space:nowrap;
    overflow:hidden; text-overflow:ellipsis; }}
  #feed .hi {{ color:{CYAN}; }}
  #tip {{ position:absolute; right:14px; top:12px; color:#666; font-size:10px;
    pointer-events:none; text-align:right; z-index:2; }}
  #pulse {{ position:absolute; top:10px; left:50%; transform:translateX(-50%);
    width:8px; height:8px; border-radius:50%; background:{NEON};
    box-shadow:0 0 12px {NEON}; animation:blink 1.1s ease-in-out infinite; z-index:2; }}
  @keyframes blink {{ 0%,100%{{opacity:1;transform:translateX(-50%) scale(1)}}
    50%{{opacity:0.35;transform:translateX(-50%) scale(0.7)}} }}
</style></head>
<body>
<div id="wrap">
  <canvas id="c"></canvas>
  <div id="pulse" title="live"></div>
  <div id="hud">AITE · LIVE GRAPH · <b id="aliveN">0</b> ALIVE · <span id="tickN">0</span> TICK</div>
  <div id="tip">drag orbit · scroll zoom · gold=bot · red=link · blast=death</div>
  <div id="feed">booting activity feed…</div>
</div>
<script>
(function(){{
  const DATA = {payload};
  const GOLD = '{GOLD}', CRIMSON = '{CRIMSON}', CYAN = '{CYAN}', NEON = '{NEON}';
  const canvas = document.getElementById('c');
  const ctx = canvas.getContext('2d');
  const feedEl = document.getElementById('feed');
  const aliveEl = document.getElementById('aliveN');
  const tickEl = document.getElementById('tickN');
  let W, H, cx, cy, dpr = window.devicePixelRatio || 1;
  const HEIGHT = {h};

  function resize(){{
    dpr = window.devicePixelRatio || 1;
    W = canvas.width = Math.max(320, canvas.clientWidth) * dpr;
    H = canvas.height = HEIGHT * dpr;
    canvas.style.height = HEIGHT + 'px';
    cx = W/2; cy = H/2;
  }}
  resize();
  window.addEventListener('resize', resize);

  let yaw = 0.42, pitch = 0.28, dist = 3.05;
  let drag=false, lx=0, ly=0;
  canvas.addEventListener('mousedown', e => {{ drag=true; lx=e.clientX; ly=e.clientY; }});
  window.addEventListener('mouseup', () => drag=false);
  window.addEventListener('mousemove', e => {{
    if(!drag) return;
    yaw += (e.clientX-lx)*0.0055;
    pitch = Math.max(-1.25, Math.min(1.25, pitch + (e.clientY-ly)*0.0055));
    lx=e.clientX; ly=e.clientY;
  }});
  canvas.addEventListener('wheel', e => {{
    dist = Math.max(1.55, Math.min(6.2, dist + e.deltaY*0.0022));
    e.preventDefault();
  }}, {{passive:false}});

  function project(x,y,z){{
    const cy0=Math.cos(yaw), sy=Math.sin(yaw);
    const cp=Math.cos(pitch), sp=Math.sin(pitch);
    let x1 = x*cy0 - z*sy;
    let z1 = x*sy + z*cy0;
    let y1 = y*cp - z1*sp;
    z1 = y*sp + z1*cp;
    const f = (255*dpr) / (dist + z1 + 2.6);
    return {{x: cx + x1*f, y: cy + y1*f, s: Math.max(2.2, f*0.052), z: z1}};
  }}

  const nodes = DATA.nodes.map(n => ({{
    ...n,
    bx: n.x, by: n.y, bz: n.z,
    blast: 0,
    particles: [],
    activity: 0,
    removed: false,
    workPulse: 0,
  }}));
  const idMap = {{}};
  nodes.forEach(n => idMap[n.id]=n);

  // Flow particles on edges
  const edgeFlows = DATA.edges.map(e => {{
    const count = 3 + Math.floor(Math.random()*3);
    return {{
      source: e.source, target: e.target,
      parts: Array.from({{length: count}}, (_,i) => ({{
        t: Math.random(), speed: 0.004 + Math.random()*0.008, glow: 0.4+Math.random()*0.6
      }}))
    }};
  }});

  function triggerBlast(n){{
    if(n.removed) return;
    n.dead = true; n.blast = 0.01;
    n.particles = [];
    for(let i=0;i<48;i++){{
      const a=Math.random()*Math.PI*2, b=Math.random()*Math.PI;
      const sp = 0.035+Math.random()*0.09;
      n.particles.push({{
        vx: Math.sin(b)*Math.cos(a)*sp,
        vy: Math.cos(b)*sp,
        vz: Math.sin(b)*Math.sin(a)*sp,
        life: 1.0,
        px: n.x, py: n.y, pz: n.z,
        gold: Math.random()>0.45
      }});
    }}
  }}

  // Stagger death blasts for already-dead
  nodes.filter(n=>n.dead).forEach((n,i) => {{
    setTimeout(() => triggerBlast(n), 180 + i*160);
  }});

  function spikeNode(n, amount){{
    if(!n || n.dead || n.removed) return;
    n.activity = Math.min(1.5, n.activity + amount);
    n.workPulse = 1;
  }}

  // Activity "polling" — replay embedded feed on a timer (simulates jsonl poll)
  let actIdx = 0;
  const activity = DATA.activity || [];
  function pollActivity(){{
    if(!activity.length){{
      // Idle synthetic work spikes so graph never feels dead
      const live = nodes.filter(n => !n.dead && !n.removed);
      if(live.length){{
        const n = live[Math.floor(Math.random()*live.length)];
        spikeNode(n, 0.55 + Math.random()*0.5);
        feedEl.innerHTML = '<span class="hi">SYN</span> · bot work · ' + n.name;
      }}
      return;
    }}
    const ev = activity[actIdx % activity.length];
    actIdx++;
    let hit = null;
    if(ev.bot && idMap[ev.bot]) hit = idMap[ev.bot];
    if(!hit && ev.msg){{
      hit = nodes.find(n => !n.removed && ev.msg.indexOf(n.name) >= 0);
    }}
    if(!hit){{
      const live = nodes.filter(n => !n.dead && !n.removed);
      if(live.length) hit = live[actIdx % live.length];
    }}
    if(hit){{
      spikeNode(hit, ev.level === 'EXAM' || ev.level === 'TRADE' ? 1.1 : 0.7);
      // Light connected edges
      edgeFlows.forEach(ef => {{
        if(ef.source === hit.id || ef.target === hit.id){{
          ef.parts.forEach(p => {{ p.glow = 1; p.speed = 0.014; }});
        }}
      }});
    }}
    const label = (ev.level||'INFO') + ' · ' + (ev.msg||'activity');
    feedEl.innerHTML = '<span class="hi">POLL</span> · ' + label.replace(/[<>]/g,'');
    tickEl.textContent = String((DATA.ticks||0) + actIdx);
  }}
  setInterval(pollActivity, 900);
  pollActivity();

  // Soft agent-status coupling: when agents working, random alive bots spike
  setInterval(() => {{
    const busy = (DATA.agents||[]).filter(a => a.status==='working'||a.status==='thinking');
    if(!busy.length && !DATA.daemon_running) return;
    const live = nodes.filter(n => !n.dead && !n.removed);
    if(!live.length) return;
    spikeNode(live[Math.floor(Math.random()*live.length)], 0.45);
  }}, 1400);

  let t0 = performance.now();
  function frame(now){{
    const t = (now - t0) / 1000;
    ctx.clearRect(0,0,W,H);

    // Atmosphere rings
    ctx.strokeStyle = 'rgba(212,175,55,0.045)';
    ctx.lineWidth = 1;
    for(let r=0;r<3;r++){{
      const rr = (90+r*55)*dpr + Math.sin(t*0.7+r)*8*dpr;
      ctx.beginPath(); ctx.ellipse(cx, cy+20*dpr, rr*1.4, rr*0.45, 0, 0, Math.PI*2); ctx.stroke();
    }}

    // Floor grid
    ctx.strokeStyle = 'rgba(212,175,55,0.055)';
    for(let g=-2; g<=2; g++){{
      const a=project(-2.2, -1.6, g), b=project(2.2, -1.6, g);
      const c=project(g, -1.6, -2.2), d=project(g, -1.6, 2.2);
      ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(c.x,c.y); ctx.lineTo(d.x,d.y); ctx.stroke();
    }}

    // Update node orbits
    nodes.forEach(n => {{
      if(n.removed) return;
      const ang = t * (0.35 + n.orbit*3) + n.phase;
      n.x = n.bx + Math.cos(ang) * n.orbit * 1.8;
      n.y = n.by + Math.sin(ang*1.3) * n.orbit * 1.2;
      n.z = n.bz + Math.sin(ang*0.9) * n.orbit * 1.8;
      n.activity *= 0.965;
      n.workPulse *= 0.94;
    }});

    // Edges + flow particles
    edgeFlows.forEach(ef => {{
      const a=idMap[ef.source], b=idMap[ef.target];
      if(!a||!b||a.removed||b.removed) return;
      if(a.dead && a.blast>0.88) return;
      if(b.dead && b.blast>0.88) return;
      const pa=project(a.x,a.y,a.z), pb=project(b.x,b.y,b.z);
      const hot = Math.max(a.activity, b.activity, a.workPulse, b.workPulse);
      const alpha = 0.28 + hot*0.45;
      ctx.strokeStyle = `rgba(229,9,20,${{alpha}})`;
      ctx.lineWidth = (1.1 + hot*1.8)*dpr;
      ctx.beginPath(); ctx.moveTo(pa.x,pa.y); ctx.lineTo(pb.x,pb.y); ctx.stroke();

      ef.parts.forEach(p => {{
        p.t += p.speed * (1 + hot*1.5);
        if(p.t > 1) p.t -= 1;
        p.glow *= 0.992;
        const tt = p.t;
        const x = a.x + (b.x-a.x)*tt;
        const y = a.y + (b.y-a.y)*tt;
        const z = a.z + (b.z-a.z)*tt;
        const pp = project(x,y,z);
        const g = 0.35 + p.glow*0.65 + hot*0.3;
        ctx.fillStyle = `rgba(229,9,20,${{Math.min(1,g)}})`;
        ctx.beginPath();
        ctx.arc(pp.x, pp.y, (1.8+hot*2.2)*dpr, 0, Math.PI*2);
        ctx.fill();
        if(hot > 0.35){{
          ctx.fillStyle = `rgba(212,175,55,${{hot*0.7}})`;
          ctx.fillRect(pp.x-dpr, pp.y-dpr, 2*dpr, 2*dpr);
        }}
      }});
    }});

    // Nodes
    const sorted = nodes.filter(n => !n.removed).slice()
      .sort((a,b)=> project(a.x,a.y,a.z).z - project(b.x,b.y,b.z).z);

    let aliveCount = 0;
    sorted.forEach(n => {{
      // Death particles
      n.particles.forEach(p => {{
        p.px += p.vx; p.py += p.vy; p.pz += p.vz;
        p.vy -= 0.0008;
        p.life *= 0.958;
        const pp = project(p.px, p.py, p.pz);
        const col = p.gold ? GOLD : CRIMSON;
        ctx.fillStyle = col;
        ctx.globalAlpha = Math.max(0, p.life);
        ctx.beginPath();
        ctx.arc(pp.x, pp.y, (2.2+p.life*2)*dpr, 0, Math.PI*2);
        ctx.fill();
        ctx.globalAlpha = 1;
      }});
      n.particles = n.particles.filter(p => p.life > 0.035);

      if(n.dead){{
        n.blast = Math.min(1, n.blast + 0.014);
        if(n.blast > 0.92 && n.particles.length === 0){{
          n.removed = true;
          return;
        }}
      }} else {{
        aliveCount++;
      }}

      const p = project(n.x, n.y, n.z);
      const pulse = 1 + Math.sin(t*3.2 + n.phase)*0.12 + n.activity*0.35 + n.workPulse*0.25;
      let col = GOLD;
      if(n.status==='candidate') col = CYAN;
      if(n.status==='fading') col = '#FFD600';
      if(n.dead) col = CRIMSON;
      const alpha = n.dead ? Math.max(0, 1 - n.blast) : 1;
      const radius = p.s * pulse * (n.dead ? 1.5 : 1.15);

      // Outer glow
      const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, radius*5.5);
      const ga = Math.floor(alpha * (55 + n.activity*90 + n.workPulse*60));
      g.addColorStop(0, col + ga.toString(16).padStart(2,'0'));
      g.addColorStop(1, 'transparent');
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(p.x, p.y, radius*5.5, 0, Math.PI*2); ctx.fill();

      // Core
      ctx.globalAlpha = alpha;
      ctx.fillStyle = col;
      ctx.beginPath(); ctx.arc(p.x, p.y, radius, 0, Math.PI*2); ctx.fill();
      // Hot core when working
      if(!n.dead && (n.activity>0.2 || n.workPulse>0.2)){{
        ctx.fillStyle = NEON;
        ctx.globalAlpha = alpha * (0.35 + n.activity*0.4);
        ctx.beginPath(); ctx.arc(p.x, p.y, radius*0.45, 0, Math.PI*2); ctx.fill();
      }}
      ctx.globalAlpha = 1;

      if(!n.dead && p.s > 3.2){{
        ctx.fillStyle = 'rgba(255,255,255,0.6)';
        ctx.font = `${{Math.round(9*dpr)}}px monospace`;
        ctx.fillText(n.name, p.x + radius + 3*dpr, p.y - 2*dpr);
      }}
    }});

    aliveEl.textContent = String(aliveCount);
    if(!drag) yaw += 0.0028 + (DATA.daemon_running ? 0.0012 : 0);
    requestAnimationFrame(frame);
  }}
  requestAnimationFrame(frame);
}})();
</script>
</body></html>"""


def render_bot_graph_3d(
    bots: Optional[List[Dict[str, Any]]] = None,
    killed_ids: Optional[List[str]] = None,
    height: int = _GRAPH_H,
    use_plotly: bool = False,  # kept for API compat; ignored — always live iframe
) -> None:
    """Render the live 3D bot constellation via st.iframe."""
    del use_plotly  # never use static Plotly as primary
    bots = _normalize_bots(bots)
    killed = list(killed_ids or [])
    for b in bots:
        if str(b.get("status", "")).lower() == "dead":
            kid = str(b.get("bot_id") or "")
            if kid and kid not in killed:
                killed.append(kid)

    h = max(520, min(640, int(height or _GRAPH_H)))
    live = _load_live_feed()
    try:
        html = build_graph_html(bots, killed, height=h, live=live)
        st.iframe(html, height=h, width="stretch")
    except Exception as exc:
        st.info(f"Bot graph unavailable: {exc}")

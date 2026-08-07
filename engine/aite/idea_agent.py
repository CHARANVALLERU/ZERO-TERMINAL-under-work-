"""
ZERO AITE idea agent — natural-language trading idea → BotGenome → exam/breed queue.

Does NOT rewrite breeding/exam; only interfaces with them.
"""
from __future__ import annotations

import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from engine.aite import config as cfg
from engine.aite import store
from engine.aite.activity_log import log_activity
from engine.aite.agents import AgentSwarm
from engine.aite.models import BotGenome, Rule, _uid, new_bot_name

# Optional jobs dir used by daemon (write-only from our side) — lazy vs cfg redirect
def _idea_queue_path():
    return cfg.AITE_DB_DIR / "idea_queue.jsonl"


def _jobs_dir():
    return cfg.AITE_DB_DIR / "jobs"


def __getattr__(name: str):
    if name == "IDEA_QUEUE_PATH":
        return _idea_queue_path()
    if name == "JOBS_DIR":
        return _jobs_dir()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

_SYMBOL_PATTERNS = [
    (r"\bbank\s*nifty\b|\bbnf\b|\bbanknifty\b", "BANKNIFTY"),
    (r"\bsensex\b", "SENSEX"),
    (r"\bnifty\s*50\b|\bnifty\b", "NIFTY 50"),
]

_STYLE_KEYWORDS = {
    "momentum": ("momentum", "trend follow", "breakout trend", "ema cross", "macd"),
    "mean_reversion": ("mean rev", "mean-reversion", "oversold", "overbought", "reversion", "fade"),
    "breakout": ("breakout", "break out", "range break", "volatility expansion"),
    "flow": ("orderflow", "order flow", "oi ", "pcr", "volume spike", "vwap"),
}

_SIDE_KEYWORDS = {
    "LONG": ("long only", "only long", "buy the dip", "bullish only"),
    "SHORT": ("short only", "only short", "bearish only"),
    "BOTH": ("both sides", "long/short", "long and short"),
}

_STYLE_RULE_TEMPLATES: Dict[str, List[Tuple[str, str, float]]] = {
    "momentum": [
        ("mom_20", ">", 0.5),
        ("ema_spread", ">", 0.0),
        ("macd_hist", ">", 0.0),
        ("adx", ">", 20.0),
    ],
    "mean_reversion": [
        ("rsi", "<", 35.0),
        ("bb_pct_b", "<", 20.0),
        ("stoch_k", "<", 25.0),
        ("rsi", ">", 65.0),
    ],
    "breakout": [
        ("atr_pct", ">", 1.0),
        ("vol_z", ">", 1.0),
        ("adx", ">", 22.0),
        ("ret_z", ">", 1.0),
    ],
    "flow": [
        ("obv_slope", ">", 0.0),
        ("vwap_dist", ">", 0.0),
        ("vol_z", ">", 0.5),
        ("mom_10", ">", 0.0),
    ],
    "mixed": [
        ("rsi", ">", 50.0),
        ("macd_hist", ">", 0.0),
        ("ema_spread", ">", 0.0),
        ("mom_10", ">", 0.0),
    ],
}


def _detect_symbol(text: str, default: str = "NIFTY 50") -> str:
    low = text.lower()
    for pat, sym in _SYMBOL_PATTERNS:
        if re.search(pat, low):
            return sym
    return default


def _detect_style(text: str) -> str:
    low = text.lower()
    scores = {s: 0 for s in _STYLE_KEYWORDS}
    for style, kws in _STYLE_KEYWORDS.items():
        for kw in kws:
            if kw in low:
                scores[style] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "mixed"


def _detect_side(text: str) -> str:
    low = text.lower()
    for side, kws in _SIDE_KEYWORDS.items():
        for kw in kws:
            if kw in low:
                return side
    if "short" in low and "long" not in low:
        return "SHORT"
    if "long" in low and "short" not in low:
        return "LONG"
    return "BOTH"


def _detect_stops(text: str) -> Tuple[float, float, int]:
    """Parse stop/take ATR and hold bars if mentioned; else defaults."""
    stop, take, hold = 1.5, 2.5, 12
    m = re.search(r"stop\s*(?:atr)?\s*[:=]?\s*([0-9]*\.?[0-9]+)", text.lower())
    if m:
        stop = float(m.group(1))
    m = re.search(r"take\s*(?:atr|profit)?\s*[:=]?\s*([0-9]*\.?[0-9]+)", text.lower())
    if m:
        take = float(m.group(1))
    m = re.search(r"hold\s*(?:bars?|periods?)?\s*[:=]?\s*(\d+)", text.lower())
    if m:
        hold = int(m.group(1))
    # RSI threshold override hint
    return stop, take, hold


def _rules_for_style(style: str, text: str) -> List[Rule]:
    templates = list(_STYLE_RULE_TEMPLATES.get(style, _STYLE_RULE_TEMPLATES["mixed"]))
    # RSI custom threshold
    m = re.search(r"rsi\s*(<|>|above|below)\s*(\d+(?:\.\d+)?)", text.lower())
    rules: List[Rule] = []
    used_rsi = False
    for ind, op, thr in templates[:4]:
        if ind == "rsi" and m and not used_rsi:
            op_raw = m.group(1)
            op = "<" if op_raw in ("<", "below") else ">"
            thr = float(m.group(2))
            used_rsi = True
        rules.append(Rule(indicator=ind, operator=op, threshold=float(thr), weight=1.0))
    if m and not used_rsi:
        op_raw = m.group(1)
        op = "<" if op_raw in ("<", "below") else ">"
        rules.append(Rule(indicator="rsi", operator=op, threshold=float(m.group(2)), weight=1.2))
    return rules[: cfg.MAX_RULES]


def idea_to_genome(
    idea: str,
    *,
    symbol: Optional[str] = None,
    name: Optional[str] = None,
) -> BotGenome:
    """Compile a natural-language idea into a BotGenome (candidate status)."""
    text = (idea or "").strip()
    if not text:
        text = "mixed momentum on nifty"

    sym = symbol or _detect_symbol(text)
    style = _detect_style(text)
    side = _detect_side(text)
    stop, take, hold = _detect_stops(text)
    rules = _rules_for_style(style, text)
    seq = int(time.time()) % 1000

    genome = BotGenome(
        bot_id=_uid("bot"),
        name=name or new_bot_name(style, 0, seq),
        symbol=sym,
        side_bias=side,
        rules=rules,
        stop_atr=round(stop, 2),
        take_atr=round(take, 2),
        hold_bars=int(hold),
        generation=0,
        style=style,
        status="candidate",
    )
    return genome


def queue_idea(
    idea: str,
    *,
    symbol: Optional[str] = None,
    run_exam_now: bool = False,
    enqueue_breed: bool = True,
) -> Dict[str, Any]:
    """
    Parse idea → genome → persist to ideas.jsonl + idea_queue.jsonl.
    Optionally run a single OOS exam immediately and/or enqueue a breed job.
    """
    swarm = AgentSwarm()
    swarm.begin_run("idea_ingest")
    swarm.think("researcher", f"Parsing idea: {idea[:80]}")
    swarm.work("researcher", "Compiling strategy genome")

    genome = idea_to_genome(idea, symbol=symbol)
    swarm.done("researcher", f"Genome {genome.name} ({genome.style}/{genome.side_bias})")

    record: Dict[str, Any] = {
        "idea_id": f"idea_{uuid.uuid4().hex[:10]}",
        "ts": time.time(),
        "idea": idea,
        "genome": genome.to_dict(),
        "queued_breed": bool(enqueue_breed),
        "exam": None,
    }

    store.save_idea(record)
    store.append_jsonl(_idea_queue_path(), {
        "idea_id": record["idea_id"],
        "bot_id": genome.bot_id,
        "symbol": genome.symbol,
        "style": genome.style,
        "ts": record["ts"],
        "action": "breed" if enqueue_breed else "hold",
    })
    store.upsert_bot(genome.to_dict())

    log_activity(
        f"Idea queued → {genome.name} [{genome.symbol}/{genome.style}]",
        level="IDEA",
        source="idea_agent",
        symbol=genome.symbol,
        bot_id=genome.bot_id,
        idea_id=record["idea_id"],
    )

    if enqueue_breed:
        swarm.work("breeder_analyst", f"Queue breed seed {genome.name}")
        _write_breed_job(genome, record["idea_id"])
        try:
            from engine.aite.daemon import enqueue_job

            job_id = enqueue_job("breed_cycle", {
                "idea": idea,
                "genome": genome.to_dict(),
                "symbols": [genome.symbol],
                "n_population": 48,
                "generations": 1,
                "deploy": True,
                "monitor": True,
            })
            record["job_id"] = job_id
        except Exception:
            pass
        swarm.done("breeder_analyst", f"Seeded {genome.bot_id}")
        try:
            from engine.aite.orchestra import Orchestra

            Orchestra(swarm).handoff("researcher", "breeder_analyst", f"Queued breed for {genome.name}")
        except Exception:
            pass

    if run_exam_now:
        swarm.work("risk", f"OOS exam {genome.name}")
        try:
            from engine.aite.exam import load_market_frame, run_exam
            from engine.aite.orderflow import normalize_chart_frame
            df = normalize_chart_frame(load_market_frame(genome.symbol))
            exam = run_exam(genome, df)
            record["exam"] = exam.to_dict()
            if exam.passed:
                genome.status = "exam"
                store.upsert_bot(genome.to_dict())
                swarm.done("risk", f"Exam PASSED fitness={exam.fitness:.3f}")
            else:
                swarm.done("risk", f"Exam FAIL: {exam.reason[:80]}")
            log_activity(
                f"Idea exam {genome.name}: {'PASS' if exam.passed else 'FAIL'}",
                level="EXAM",
                source="idea_agent",
                bot_id=genome.bot_id,
                passed=exam.passed,
                fitness=exam.fitness,
            )
        except Exception as exc:
            record["exam"] = {"error": str(exc)[:200]}
            swarm.error("risk", str(exc)[:160])

    swarm.finish_run(ok=True, message=f"Idea {record['idea_id']} ingested")
    return record


def _write_breed_job(genome: BotGenome, idea_id: str) -> None:
    """Drop a job file the daemon/runner can pick up — never raises."""
    try:
        jdir = _jobs_dir()
        jdir.mkdir(parents=True, exist_ok=True)
        path = jdir / f"breed_{idea_id}.json"
        store.write_json(path, {
            "type": "breed_seed",
            "idea_id": idea_id,
            "bot_id": genome.bot_id,
            "symbol": genome.symbol,
            "genome": genome.to_dict(),
            "ts": time.time(),
            "status": "queued",
        })
    except Exception:
        pass


def submit_idea_and_exam(idea: str, symbol: Optional[str] = None) -> Dict[str, Any]:
    """UI helper: always queue + run exam once."""
    return queue_idea(idea, symbol=symbol, run_exam_now=True, enqueue_breed=True)


def list_queued_ideas(limit: int = 50) -> List[Dict[str, Any]]:
    return store.read_jsonl(_idea_queue_path(), limit=limit)


def list_ideas(limit: int = 50) -> List[Dict[str, Any]]:
    return store.load_ideas(limit=limit)

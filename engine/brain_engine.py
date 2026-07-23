"""
ZERO Brain Engine
=================

A persistent, trainable knowledge base embedded in the ZERO trading terminal.

Architecture inspired by claude-obsidian's compound wiki pattern:
  - entries.json  : all knowledge entries (concepts, mental models, biases, market notes)
  - hot.json      : rolling 500-word context cache (most recent relevant knowledge)
  - daily_logs/   : per-day trading mental model snapshots (linked to prediction matrix)

The brain has NO external API calls — it is fully offline, private, and instant.
Bias detection uses keyword matching from the obsidian_integration_plan cognitive model.
"""

from __future__ import annotations

import os
import json
import datetime
import hashlib
import re
from typing import Optional

# ──────────────────────────────────────────────────────────────────────────────
#  Storage paths
# ──────────────────────────────────────────────────────────────────────────────
_BRAIN_DIR   = os.path.join(os.path.dirname(__file__), "..", "db", "brain")
_ENTRIES_PATH = os.path.join(_BRAIN_DIR, "entries.json")
_HOT_PATH     = os.path.join(_BRAIN_DIR, "hot.json")
_LOGS_DIR     = os.path.join(_BRAIN_DIR, "daily_logs")


# ──────────────────────────────────────────────────────────────────────────────
#  Cognitive bias patterns (from obsidian_integration_plan.txt Section 3 & 6)
# ──────────────────────────────────────────────────────────────────────────────
_BIAS_PATTERNS = {
    "FOMO":             ["fomo", "missed", "missed out", "fear of missing", "chased", "chasing",
                         "jumped in", "late entry", "already moved"],
    "Loss Aversion":    ["loss aversion", "can't take loss", "held too long", "didn't cut",
                         "averaging down", "hope trade", "holding loser"],
    "Overconfidence":   ["overconfident", "sure thing", "can't lose", "guaranteed", "obvious trade",
                         "no risk", "easy money"],
    "Revenge Trading":  ["revenge", "made it back", "got back", "recover loss", "doubled down",
                         "overtrade", "over-traded", "traded again after loss"],
    "Panic":            ["panic", "panic sold", "panic exited", "stop hit", "panic bought",
                         "fear", "scared out"],
    "Greed":            ["greed", "greedy", "held for more", "didn't book profit", "more profit",
                         "let it run too long", "too greedy"],
}

_ENTRY_TYPES = {
    "mental_model":  ["first principles", "inversion", "mental model", "framework", "rule",
                      "system", "strategy", "approach", "method", "process"],
    "market_note":   ["nifty", "banknifty", "sensex", "market", "index", "resistance",
                      "support", "level", "breakout", "breakdown", "trend", "range"],
    "post_market":   ["today", "session", "mistake", "deviated", "plan", "result",
                      "performance", "post market", "post-market", "end of day"],
    "bias_log":      list({kw for patterns in _BIAS_PATTERNS.values() for kw in patterns}),
    "concept":       [],  # fallback
}


# ──────────────────────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────────────────────
def _entry_id(text: str) -> str:
    return hashlib.sha1(text.strip().lower().encode()).hexdigest()[:12]


def _detect_type(text: str) -> str:
    lower = text.lower()
    for etype, keywords in _ENTRY_TYPES.items():
        if etype == "concept":
            continue
        for kw in keywords:
            if kw in lower:
                return etype
    return "concept"


def _detect_biases(text: str) -> list[str]:
    lower = text.lower()
    flagged = []
    for bias, keywords in _BIAS_PATTERNS.items():
        for kw in keywords:
            if kw in lower:
                flagged.append(bias)
                break
    return flagged


def _score_relevance(entry: dict, query: str) -> int:
    """Simple keyword relevance score."""
    score = 0
    lower = query.lower()
    words = set(re.findall(r"\w+", lower))
    content_lower = (entry.get("content", "") + " " + " ".join(entry.get("tags", []))).lower()
    for word in words:
        if len(word) > 3 and word in content_lower:
            score += 1
    return score


# ──────────────────────────────────────────────────────────────────────────────
#  BrainEngine
# ──────────────────────────────────────────────────────────────────────────────
class BrainEngine:
    """
    The ZERO Brain: a persistent, trainable knowledge base for the trading terminal.

    Inspired by the claude-obsidian compound wiki pattern and the ZERO Mental Model
    Engine architecture from obsidian_integration_plan.txt.
    """

    def __init__(self):
        os.makedirs(_BRAIN_DIR, exist_ok=True)
        os.makedirs(_LOGS_DIR, exist_ok=True)
        self._entries: list[dict] = []
        self._hot: dict = {}
        self._load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load(self):
        if os.path.exists(_ENTRIES_PATH):
            try:
                raw = json.loads(open(_ENTRIES_PATH).read())
                self._entries = raw.get("entries", [])
                self._hot = raw.get("hot", {})
            except (json.JSONDecodeError, IOError):
                self._entries = []
                self._hot = {}

    def _save(self):
        try:
            with open(_ENTRIES_PATH, "w") as f:
                json.dump({"entries": self._entries, "hot": self._hot, "version": "1.0"}, f, indent=2)
        except IOError:
            pass

    def _save_hot(self):
        try:
            with open(_HOT_PATH, "w") as f:
                json.dump(self._hot, f, indent=2)
        except IOError:
            pass

    # ── Core Operations ───────────────────────────────────────────────────────

    def ingest(self, text: str, source: str = "user") -> dict:
        """
        Teach the brain something new.
        Returns the new entry dict.
        """
        text = text.strip()
        if not text:
            return {}

        eid = _entry_id(text + datetime.datetime.now().isoformat())
        etype = _detect_type(text)
        biases = _detect_biases(text)
        tags = list({etype} | set(biases))

        entry = {
            "id": eid,
            "content": text,
            "source": source,
            "type": etype,
            "tags": tags,
            "biases": biases,
            "created": datetime.datetime.now().isoformat(timespec="seconds"),
            "date": datetime.date.today().isoformat(),
        }

        # Prepend so newest is first
        self._entries.insert(0, entry)

        # Cap at 500 entries (claude-obsidian SEEN_CAP pattern)
        if len(self._entries) > 500:
            self._entries = self._entries[:500]

        self._update_hot(entry)
        self._save()
        return entry

    def query(self, text: str, top_k: int = 5) -> list[dict]:
        """
        Search the brain for relevant knowledge.
        Returns top-k entries by relevance score.
        """
        if not text.strip():
            return self._entries[:top_k]

        scored = [(e, _score_relevance(e, text)) for e in self._entries]
        scored.sort(key=lambda x: (-x[1], x[0]["created"]))
        results = [e for e, s in scored if s > 0]

        # If nothing matched, return most recent
        if not results:
            return self._entries[:top_k]

        return results[:top_k]

    def get_recent(self, n: int = 5) -> list[dict]:
        """Return the N most recent entries."""
        return self._entries[:n]

    def get_hot_cache(self) -> dict:
        return self._hot

    def get_bias_summary(self) -> dict[str, int]:
        """Count bias occurrences across all entries."""
        counts: dict[str, int] = {b: 0 for b in _BIAS_PATTERNS}
        for e in self._entries:
            for b in e.get("biases", []):
                if b in counts:
                    counts[b] += 1
        return counts

    def get_bias_pct(self) -> dict[str, float]:
        """Bias as % of total entries (capped at 100%)."""
        total = max(len(self._entries), 1)
        counts = self.get_bias_summary()
        return {b: round(min(c / total * 100, 100), 1) for b, c in counts.items()}

    def get_entries_count(self) -> int:
        return len(self._entries)

    # ── Market Auto-Ingest (from prediction matrix) ───────────────────────────

    def export_daily_log(self, matrix: dict) -> dict:
        """
        Auto-populate today's mental model log from the prediction matrix.
        This is the 'Pre-Market Forecast' step from obsidian_integration_plan.txt.
        Returns today's log dict.
        """
        today = datetime.date.today().isoformat()
        log_path = os.path.join(_LOGS_DIR, f"{today}.json")

        forecasts = {}
        for idx in ["NIFTY 50", "BANKNIFTY", "SENSEX"]:
            d = (matrix or {}).get(idx) or {}
            if d:
                forecasts[idx] = {
                    "pred_open":  round(float(d.get("pred_open", 0) or 0), 2),
                    "pred_high":  round(float(d.get("pred_high", 0) or 0), 2),
                    "pred_low":   round(float(d.get("pred_low", 0) or 0), 2),
                    "confidence": round(float(d.get("confidence", 0) or 0), 1),
                }

        # Check if today's bias log entries exist
        today_biases: list[str] = []
        for e in self._entries:
            if e.get("date") == today and e.get("biases"):
                today_biases.extend(e["biases"])
        unique_biases = list(dict.fromkeys(today_biases))  # preserve order, dedupe

        log = {
            "date": today,
            "forecasts": forecasts,
            "biases_flagged": unique_biases,
            "score": self._compute_discipline_score(today),
            "entries_today": sum(1 for e in self._entries if e.get("date") == today),
        }

        try:
            with open(log_path, "w") as f:
                json.dump(log, f, indent=2)
        except IOError:
            pass

        return log

    def _compute_discipline_score(self, date_str: str) -> int:
        """
        Score 0–10. Starts at 10; each unique bias detected today costs 2 pts,
        each entry logged adds 0.5 pts (capped at +3). From plan Section 6.
        """
        biases_today: set[str] = set()
        entries_today = 0
        for e in self._entries:
            if e.get("date") == date_str:
                entries_today += 1
                for b in e.get("biases", []):
                    biases_today.add(b)

        score = 10.0
        score -= len(biases_today) * 2
        score += min(entries_today * 0.5, 3.0)
        return max(0, min(10, int(round(score))))

    def get_daily_log(self, date_str: Optional[str] = None) -> dict:
        """Load today's (or a specific date's) mental model log, merging Obsidian logs if present."""
        if date_str is None:
            date_str = datetime.date.today().isoformat()
        
        log = {"date": date_str, "forecasts": {}, "biases_flagged": [], "score": 10, "entries_today": 0}
        
        # 1. Try loading from local json log first
        log_path = os.path.join(_LOGS_DIR, f"{date_str}.json")
        if os.path.exists(log_path):
            try:
                local_log = json.loads(open(log_path).read())
                log.update(local_log)
            except (json.JSONDecodeError, IOError):
                pass
                
        # 2. Try merging values from matching Obsidian daily note if present
        try:
            from config import OBSIDIAN_VAULT_PATH
            obs_note_path = os.path.join(OBSIDIAN_VAULT_PATH, "01_Daily_Logs", f"{date_str}.md")
            if os.path.exists(obs_note_path):
                from engine.obsidian_sync import get_biases_and_score_from_obsidian
                obs_data = get_biases_and_score_from_obsidian(date_str)
                
                # Merge biases
                combined_biases = list(set(log.get("biases_flagged", []) + obs_data.get("biases_flagged", [])))
                log["biases_flagged"] = combined_biases
                
                # Apply custom score from Obsidian if it was modified (not default 10)
                obs_score = obs_data.get("score")
                if obs_score is not None and obs_score != 10:
                    log["score"] = obs_score
                elif obs_data.get("biases_flagged"):
                    # Recompute score based on the combined biases
                    log["score"] = self._compute_discipline_score_for_biases(date_str, log["biases_flagged"])
        except Exception:
            pass
            
        return log

    def _compute_discipline_score_for_biases(self, date_str: str, biases: list[str]) -> int:
        """Score 0-10 based on the provided list of biases and logged entry counts."""
        entries_today = sum(1 for e in self._entries if e.get("date") == date_str)
        score = 10.0
        score -= len(biases) * 2
        score += min(entries_today * 0.5, 3.0)
        return max(0, min(10, int(round(score))))

    # ── Hot Cache (claude-obsidian hot.md pattern) ────────────────────────────

    def _update_hot(self, latest_entry: dict):
        """Keep a rolling 500-word context snapshot of recent brain activity."""
        recent = self._entries[:5]
        self._hot = {
            "updated": datetime.datetime.now().isoformat(timespec="seconds"),
            "recent_facts": [e["content"][:120] for e in recent],
            "recent_types": [e["type"] for e in recent],
            "recent_biases": list({b for e in recent for b in e.get("biases", [])}),
            "total_entries": len(self._entries),
            "last_entry_type": latest_entry.get("type", "concept"),
        }
        self._save_hot()

    # ── Delete / Clear ────────────────────────────────────────────────────────

    def delete_entry(self, eid: str) -> bool:
        before = len(self._entries)
        self._entries = [e for e in self._entries if e["id"] != eid]
        if len(self._entries) < before:
            self._save()
            return True
        return False

    def clear_all(self):
        self._entries = []
        self._hot = {}
        self._save()


# ── Module-level singleton ────────────────────────────────────────────────────
_brain: Optional[BrainEngine] = None


def get_brain() -> BrainEngine:
    """Return the module-level singleton (created once per process)."""
    global _brain
    if _brain is None:
        _brain = BrainEngine()
    return _brain

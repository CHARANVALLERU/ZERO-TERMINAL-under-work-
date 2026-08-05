"""
ZERO ENGINE — Agent Debate Layer
=================================

Optional LLM-driven bull-vs-bear debate inspired by the TradingAgents
framework (https://github.com/tauricresearch/tradingagents), layered on top
of the heuristic 4-agent consensus in ``engine/multi_agent_consensus.py``.

Flow (TradingAgents-style):
  1. Bull Researcher argues FOR the predicted move.
  2. Bear Researcher rebuts the bull case.
  3. Risk Manager + Portfolio Manager synthesize the final verdict.

The LLM path uses Google Gemini via the same discovery pattern as
``engine/gemini_chat.py``: ``GEMINI_API_KEY`` env var, lazy import of the
legacy ``google.generativeai`` SDK first, then the new ``google.genai`` SDK.
``google-generativeai`` is OPTIONAL — with no SDK or no key the module
returns a deterministic offline pseudo-debate (``llm_used=False``) derived
from the consensus engine's scoring style, so it is fully functional with
only the core deps (numpy/pandas/requests — none of which are even needed
here). No network calls happen at import time.

Every debate appends one JSON line to ``db/agent_decisions.jsonl`` so a
future orchestrator can score verdicts against realized OHLC.

Usage:
    from engine.agent_debate import debate
    result = debate("NIFTY", prediction_dict, news_items=news,
                    sentiment_data=sent, option_chain=oc)
"""

from __future__ import annotations

import datetime
import json
import math
import os
from typing import Any, Dict, List, Optional


# ── Env helpers (never raise at import time) ───────────────────────────────

def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, ""))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, ""))
    except (TypeError, ValueError):
        return default


# ── Paths ──────────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DECISION_LOG_PATH = os.getenv(
    "ZERO_DECISION_LOG", os.path.join(_ROOT, "db", "agent_decisions.jsonl")
)

# ── LLM configuration (env-overridable) ────────────────────────────────────
_API_KEY_ENV = "GEMINI_API_KEY"
_MODEL_NAME = os.getenv("ZERO_DEBATE_MODEL", "gemini-2.0-flash") or "gemini-2.0-flash"
_LLM_TEMPERATURE = _env_float("ZERO_DEBATE_TEMPERATURE", 0.4)
_LLM_MAX_TOKENS = _env_int("ZERO_DEBATE_MAX_TOKENS", 1024)
_MAX_NEWS_TITLES = _env_int("ZERO_DEBATE_MAX_NEWS", 5)

# ── Fallback thresholds (mirror multi_agent_consensus.py scoring style) ────
_VIX_MODERATE = _env_float("ZERO_DEBATE_VIX_MODERATE", 18.0)
_VIX_HIGH = _env_float("ZERO_DEBATE_VIX_HIGH", 24.0)
_VIX_EXTREME = _env_float("ZERO_DEBATE_VIX_EXTREME", 30.0)
_PCR_BULL = _env_float("ZERO_DEBATE_PCR_BULL", 0.7)
_PCR_BEAR = _env_float("ZERO_DEBATE_PCR_BEAR", 1.3)
_MIN_CONVICTION = _env_float("ZERO_DEBATE_MIN_CONVICTION", 0.12)
_GAP_SIGNAL_PCT = _env_float("ZERO_DEBATE_GAP_SIGNAL_PCT", 0.15)

# Headline keyword sets — same style as FundamentalAnalyst in the consensus engine
_BULL_KEYWORDS = (
    "growth", "stimulus", "cut", "expansion", "rally", "surge",
    "record", "beat", "upgrade", "inflow",
)
_BEAR_KEYWORDS = (
    "hike", "inflation", "war", "deficit", "tightening", "slowdown",
    "crash", "miss", "downgrade", "outflow", "fear",
)

_RISK_LEVELS = ("LOW", "MODERATE", "HIGH", "EXTREME")
_ACTIONS = ("LONG", "SHORT", "WAIT")

# Prediction-dict keys surfaced into LLM context (label, key)
_PRED_KEYS = (
    ("spot_close", "spot close"),
    ("spot", "spot"),
    ("prev_close", "previous close"),
    ("pred_open", "predicted open"),
    ("pred_high", "predicted high"),
    ("pred_low", "predicted low"),
    ("pred_close", "predicted close"),
    ("atr", "ATR"),
    ("vix", "VIX"),
)


# ── Small numeric / parsing utilities (module-private, never raise) ───────

def _num(value: Any, default: float = 0.0) -> float:
    """Coerce anything to a finite float, else ``default``."""
    try:
        if value is None or isinstance(value, bool):
            return default
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(min(value, hi), lo)


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """
    Robustly pull the first JSON object out of an LLM response:
    strip ``` fences, take first '{' to last '}', json.loads.
    Returns None on any failure (caller retries once).
    """
    if not text or not isinstance(text, str):
        return None
    cleaned = text.strip()

    # Strip a wrapping markdown fence (```json ... ``` or ``` ... ```)
    if cleaned.startswith("```"):
        first_nl = cleaned.find("\n")
        if first_nl != -1:
            cleaned = cleaned[first_nl + 1:]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]

    # Drop any remaining fence lines
    if "```" in cleaned:
        cleaned = "\n".join(
            ln for ln in cleaned.splitlines() if not ln.strip().startswith("```")
        )

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(cleaned[start:end + 1])
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _parse_case_payload(data: Dict[str, Any]) -> tuple:
    """Validate a researcher payload -> (arguments list, strength 0..1)."""
    args_raw = data.get("arguments", [])
    if isinstance(args_raw, str):
        args_raw = [args_raw]
    args: List[str] = []
    if isinstance(args_raw, list):
        for a in args_raw:
            s = str(a).strip()
            if s:
                args.append(s[:240])
            if len(args) >= 8:
                break
    strength = _clamp(_num(data.get("strength"), 0.5), 0.0, 1.0)
    return args, round(strength, 3)


def _default_kill_condition(action: str, pred_low: float, pred_high: float) -> str:
    """Explicit invalidation trigger used by the fallback and by LLM-default filling."""
    if action == "LONG":
        return (
            f"thesis invalid below pred_low {pred_low:.2f}"
            if pred_low > 0
            else "thesis invalid on breakdown below predicted range low"
        )
    if action == "SHORT":
        return (
            f"thesis invalid above pred_high {pred_high:.2f}"
            if pred_high > 0
            else "thesis invalid on breakout above predicted range high"
        )
    triggers = []
    if pred_high > 0:
        triggers.append(f"breakout above pred_high {pred_high:.2f}")
    if pred_low > 0:
        triggers.append(f"breakdown below pred_low {pred_low:.2f}")
    return "no trade; re-evaluate on " + (
        " or ".join(triggers) if triggers else "a fresh catalyst"
    )


def _parse_pm_payload(data: Dict[str, Any], prediction: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the Risk Manager + Portfolio Manager payload with safe defaults."""
    pred_low = _num(prediction.get("pred_low"))
    pred_high = _num(prediction.get("pred_high"))

    risk_level = str(data.get("risk_level", "MODERATE")).upper().strip()
    if risk_level not in _RISK_LEVELS:
        risk_level = "MODERATE"

    notes_raw = data.get("risk_notes", data.get("notes", []))
    if isinstance(notes_raw, str):
        notes_raw = [notes_raw]
    notes = (
        [str(n).strip()[:200] for n in notes_raw if str(n).strip()][:6]
        if isinstance(notes_raw, list)
        else []
    )
    if not notes:
        notes = ["LLM risk synthesis returned no specific notes."]

    action = str(data.get("action", "WAIT")).upper().strip()
    if action not in _ACTIONS:
        action = "WAIT"

    conviction = round(_clamp(_num(data.get("conviction"), 0.3), 0.0, 1.0), 3)

    kill = str(data.get("kill_condition", "")).strip()
    if not kill:
        kill = _default_kill_condition(action, pred_low, pred_high)

    size = round(_clamp(_num(data.get("position_size_hint_pct"), 0.0), 0.0, 25.0), 1)

    reasoning = str(data.get("reasoning", "")).strip() or "LLM portfolio manager verdict."

    return {
        "risk_assessment": {"risk_level": risk_level, "notes": notes},
        "pm_verdict": {
            "action": action,
            "conviction": conviction,
            "kill_condition": kill[:300],
            "position_size_hint_pct": size,
            "reasoning": reasoning[:600],
        },
    }


def _emergency_result(index_name: str, prediction: Any) -> Dict[str, Any]:
    """Last-resort valid-schema result — the public API never raises."""
    return {
        "bull_case": {
            "arguments": ["Debate unavailable — defaulting to a neutral stance."],
            "strength": 0.0,
        },
        "bear_case": {
            "arguments": ["Debate unavailable — defaulting to a neutral stance."],
            "strength": 0.0,
        },
        "risk_assessment": {
            "risk_level": "MODERATE",
            "notes": ["Debate engine error; treat all signals with caution."],
        },
        "pm_verdict": {
            "action": "WAIT",
            "conviction": 0.0,
            "kill_condition": "no trade — debate engine error",
            "position_size_hint_pct": 0.0,
            "reasoning": f"Agent debate for {index_name} failed; safe WAIT fallback returned.",
        },
        "rounds": 0,
        "llm_used": False,
        "model": None,
    }


class AgentDebateEngine:
    """
    Bull-vs-bear debate engine with an optional Gemini LLM path and a
    deterministic offline fallback. All public methods return fallback
    dicts on any error — they never raise.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self._api_key = api_key if api_key is not None else os.getenv(_API_KEY_ENV, "")
        self._model_name = model or _MODEL_NAME
        self._client: Any = None
        self._old_model: Any = None
        self._use_old_sdk = False
        self._llm_checked = False
        self._llm_available = False

    # ── Public API ────────────────────────────────────────────────────────

    def debate(
        self,
        index_name: str,
        prediction: dict,
        news_items: list | None = None,
        sentiment_data: dict | None = None,
        option_chain: dict | None = None,
    ) -> dict:
        """
        Run a 3-round bull/bear/PM debate over a prediction dict.

        Returns the verdict schema (see module docstring / README):
        bull_case, bear_case, risk_assessment, pm_verdict, rounds,
        llm_used, model. Never raises — falls back to the deterministic
        heuristic debate, then to a safe WAIT result.
        """
        try:
            idx = str(index_name or "UNKNOWN")
            pred = prediction if isinstance(prediction, dict) else {}
            news = news_items if isinstance(news_items, list) else []
            sent = sentiment_data if isinstance(sentiment_data, dict) else {}
            oc = option_chain if isinstance(option_chain, dict) else {}

            result: Optional[Dict[str, Any]] = None
            if self._ensure_llm():
                try:
                    result = self._llm_debate(idx, pred, news, sent, oc)
                except Exception as exc:
                    print(f"[agent_debate] LLM debate failed, using fallback: {exc}")
                    result = None
            if result is None:
                result = self._fallback_debate(idx, pred, news, sent, oc)

            self._log_decision(idx, pred, result)
            return result
        except Exception as exc:
            print(f"[agent_debate] debate() error: {exc}")
            return _emergency_result(str(index_name or "UNKNOWN"), prediction)

    def is_llm_available(self) -> bool:
        """True when a Gemini SDK is importable and a key is configured."""
        try:
            return self._ensure_llm()
        except Exception:
            return False

    @staticmethod
    def load_decision_log(limit: int | None = None) -> list:
        """Class-level alias for the module function."""
        return load_decision_log(limit)

    @staticmethod
    def verdict_accuracy_placeholder() -> dict:
        """Class-level alias for the module function."""
        return verdict_accuracy_placeholder()

    # ── LLM discovery (mirrors engine/gemini_chat.py) ────────────────────

    def _ensure_llm(self) -> bool:
        if self._llm_checked:
            return self._llm_available
        self._llm_checked = True
        if not self._api_key:
            return False
        # Preferred: legacy google.generativeai SDK
        try:
            import google.generativeai as _legacy_genai  # type: ignore

            _legacy_genai.configure(api_key=self._api_key)
            self._old_model = _legacy_genai.GenerativeModel(self._model_name)
            self._use_old_sdk = True
            self._llm_available = True
            return True
        except ImportError:
            pass
        except Exception as exc:
            print(f"[agent_debate] legacy SDK init failed: {exc}")
        # Fallback: new google.genai SDK
        try:
            from google import genai as _new_genai  # type: ignore

            self._client = _new_genai.Client(api_key=self._api_key)
            self._use_old_sdk = False
            self._llm_available = True
            return True
        except ImportError:
            pass
        except Exception as exc:
            print(f"[agent_debate] genai client init failed: {exc}")
        self._llm_available = False
        return False

    def _llm_generate(self, prompt: str) -> Optional[str]:
        """Single text generation on whichever SDK initialized; None on failure."""
        try:
            if self._use_old_sdk:
                if self._old_model is None:
                    return None
                try:
                    resp = self._old_model.generate_content(
                        prompt,
                        generation_config={
                            "temperature": _LLM_TEMPERATURE,
                            "max_output_tokens": _LLM_MAX_TOKENS,
                        },
                    )
                except TypeError:
                    resp = self._old_model.generate_content(prompt)
                text = getattr(resp, "text", None)
                return text.strip() if isinstance(text, str) and text.strip() else None

            if self._client is None:
                return None
            config = None
            try:
                from google.genai import types as _genai_types  # type: ignore

                config = _genai_types.GenerateContentConfig(
                    temperature=_LLM_TEMPERATURE,
                    max_output_tokens=_LLM_MAX_TOKENS,
                )
            except Exception:
                config = None
            if config is not None:
                resp = self._client.models.generate_content(
                    model=self._model_name, contents=prompt, config=config
                )
            else:
                resp = self._client.models.generate_content(
                    model=self._model_name, contents=prompt
                )
            text = getattr(resp, "text", None)
            return text.strip() if isinstance(text, str) and text.strip() else None
        except Exception as exc:
            print(f"[agent_debate] LLM generate failed: {exc}")
            return None

    def _llm_json_call(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Generate + extract JSON; retry once with a 'valid JSON only' re-prompt."""
        for attempt in (0, 1):
            p = prompt if attempt == 0 else (
                prompt
                + "\n\nReturn only valid JSON. No markdown fences, no commentary, no trailing text."
            )
            data = _extract_json(self._llm_generate(p) or "")
            if data is not None:
                return data
        return None

    # ── LLM debate (3 structured rounds) ─────────────────────────────────

    def _compact_context(
        self,
        index_name: str,
        prediction: Dict[str, Any],
        news_items: list,
        sentiment_data: Dict[str, Any],
        option_chain: Dict[str, Any],
    ) -> str:
        """Small prompt context: prediction numbers, top-5 news titles, PCR/OI walls."""
        lines = [f"Index: {index_name}"]
        for key, label in _PRED_KEYS:
            f = _num(prediction.get(key), default=float("nan"))
            if not math.isnan(f):
                lines.append(f"{label}: {f:.2f}")

        spot = (
            _num(prediction.get("spot_close"))
            or _num(prediction.get("spot"))
            or _num(prediction.get("prev_close"))
        )
        pred_open = _num(prediction.get("pred_open"))
        pred_close = _num(prediction.get("pred_close"))
        gap_pct = ((pred_open - spot) / spot * 100.0) if (spot > 0 and pred_open > 0) else 0.0
        oc_move = ((pred_close - pred_open) / pred_open * 100.0) if (pred_open > 0 and pred_close > 0) else 0.0
        drift = gap_pct + oc_move
        direction = "UP" if drift > 0.1 else ("DOWN" if drift < -0.1 else "FLAT")
        lines.append(
            f"Predicted session direction: {direction} "
            f"(gap {gap_pct:+.2f}%, open-to-close {oc_move:+.2f}%)"
        )

        if sentiment_data:
            s = _num(sentiment_data.get("score"), default=float("nan"))
            if not math.isnan(s):
                lines.append(f"News sentiment score: {s:+.3f}")

        titles: List[str] = []
        for item in news_items:
            if isinstance(item, dict):
                t = str(item.get("title", "")).strip()
                if t:
                    titles.append(t[:120])
            if len(titles) >= _MAX_NEWS_TITLES:
                break
        if titles:
            lines.append("Top news headlines:")
            lines.extend(f"  - {t}" for t in titles)

        if option_chain:
            bits = []
            for k in ("pcr", "max_pain", "call_wall", "put_wall", "resistance", "support"):
                v = option_chain.get(k)
                if isinstance(v, bool):
                    continue
                if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v)):
                    bits.append(f"{k}={v}")
                elif isinstance(v, str) and v:
                    bits.append(f"{k}={v}")
            if bits:
                lines.append("Option chain: " + ", ".join(bits))
        return "\n".join(lines)

    def _llm_debate(
        self,
        index_name: str,
        prediction: Dict[str, Any],
        news_items: list,
        sentiment_data: Dict[str, Any],
        option_chain: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """3 forced-JSON LLM rounds. Returns None if any stage fails (caller falls back)."""
        context = self._compact_context(index_name, prediction, news_items, sentiment_data, option_chain)

        # Round 1 — Bull Researcher argues FOR the predicted move
        bull_prompt = (
            f"You are the BULL RESEARCHER on an Indian index trading desk.\n"
            f"Defend the predicted move for {index_name}. Build the strongest long thesis using ONLY the data below.\n\n"
            f"{context}\n\n"
            "Rules: 3-6 arguments, one sentence each, cite the numbers. Respond with JSON only, no markdown:\n"
            '{"arguments": ["...", "..."], "strength": <float 0-1>}'
        )
        bull_data = self._llm_json_call(bull_prompt)
        if not bull_data:
            return None
        bull_args, bull_strength = _parse_case_payload(bull_data)
        if not bull_args:
            return None

        # Round 2 — Bear Researcher rebuts
        bear_prompt = (
            f"You are the BEAR RESEARCHER on an Indian index trading desk.\n"
            f"Rebut the bull case and attack the predicted move for {index_name}. Use ONLY the data below.\n\n"
            f"{context}\n\n"
            f"BULL CASE TO REBUT (strength {bull_strength:.2f}):\n"
            f"{json.dumps(bull_args, ensure_ascii=False)}\n\n"
            "Rules: 3-6 arguments, one sentence each, cite the numbers. Respond with JSON only, no markdown:\n"
            '{"arguments": ["...", "..."], "strength": <float 0-1>}'
        )
        bear_data = self._llm_json_call(bear_prompt)
        if not bear_data:
            return None
        bear_args, bear_strength = _parse_case_payload(bear_data)
        if not bear_args:
            return None

        # Round 3 — Risk Manager + Portfolio Manager synthesize the verdict
        pm_prompt = (
            f"You are the RISK MANAGER and PORTFOLIO MANAGER of an Indian index desk.\n"
            f"Weigh this debate and issue the final verdict for {index_name}.\n\n"
            f"{context}\n\n"
            f"BULL CASE (strength {bull_strength:.2f}):\n"
            f"{json.dumps(bull_args, ensure_ascii=False)}\n\n"
            f"BEAR CASE (strength {bear_strength:.2f}):\n"
            f"{json.dumps(bear_args, ensure_ascii=False)}\n\n"
            "Respond with JSON only, no markdown:\n"
            '{"risk_level": "LOW"|"MODERATE"|"HIGH"|"EXTREME", "risk_notes": ["..."], '
            '"action": "LONG"|"SHORT"|"WAIT", "conviction": <float 0-1>, '
            '"kill_condition": "<one-sentence invalidation trigger>", '
            '"position_size_hint_pct": <float 0-10>, "reasoning": "<2-3 sentences>"}'
        )
        pm_data = self._llm_json_call(pm_prompt)
        if not pm_data:
            return None
        parsed = _parse_pm_payload(pm_data, prediction)

        return {
            "bull_case": {"arguments": bull_args, "strength": bull_strength},
            "bear_case": {"arguments": bear_args, "strength": bear_strength},
            "risk_assessment": parsed["risk_assessment"],
            "pm_verdict": parsed["pm_verdict"],
            "rounds": 3,
            "llm_used": True,
            "model": self._model_name,
        }

    # ── Deterministic offline fallback ────────────────────────────────────

    def _fallback_debate(
        self,
        index_name: str,
        prediction: Dict[str, Any],
        news_items: list,
        sentiment_data: Dict[str, Any],
        option_chain: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Pseudo-debate derived from multi_agent_consensus.py scoring style:
        clamped factor scores, keyword counting, VIX risk tiers, and a
        risk-penalized blended verdict with an explicit kill condition.
        """
        pred_open = _num(prediction.get("pred_open"))
        pred_high = _num(prediction.get("pred_high"))
        pred_low = _num(prediction.get("pred_low"))
        pred_close = _num(prediction.get("pred_close"))
        spot = (
            _num(prediction.get("spot_close"))
            or _num(prediction.get("spot"))
            or _num(prediction.get("prev_close"))
            or _num(prediction.get("last_close"))
        )
        if spot <= 0:
            spot = pred_close if pred_close > 0 else pred_open
        vix = _num(prediction.get("vix"), 15.0)
        if vix <= 0:
            vix = 15.0
        atr = _num(prediction.get("atr"))
        sent_score = _num(sentiment_data.get("score")) if sentiment_data else 0.0
        pcr = _num(option_chain.get("pcr"), 1.0) if option_chain else 1.0
        if pcr <= 0:
            pcr = 1.0

        gap_pct = ((pred_open - spot) / spot * 100.0) if (spot > 0 and pred_open > 0) else 0.0
        oc_move_pct = ((pred_close - pred_open) / pred_open * 100.0) if (pred_open > 0 and pred_close > 0) else 0.0
        range_pct = (
            ((pred_high - pred_low) / spot * 100.0)
            if (spot > 0 and pred_high > pred_low > 0)
            else 0.0
        )
        atr_pct = (atr / spot * 100.0) if (spot > 0 and atr > 0) else 0.0

        bull_args: List[str] = []
        bear_args: List[str] = []
        bull_points = 0.0
        bear_points = 0.0

        # 1) News sentiment factor
        if sent_score > 0.05:
            bull_args.append(f"News sentiment net positive ({sent_score:+.2f}) supports upside follow-through.")
            bull_points += min(sent_score, 1.0) * 0.25
        elif sent_score < -0.05:
            bear_args.append(f"News sentiment net negative ({sent_score:+.2f}) pressures the tape lower.")
            bear_points += min(abs(sent_score), 1.0) * 0.25

        # 2) Headline keyword skew (FundamentalAnalyst-style keyword counting)
        titles: List[str] = []
        for item in news_items[:20]:
            if isinstance(item, dict):
                t = str(item.get("title", "")).strip()
                if t:
                    titles.append(t)
        bull_hits = sum(1 for t in titles if any(k in t.lower() for k in _BULL_KEYWORDS))
        bear_hits = sum(1 for t in titles if any(k in t.lower() for k in _BEAR_KEYWORDS))
        if bull_hits > bear_hits:
            bull_args.append(f"Headline flow skews bullish ({bull_hits} positive vs {bear_hits} negative catalysts).")
            bull_points += 0.1 * min(bull_hits - bear_hits, 3)
        elif bear_hits > bull_hits:
            bear_args.append(f"Headline flow skews bearish ({bear_hits} negative vs {bull_hits} positive catalysts).")
            bear_points += 0.1 * min(bear_hits - bull_hits, 3)

        # 3) Option PCR signal
        if pcr < _PCR_BULL:
            bull_args.append(f"Option PCR {pcr:.2f} below {_PCR_BULL:.2f} — call-side dominance favors the bulls.")
            bull_points += 0.2
        elif pcr > _PCR_BEAR:
            bear_args.append(f"Option PCR {pcr:.2f} above {_PCR_BEAR:.2f} — put-heavy positioning signals downside hedging.")
            bear_points += 0.2
        elif pcr > 1.0:
            bear_points += 0.05
        elif pcr < 1.0:
            bull_points += 0.05

        # 4) Gap momentum
        if gap_pct > _GAP_SIGNAL_PCT:
            bull_args.append(f"Predicted gap-up open (+{gap_pct:.2f}%) shows overnight demand.")
            bull_points += min(gap_pct / 1.5, 1.0) * 0.25
        elif gap_pct < -_GAP_SIGNAL_PCT:
            bear_args.append(f"Predicted gap-down open ({gap_pct:.2f}%) shows overnight supply.")
            bear_points += min(abs(gap_pct) / 1.5, 1.0) * 0.25

        # 5) Open-to-close drift
        if oc_move_pct > 0.05:
            bull_args.append(f"Model projects intraday gains into the close (+{oc_move_pct:.2f}%).")
            bull_points += min(oc_move_pct, 1.0) * 0.15
        elif oc_move_pct < -0.05:
            bear_args.append(f"Model projects an intraday fade into the close ({oc_move_pct:.2f}%).")
            bear_points += min(abs(oc_move_pct), 1.0) * 0.15

        # 6) Volatility regime
        if vix >= _VIX_HIGH:
            bear_args.append(f"Elevated volatility (VIX {vix:.1f}) raises whipsaw and ruin risk.")
            bear_points += 0.2
        elif vix >= _VIX_MODERATE:
            bear_args.append(f"Moderate volatility (VIX {vix:.1f}) argues for reduced sizing.")
            bear_points += 0.1
        else:
            bull_args.append(f"Low volatility (VIX {vix:.1f}) favors orderly trend continuation.")
            bull_points += 0.15

        # 7) OI walls
        support = None
        resistance = None
        if option_chain:
            support = option_chain.get("support") or option_chain.get("put_wall")
            resistance = option_chain.get("resistance") or option_chain.get("call_wall")
        if support:
            bull_args.append(f"Put-side OI wall near {support} provides a demand floor.")
            bull_points += 0.1
        if resistance:
            bear_args.append(f"Call-side OI wall near {resistance} caps upside absent a volatility expansion.")
            bear_points += 0.1

        if not bull_args:
            bull_args.append("No dominant bullish catalysts detected in the heuristic scan.")
        if not bear_args:
            bear_args.append("No dominant bearish catalysts detected in the heuristic scan.")

        bull_strength = round(min(bull_points, 1.0), 3)
        bear_strength = round(min(bear_points, 1.0), 3)

        # Risk assessment (RiskManager-style VIX tiers + range/ATR stress)
        risk_notes: List[str] = []
        if vix >= _VIX_EXTREME:
            risk_notes.append(f"VIX {vix:.1f} in an extreme regime — gap risk dominates all setups.")
        elif vix >= _VIX_HIGH:
            risk_notes.append(f"VIX {vix:.1f} elevated — widen stops and cut position size.")
        elif vix >= _VIX_MODERATE:
            risk_notes.append(f"VIX {vix:.1f} moderate — standard risk-defined parameters apply.")
        else:
            risk_notes.append(f"VIX {vix:.1f} calm — favorable regime for trend strategies.")
        if range_pct >= 3.0:
            risk_notes.append(f"Predicted day range {range_pct:.2f}% of spot is abnormally wide.")
        elif range_pct >= 2.0:
            risk_notes.append(f"Predicted day range {range_pct:.2f}% of spot is elevated.")
        if atr_pct >= 2.5:
            risk_notes.append(f"ATR {atr_pct:.2f}% of spot signals structural volatility.")

        if vix >= _VIX_EXTREME or range_pct >= 4.0:
            risk_level = "EXTREME"
        elif vix >= _VIX_HIGH or range_pct >= 3.0 or atr_pct >= 3.0:
            risk_level = "HIGH"
        elif vix >= _VIX_MODERATE or range_pct >= 2.0 or atr_pct >= 2.0:
            risk_level = "MODERATE"
        else:
            risk_level = "LOW"

        # Portfolio Manager verdict — blended sign/strength with risk penalty
        net = bull_strength - bear_strength
        if risk_level in ("HIGH", "EXTREME"):
            net *= 0.7  # consensus-engine style risk penalty
        conviction = round(min(abs(net), 1.0), 3)

        if risk_level == "EXTREME" or conviction < _MIN_CONVICTION:
            action = "WAIT"
        elif net > 0:
            action = "LONG"
        else:
            action = "SHORT"

        kill = _default_kill_condition(action, pred_low, pred_high)

        size = conviction * 10.0
        if risk_level == "MODERATE":
            size *= 0.7
        elif risk_level == "HIGH":
            size *= 0.4
        elif risk_level == "EXTREME":
            size = 0.0
        if action == "WAIT":
            size = 0.0
        size = round(min(size, 10.0), 1)

        reasoning = (
            f"Offline heuristic debate for {index_name}: bull {bull_strength:.2f} vs bear "
            f"{bear_strength:.2f} (net {net:+.2f} after {risk_level} risk adjustment); "
            f"gap {gap_pct:+.2f}%, PCR {pcr:.2f}, VIX {vix:.1f}, sentiment {sent_score:+.2f} "
            f"-> {action} at {conviction:.2f} conviction."
        )

        return {
            "bull_case": {"arguments": bull_args, "strength": bull_strength},
            "bear_case": {"arguments": bear_args, "strength": bear_strength},
            "risk_assessment": {"risk_level": risk_level, "notes": risk_notes},
            "pm_verdict": {
                "action": action,
                "conviction": conviction,
                "kill_condition": kill,
                "position_size_hint_pct": size,
                "reasoning": reasoning,
            },
            "rounds": 3,
            "llm_used": False,
            "model": None,
        }

    # ── Decision log ──────────────────────────────────────────────────────

    def _log_decision(self, index_name: str, prediction: Dict[str, Any], result: Dict[str, Any]) -> None:
        """Append one JSON line to db/agent_decisions.jsonl. Failures are swallowed."""
        try:
            os.makedirs(os.path.dirname(_DECISION_LOG_PATH), exist_ok=True)
            snapshot = {
                k: (_num(prediction.get(k)) if prediction.get(k) is not None else None)
                for k in ("pred_open", "pred_high", "pred_low", "pred_close")
            }
            entry = {
                "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                "index": str(index_name),
                "prediction_snapshot": snapshot,
                "verdict": result.get("pm_verdict", {}),
                "llm_used": bool(result.get("llm_used", False)),
                "model": result.get("model"),
            }
            with open(_DECISION_LOG_PATH, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as exc:
            print(f"[agent_debate] decision log write failed: {exc}")


# ── Decision log module functions ──────────────────────────────────────────

def load_decision_log(limit: int | None = None) -> list:
    """
    Read db/agent_decisions.jsonl into a list of dicts (oldest first).
    ``limit`` returns the most recent N entries. Never raises.
    """
    entries: List[Dict[str, Any]] = []
    try:
        if not os.path.exists(_DECISION_LOG_PATH):
            return entries
        with open(_DECISION_LOG_PATH, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if isinstance(obj, dict):
                    entries.append(obj)
    except Exception as exc:
        print(f"[agent_debate] decision log read failed: {exc}")
        return []
    if isinstance(limit, int) and not isinstance(limit, bool):
        if limit <= 0:
            return []
        return entries[-limit:]
    return entries


def verdict_accuracy_placeholder() -> dict:
    """
    Stub for a future accuracy scorer: an orchestrator can join each logged
    verdict's prediction_snapshot against that session's realized OHLC and
    compute hit-rates per action. Never raises.
    """
    pending = 0
    try:
        pending = len(load_decision_log())
    except Exception:
        pending = 0
    return {
        "status": "needs_actuals_join",
        "logged_decisions": pending,
        "note": "Join db/agent_decisions.jsonl verdicts against realized OHLC to score accuracy.",
    }


# ── Convenience singleton + module-level debate() ─────────────────────────
_default_engine: Optional[AgentDebateEngine] = None


def _get_default_engine() -> AgentDebateEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = AgentDebateEngine()
    return _default_engine


def debate(index_name: str, prediction: dict, **kw: Any) -> dict:
    """Module-level one-shot debate using the shared default engine. Never raises."""
    try:
        return _get_default_engine().debate(index_name, prediction, **kw)
    except Exception as exc:
        print(f"[agent_debate] module debate() error: {exc}")
        return _emergency_result(str(index_name or "UNKNOWN"), prediction)

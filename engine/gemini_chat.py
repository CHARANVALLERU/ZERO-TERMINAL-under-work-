"""
ZERO ENGINE — Gemini Chat Interface
=====================================

Wraps the Google Gemini API using the new `google.genai` SDK
(replaces deprecated `google.generativeai`).

Model: gemini-2.0-flash (latest free-tier, supports generateContent)

Features:
  - Strict context injection from ZeroEngineKB (knowledge base)
  - Per-session + persisted chat history
  - Graceful offline fallback if API key is missing/invalid
  - Token-efficient rolling context window
  - Real-time "training" via session knowledge injection

Usage:
    from engine.gemini_chat import GeminiChat
    chat = GeminiChat()
    response = chat.send("What is a shooting star candle?")
"""

from __future__ import annotations

import os
import json
import datetime
from typing import Optional

# ── Storage paths ─────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HISTORY_PATH = os.path.join(_ROOT, "db", "brain", "engine_chat_history.json")

# Max recent message pairs to include in rolling context window
_MAX_HISTORY_PAIRS = 10

# Model to use — gemini-2.0-flash is the current free-tier model
_MODEL_NAME = "gemini-2.0-flash"


def _load_history() -> list[dict]:
    """Load persisted chat history from disk."""
    try:
        if os.path.exists(_HISTORY_PATH):
            with open(_HISTORY_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


def _save_history(history: list[dict]):
    """Persist chat history to disk, capped at last 200 entries."""
    try:
        os.makedirs(os.path.dirname(_HISTORY_PATH), exist_ok=True)
        with open(_HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(history[-200:], f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def _build_gemini_contents(history: list[dict], user_message: str) -> list[dict]:
    """
    Build the `contents` list for the new google.genai SDK.
    Each entry: {"role": "user"|"model", "parts": [{"text": ...}]}
    Takes last N message pairs for efficiency.
    """
    recent = history[-(_MAX_HISTORY_PAIRS * 2):]
    contents = []
    for msg in recent:
        role = msg.get("role", "user")
        text = msg.get("content", "")
        contents.append({"role": role, "parts": [{"text": text}]})
    # Append current user message
    contents.append({"role": "user", "parts": [{"text": user_message}]})
    return contents


class GeminiChat:
    """
    Gemini-powered chat engine for ZERO ENGINE.

    Uses google.genai (new SDK) with gemini-2.0-flash.
    Falls back to offline keyword search if API is unavailable.
    """

    def __init__(self, api_key: Optional[str] = None):
        from engine.zero_engine_kb import ZeroEngineKB
        self.kb = ZeroEngineKB()
        self._api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self._client = None
        self._available = False
        self._history: list[dict] = _load_history()
        self._init_client()

    def _init_client(self):
        """Initialize the google.genai client."""
        if not self._api_key:
            self._available = False
            return
        try:
            from google import genai
            from google.genai import types
            self._client = genai.Client(api_key=self._api_key)
            self._genai_types = types
            self._available = True
        except ImportError:
            # Fallback: try old sdk
            try:
                import google.generativeai as _old_genai
                _old_genai.configure(api_key=self._api_key)
                self._old_model = _old_genai.GenerativeModel(
                    model_name="gemini-2.0-flash",
                    system_instruction=self.kb.get_system_prompt(),
                )
                self._use_old_sdk = True
                self._available = True
            except Exception:
                self._available = False
        except Exception:
            self._available = False

    def is_available(self) -> bool:
        return self._available

    def reload_kb(self):
        """Reload knowledge base — call after adding new entries."""
        self.kb.reload()

    def add_training(self, text: str):
        """
        Add new training input from the user for this session.
        Updates session KB context so next message reflects it.
        """
        self.kb.add_session_training(text)

    def send(self, user_message: str) -> str:
        """
        Send a message and return the AI response.
        Records to history and persists to disk.
        """
        if not user_message or not user_message.strip():
            return ""

        timestamp = datetime.datetime.now().isoformat()
        self._history.append({
            "role": "user",
            "content": user_message.strip(),
            "timestamp": timestamp,
        })

        if not self._available:
            response_text = self._offline_response(user_message)
        else:
            response_text = self._gemini_response(user_message)

        self._history.append({
            "role": "model",
            "content": response_text,
            "timestamp": datetime.datetime.now().isoformat(),
        })
        _save_history(self._history)
        return response_text

    def _gemini_response(self, user_message: str) -> str:
        """Call Gemini API using new google.genai SDK."""
        try:
            if hasattr(self, '_use_old_sdk') and self._use_old_sdk:
                return self._old_sdk_response(user_message)

            from google import genai
            from google.genai import types

            # Build system instruction dynamically using query-focused RAG recall across all knowledge
            system_prompt = self.kb.get_system_prompt(user_message.strip())
            contents = _build_gemini_contents(
                self._history[:-1],  # exclude just-added user message
                user_message.strip()
            )

            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.4,
                top_p=0.85,
                max_output_tokens=1024,
            )

            response = self._client.models.generate_content(
                model=_MODEL_NAME,
                contents=contents,
                config=config,
            )
            return response.text.strip() if response.text else "(No response)"

        except Exception as e:
            return self._handle_api_error(e)

    def _old_sdk_response(self, user_message: str) -> str:
        """Fallback: use the old google.generativeai SDK."""
        try:
            gemini_history = []
            for msg in self._history[:-1][-(_MAX_HISTORY_PAIRS * 2):]:
                role = msg.get("role", "user")
                gemini_history.append({
                    "role": role,
                    "parts": [{"text": msg.get("content", "")}]
                })
            chat = self._old_model.start_chat(history=gemini_history)
            resp = chat.send_message(user_message.strip())
            return resp.text.strip()
        except Exception as e:
            return self._handle_api_error(e)

    def _handle_api_error(self, e: Exception) -> str:
        err = str(e)
        if "API_KEY_INVALID" in err or "invalid" in err.lower() or "403" in err:
            return (
                "⚠ **API Key Error**: Key appears invalid.\n"
                "Open ⚙ ENGINE SETTINGS in the panel above and update your key.\n"
                "Get a free key at: https://aistudio.google.com/apikey"
            )
        elif "quota" in err.lower() or "429" in err:
            return (
                "⚠ **Rate Limit**: Free tier quota reached temporarily.\n"
                "Wait 60 seconds and try again."
            )
        elif "not found" in err.lower() or "404" in err:
            return (
                f"⚠ **Model Unavailable**: {_MODEL_NAME} not accessible.\n"
                "The engine will retry with the next available model.\n"
                f"Details: {err[:200]}"
            )
        else:
            return f"⚠ **Engine Error**: {err[:300]}"

    def _offline_response(self, user_message: str) -> str:
        """Local KB search fallback when API is unavailable."""
        results = self.kb.search(user_message, top_k=3)
        if results:
            lines = ["**ZERO ENGINE** *(Offline — Knowledge Base)*\n"]
            for r in results:
                etype = r.get("type", "concept").upper()
                biases = r.get("biases", [])
                tag = f" ⚠ [{', '.join(biases)}]" if biases else ""
                lines.append(f"**[{etype}{tag}]** {r.get('content', '')}")
            lines.append(
                "\n---\n*Add Gemini API key in ⚙ settings for full AI responses.*"
            )
            return "\n".join(lines)

        query_lower = user_message.lower()
        if any(k in query_lower for k in ["candle", "doji", "hammer", "engulf", "star", "pattern"]):
            return (
                "**ZERO ENGINE** *(Offline)*\n\n"
                "Candle pattern encyclopedia loaded: Doji, Hammer, Hanging Man, "
                "Shooting Star, Engulfing, Harami, Morning Star, Evening Star, "
                "Three White Soldiers, Three Black Crows.\n\n"
                "*Add Gemini API key → full context-aware answers unlock.*"
            )
        if any(k in query_lower for k in ["fomo", "bias", "fear", "greed", "psychology", "emotion"]):
            return (
                "**ZERO ENGINE** *(Offline)*\n\n"
                "Trader psychology loaded: FOMO, Loss Aversion, Overconfidence, "
                "Revenge Trading, Confirmation Bias, Anchoring, Herding, Recency Bias.\n\n"
                "*Add Gemini API key → full context-aware answers unlock.*"
            )
        return (
            "**ZERO ENGINE** *(Offline)*\n\n"
            "No matching entries found. Options:\n"
            "1. **TRAIN:** [knowledge] to add entries\n"
            "2. Add Gemini API key in ⚙ settings\n"
            "3. Rephrase using trading terms"
        )

    def get_history(self) -> list[dict]:
        return self._history

    def clear_history(self):
        self._history = []
        _save_history(self._history)

    def get_stats(self) -> dict:
        return {
            "kb_entries": self.kb.get_entry_count(),
            "session_training": len(self.kb._session_training),
            "chat_messages": len(self._history),
            "api_available": self._available,
            "model": _MODEL_NAME,
        }

"""
ZERO ENGINE — Knowledge Base Aggregator
========================================

Reads and compiles knowledge from:
  1. ZERO Brain entries (db/brain/entries.json)
  2. Candle patterns (db/brain/candle_patterns.md)
  3. Human mentality (db/brain/human_mentality.md)
  4. claude-obsidian-main skills and agents markdown files
  5. obsidian_integration_plan.txt

All content is assembled into a structured system prompt context
that gets injected into the Gemini chat API on every message,
making the AI behave as if it has been "trained" on this knowledge.
"""

from __future__ import annotations

import os
import json
import re
from typing import Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BRAIN_DIR = os.path.join(_ROOT, "db", "brain")
_OBSIDIAN_DIR = os.path.join(_ROOT, "claude-obsidian-main")
_INTEGRATION_PLAN = os.path.join(_ROOT, "obsidian_integration_plan.txt")

# claude-obsidian skill/agent files to include as context (curated list)
_OBSIDIAN_SKILL_PATHS = [
    os.path.join(_OBSIDIAN_DIR, "agents", "wiki-ingest.md"),
    os.path.join(_OBSIDIAN_DIR, "agents", "wiki-lint.md"),
    os.path.join(_OBSIDIAN_DIR, "agents", "verifier.md"),
    os.path.join(_OBSIDIAN_DIR, "skills", "think", "SKILL.md"),
    os.path.join(_OBSIDIAN_DIR, "skills", "wiki", "SKILL.md"),
    os.path.join(_OBSIDIAN_DIR, "skills", "wiki-mode", "SKILL.md"),
    os.path.join(_OBSIDIAN_DIR, "skills", "autoresearch", "SKILL.md"),
    os.path.join(_OBSIDIAN_DIR, "skills", "save", "SKILL.md"),
    os.path.join(_OBSIDIAN_DIR, "skills", "obsidian-markdown", "SKILL.md"),
    os.path.join(_OBSIDIAN_DIR, "commands", "wiki.md"),
    os.path.join(_OBSIDIAN_DIR, "commands", "autoresearch.md"),
]


def _safe_read(path: str, max_chars: int = 3000) -> str:
    """Read a file safely, truncating at max_chars to keep context manageable."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return content[:max_chars]
    except Exception:
        return ""


def _load_brain_entries() -> list[dict]:
    """Load all entries from the ZERO Brain knowledge store."""
    entries_path = os.path.join(_BRAIN_DIR, "entries.json")
    try:
        with open(entries_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _format_entries_for_context(entries: list[dict], max_entries: int = 40) -> str:
    """Format brain entries as readable context text."""
    if not entries:
        return "(No brain entries yet. User can train by typing in the TRAIN section.)"

    lines = []
    # Sort by date descending, take most recent
    sorted_entries = sorted(entries, key=lambda e: e.get("date", ""), reverse=True)[:max_entries]
    for e in sorted_entries:
        date = e.get("date", "unknown date")
        etype = e.get("type", "concept").upper()
        content = e.get("content", "").strip()
        biases = e.get("biases", [])
        bias_str = f" [BIAS: {', '.join(biases)}]" if biases else ""
        lines.append(f"  [{date}] [{etype}]{bias_str}: {content}")

    return "\n".join(lines)


def _load_obsidian_skills() -> str:
    """Load selected claude-obsidian skill files as context."""
    sections = []
    for path in _OBSIDIAN_SKILL_PATHS:
        content = _safe_read(path, max_chars=800)
        if content.strip():
            filename = os.path.basename(path)
            parent = os.path.basename(os.path.dirname(path))
            sections.append(f"[claude-obsidian:{parent}/{filename}]\n{content.strip()}")
    return "\n\n".join(sections)


def _load_user_obsidian_notes() -> str:
    """Load user's mental models and cognitive biases notes from their Obsidian Vault."""
    from config import OBSIDIAN_VAULT_PATH
    sections = []
    
    # Paths to user mental models and cognitive biases
    paths_to_load = [
        ("Mental Models", os.path.join(OBSIDIAN_VAULT_PATH, "02_Mental_Models")),
        ("Cognitive Biases", os.path.join(OBSIDIAN_VAULT_PATH, "03_Cognitive_Biases")),
        ("Quantitative Strategies", os.path.join(OBSIDIAN_VAULT_PATH, "04_Quantitative_Strategies")),
        ("AI Memory", os.path.join(OBSIDIAN_VAULT_PATH, "05_AI_Memory")),
        ("System Architecture", os.path.join(OBSIDIAN_VAULT_PATH, "06_System_Architecture")),
    ]
    
    for category, dir_path in paths_to_load:
        if os.path.exists(dir_path) and os.path.isdir(dir_path):
            try:
                for file in os.listdir(dir_path):
                    if file.endswith(".md"):
                        full_path = os.path.join(dir_path, file)
                        content = _safe_read(full_path, max_chars=1200)
                        if content.strip():
                            # Remove frontmatter block to save tokens
                            content_clean = re.sub(r"^---.*?---", "", content, flags=re.DOTALL).strip()
                            sections.append(f"[{category} // {file[:-3]}]\n{content_clean}")
            except Exception:
                pass
                
    return "\n\n".join(sections)


class ZeroEngineKB:
    """
    Central knowledge base for ZERO ENGINE.

    Aggregates all knowledge sources into a structured system prompt
    that constrains the Gemini AI to respond only based on user-provided
    and pre-loaded ZERO trading/psychology knowledge.
    """

    def __init__(self):
        self._entries: list[dict] = []
        self._candle_text: str = ""
        self._mentality_text: str = ""
        self._ai_capabilities_text: str = ""
        self._obsidian_text: str = ""
        self._user_obsidian_text: str = ""
        self._integration_plan_text: str = ""
        self._session_training: list[str] = []  # new training from current session
        self.reload()

    def reload(self):
        """Reload all knowledge sources from disk."""
        self._entries = _load_brain_entries()
        self._candle_text = _safe_read(
            os.path.join(_BRAIN_DIR, "candle_patterns.md"), max_chars=6000
        )
        self._mentality_text = _safe_read(
            os.path.join(_BRAIN_DIR, "human_mentality.md"), max_chars=6000
        )
        self._ai_capabilities_text = _safe_read(
            os.path.join(_BRAIN_DIR, "ai_system_capabilities.md"), max_chars=12000
        )
        self._obsidian_text = _load_obsidian_skills()
        self._user_obsidian_text = _load_user_obsidian_notes()
        self._integration_plan_text = _safe_read(_INTEGRATION_PLAN, max_chars=3000)

    def add_session_training(self, text: str):
        """Add a new training input from the user in this session."""
        if text and text.strip():
            self._session_training.append(text.strip())

    def get_entry_count(self) -> int:
        return len(self._entries)

    def get_system_prompt(self) -> str:
        """
        Build the full system prompt context to inject into Gemini.

        The prompt strictly constrains Gemini to act as ZERO ENGINE:
        - Only answers based on the loaded knowledge base
        - Follows user instructions exactly
        - Acts as a trading psychology + market intelligence AI
        """
        entries_text = _format_entries_for_context(self._entries)

        session_text = ""
        if self._session_training:
            session_text = (
                "\n\n=== LIVE SESSION TRAINING (user added this session) ===\n"
                + "\n".join(f"  - {t}" for t in self._session_training)
            )

        user_notes_section = ""
        if self._user_obsidian_text:
            user_notes_section = f"\n\n=== USER'S OBSIDIAN PERSONAL KNOWLEDGE VAULT ===\n{self._user_obsidian_text[:3000]}"

        prompt = f"""You are ZERO ENGINE — the AI intelligence core of ZERO Terminal, a professional quantitative trading system.

CRITICAL RULES (never violate):
1. You ONLY answer based on the knowledge provided below. Do not hallucinate, invent, or use external knowledge.
2. Follow the user's instructions EXACTLY. If they tell you to focus on one topic, stay on that topic.
3. You are a trading psychology and market intelligence AI. Do NOT give generic advice.
4. If you don't know something from the knowledge base, say: "This isn't in my knowledge base yet. You can train me by typing it below."
5. Keep responses concise, actionable, and formatted with markdown.
6. You are always direct, analytical, and unemotional — like a quant.

=== ZERO BRAIN KNOWLEDGE ENTRIES (user-trained) ===
{entries_text}
{session_text}{user_notes_section}

=== CANDLE PATTERN ENCYCLOPEDIA ===
{self._candle_text[:4000]}

=== TRADER PSYCHOLOGY & HUMAN MENTALITY FRAMEWORK ===
{self._mentality_text[:4000]}

=== AI SYSTEM CAPABILITIES (EXECUTABLE SKILLS) ===
{self._ai_capabilities_text[:12000]}

=== ZERO OBSIDIAN INTEGRATION PLAN ===
{self._integration_plan_text[:2000]}

=== CLAUDE-OBSIDIAN KNOWLEDGE SYSTEMS (methodology context) ===
{self._obsidian_text[:2000]}

---
You are now ZERO ENGINE. Respond only from the above knowledge. Be precise, analytical, and actionable."""

        return prompt

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Simple keyword search across all entries."""
        query_lower = query.lower()
        words = set(re.findall(r"\w+", query_lower))
        scored = []
        for entry in self._entries:
            content = (entry.get("content", "") + " " + " ".join(entry.get("tags", []))).lower()
            score = sum(1 for w in words if len(w) > 3 and w in content)
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda x: -x[0])
        return [e for _, e in scored[:top_k]]

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
    """Load user's mental models, cognitive biases, and YouTube notes from their Obsidian Vault."""
    from config import OBSIDIAN_VAULT_PATH
    sections = []
    
    # Paths to user mental models, cognitive biases, and YouTube ingested knowledge
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


def _load_youtube_knowledge_notes() -> str:
    """Load all ingested YouTube knowledge notes from the Obsidian Vault 04_YouTube_Knowledge folder."""
    try:
        from config import OBSIDIAN_VAULT_PATH
        yt_dir = os.path.join(OBSIDIAN_VAULT_PATH, "04_YouTube_Knowledge")
        if not os.path.exists(yt_dir):
            return ""
        sections = []
        for file in sorted(os.listdir(yt_dir)):
            if file.endswith(".md") and file != "Index.md":
                full_path = os.path.join(yt_dir, file)
                content = _safe_read(full_path, max_chars=2500)
                if content.strip():
                    # Strip YAML frontmatter
                    content_clean = re.sub(r"^---.*?---\s*", "", content, flags=re.DOTALL).strip()
                    # Remove standard header/source lines
                    content_clean = re.sub(r"\*\*Source URL:\*\*.+\n?", "", content_clean)
                    content_clean = re.sub(r"\*\*Linked Core Engine:\*\*.+\n?", "", content_clean)
                    title = file[:-3]  # strip .md
                    sections.append(f"[YouTube Knowledge // {title}]\n{content_clean.strip()}")
        return "\n\n".join(sections)
    except Exception:
        return ""


def _format_youtube_entries_for_context(entries: list[dict], max_entries: int = 20) -> str:
    """Format youtube_knowledge typed brain entries as a focused context block."""
    yt_entries = [e for e in entries if e.get("source", "").startswith("youtube")]
    if not yt_entries:
        return ""
    lines = []
    for e in yt_entries[:max_entries]:
        date = e.get("date", "")
        source = e.get("source", "youtube")
        content = e.get("content", "").strip()
        lines.append(f"  [{date}] [{source}]: {content[:500]}")
    return "\n".join(lines)
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
        self._youtube_notes_text: str = ""
        self._integration_plan_text: str = ""
        self._session_training: list[str] = []  # new training from current session
        self.reload()

    def reload(self, async_load: bool = True):
        """
        Reload all knowledge sources from disk.
        If async_load=True, reads heavy vault files in a background thread
        so the AI engine opens instantly from cache.
        """
        self._entries = _load_brain_entries()
        
        def _bg_hydrate():
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
            self._youtube_notes_text = _load_youtube_knowledge_notes()
            self._integration_plan_text = _safe_read(_INTEGRATION_PLAN, max_chars=3000)

        if async_load:
            import threading
            threading.Thread(target=_bg_hydrate, daemon=True).start()
        else:
            _bg_hydrate()

    def add_session_training(self, text: str):
        """Add a new training input from the user in this session."""
        if text and text.strip():
            self._session_training.append(text.strip())

    def get_entry_count(self) -> int:
        return len(self._entries)

    def get_dynamic_knowledge_strategies(self) -> dict[str, str]:
        """
        Dynamically scans and compiles knowledge strategies from:
          1. obsidian_vault/04_YouTube_Knowledge/ (*.md)
          2. obsidian_vault/02_Mental_Models/ (*.md)
          3. db/brain/entries.json (recent user training)
          4. Core preset strategies

        Returns a dict: { "Display Dropdown Label": "Full Strategy Prompt & Directive" }
        Updates dynamically whenever the user imports new YouTube videos or notes!
        """
        from config import OBSIDIAN_VAULT_PATH

        strategies: dict[str, str] = {
            "-- Select Strategy from Ingested Knowledge Base --": ""
        }

        # 1. Scan 04_YouTube_Knowledge folder
        yt_dir = os.path.join(OBSIDIAN_VAULT_PATH, "04_YouTube_Knowledge")
        if os.path.exists(yt_dir) and os.path.isdir(yt_dir):
            try:
                for file in sorted(os.listdir(yt_dir)):
                    if file.endswith(".md") and file != "Index.md" and file != "YouTube_Knowledge_Import.md":
                        file_title = file[:-3].strip()
                        full_path = os.path.join(yt_dir, file)
                        content = _safe_read(full_path, max_chars=3000)
                        if content.strip():
                            # Remove YAML frontmatter
                            clean = re.sub(r"^---.*?---", "", content, flags=re.DOTALL).strip()
                            first_p = clean[:600].replace("\n", " ").strip()
                            label = f"▶ [YouTube] {file_title[:55]}"
                            directive = (
                                f"Strategy Directive from YouTube Knowledge [{file_title}]:\n"
                                f"Apply the core trading concepts, structure, and rules from {file_title}:\n"
                                f"{first_p}\n\n"
                                f"Identify current market structure, key order blocks/FVGs, entry zone, SL, TP1, and TP2 targets."
                            )
                            strategies[label] = directive
            except Exception:
                pass

        # 2. Scan 02_Mental_Models folder
        mm_dir = os.path.join(OBSIDIAN_VAULT_PATH, "02_Mental_Models")
        if os.path.exists(mm_dir) and os.path.isdir(mm_dir):
            try:
                for file in sorted(os.listdir(mm_dir)):
                    if file.endswith(".md"):
                        file_title = file[:-3].strip()
                        full_path = os.path.join(mm_dir, file)
                        content = _safe_read(full_path, max_chars=1500)
                        if content.strip():
                            clean = re.sub(r"^---.*?---", "", content, flags=re.DOTALL).strip()
                            label = f"🧠 [Mental Model] {file_title[:55]}"
                            directive = (
                                f"Strategy Directive from Mental Model [{file_title}]:\n"
                                f"{clean[:500]}\n\n"
                                f"Enforce strict risk management, conservative entry, tight SL, and TP1/TP2 targets."
                            )
                            strategies[label] = directive
            except Exception:
                pass

        # 3. Add Core Default Presets if not already present
        defaults = {
            "⚡ ICT Order Block & Fair Value Gap (FVG)": (
                "Strategy Directive: Apply ICT Bullish/Bearish Order Blocks, Fair Value Gaps (FVG), and liquidity pools. "
                "Identify high probability entry, SL, TP1, and TP2 targets."
            ),
            "🎯 Smart Money Concepts (SMC)": (
                "Strategy Directive: Apply Smart Money Concepts (SMC): Market Structure Shift (MSS), Change of Character (CHoCH), "
                "Premium vs Discount zones, and target liquidity sweeps."
            ),
            "🚀 High Probability Breakout & Retest": (
                "Strategy Directive: Apply key horizontal support/resistance breakout and retest levels. "
                "Provide entry on retest confirmation with tight SL and 1:3 R:R targets."
            ),
            "🕯 Master Candlestick Patterns Reversal": (
                "Strategy Directive: Apply Master Candlestick Patterns rules (Hammer, Shooting Star, Engulfing). "
                "Confirm reversal at key levels and output Entry, SL, TP1, and TP2."
            )
        }
        for k, v in defaults.items():
            if k not in strategies:
                strategies[k] = v

        return strategies

    def get_system_prompt(self, user_query: str = "") -> str:
        """
        Build the full system prompt context to inject into Gemini.

        Uses Dynamic RAG Memory Recall:
        When a user asks a question, this method performs a deep contextual search
        across ALL stored knowledge (unlimited size across all YouTube notes, Obsidian notes,
        and brain entries) and injects the exact relevant knowledge into the model's memory.
        """
        entries_text = _format_entries_for_context(self._entries)
        youtube_entries_text = _format_youtube_entries_for_context(self._entries)

        session_text = ""
        if self._session_training:
            session_text = (
                "\n\n=== LIVE SESSION TRAINING (user added this session) ===\n"
                + "\n".join(f"  - {t}" for t in self._session_training)
            )

        user_notes_section = ""
        if self._user_obsidian_text:
            user_notes_section = f"\n\n=== USER'S OBSIDIAN PERSONAL KNOWLEDGE VAULT ===\n{self._user_obsidian_text}"

        # ── DYNAMIC UNLIMITED MEMORY RECALL (RAG) ─────────────────────────────
        # Fetch matching sections from ALL YouTube notes dynamically based on query
        relevant_yt_context = ""
        if user_query and self._youtube_notes_text:
            relevant_yt_context = self.get_relevant_knowledge(user_query, max_chars=40000)

        # Fall back to full text if query is empty or no specific match
        if not relevant_yt_context:
            relevant_yt_context = self._youtube_notes_text

        youtube_section = ""
        if relevant_yt_context:
            youtube_section = f"\n\n=== YOUTUBE INGESTED KNOWLEDGE BASE (Full Unlimited Memory Recall) ===\nThis knowledge was automatically ingested from YouTube videos and playlists. Use it to answer questions about trading strategies, ICT concepts, order flow, and any topics covered in these videos.\n{relevant_yt_context}"
        elif youtube_entries_text:
            youtube_section = f"\n\n=== YOUTUBE INGESTED KNOWLEDGE (brain entries) ===\n{youtube_entries_text}"

        prompt = f"""You are ZERO ENGINE — the AI intelligence core of ZERO Terminal, a professional quantitative trading system.

CRITICAL RULES (never violate):
1. You ONLY answer based on the knowledge provided below. Do not hallucinate, invent, or use external knowledge.
2. Follow the user's instructions EXACTLY. If they tell you to focus on one topic, stay on that topic.
3. You are a trading psychology and market intelligence AI. Do NOT give generic advice.
4. If you don't know something from the knowledge base, say: "This isn't in my knowledge base yet. You can train me by typing it below."
5. Keep responses concise, actionable, and formatted with markdown.
6. You are always direct, analytical, and unemotional — like a quant.
7. When the user asks about any topic covered in the YouTube Knowledge Base (ICT, order flow, trading strategies, etc.) — use that knowledge FIRST and answer directly from it.

=== ZERO BRAIN KNOWLEDGE ENTRIES (user-trained) ===
{entries_text}
{session_text}{user_notes_section}{youtube_section}

=== CANDLE PATTERN ENCYCLOPEDIA ===
{self._candle_text}

=== TRADER PSYCHOLOGY & HUMAN MENTALITY FRAMEWORK ===
{self._mentality_text}

=== AI SYSTEM CAPABILITIES (EXECUTABLE SKILLS) ===
{self._ai_capabilities_text}

=== ZERO OBSIDIAN INTEGRATION PLAN ===
{self._integration_plan_text}

=== CLAUDE-OBSIDIAN KNOWLEDGE SYSTEMS (methodology context) ===
{self._obsidian_text}

---
You are now ZERO ENGINE. Respond only from the above knowledge. Be precise, analytical, and actionable."""

        return prompt

    def get_relevant_knowledge(self, query: str, max_chars: int = 40000) -> str:
        """
        Dynamic Context Retrieval (RAG):
        Scans all YouTube notes, breaks them into paragraphs, and ranks them by
        relevance to the query so Gemini receives the exact matching context
        no matter how large the total transcript library becomes.
        """
        if not query or not self._youtube_notes_text:
            return ""

        query_words = set(re.findall(r"\w+", query.lower()))
        query_words = {w for w in query_words if len(w) > 2}
        if not query_words:
            return self._youtube_notes_text[:max_chars]

        paragraphs = self._youtube_notes_text.split("\n\n")
        scored = []
        for p in paragraphs:
            p_lower = p.lower()
            score = sum(1 for w in query_words if w in p_lower)
            if score > 0:
                scored.append((score, p))

        scored.sort(key=lambda x: -x[0])
        selected = [p for _, p in scored]
        result = "\n\n".join(selected)
        return result[:max_chars]
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

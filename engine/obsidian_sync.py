import os
import datetime
import re
import logging
from config import OBSIDIAN_VAULT_PATH

logger = logging.getLogger('ZERO_OBSIDIAN_SYNC')

def get_daily_log_path(date_str: str) -> str:
    """Get the path to today's daily log inside the Obsidian vault."""
    return os.path.join(OBSIDIAN_VAULT_PATH, "01_Daily_Logs", f"{date_str}.md")

def ensure_vault_structure():
    """Ensure that the Obsidian Vault directory structure and templates exist."""
    dirs = [
        os.path.join(OBSIDIAN_VAULT_PATH, "01_Daily_Logs"),
        os.path.join(OBSIDIAN_VAULT_PATH, "02_Mental_Models"),
        os.path.join(OBSIDIAN_VAULT_PATH, "03_Cognitive_Biases"),
        os.path.join(OBSIDIAN_VAULT_PATH, "04_YouTube_Knowledge"),
        os.path.join(OBSIDIAN_VAULT_PATH, "Templates"),
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)

    # Ensure 04_YouTube_Knowledge/Index.md exists and links to core engine
    yt_index = os.path.join(OBSIDIAN_VAULT_PATH, "04_YouTube_Knowledge", "Index.md")
    if not os.path.exists(yt_index):
        with open(yt_index, "w", encoding="utf-8") as f:
            f.write("---\naliases: [YouTube Knowledge Index, YouTube Ingestion Hub]\n"
                    "tags: [youtube, knowledge_base, index]\ntype: index\n---\n\n"
                    "# 📺 YouTube Knowledge Base Index\n\n"
                    "All converted YouTube video and playlist notes automatically link here "
                    "and connect to [[ZERO Brain Engine]] and [[ZERO]].\n\n"
                    "## 📚 Ingested Knowledge Notes\n")

    # Ensure ZERO Brain Engine.md exists at vault root as core graph hub
    brain_engine_note = os.path.join(OBSIDIAN_VAULT_PATH, "ZERO Brain Engine.md")
    if not os.path.exists(brain_engine_note):
        with open(brain_engine_note, "w", encoding="utf-8") as f:
            f.write("---\naliases: [ZERO Brain Engine, Knowledge Core, ZERO Core Engine]\n"
                    "tags: [core-engine, zero-brain, intelligence]\ntype: engine_core\n---\n\n"
                    "# 🧠 ZERO Brain Engine Core\n\n"
                    "The central intelligence hub for ZERO Market Intelligence Terminal.\n\n"
                    "## 🔗 Connected Subsystems\n"
                    "* [[00_Index_MOC]]\n"
                    "* [[01_Daily_Logs/Index]]\n"
                    "* [[02_Mental_Models/Index]]\n"
                    "* [[04_YouTube_Knowledge/Index]]\n"
                    "* [[05_AI_Memory/Index]]\n\n"
                    "## 🎥 Ingested YouTube Knowledge\n")

        
    # Create template daily note if not present
    template_path = os.path.join(OBSIDIAN_VAULT_PATH, "Templates", "daily_template.md")
    if not os.path.exists(template_path):
        template_content = """---
date: {{date}}
nifty_range: [{{nifty_low}}, {{nifty_high}}]
nifty_confidence: {{nifty_conf}}
biases_flagged: []
models_used: []
score: 0
---
# Trade & Mental Log - {{date}}

## 1. ZERO Pre-Market Quantitative Forecasts
* **Nifty 50:** Predicted Open: {{nifty_op}} | Clamped Range: {{nifty_low}} to {{nifty_high}}
* **Bank Nifty:** Predicted Open: {{bn_op}} | Clamped Range: {{bn_low}} to {{bn_high}}

## 2. Pre-Market Cognitive Thesis (My Execution Plan)
* What is my bias today?
* What rules am I bound to? (e.g. [[First Principles]], [[Probabilistic Thinking]])

## 3. Voice Transcription Input
<!-- VOICE_LOG_PLACEHOLDER -->
* (Local voice voice-notes or transcriptions get appended here)

## 4. Post-Market Calibration (Mistake Logging)
* Did I deviate from my targets?
* Did I experience [[FOMO]] or [[Loss Aversion]] today?
"""
        with open(template_path, "w", encoding="utf-8") as f:
            f.write(template_content)

def parse_markdown_frontmatter(file_content: str) -> dict:
    """Parse YAML frontmatter from markdown file content without external YAML package."""
    metadata = {}
    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", file_content, re.DOTALL)
    if not match:
        return metadata
    
    frontmatter_text = match.group(1)
    for line in frontmatter_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()
            
            # Parse list like [FOMO, Loss Aversion] or [24200.0, 24600.0]
            if val.startswith("[") and val.endswith("]"):
                list_content = val[1:-1].strip()
                if not list_content:
                    metadata[key] = []
                else:
                    items = [item.strip().strip("'\"") for item in list_content.split(",")]
                    typed_items = []
                    for item in items:
                        item_clean = re.sub(r"^\[\[(.*?)\]\]$", r"\1", item)  # clean wikilinks
                        try:
                            if "." in item_clean:
                                typed_items.append(float(item_clean))
                            else:
                                typed_items.append(int(item_clean))
                        except ValueError:
                            typed_items.append(item_clean)
                    metadata[key] = typed_items
            else:
                val_clean = val.strip("'\"")
                val_clean = re.sub(r"^\[\[(.*?)\]\]$", r"\1", val_clean)
                try:
                    if "." in val_clean:
                        metadata[key] = float(val_clean)
                    else:
                        metadata[key] = int(val_clean)
                except ValueError:
                    if val_clean.lower() == "true":
                        metadata[key] = True
                    elif val_clean.lower() == "false":
                        metadata[key] = False
                    elif val_clean.lower() == "null" or val_clean == "":
                        metadata[key] = None
                    else:
                        metadata[key] = val_clean
    return metadata

def serialize_frontmatter(metadata: dict) -> str:
    """Serialize a dict to YAML frontmatter format."""
    lines = ["---"]
    for k, v in metadata.items():
        if isinstance(v, list):
            items_str = ", ".join(f"{x}" if isinstance(x, (int, float)) else f"'{x}'" for x in v)
            lines.append(f"{k}: [{items_str}]")
        elif isinstance(v, bool):
            lines.append(f"{k}: {str(v).lower()}")
        elif v is None:
            lines.append(f"{k}: null")
        elif isinstance(v, (int, float)):
            lines.append(f"{k}: {v}")
        else:
            lines.append(f"{k}: '{v}'")
    lines.append("---")
    return "\n".join(lines)

def update_markdown_frontmatter(file_content: str, updates: dict) -> str:
    """Updates key-value pairs in the markdown file frontmatter, preserving others."""
    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", file_content, re.DOTALL)
    if not match:
        new_frontmatter = serialize_frontmatter(updates)
        return new_frontmatter + "\n" + file_content
        
    metadata = parse_markdown_frontmatter(file_content)
    metadata.update(updates)
    new_frontmatter = serialize_frontmatter(metadata)
    body_text = file_content[match.end():]
    return new_frontmatter + "\n" + body_text

def sync_forecast_to_obsidian(matrix: dict, date_str: str = None) -> bool:
    """
    Syncs pre-market predictions from the matrix to today's Obsidian daily log.
    If the daily note doesn't exist, it creates it using the template daily note.
    Otherwise, it updates its frontmatter and forecasts section.
    """
    if not date_str:
        date_str = datetime.date.today().isoformat()
        
    ensure_vault_structure()
    note_path = get_daily_log_path(date_str)
    
    nifty = matrix.get("NIFTY 50", {})
    bn = matrix.get("BANKNIFTY", {})
    sensex = matrix.get("SENSEX", {})
    
    # Check if there was an error in predictions
    if not nifty or "error" in nifty:
        logger.warning("Prediction matrix contains errors or is empty. Skipping Obsidian sync.")
        return False
        
    nifty_low = nifty.get("pred_low", 0.0)
    nifty_high = nifty.get("pred_high", 0.0)
    nifty_conf = nifty.get("confidence", 100.0)
    nifty_op = nifty.get("pred_open", 0.0)
    
    bn_low = bn.get("pred_low", 0.0) if bn else 0.0
    bn_high = bn.get("pred_high", 0.0) if bn else 0.0
    bn_conf = bn.get("confidence", 100.0) if bn else 100.0
    bn_op = bn.get("pred_open", 0.0) if bn else 0.0
    
    sensex_low = sensex.get("pred_low", 0.0) if sensex else 0.0
    sensex_high = sensex.get("pred_high", 0.0) if sensex else 0.0
    sensex_conf = sensex.get("confidence", 100.0) if sensex else 100.0
    sensex_op = sensex.get("pred_open", 0.0) if sensex else 0.0

    # Frontmatter updates
    fm_updates = {
        "date": date_str,
        "nifty_range": [nifty_low, nifty_high],
        "nifty_confidence": nifty_conf,
        "banknifty_range": [bn_low, bn_high],
        "sensex_range": [sensex_low, sensex_high],
    }
    
    if not os.path.exists(note_path):
        # Create from template
        template_path = os.path.join(OBSIDIAN_VAULT_PATH, "Templates", "daily_template.md")
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                content = f.read()
                
            # Replace template placeholders
            content = content.replace("{{date}}", date_str)
            content = content.replace("{{nifty_low}}", str(nifty_low))
            content = content.replace("{{nifty_high}}", str(nifty_high))
            content = content.replace("{{nifty_conf}}", str(nifty_conf))
            content = content.replace("{{nifty_op}}", str(nifty_op))
            content = content.replace("{{bn_op}}", str(bn_op))
            content = content.replace("{{bn_low}}", str(bn_low))
            content = content.replace("{{bn_high}}", str(bn_high))
            
            # Apply initial frontmatter
            content = update_markdown_frontmatter(content, fm_updates)
            
            with open(note_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"Created new Obsidian daily note: {note_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to create daily log note from template: {e}")
            return False
    else:
        # File exists, update it
        try:
            with open(note_path, "r", encoding="utf-8") as f:
                content = f.read()
                
            # 1. Update Frontmatter
            content = update_markdown_frontmatter(content, fm_updates)
            
            # 2. Update quantitative forecasts section (body)
            # Find the section and rewrite it
            forecasts_section = (
                f"## 1. ZERO Pre-Market Quantitative Forecasts\n"
                f"* **Nifty 50:** Predicted Open: {nifty_op} | Clamped Range: {nifty_low} to {nifty_high}\n"
                f"* **Bank Nifty:** Predicted Open: {bn_op} | Clamped Range: {bn_low} to {bn_high}\n"
                f"* **Sensex:** Predicted Open: {sensex_op} | Clamped Range: {sensex_low} to {sensex_high}"
            )
            
            pattern = r"## 1\. ZERO Pre-Market Quantitative Forecasts\r?\n.*?(?=\r?\n## 2\.)"
            if re.search(pattern, content, re.DOTALL):
                content = re.sub(pattern, forecasts_section, content, flags=re.DOTALL)
            
            with open(note_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"Updated Obsidian daily note: {note_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to update daily log note: {e}")
            return False

def get_biases_and_score_from_obsidian(date_str: str) -> dict:
    """Reads biases_flagged and score from Obsidian daily log frontmatter."""
    note_path = get_daily_log_path(date_str)
    if not os.path.exists(note_path):
        return {"biases_flagged": [], "score": 10}
        
    try:
        with open(note_path, "r", encoding="utf-8") as f:
            content = f.read()
        metadata = parse_markdown_frontmatter(content)
        
        # Clean and extract score
        score = metadata.get("score", 10)
        try:
            score = int(score)
        except (ValueError, TypeError):
            score = 10
            
        # Clean and extract biases
        biases = metadata.get("biases_flagged", [])
        if not isinstance(biases, list):
            biases = [biases] if biases else []
        
        # Clean up biases (e.g. remove empty strings, convert to string, strip whitespace)
        cleaned_biases = []
        for b in biases:
            if b:
                # Clean links and strings
                b_str = str(b).strip()
                b_str = re.sub(r"^\[\[(.*?)\]\]$", r"\1", b_str)
                if b_str:
                    cleaned_biases.append(b_str)
                    
        return {
            "biases_flagged": cleaned_biases,
            "score": score
        }
    except Exception as e:
        logger.error(f"Error parsing Obsidian note for biases/score: {e}")
        return {"biases_flagged": [], "score": 10}

def inject_voice_log(date_str: str, audio_path: str) -> bool:
    """
    Transcribes audio_path via local whisper or mock and appends under
    the <!-- VOICE_LOG_PLACEHOLDER --> block in Obsidian daily note.
    Also auto-detects cognitive biases and updates frontmatter.
    """
    ensure_vault_structure()
    note_path = get_daily_log_path(date_str)
    if not os.path.exists(note_path):
        # Create a blank note with template first
        sync_forecast_to_obsidian({}, date_str=date_str)
        
    # Attempt transcription
    transcription = ""
    try:
        # Try importing faster_whisper to process audio locally
        from faster_whisper import WhisperModel
        logger.info(f"Running Speech-To-Text via faster-whisper on {audio_path}")
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, info = model.transcribe(audio_path, beam_size=5)
        transcription = " ".join([seg.text for seg in segments]).strip()
    except ImportError:
        logger.warning("faster-whisper package not installed. Falling back to mock transcription.")
        # Mock transcription for testing / when whisper is absent
        filename = os.path.basename(audio_path).lower()
        if "fomo" in filename:
            transcription = "I was super anxious today because the market started moving and I chased it immediately. Major FOMO."
        elif "loss" in filename:
            transcription = "I held my losing trade for too long hoping it would bounce back, classic loss aversion mistake."
        else:
            transcription = "Logged voice entry: Completed session today. Managed rules reasonably well."
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        return False

    if not transcription:
        logger.warning("No transcription generated.")
        return False

    timestamp = datetime.datetime.now().strftime("%I:%M %p")
    voice_entry = f"\n* **Voice Log ({timestamp}):** {transcription}\n"

    try:
        with open(note_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Inject under placeholder
        placeholder = "<!-- VOICE_LOG_PLACEHOLDER -->"
        if placeholder in content:
            content = content.replace(placeholder, f"{placeholder}{voice_entry}")
        else:
            # Fallback append to end of file
            content += f"\n\n## 3. Voice Transcription Input\n{voice_entry}"
            
        # Detect biases in transcription text
        detected_biases = []
        from engine.brain_engine import _BIAS_PATTERNS
        lower_trans = transcription.lower()
        for bias_name, patterns in _BIAS_PATTERNS.items():
            for pat in patterns:
                if pat in lower_trans:
                    detected_biases.append(bias_name)
                    break
                    
        # Update frontmatter with detected biases if any
        if detected_biases:
            metadata = parse_markdown_frontmatter(content)
            existing_biases = metadata.get("biases_flagged", [])
            if not isinstance(existing_biases, list):
                existing_biases = [existing_biases] if existing_biases else []
            combined_biases = list(set(existing_biases + detected_biases))
            
            # Recompute discipline score automatically
            score = 10 - len(combined_biases) * 2
            # Add entry score bonus
            score = max(0, min(10, score))
            
            content = update_markdown_frontmatter(content, {
                "biases_flagged": combined_biases,
                "score": score
            })
            
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        logger.info(f"Injected voice note and updated biases in Obsidian note: {note_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to inject voice log: {e}")
        return False

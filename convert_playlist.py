import sys
import os

# ── Windows Asyncio Proactor ConnectionResetError (WinError 10054) Patch ──
if sys.platform == 'win32':
    try:
        import asyncio
        from asyncio.proactor_events import _ProactorBasePipeTransport
        _orig_call_conn_lost = _ProactorBasePipeTransport._call_connection_lost
        def _patched_call_conn_lost(self, exc=None):
            try:
                _orig_call_conn_lost(self, exc)
            except (ConnectionResetError, OSError):
                pass
        _ProactorBasePipeTransport._call_connection_lost = _patched_call_conn_lost
    except Exception:
        pass

import argparse
import subprocess
import re
import datetime
import json

DEFAULT_OUTPUT = "playlist_summary.md"

def write_status(msg):
    """Writes status messages to db/.yt_status.txt for Streamlit UI polling."""
    try:
        status_file = os.path.join(os.path.dirname(__file__), "db", ".yt_status.txt")
        os.makedirs(os.path.dirname(status_file), exist_ok=True)
        with open(status_file, "w", encoding="utf-8") as f:
            f.write(msg)
    except Exception:
        pass

def sanitize_filename(title):
    """Sanitizes string for valid filesystem / Obsidian note filename."""
    clean = re.sub(r'[\\/*?:"<>|]', "", title).strip()
    return clean if clean else "YouTube_Knowledge_Import"

def extract_video_id(url):
    """Extract YouTube video ID from any YouTube URL format."""
    patterns = [
        r'(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def extract_playlist_id(url):
    """Extract YouTube playlist ID from URL."""
    match = re.search(r'[?&]list=([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    return None

def get_playlist_videos(url):
    """
    Extracts ALL video entries from a YouTube playlist or single video URL.
    Iterates through all items using yt_dlp Python API.
    Returns: (playlist_title, list of video dicts [{'id', 'url', 'title'}])
    """
    write_status("Processing URL: Extracting video playlist metadata...")
    print(f"Extracting video list from target: {url}")

    playlist_id = extract_playlist_id(url)
    video_items = []
    main_title = None

    if playlist_id:
        clean_playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
        try:
            import yt_dlp
            ydl_opts = {
                'extract_flat': 'in_playlist',
                'skip_download': True,
                'quiet': True,
                'ignoreerrors': True,
                'no_warnings': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(clean_playlist_url, download=False)
                if info:
                    main_title = sanitize_filename(info.get('title') or f"Playlist_{playlist_id}")
                    entries = info.get('entries', []) or []
                    for entry in entries:
                        if not entry:
                            continue
                        vid_id = entry.get('id') or extract_video_id(entry.get('url', ''))
                        vid_title = entry.get('title') or f"Video {vid_id}"
                        if vid_id:
                            video_items.append({
                                'id': vid_id,
                                'url': f"https://www.youtube.com/watch?v={vid_id}",
                                'title': vid_title
                            })
        except Exception as e:
            print(f"yt-dlp module playlist extraction warning: {e}")

    # Fallback to subprocess yt-dlp if Python module yielded no items for playlist
    if playlist_id and not video_items:
        try:
            cmd = [sys.executable, "-m", "yt_dlp", "--no-warnings", "--flat-playlist", "--print", "%(id)s||%(title)s", url]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
            for line in lines:
                parts = line.split("||")
                vid_id = parts[0].strip()
                vid_title = parts[1].strip() if len(parts) > 1 else f"Video {vid_id}"
                if vid_id and len(vid_id) == 11:
                    video_items.append({
                        'id': vid_id,
                        'url': f"https://www.youtube.com/watch?v={vid_id}",
                        'title': vid_title
                    })
        except Exception as e:
            print(f"yt-dlp CLI playlist extraction fallback warning: {e}")

    # Single video case
    if not video_items:
        vid_id = extract_video_id(url)
        vid_title = "YouTube Video"
        try:
            cmd = [sys.executable, "-m", "yt_dlp", "--no-warnings", "--print", "title", "--playlist-items", "1", url]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
            if lines:
                vid_title = lines[-1]
        except Exception:
            pass

        if not main_title:
            main_title = sanitize_filename(vid_title)

        video_items.append({
            'id': vid_id or "unknown",
            'url': url,
            'title': vid_title
        })

    if not main_title:
        main_title = "YouTube_Knowledge_Import"

    print(f"Extracted {len(video_items)} video(s) for playlist/video '{main_title}'.")
    return main_title, video_items


def _parse_vtt_to_lines(vtt_text):
    """Parse a WebVTT subtitle string into (raw_pieces, formatted_lines)."""
    raw_pieces = []
    formatted = []
    seen = set()
    timestamp_re = re.compile(r'(\d+):(\d+):(\d+\.\d+)\s*-->')
    for line in vtt_text.splitlines():
        line = line.strip()
        # Skip headers, timestamps, empty, numeric cue IDs
        if not line or line.startswith('WEBVTT') or line.startswith('NOTE') or line.isdigit():
            continue
        ts_match = timestamp_re.match(line)
        if ts_match:
            continue
        # Strip inline timing/color tags: <00:00:01.000><c>text</c>
        clean = re.sub(r'<[^>]+>', '', line).strip()
        if not clean or clean in ('[Music]', '[Applause]', '[Laughter]'):
            continue
        if clean not in seen:
            seen.add(clean)
            raw_pieces.append(clean)
            formatted.append(f"[00:00] {clean}")
    return raw_pieces, formatted


def _parse_json3_to_lines(json_text):
    """Parse a YouTube json3 caption string into (raw_pieces, formatted_lines)."""
    raw_pieces = []
    formatted = []
    try:
        data = json.loads(json_text)
        for ev in data.get('events', []):
            segs = ev.get('segs', [])
            text = ' '.join(s.get('utf8', '') for s in segs).strip()
            start_ms = ev.get('tStartMs', 0)
            if text and text not in ('\n', '[Music]', '[Applause]', '[Laughter]'):
                start_sec = start_ms / 1000.0
                m, s = int(start_sec // 60), int(start_sec % 60)
                raw_pieces.append(text)
                formatted.append(f"[{m:02d}:{s:02d}] {text}")
    except Exception:
        pass
    return raw_pieces, formatted


def fetch_transcript(video_id):
    """
    Fetch transcript for a YouTube video using a 4-tier fallback strategy:
      Tier 1 — yt-dlp + Browser Cookies (Chrome → Edge → Firefox)
               Uses the user's actual logged-in browser session; YouTube sees it
               as a normal browser request, bypassing IP blocks completely.
      Tier 2 — yt-dlp direct info extraction + subtitle URL download (no cookies)
      Tier 3 — youtube-transcript-api (direct / Webshare proxy / Generic proxy)
      Tier 4 — yt-dlp audio download + faster-whisper local transcription (offline)
    Returns: (raw_lines_list, formatted_text_string, error_message)
    """
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    # ── Read proxy credentials ────────────────────────────────────────────────
    try:
        from config import (
            YOUTUBE_PROXY_USERNAME, YOUTUBE_PROXY_PASSWORD,
            YOUTUBE_PROXY_HTTP, YOUTUBE_PROXY_HTTPS
        )
    except ImportError:
        YOUTUBE_PROXY_USERNAME = os.getenv("YOUTUBE_PROXY_USERNAME", os.getenv("WEBSHARE_PROXY_USERNAME", ""))
        YOUTUBE_PROXY_PASSWORD = os.getenv("YOUTUBE_PROXY_PASSWORD", os.getenv("WEBSHARE_PROXY_PASSWORD", ""))
        YOUTUBE_PROXY_HTTP = os.getenv("YOUTUBE_PROXY_HTTP", os.getenv("HTTP_PROXY", ""))
        YOUTUBE_PROXY_HTTPS = os.getenv("YOUTUBE_PROXY_HTTPS", os.getenv("HTTPS_PROXY", ""))

    proxy_url = None
    if YOUTUBE_PROXY_USERNAME and YOUTUBE_PROXY_PASSWORD:
        proxy_url = f"http://{YOUTUBE_PROXY_USERNAME}:{YOUTUBE_PROXY_PASSWORD}@p.webshare.io:80"
    elif YOUTUBE_PROXY_HTTP:
        proxy_url = YOUTUBE_PROXY_HTTP

    # ── Helper: download a caption URL and return raw text ───────────────────
    def _download_caption_url(url):
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                              'AppleWebKit/537.36 (KHTML, like Gecko) '
                              'Chrome/124.0.0.0 Safari/537.36'
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read().decode('utf-8', errors='ignore')
        except Exception:
            return None

    # ── Helper: extract best subtitle URL from yt-dlp info dict ─────────────
    def _best_sub_url(info):
        caps = {}
        for key in ('automatic_captions', 'subtitles'):
            caps.update(info.get(key) or {})
        for lang in ('en', 'en-orig', 'en-US', 'en-GB'):
            cap_list = caps.get(lang)
            if cap_list:
                for fmt in ('json3', 'srv1', 'vtt', 'ttml'):
                    url = next((c['url'] for c in cap_list if c.get('ext') == fmt), None)
                    if url:
                        return url, fmt
        if caps:
            first = next(iter(caps.values()))
            if first:
                return first[0].get('url'), first[0].get('ext', 'vtt')
        return None, None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # TIER 1 — yt-dlp with Browser Cookies (Chrome → Edge → Firefox → Brave)
    #           Reads from the user's locally installed browser; YouTube treats
    #           the request as coming from a real browser session — no IP block.
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    browsers = [('chrome',), ('edge',), ('firefox',), ('brave',), ('opera',)]
    for browser_tuple in browsers:
        browser_name = browser_tuple[0]
        try:
            import yt_dlp
            print(f"  [*] Tier 1: trying yt-dlp with {browser_name} cookies for {video_id}...")
            ydl_opts = {
                'skip_download': True,
                'quiet': True,
                'no_warnings': True,
                'cookiesfrombrowser': browser_tuple,
                'writeautomaticsub': True,
                'writesubtitles': True,
                'subtitleslangs': ['en', 'en-orig'],
                'subtitlesformat': 'json3/vtt/best',
            }
            if proxy_url:
                ydl_opts['proxy'] = proxy_url

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                if info:
                    sub_url, fmt = _best_sub_url(info)
                    if sub_url:
                        content = _download_caption_url(sub_url)
                        if content:
                            if fmt == 'json3' or content.startswith('{'):
                                raw, lines = _parse_json3_to_lines(content)
                            else:
                                raw, lines = _parse_vtt_to_lines(content)
                            if lines:
                                print(f"  [+] Tier 1 SUCCESS via {browser_name} cookies ({len(lines)} lines)")
                                return raw, "\n".join(lines), None
        except Exception as e1:
            print(f"  [!] Tier 1 {browser_name} cookies notice: {e1}")
            continue

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # TIER 2 — yt-dlp info extraction (no cookies) + subtitle URL download
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    try:
        import yt_dlp
        print(f"  [*] Tier 2: yt-dlp no-cookie caption fetch for {video_id}...")
        ydl_opts2 = {'skip_download': True, 'quiet': True, 'no_warnings': True}
        if proxy_url:
            ydl_opts2['proxy'] = proxy_url
        with yt_dlp.YoutubeDL(ydl_opts2) as ydl:
            info = ydl.extract_info(video_url, download=False)
            if info:
                sub_url, fmt = _best_sub_url(info)
                if sub_url:
                    content = _download_caption_url(sub_url)
                    if content:
                        if fmt == 'json3' or content.startswith('{'):
                            raw, lines = _parse_json3_to_lines(content)
                        else:
                            raw, lines = _parse_vtt_to_lines(content)
                        if lines:
                            print(f"  [+] Tier 2 SUCCESS via yt-dlp no-cookie ({len(lines)} lines)")
                            return raw, "\n".join(lines), None
    except Exception as e2:
        print(f"  [!] Tier 2 yt-dlp no-cookie notice: {e2}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # TIER 3 — youtube-transcript-api (direct / Webshare proxy / Generic proxy)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        proxy_config_obj = None
        try:
            from youtube_transcript_api.proxies import WebshareProxyConfig, GenericProxyConfig
            if YOUTUBE_PROXY_USERNAME and YOUTUBE_PROXY_PASSWORD:
                proxy_config_obj = WebshareProxyConfig(
                    proxy_username=YOUTUBE_PROXY_USERNAME,
                    proxy_password=YOUTUBE_PROXY_PASSWORD
                )
            elif YOUTUBE_PROXY_HTTP:
                proxy_config_obj = GenericProxyConfig(
                    http_url=YOUTUBE_PROXY_HTTP,
                    https_url=YOUTUBE_PROXY_HTTPS or YOUTUBE_PROXY_HTTP
                )
        except Exception:
            pass

        print(f"  [*] Tier 3: youtube-transcript-api for {video_id}...")
        if proxy_config_obj:
            api = YouTubeTranscriptApi(proxy_config=proxy_config_obj)
        else:
            api = YouTubeTranscriptApi()

        try:
            snippets = api.fetch(video_id)
        except AttributeError:
            snippets = YouTubeTranscriptApi.get_transcript(video_id)

        if snippets:
            lines, raw = [], []
            for s in snippets:
                text = (s.get('text') if isinstance(s, dict) else getattr(s, 'text', '')).strip()
                start = (s.get('start') if isinstance(s, dict) else getattr(s, 'start', 0.0)) or 0.0
                if not text or text in ('[Music]', '[Applause]', '[Laughter]'):
                    continue
                m, sec = int(start // 60), int(start % 60)
                lines.append(f"[{m:02d}:{sec:02d}] {text}")
                raw.append(text)
            if lines:
                print(f"  [+] Tier 3 SUCCESS via youtube-transcript-api ({len(lines)} lines)")
                return raw, "\n".join(lines), None
    except Exception as e3:
        print(f"  [!] Tier 3 youtube-transcript-api notice: {e3}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # TIER 4 — yt-dlp audio download + faster-whisper local transcription
    #           Completely offline after initial audio download. No YouTube API
    #           calls for transcription — fully bypasses caption restrictions.
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    audio_path = None
    try:
        import yt_dlp
        import tempfile
        print(f"  [*] Tier 4: downloading audio for local Whisper transcription ({video_id})...")
        tmp_dir = tempfile.mkdtemp()
        
        # Formats to try in sequence
        format_strategies = [
            'bestaudio/best',
            'm4a/webm/mp3/bestaudio',
            'worst[ext=m4a]/worst',
        ]
        
        for fmt in format_strategies:
            if audio_path and os.path.exists(audio_path):
                break
            audio_out = os.path.join(tmp_dir, f"{video_id}.%(ext)s")
            ydl_audio_opts = {
                'format': fmt,
                'outtmpl': audio_out,
                'quiet': True,
                'no_warnings': True,
                'nocheckcertificate': True,
                'ignoreerrors': True,
            }
            if proxy_url:
                ydl_audio_opts['proxy'] = proxy_url

            # Try with browser cookies first, then without cookies
            for browser_tuple in [('chrome',), ('edge',), ('firefox',), ('brave',), None]:
                try:
                    opts = dict(ydl_audio_opts)
                    if browser_tuple:
                        opts['cookiesfrombrowser'] = browser_tuple
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        ydl.download([video_url])
                    for f in os.listdir(tmp_dir):
                        full_f = os.path.join(tmp_dir, f)
                        if os.path.isfile(full_f) and os.path.getsize(full_f) > 1000:
                            audio_path = full_f
                            break
                    if audio_path and os.path.exists(audio_path):
                        break
                except Exception:
                    continue

        if audio_path and os.path.exists(audio_path):
            try:
                from faster_whisper import WhisperModel
                print(f"  [*] Tier 4: transcribing with faster-whisper (tiny model)...")
                # Load model (cached in user directory)
                model = WhisperModel("tiny", device="cpu", compute_type="int8")
                segments, _ = model.transcribe(audio_path, beam_size=1)
                lines, raw = [], []
                for seg in segments:
                    text = seg.text.strip()
                    if not text:
                        continue
                    m, s = int(seg.start // 60), int(seg.start % 60)
                    lines.append(f"[{m:02d}:{s:02d}] {text}")
                    raw.append(text)
                if lines:
                    print(f"  [+] Tier 4 SUCCESS via faster-whisper ({len(lines)} segments)")
                    return raw, "\n".join(lines), None
            except ImportError:
                print("  [!] Tier 4: faster-whisper not installed. Run: pip install faster-whisper")
            except Exception as ew:
                print(f"  [!] Tier 4 Whisper error: {ew}")
        else:
            print(f"  [!] Tier 4: audio download failed — no file found")
    except Exception as e4:
        print(f"  [!] Tier 4 audio/whisper notice: {e4}")
    finally:
        # Clean up temp audio directory
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except Exception:
                pass

    # ── All tiers exhausted ───────────────────────────────────────────────────
    return [], None, (
        "All transcript extraction methods failed for this video.\n"
        "SOLUTIONS:\n"
        "  1. Make sure Chrome/Edge/Firefox is installed and logged into YouTube\n"
        "     (Tier 1 uses your browser cookies — most reliable free method)\n"
        "  2. Install faster-whisper for offline audio transcription:\n"
        "     pip install faster-whisper\n"
        "  3. Set Webshare proxy credentials in the sidebar Proxy Settings panel\n"
        "     (YOUTUBE_PROXY_USERNAME / YOUTUBE_PROXY_PASSWORD)"
    )


def convert_transcript_to_machine_language(raw_pieces, title):
    """
    Transforms raw spoken conversational transcripts into Machine Understandable Language (MUL).
    Extracts:
      1. Machine Knowledge JSON Payload (Metadata, categories, sentiment scores)
      2. [CONCEPT] Key Principles & Definitions
      3. [STRATEGY_RULE] Actionable Trading Rules & Execution Signals
      4. [MENTAL_MODEL] Cognitive Frameworks & Risk Management Logic
      5. [MARKET_BIAS] Directional Bias & Sentiment Vectors
    """
    if not raw_pieces:
        return ""

    full_raw = " ".join(raw_pieces)

    cleaned = re.sub(r'\[.*?\]', '', full_raw)
    cleaned = re.sub(r'\b(um|uh|like|you know|subscribe|like and subscribe|welcome back|hey guys|guys|so yeah)\b', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', cleaned) if len(s.strip()) > 15]

    concepts = []
    rules = []
    mental_models = []

    rule_keywords = ["if", "when", "entry", "exit", "stop loss", "take profit", "target", "breakout", "rejection", "confirmation", "always", "never", "rule", "strategy", "setup", "buy", "sell"]
    model_keywords = ["framework", "principle", "psychology", "mindset", "discipline", "fomo", "greed", "risk", "edge", "probability", "bias", "patience", "liquidity", "order flow"]
    bias_bullish = ["bullish", "uptrend", "long", "rally", "support", "breakout", "demand"]
    bias_bearish = ["bearish", "downtrend", "short", "dump", "resistance", "breakdown", "supply"]

    bull_count = 0
    bear_count = 0

    for stmt in sentences:
        stmt_lower = stmt.lower()

        if any(b in stmt_lower for b in bias_bullish):
            bull_count += 1
        if any(b in stmt_lower for b in bias_bearish):
            bear_count += 1

        if any(k in stmt_lower for k in rule_keywords) and len(stmt) < 200:
            rules.append(stmt)
        elif any(k in stmt_lower for k in model_keywords):
            mental_models.append(stmt)
        else:
            if len(stmt) < 180 and len(concepts) < 15:
                concepts.append(stmt)

    total_sentiment = max(bull_count + bear_count, 1)
    net_bias = round((bull_count - bear_count) / total_sentiment, 2)
    sentiment_str = "BULLISH" if net_bias > 0.2 else ("BEARISH" if net_bias < -0.2 else "NEUTRAL")

    top_concepts = concepts[:10]
    top_rules = rules[:10]
    top_models = mental_models[:10]

    mul_output = []
    mul_output.append("## [MACHINE_UNDERSTANDABLE_KNOWLEDGE_PAYLOAD]\n")

    machine_spec = {
        "source_title": title,
        "language_format": "Machine Understandable Language (MUL) v1.0",
        "market_bias": sentiment_str,
        "bias_score": net_bias,
        "extracted_rules_count": len(top_rules),
        "extracted_concepts_count": len(top_concepts),
        "extracted_models_count": len(top_models),
        "ingestion_ready": True
    }

    mul_output.append("```json")
    mul_output.append(json.dumps(machine_spec, indent=2))
    mul_output.append("```\n")

    if top_concepts:
        mul_output.append("### [CONCEPT] Core Principles & Terminology")
        for c in top_concepts:
            mul_output.append(f"- **[CONCEPT]**: {c}")
        mul_output.append("")

    if top_rules:
        mul_output.append("### [STRATEGY_RULE] Actionable Trading Rules & Execution Signals")
        for r in top_rules:
            mul_output.append(f"- **[STRATEGY_RULE]**: {r}")
        mul_output.append("")

    if top_models:
        mul_output.append("### [MENTAL_MODEL] Cognitive & Risk Management Frameworks")
        for m in top_models:
            mul_output.append(f"- **[MENTAL_MODEL]**: {m}")
        mul_output.append("")

    mul_output.append(f"### [MARKET_BIAS] Directional Sentiment Vector: {sentiment_str} (Score: {net_bias:+0.2f})\n")

    return "\n".join(mul_output)


def process_youtube_conversion(url, output_file=DEFAULT_OUTPUT, auto_ingest=True):
    """
    Converts YouTube video or playlist to Markdown using real transcripts,
    transforms content into Machine Understandable Language (MUL),
    and ingests it into ZERO Brain & Gemini Knowledge Engine.
    """
    try:
        write_status("Step 1/3: Extracting playlist metadata & video URLs...")
        main_title, video_items = get_playlist_videos(url)
        total_vids = len(video_items)
        print(f"Starting transcript extraction for {total_vids} video(s)...")

        from config import OBSIDIAN_VAULT_PATH
        obsidian_yt_dir = os.path.join(OBSIDIAN_VAULT_PATH, "04_YouTube_Knowledge")
        os.makedirs(obsidian_yt_dir, exist_ok=True)

        obsidian_filename = f"{main_title}.md"
        obsidian_note_path = os.path.join(obsidian_yt_dir, obsidian_filename)

        write_status(f"Step 2/3: Extracting transcripts from {total_vids} video(s)...")

        with open(obsidian_note_path, "w", encoding="utf-8") as f:
            f.write("---\n")
            f.write("type: youtube_knowledge\n")
            f.write("format: machine_understandable_language\n")
            f.write(f"source_url: '{url}'\n")
            f.write(f"playlist_title: '{main_title}'\n")
            f.write(f"total_videos: {total_vids}\n")
            f.write(f"date: '{datetime.date.today().isoformat()}'\n")
            f.write("tags: [youtube, machine_knowledge, mental_models, strategy_rules]\n")
            f.write("---\n\n")
            f.write(f"# {main_title}\n\n")
            f.write(f"**Source Playlist/Video URL:** {url}\n\n")
            f.write(f"**Total Videos Decoded:** {total_vids}\n\n")
            f.write(f"**Linked Core Engine:** [[ZERO Brain Engine]] | [[04_YouTube_Knowledge/Index]] | [[01_Daily_Logs/{datetime.date.today().isoformat()}]]\n\n")
            f.write("---\n\n")

            total_chars = 0
            successful_vids = 0

            for index, item in enumerate(video_items, start=1):
                vid_id = item['id']
                vid_url = item['url']
                vid_title = item['title']

                write_status(f"Step 2/3: Extracting video {index}/{total_vids}: {vid_title[:30]}...")
                print(f"[{index}/{total_vids}] Processing video ID: {vid_id} - '{vid_title}'")

                f.write(f"## Video {index}: {vid_title}\n")
                f.write(f"**URL:** {vid_url}\n")
                f.write(f"**Video ID:** `{vid_id}`\n\n")

                if vid_id == "unknown":
                    f.write("*Could not extract valid video ID.*\n\n---\n\n")
                    continue

                raw_pieces, formatted_transcript, error = fetch_transcript(vid_id)

                if formatted_transcript:
                    successful_vids += 1
                    char_count = len(formatted_transcript)
                    total_chars += char_count
                    print(f"  [+] Transcript extracted ({char_count:,} chars)")

                    machine_payload = convert_transcript_to_machine_language(raw_pieces, vid_title)
                    f.write(machine_payload)
                    f.write("\n")

                    f.write("### Full Raw Transcript Reference\n\n")
                    f.write(formatted_transcript)
                    f.write("\n\n")
                else:
                    print(f"  [-] Transcript unavailable: {error}")
                    f.write(f"*Transcript unavailable for this video: {error}*\n\n")

                f.write("---\n\n")

            print(f"\n[+] Conversion complete: {successful_vids}/{total_vids} transcripts extracted ({total_chars:,} total characters).")

        if os.path.abspath(output_file) != os.path.abspath(obsidian_note_path):
            try:
                import shutil
                shutil.copyfile(obsidian_note_path, output_file)
            except Exception:
                pass

        print(f"SUCCESS! Knowledge saved to Obsidian Vault: {obsidian_note_path}")

        try:
            from engine.vault_sync import sync_youtube_note
            sync_youtube_note(f"04_YouTube_Knowledge/{main_title}.md")
        except Exception as ve:
            print(f"vault_sync notice: {ve}")

        index_file = os.path.join(obsidian_yt_dir, "Index.md")        if os.path.exists(index_file):
            try:
                with open(index_file, "r", encoding="utf-8") as f:
                    idx_content = f.read()
                note_link = f"* [[{main_title}]]"
                if note_link not in idx_content:
                    with open(index_file, "a", encoding="utf-8") as f:
                        f.write(f"\n{note_link}")
            except Exception:
                pass

        if auto_ingest:
            write_status("Step 3/3: Ingesting Machine Knowledge into ZERO Brain...")
            print("\nAutomating Machine Knowledge Base Integration into ZERO Brain...")
            try:
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                from engine.brain_engine import get_brain
                brain = get_brain()
                added = brain.ingest_markdown_file(obsidian_note_path, source=f"youtube:{main_title}")
                print(f"SUCCESS! Automatically ingested {len(added)} Machine-Understandable knowledge entries into ZERO Brain.")

                try:
                    reload_flag = os.path.join(os.path.dirname(__file__), "db", ".kb_reload.flag")
                    with open(reload_flag, "w", encoding="utf-8") as f:
                        f.write(f"reload:{main_title}:{datetime.date.today().isoformat()}")
                    print(f"KB reload signal written — Gemini engine will use '{main_title}' on next query.")
                except Exception as reload_err:
                    print(f"KB reload signal warning: {reload_err}")

            except Exception as ie:
                print(f"Error ingesting markdown into ZERO Brain: {ie}")

        write_status(f"COMPLETED: Ingested {successful_vids}/{total_vids} videos from '{main_title}' into ZERO Brain!")
        return True, obsidian_note_path

    except Exception as e:
        write_status(f"ERROR: {e}")
        print(f"An error occurred during conversion: {e}")
        return False, str(e)


def main():
    parser = argparse.ArgumentParser(description="Convert YouTube playlist or video to Machine Understandable Language and ingest to ZERO Brain.")
    parser.add_argument("--url", type=str, help="YouTube video or playlist URL")
    parser.add_argument("--output", type=str, default=DEFAULT_OUTPUT, help="Output markdown filename")
    parser.add_argument("--no-ingest", action="store_true", help="Skip automatic ingestion into ZERO Brain")
    args = parser.parse_args()

    target_url = args.url
    if not target_url:
        print("==================================================")
        print("    ZERO TERMINAL - YOUTUBE KNOWLEDGE CONVERTER    ")
        print("==================================================")
        target_url = input("Paste the URL (playlist or single video): ").strip()

    if not target_url:
        print("Error: No YouTube URL provided. Aborting conversion.")
        sys.exit(1)

    process_youtube_conversion(target_url, output_file=args.output, auto_ingest=not args.no_ingest)


if __name__ == "__main__":
    main()

import sys
import argparse
import subprocess
import os
import re
import datetime


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
    return re.sub(r'[\\/*?:"<>|]', "", title).strip()

def get_video_title(url):
    """Fetches video/playlist title using yt-dlp."""
    try:
        cmd = [sys.executable, "-m", "yt_dlp", "--no-warnings", "--print", "title", "--playlist-items", "1", url]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        lines = [line.strip() for line in result.stdout.strip().splitlines() if line.strip() and not line.startswith("WARNING")]
        if lines:
            title = sanitize_filename(lines[-1])
            if title:
                return title
    except Exception as e:
        print(f"Title extraction warning: {e}")
    return "YouTube_Knowledge_Import"

def get_urls(url):
    """
    Extracts video URLs. Handles both playlist URLs and single video URLs.
    """
    write_status("Processing URL: Extracting video list...")
    print(f"Extracting video URL(s) from target: {url}")
    # Check if it's a playlist or single video
    if "list=" in url:
        cmd = [sys.executable, "-m", "yt_dlp", "--no-warnings", "--flat-playlist", "--print", "webpage_url", url]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            urls = [line.strip() for line in result.stdout.splitlines() if line.strip() and "watch?v=" in line]
            if urls:
                return urls
        except Exception as e:
            print(f"Warning: yt-dlp playlist extraction failed ({e}). Falling back to direct URL.")
    
    # Single video or fallback
    return [url]


def extract_video_id(url):
    """Extract YouTube video ID from any YouTube URL format."""
    patterns = [
        r'(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def fetch_transcript(video_id):
    """
    Fetch transcript for a YouTube video using youtube-transcript-api.
    Returns a structured text string with timestamps.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id)
        snippets = list(transcript)
        if not snippets:
            return None, "No transcript segments returned."

        # Format into readable Markdown with timestamps
        lines = []
        for s in snippets:
            text = s.text.strip()
            if not text or text in ('', '[Music]', '[Applause]', '[Laughter]'):
                continue
            minutes = int(s.start // 60)
            seconds = int(s.start % 60)
            lines.append(f"[{minutes:02d}:{seconds:02d}] {text}")

        return "\n".join(lines), None
    except Exception as e:
        return None, str(e)


def process_youtube_conversion(url, output_file=DEFAULT_OUTPUT, auto_ingest=True):
    """
    Converts YouTube video or playlist to Markdown using real transcripts
    and optionally ingests into Brain Engine.
    """
    try:
        write_status("Step 1/3: Extracting video URLs & fetching titles...")
        main_title = get_video_title(url)
        urls = get_urls(url)
        print(f"Found {len(urls)} video(s). Starting transcript extraction...")

        # Determine Obsidian Vault path
        from config import OBSIDIAN_VAULT_PATH
        obsidian_yt_dir = os.path.join(OBSIDIAN_VAULT_PATH, "04_YouTube_Knowledge")
        os.makedirs(obsidian_yt_dir, exist_ok=True)

        # Format filename using YouTube Title
        obsidian_filename = f"{main_title}.md"
        obsidian_note_path = os.path.join(obsidian_yt_dir, obsidian_filename)

        write_status(f"Step 2/3: Extracting transcripts from {len(urls)} video(s)...")

        with open(obsidian_note_path, "w", encoding="utf-8") as f:
            f.write(f"---\n")
            f.write(f"type: youtube_knowledge\n")
            f.write(f"source_url: '{url}'\n")
            f.write(f"date: '{datetime.date.today().isoformat()}'\n")
            f.write(f"tags: [youtube, mental_models, knowledge_base]\n")
            f.write(f"---\n\n")
            f.write(f"# {main_title}\n\n")
            f.write(f"**Source URL:** {url}\n\n")
            f.write(f"**Linked Core Engine:** [[ZERO Brain Engine]] | [[04_YouTube_Knowledge/Index]] | [[01_Daily_Logs/{datetime.date.today().isoformat()}]]\n\n")
            f.write(f"---\n\n")

            total_chars = 0
            for index, vid_url in enumerate(urls, start=1):
                write_status(f"Step 2/3: Extracting transcript {index}/{len(urls)}...")
                print(f"[{index}/{len(urls)}] Processing: {vid_url}")

                video_id = extract_video_id(vid_url)
                if not video_id:
                    f.write(f"## Video {index}\n")
                    f.write(f"**URL:** {vid_url}\n\n")
                    f.write(f"*Could not extract video ID from URL.*\n\n---\n\n")
                    continue

                transcript_text, error = fetch_transcript(video_id)

                f.write(f"## Video {index}: {main_title if index == 1 else vid_url}\n")
                f.write(f"**URL:** {vid_url}\n")
                f.write(f"**Video ID:** `{video_id}`\n\n")

                if transcript_text:
                    char_count = len(transcript_text)
                    total_chars += char_count
                    print(f"  [+] Transcript: {char_count} chars extracted")
                    f.write(f"### Full Transcript\n\n")
                    f.write(transcript_text)
                    f.write("\n\n")
                else:
                    print(f"  [-] Transcript unavailable: {error}")
                    f.write(f"*Transcript unavailable: {error}*\n\n")

                f.write("---\n\n")

            if total_chars > 0:
                print(f"\n[+] Total transcript content: {total_chars:,} characters extracted")
            else:
                print("\n[!] No transcripts were available. Notes saved with URL metadata only.")

        # Also write local copy to output_file if different
        if os.path.abspath(output_file) != os.path.abspath(obsidian_note_path):
            try:
                import shutil
                shutil.copyfile(obsidian_note_path, output_file)
            except Exception:
                pass
                    
        print(f"\nSUCCESS! Your YouTube context has been saved to Obsidian Vault: {obsidian_note_path}")

        # Automatically register note link into 04_YouTube_Knowledge/Index.md for full Graph connection
        index_file = os.path.join(obsidian_yt_dir, "Index.md")
        if os.path.exists(index_file):
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
            write_status("Step 3/3: Ingesting into ZERO Brain & linking Obsidian Graph...")
            print("\nAutomating Knowledge Base Integration into ZERO Brain...")
            try:
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                from engine.brain_engine import get_brain
                brain = get_brain()
                added = brain.ingest_markdown_file(obsidian_note_path, source=f"youtube:{main_title}")
                print(f"SUCCESS! Automatically ingested {len(added)} knowledge entries into ZERO Brain.")

                # ── Hot-reload the Gemini KB so new YouTube knowledge is live instantly ──
                try:
                    from engine.zero_engine_kb import ZeroEngineKB
                    # Write a reload signal file so the running Streamlit app picks it up
                    reload_flag = os.path.join(os.path.dirname(__file__), "db", ".kb_reload.flag")
                    with open(reload_flag, "w", encoding="utf-8") as f:
                        f.write(f"reload:{main_title}:{datetime.date.today().isoformat()}")
                    print(f"Knowledge Base reload signal written — Gemini engine will use '{main_title}' on next query.")
                except Exception as reload_err:
                    print(f"KB reload signal warning: {reload_err}")

            except Exception as ie:
                print(f"Error ingesting markdown into ZERO Brain: {ie}")

        write_status(f"COMPLETED: Knowledge note '{main_title}' added & linked in Obsidian Graph!")
        return True, obsidian_note_path

        
    except Exception as e:
        write_status(f"ERROR: {e}")
        print(f"An error occurred during conversion: {e}")
        return False, str(e)


def main():
    parser = argparse.ArgumentParser(description="Convert YouTube playlist or video to Markdown and ingest to ZERO Brain.")
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

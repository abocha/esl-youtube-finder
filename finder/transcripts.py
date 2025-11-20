# finder/transcripts.py
import html
import logging
import random
import requests
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Union, List

# Primary Provider
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
)

# Secondary Provider
try:
    import yt_dlp
except ImportError:
    yt_dlp = None

# Tertiary Provider
try:
    from pytubefix import YouTube as PytubeFixYouTube
except ImportError:
    PytubeFixYouTube = None

from terminal_logger import TerminalLogger
from .config import TRANSCRIPT_CACHE_DIR, SUPADATA_API_KEY, settings

logger = TerminalLogger("esl_finder.transcripts")

# User-Agent rotation to reduce rate limiting
USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Firefox on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]


@dataclass
class TranscriptResult:
    text: Optional[str]
    source: str  # 'cache', 'youtube_api', 'ytdlp', 'supadata', 'none'
    error: Optional[str] = None


class TranscriptFetcher:
    def __init__(self):
        self.cache_dir = Path(TRANSCRIPT_CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.last_supadata_request_time = 0.0

    def _get_random_user_agent(self) -> str:
        """Get a random user agent from the pool."""
        return random.choice(USER_AGENTS)

    def fetch(self, video_id: str, allow_paid: bool = False) -> TranscriptResult:
        # 1. Cache Check
        if cached := self._read_cache(video_id):
            return cached

        # 2. YouTube Transcript API (Best free option)
        try:
            text = self._fetch_youtube_api(video_id)
            if text:
                return self._save_cache(video_id, text, "youtube_api")
        except Exception as e:
            logger.debug(f"YouTube API attempt failed for {video_id}: {e}")

        # 3. yt-dlp (Robust Fallback with Impersonation)
        if yt_dlp:
            try:
                text = self._fetch_ytdlp(video_id)
                if text:
                    return self._save_cache(video_id, text, "ytdlp")
            except Exception as e:
                logger.warn(f"yt-dlp attempt failed for {video_id}: {e}")

        # 4. Pytubefix (Third free option)
        if PytubeFixYouTube:
            try:
                text = self._fetch_pytubefix(video_id)
                if text:
                    return self._save_cache(video_id, text, "pytubefix")
            except Exception as e:
                logger.debug(f"Pytubefix attempt failed for {video_id}: {e}")

        # 5. Supadata (Paid Backup)
        if allow_paid and SUPADATA_API_KEY:
            try:
                text = self._fetch_supadata(video_id)
                if text:
                    return self._save_cache(video_id, text, "supadata")
            except Exception as e:
                logger.error(f"Supadata attempt failed for {video_id}: {e}")

        return TranscriptResult(None, "none", "All providers failed")

    def _fetch_youtube_api(self, video_id: str) -> Optional[str]:
        """
        Fetch transcript using youtube-transcript-api v1.2.3+
        Uses YouTubeTranscriptApi().list(video_id) API with custom user-agent.
        """
        try:
            # Create custom session with rotated user-agent
            session = requests.Session()
            session.headers.update({"User-Agent": self._get_random_user_agent()})

            # v1.2.3+ uses instance methods and accepts http_client
            api = YouTubeTranscriptApi(http_client=session)
            transcript_list = api.list(video_id)

            # Try to find an English transcript
            try:
                transcript = transcript_list.find_transcript(["en"])
            except NoTranscriptFound:
                return None

            # Fetch the transcript data
            data = transcript.fetch()
            full_text = " ".join([item["text"] for item in data])
            return self._clean_text(full_text)

        except (TranscriptsDisabled, NoTranscriptFound):
            return None
        except Exception as e:
            raise RuntimeError(f"YTApi Error: {e}")

    def _fetch_ytdlp(self, video_id: str) -> Optional[str]:
        url = f"https://www.youtube.com/watch?v={video_id}"

        user_agent = self._get_random_user_agent()

        ydl_opts = {
            "skip_download": True,
            "writeautomaticsub": True,
            "writesubtitles": True,
            "sublangs": ["en.*", "en"],
            "quiet": True,
            "no_warnings": True,
            "logtostderr": False,
            "force_ipv4": True,
            "user_agent": user_agent,  # Use rotated user-agent
            # 'impersonate': 'chrome', # Causes AssertionError in current yt-dlp version
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            subtitles = info.get("subtitles") or info.get("automatic_captions")
            if not subtitles:
                return None

            en_subs = None
            for lang in subtitles:
                if lang.startswith("en"):
                    en_subs = subtitles[lang]
                    break

            if not en_subs:
                return None

            sub_url = next(
                (s["url"] for s in en_subs if s["ext"] in ["vtt", "srv3", "json3"]),
                en_subs[0]["url"],
            )

            headers = {"User-Agent": user_agent}
            resp = requests.get(sub_url, headers=headers)
            resp.raise_for_status()

            return self._clean_vtt(resp.text)

    def _fetch_pytubefix(self, video_id: str) -> Optional[str]:
        """
        Fetch transcript using pytubefix caption API.
        Third free fallback option.
        """
        if not PytubeFixYouTube:
            return None

        try:
            url = f"https://www.youtube.com/watch?v={video_id}"

            # Create YouTube object (accepts proxies but not custom session)
            # Note: pytubefix doesn't support custom user-agents in constructor
            yt = PytubeFixYouTube(url)

            if not yt.captions:
                return None

            # Try to find English caption
            caption = None

            # Try direct English codes
            for lang_code in ["en", "a.en", "en-US", "en-GB"]:
                if lang_code in yt.captions.lang_code_index:
                    caption = yt.captions[lang_code]
                    break

            # If not found, try any English variant
            if not caption:
                for lang_code in yt.captions.lang_code_index.keys():
                    if "en" in lang_code.lower():
                        caption = yt.captions[lang_code]
                        break

            if not caption:
                return None

            # Get plain text transcript
            transcript = caption.generate_txt_captions()
            return self._clean_text(transcript)

        except Exception as e:
            logger.debug(f"Pytubefix attempt failed for {video_id}: {e}")
            return None

    def _fetch_supadata(self, video_id: str) -> Optional[str]:
        # Rate limiting
        elapsed = time.time() - self.last_supadata_request_time
        if elapsed < settings.supadata_request_delay:
            time.sleep(settings.supadata_request_delay - elapsed)

        self.last_supadata_request_time = time.time()
        url = f"https://api.supadata.ai/v1/youtube/transcript?videoId={video_id}"
        headers = {"x-api-key": SUPADATA_API_KEY}
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()

        data = resp.json()
        content = data.get("content")

        # FIX: Supadata might return list of segments
        return self._ensure_string(content)

    def _ensure_string(self, content: Union[str, List, None]) -> Optional[str]:
        """Safely converts content to string, joining lists if necessary."""
        if content is None:
            return None
        if isinstance(content, str):
            return self._clean_text(content)
        if isinstance(content, list):
            # Assuming list of strings or dicts with 'text'
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and "text" in item:
                    parts.append(item["text"])
            return self._clean_text(" ".join(parts))
        return str(content)

    def _clean_text(self, text: str) -> str:
        import re

        # 1. Unescape HTML
        text = html.unescape(text)

        # 2. Remove timestamps like (12:30) or [00:01]
        text = re.sub(r"\[?\d{1,2}:\d{2}(:\d{2})?\]?", "", text)

        # 3. Remove speaker labels like "Speaker 1:" or ">>"
        text = re.sub(r"Speaker \d+:", "", text)
        text = re.sub(r"^>>\s?", "", text, flags=re.MULTILINE)

        # 4. Remove music/sound markers like [Music], (Applause)
        text = re.sub(r"\[.*?\]", "", text)
        text = re.sub(r"\(.*?\)", "", text)

        # 5. Collapse whitespace
        return re.sub(r"\s+", " ", text).strip()

    def _clean_vtt(self, vtt_text: str) -> str:
        lines = []
        for line in vtt_text.splitlines():
            if "WEBVTT" in line or "-->" in line or not line.strip():
                continue
            clean = line.replace("&nbsp;", " ")
            if "<" in clean:
                import re

                clean = re.sub(r"<[^>]+>", "", clean)
            lines.append(clean.strip())
        return self._clean_text(" ".join(lines))

    def _read_cache(self, video_id: str) -> Optional[TranscriptResult]:
        path = self.cache_dir / f"{video_id}.txt"
        if path.exists():
            try:
                text = path.read_text(encoding="utf-8")
                return TranscriptResult(text, "cache")
            except Exception:
                pass
        return None

    def _save_cache(self, video_id: str, text: str, source: str) -> TranscriptResult:
        # CRITICAL FIX: Ensure text is strictly string before writing
        if not isinstance(text, str):
            logger.error(
                f"Cache write failed: data must be str, not {type(text).__name__}"
            )
            # Try to salvage it
            text = self._ensure_string(text) or ""

        path = self.cache_dir / f"{video_id}.txt"
        try:
            path.write_text(text, encoding="utf-8")
        except Exception as e:
            logger.error(f"Cache write failed: {e}")

        return TranscriptResult(text, source)

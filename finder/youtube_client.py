# finder/youtube_client.py
import json
import time
import isodate
from typing import List
from googleapiclient.discovery import build

from terminal_logger import TerminalLogger
from .config import YOUTUBE_API_KEY

logger = TerminalLogger("esl_finder.youtube")

class YouTubeClient:
    def __init__(self):
        if not YOUTUBE_API_KEY:
            raise RuntimeError("Missing YOUTUBE_API_KEY environment variable.")
        
        # FIX: Add cache_discovery=False to silence oauth2client warnings
        self.client = build(
            "youtube", 
            "v3", 
            developerKey=YOUTUBE_API_KEY, 
            cache_discovery=False
        )

    def search(self, queries: List[str], max_results: int, max_queries: int = 5) -> List[dict]:
        """Batched search + details fetch strategy."""
        unique_video_ids = set()
        
        # 1. Search (Limited queries to save quota)
        run_queries = queries[:max_queries]
        
        for q in run_queries:
            try:
                resp = self.client.search().list(
                    part="id",
                    q=q,
                    type="video",
                    maxResults=max_results,
                    relevanceLanguage="en",
                    safeSearch="none"
                ).execute()
                
                for item in resp.get("items", []):
                    unique_video_ids.add(item["id"]["videoId"])
                    
            except Exception as e:
                logger.error(f"Search failed for query '{q}': {e}")

        if not unique_video_ids:
            return []

        # 2. Fetch Details (Batched)
        return self._fetch_details(list(unique_video_ids))

    def _fetch_details(self, video_ids: List[str]) -> List[dict]:
        videos = []
        # Chunk into 50s (YouTube API Limit)
        chunks = [video_ids[i:i + 50] for i in range(0, len(video_ids), 50)]
        
        for chunk in chunks:
            try:
                resp = self.client.videos().list(
                    part="snippet,contentDetails,statistics",
                    id=",".join(chunk)
                ).execute()
                
                for item in resp.get("items", []):
                    parsed = self._parse_video(item)
                    if parsed:
                        videos.append(parsed)
            except Exception as e:
                logger.error(f"Details fetch failed: {e}")
        
        return videos

    def _parse_video(self, item: dict) -> dict:
        try:
            snippet = item["snippet"]
            content = item["contentDetails"]
            stats = item["statistics"]
            
            dur_str = content.get("duration", "PT0S")
            dur_dt = isodate.parse_duration(dur_str)
            dur_min = dur_dt.total_seconds() / 60.0
            
            return {
                "video_id": item["id"],
                "title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "channel": snippet.get("channelTitle", ""),
                "duration_min": dur_min,
                "view_count": int(stats.get("viewCount", 0)),
                "publish_date": snippet.get("publishedAt", "")
            }
        except Exception:
            return None

def build_youtube_client():
    return YouTubeClient()

def search_videos_for_queries(client: YouTubeClient, queries: List[str], max_results: int, max_queries: int = 5):
    return client.search(queries, max_results, max_queries)
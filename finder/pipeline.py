# finder/pipeline.py
import time
import logging
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Tuple

from .profile import (
    load_profile_from_json_str,
    extract_queries,
    extract_target_level,
    extract_duration_bounds,
)
from .youtube_client import build_youtube_client, search_videos_for_queries
from .scoring import metadata_score, score_video
from .transcripts import (
    TranscriptFetcher,
)  # Assuming you created this from the previous step!
from .cefr import estimate_cefr
from .config import MAX_TRANSCRIPTS_PER_RUN
from .vibe import VibeChecker

logger = logging.getLogger("esl_finder.pipeline")


@dataclass
class PipelineStats:
    raw_count: int = 0
    meta_filtered_count: int = 0
    transcript_attempts: int = 0
    transcript_success_count: int = 0
    final_count: int = 0
    total_time: float = 0.0


class ESLSearchPipeline:
    def __init__(self):
        self.yt_client = build_youtube_client()
        self.fetcher = TranscriptFetcher()
        self.vibe_checker = VibeChecker()  # <--- NEW

    def run(
        self,
        profile_json: str,
        max_results_per_query: int,
        max_queries: int,
        max_transcripts: int,
        allow_paid: bool,
        progress_callback=None,
    ) -> Tuple[List[Dict], PipelineStats]:

        start_time = time.time()
        stats = PipelineStats()

        # 1. Load Profile
        try:
            from .profile import extract_profile_context

            profile = load_profile_from_json_str(profile_json)
            queries = extract_queries(profile, max_queries=max_queries)
            target_level = extract_target_level(profile)
            min_dur, max_dur = extract_duration_bounds(profile)
            profile_context = extract_profile_context(profile)
        except Exception as e:
            raise ValueError(f"Profile Error: {str(e)}")

        if not queries:
            raise ValueError("No search queries found in profile.")

        # 2. Search
        if progress_callback:
            progress_callback(0.1, "🔍 Searching YouTube...")
        raw_videos = self._search_candidates(
            queries, max_results_per_query, max_queries
        )
        stats.raw_count = len(raw_videos)

        if not raw_videos:
            stats.total_time = time.time() - start_time
            return [], stats

        # 3. Filter
        if progress_callback:
            progress_callback(0.3, "📊 Filtering candidates...")
        candidates, filter_stats = self._filter_candidates(
            raw_videos, profile, min_dur, max_dur
        )
        stats.meta_filtered_count = len(candidates)

        # Select top candidates
        limit = min(max_transcripts, MAX_TRANSCRIPTS_PER_RUN)
        top_candidates = candidates[:limit]

        # 4. Analyze (Parallel)
        if progress_callback:
            progress_callback(
                0.4, f"📝 Analyzing {len(top_candidates)} candidates in parallel..."
            )

        results, success_count = self._analyze_candidates(
            top_candidates,
            profile,
            profile_context,
            target_level,
            min_dur,
            max_dur,
            allow_paid,
            progress_callback,
        )
        stats.transcript_attempts = len(top_candidates)
        stats.transcript_success_count = success_count

        # 5. Finalize
        final_results = self._finalize_results(results, top_candidates)

        stats.final_count = len(final_results)
        stats.total_time = time.time() - start_time

        return final_results, stats

    def _search_candidates(
        self, queries: List[str], max_results: int, max_queries: int
    ) -> List[Dict]:
        return search_videos_for_queries(
            self.yt_client, queries, max_results, max_queries
        )

    def _filter_candidates(
        self, raw_videos: List[Dict], profile, min_dur: int, max_dur: int
    ) -> Tuple[List[Dict], Dict]:
        from .scoring import check_sensitive_topics, validate_format

        candidates = []
        filtered_sensitive = 0
        filtered_format = 0

        for vid in raw_videos:
            # Metadata score
            score, reason = metadata_score(vid, min_dur, max_dur)
            vid["metadata_score"] = score
            vid["metadata_reason"] = reason

            # Sensitive Check
            is_safe, sensitive_reason = check_sensitive_topics(
                vid, profile.topic_preferences.sensitive_or_avoid
            )
            if not is_safe:
                filtered_sensitive += 1
                logger.info(
                    f"Filtered (sensitive): {vid['title'][:50]}... - {sensitive_reason}"
                )
                continue

            # Format Check
            is_valid_format, format_bonus, format_reason = validate_format(
                vid,
                profile.video_preferences.preferred_formats,
                profile.video_preferences.avoid_formats,
            )
            if not is_valid_format:
                filtered_format += 1
                logger.info(
                    f"Filtered (format): {vid['title'][:50]}... - {format_reason}"
                )
                continue

            candidates.append(vid)

        logger.info(
            f"Filtered out {filtered_sensitive} videos (sensitive topics), {filtered_format} videos (format)"
        )

        # Sort by metadata score
        candidates.sort(key=lambda x: x["metadata_score"], reverse=True)

        return candidates, {"sensitive": filtered_sensitive, "format": filtered_format}

    def _analyze_candidates(
        self,
        candidates: List[Dict],
        profile,
        profile_context: str,
        target_level: str,
        min_dur: int,
        max_dur: int,
        allow_paid: bool,
        progress_callback=None,
    ) -> Tuple[List[Dict], int]:

        results = []
        success_count = 0

        # Pre-load models
        try:
            from .model_manager import model_manager

            model_manager.preload_all()
        except Exception as e:
            logger.warning(f"Model pre-loading warning: {e}")

        import concurrent.futures

        def process_candidate(vid):
            try:
                # Fetch
                tr = self.fetcher.fetch(vid["video_id"], allow_paid=allow_paid)
                if not tr.text:
                    return None

                # CEFR
                cefr_res = estimate_cefr(tr.text)

                # Vibe
                vibe_score = 0.5
                if tr.text and len(tr.text) > 500:
                    vibe_score = self.vibe_checker.check(tr.text, profile_context)

                # Topic Match
                from .scoring import calculate_topic_match_score

                topic_score, topic_reason = calculate_topic_match_score(
                    vid,
                    profile.topic_preferences.strong_likes,
                    profile.topic_preferences.dislikes,
                )

                # Score
                scored_vid = score_video(
                    video=vid,
                    transcript_text=tr.text,
                    cefr_label=cefr_res["label"],
                    cefr_numeric=cefr_res["numeric"],
                    target_level=target_level,
                    target_min_duration=min_dur,
                    target_max_duration=max_dur,
                    vibe_score=vibe_score,
                    topic_score=topic_score,
                )
                scored_vid["transcript_source"] = tr.source
                if topic_reason:
                    scored_vid["score_reason"] += f" | {topic_reason}"

                return scored_vid
            except Exception as e:
                logger.error(f"Error processing video {vid.get('video_id')}: {e}")
                return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_vid = {
                executor.submit(process_candidate, vid): vid for vid in candidates
            }

            completed = 0
            for future in concurrent.futures.as_completed(future_to_vid):
                completed += 1
                if progress_callback:
                    progress_callback(
                        0.4 + (completed / len(candidates)) * 0.5,
                        f"Analyzed {completed}/{len(candidates)}",
                    )

                try:
                    res = future.result()
                    if res:
                        results.append(res)
                        success_count += 1
                except Exception as exc:
                    logger.error(f"Thread exception: {exc}")

        return results, success_count

    def _finalize_results(
        self, results: List[Dict], top_candidates: List[Dict]
    ) -> List[Dict]:
        # Fallback if no transcripts found
        if not results and top_candidates:
            logger.warning("No transcripts found. Returning metadata-only results.")
            fallback_results = []
            for vid in top_candidates:
                fallback = vid.copy()
                fallback["final_score"] = vid["metadata_score"]
                fallback["cefr_label"] = "N/A"
                fallback["score_reason"] = f"Metadata only: {vid['metadata_reason']}"
                fallback["transcript_source"] = "None"
                fallback_results.append(fallback)
            return fallback_results

        results.sort(key=lambda x: x.get("final_score", 0), reverse=True)
        return results

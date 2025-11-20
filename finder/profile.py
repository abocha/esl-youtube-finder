# finder/profile.py
from typing import List, Tuple
from terminal_logger import TerminalLogger
from .models import StudentProfile

logger = TerminalLogger("esl_finder.profile")

def load_profile_from_json_str(json_str: str) -> StudentProfile:
    """Parses JSON into a strict StudentProfile object."""
    try:
        # The validators in StudentProfile handle the complex Svetlana schema automatically
        profile = StudentProfile.model_validate_json(json_str)
        logger.info(
            "Profile loaded", 
            name=profile.name, 
            level=profile.target_level
        )
        return profile
    except Exception as e:
        logger.error(f"Profile parsing failed: {e}")
        raise ValueError(f"Invalid Profile JSON: {e}")

def extract_queries(profile: StudentProfile, max_queries: int = 10) -> List[str]:
    """Extracts optimized list of search queries with weighting."""
    queries = profile.get_search_queries(max_queries=max_queries)
    logger.debug(f"Extracted {len(queries)} weighted queries.")
    return queries

def extract_target_level(profile: StudentProfile) -> str:
    return profile.target_level

def extract_duration_bounds(profile: StudentProfile) -> Tuple[int, int]:
    return (
        profile.video_preferences.min_duration_min,
        profile.video_preferences.max_duration_min
    )

def extract_profile_context(profile: StudentProfile) -> str:
    """Builds rich context string for LLM vibe checker."""
    return profile.get_profile_context()
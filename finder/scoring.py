# finder/scoring.py
import re
from typing import Tuple, Dict, Optional, List
from .config import CEFR_TO_INT


def check_sensitive_topics(
    video: Dict, sensitive_topics: List[str]
) -> Tuple[bool, str]:
    """
    Checks if video title/description contains sensitive topics for THIS student.
    Returns (is_safe, reason).
    Uses Regex word boundaries to avoid false positives (e.g. 'ass' in 'class').
    """
    if not sensitive_topics:
        return True, ""

    title_lower = video.get("title", "").lower()
    desc_lower = video.get("description", "").lower()
    combined = f"{title_lower} {desc_lower}"

    for topic in sensitive_topics:
        # Use word boundaries \b to match whole words only
        pattern = rf"\b{re.escape(topic.lower())}\b"
        if re.search(pattern, combined):
            return False, f"⚠️ FILTERED: Contains sensitive topic '{topic}'"

    return True, ""


def calculate_topic_match_score(
    video: Dict, strong_likes: List[str], dislikes: List[str]
) -> Tuple[float, str]:
    """
    Scores video based on topic match to THIS student's preferences.
    Returns (score, reason).
    """
    title_lower = video.get("title", "").lower()
    desc_lower = video.get("description", "").lower()
    combined = f"{title_lower} {desc_lower}"

    score = 0.0
    matched = []

    # Strong likes boost
    for topic in strong_likes:
        pattern = rf"\b{re.escape(topic.lower())}\b"
        if re.search(pattern, combined):
            score += 0.5
            matched.append(f"✅{topic}")

    # Dislikes penalty
    for topic in dislikes:
        pattern = rf"\b{re.escape(topic.lower())}\b"
        if re.search(pattern, combined):
            score -= 0.5
            matched.append(f"❌{topic}")

    reason = f"Topics: {', '.join(matched)}" if matched else ""
    return score, reason


def validate_format(
    video: Dict, preferred_formats: List[str], avoid_formats: List[str]
) -> Tuple[bool, float, str]:
    """
    Validates video format against THIS student's preferences.
    Returns (is_valid, bonus_score, reason).
    """
    title_lower = video.get("title", "").lower()

    # Check avoid formats (hard filter)
    for fmt in avoid_formats:
        pattern = rf"\b{re.escape(fmt.lower())}\b"
        if re.search(pattern, title_lower):
            return False, 0.0, f"Format '{fmt}' avoided"

    # Check preferred formats (soft boost)
    bonus = 0.0
    for fmt in preferred_formats:
        pattern = rf"\b{re.escape(fmt.lower())}\b"
        if re.search(pattern, title_lower):
            bonus = 0.3
            return True, bonus, f"Preferred format: {fmt}"

    return True, 0.0, ""


def calculate_wpm(word_count: int, duration_min: float) -> Tuple[float, float, str]:
    """
    Calculates Words Per Minute and a speed score (0.0 to 1.0).
    Target: 100-150 WPM (Clear conversational).
    """
    if duration_min <= 0:
        return 0, 0.5, "Unknown speed"

    wpm = word_count / duration_min

    # Enhanced granular speed bands
    if 100 <= wpm <= 150:
        return wpm, 1.0, "Perfect pace"
    elif 90 <= wpm < 100 or 150 < wpm <= 170:
        return wpm, 0.75, "Good pace"
    elif 80 <= wpm < 90 or 170 < wpm <= 190:
        return wpm, 0.5, "Acceptable pace"
    elif wpm < 80:
        return wpm, 0.3, "Very slow"
    else:  # wpm > 190
        return wpm, 0.1, "Too fast"


def metadata_score(video: Dict, min_dur: int, max_dur: int) -> Tuple[float, str]:
    """
    Scoring based purely on metadata (Views, Duration).
    Note: This is used for INITIAL FILTERING in the pipeline.
    Final scoring uses a different weighted system.
    """
    score = 0.0
    reasons = []

    # Duration
    dur = video.get("duration_min", 0)

    # Soft margins (e.g. 30% leeway)
    soft_min = min_dur * 0.7
    soft_max = max_dur * 1.3

    if min_dur <= dur <= max_dur:
        score += 1.0
        reasons.append("Perfect length")
    elif soft_min <= dur < min_dur:
        score -= 0.1
        reasons.append("Slightly short")
    elif max_dur < dur <= soft_max:
        score -= 0.1
        reasons.append("Slightly long")
    elif dur < soft_min:
        score -= 0.5
        reasons.append("Too short")
    else:  # dur > soft_max
        score -= 0.5
        reasons.append("Too long")

    # Views
    views = video.get("view_count", 0)
    if views > 10000:
        score += 0.5
    elif views < 100:
        score -= 0.5
        reasons.append("Low views")

    return score, ", ".join(reasons)


def score_video(
    video: Dict,
    transcript_text: str,
    cefr_label: str,
    cefr_numeric: int,
    target_level: str,
    target_min_duration: int,
    target_max_duration: int,
    vibe_score: float = 0.5,  # Default to neutral
    topic_score: float = 0.0,  # NEW: profile-specific topic match
) -> Dict:
    """
    10-point scoring system prioritizing CEFR match (40%),
    content quality (30%), speech speed (20%), and metadata (10%).
    Now includes profile-specific topic matching bonus/penalty.

    Based on language acquisition research:
    - CEFR match is most critical (i+1 comprehensible input)
    - Content quality drives engagement
    - Speech speed enables comprehension
    - Metadata is a weak proxy for quality
    - Topic match personalizes for individual learner interests
    """

    # 1. CEFR Match Score (0.0-1.0, weighted 4.0)
    # Implements i+1 (comprehensible input) theory
    target_num = CEFR_TO_INT.get(target_level, 3)
    distance = abs(cefr_numeric - target_num)

    if distance == 0:
        cefr_score = 1.0  # Perfect match
    elif distance == 1:
        # Reward one level UP (i+1) more than one level DOWN
        cefr_score = 0.9 if cefr_numeric > target_num else 0.8
    elif distance == 2:
        cefr_score = 0.4  # Borderline useful
    else:
        cefr_score = 0.0  # Too far off

    cefr_points = cefr_score * 4.0

    # 2. Content Quality / Vibe (0.0-1.0, weighted 3.0)
    vibe_points = vibe_score * 3.0

    # 3. Speech Speed (0.0-1.0, weighted 2.0)
    word_count = len(transcript_text.split())
    duration = video.get("duration_min", 1)
    wpm, speed_score, speed_reason = calculate_wpm(word_count, duration)

    speed_points = speed_score * 2.0

    # 4. Metadata (0.0-1.0, weighted 1.0)
    # Simplified to duration + views
    dur = video.get("duration_min", 0)
    views = video.get("view_count", 0)

    soft_min = target_min_duration * 0.7
    soft_max = target_max_duration * 1.3

    meta_score = 0.0
    meta_reasons = []

    # Duration (80% of metadata score)
    if target_min_duration <= dur <= target_max_duration:
        meta_score += 0.8
        meta_reasons.append("Perfect length")
    elif soft_min <= dur < target_min_duration or target_max_duration < dur <= soft_max:
        meta_score += 0.6
        meta_reasons.append("Acceptable length")
    elif dur < soft_min:
        meta_score += 0.2
        meta_reasons.append("Too short")
    else:  # duration > soft_max
        meta_score += 0.2
        meta_reasons.append("Too long")

    # Views (20% of metadata score) - weak signal
    if views > 5000:
        meta_score += 0.2
    elif views > 1000:
        meta_score += 0.1

    meta_points = meta_score * 1.0

    # FINAL SCORE (0-10 scale + topic bonus/penalty)
    # Topic score can add up to +1.0 or subtract up to -1.0
    final_score = cefr_points + vibe_points + speed_points + meta_points + topic_score

    # Enhanced reason string with component breakdown
    final_reason = (
        f"CEFR {cefr_label} ({cefr_points:.1f}/4.0) | "
        f"{speed_reason} {int(wpm)}wpm ({speed_points:.1f}/2.0) | "
        f"Quality {int(vibe_score*100)}% ({vibe_points:.1f}/3.0) | "
        f"{', '.join(meta_reasons) if meta_reasons else 'OK length'} ({meta_points:.1f}/1.0)"
    )

    video.update(
        {
            "final_score": final_score,
            "cefr_label": cefr_label,
            "cefr_distance": distance,
            "cefr_points": cefr_points,
            "vibe_points": vibe_points,
            "speed_points": speed_points,
            "meta_points": meta_points,
            "topic_points": topic_score,  # NEW
            "wpm": int(wpm),
            "vibe_score": vibe_score,
            "score_reason": final_reason,
        }
    )

    return video

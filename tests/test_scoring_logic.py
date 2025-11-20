import pytest
from finder.scoring import (
    score_video,
    check_sensitive_topics,
    calculate_topic_match_score,
    validate_format,
)
from finder.config import CEFR_TO_INT

# --- SCORING LOGIC TESTS ---


def test_score_video_perfect_match():
    """Test scoring for a perfect B2 educational video."""
    video = {"duration_min": 12, "view_count": 8000, "title": "Perfect B2"}
    target_level = "B2"

    res = score_video(
        video=video,
        transcript_text="word " * 1440,  # 120 wpm
        cefr_label="B2",
        cefr_numeric=CEFR_TO_INT["B2"],
        target_level=target_level,
        target_min_duration=5,
        target_max_duration=25,
        vibe_score=0.9,
    )

    # Expect high score
    # CEFR (4.0) + Vibe (0.9*3=2.7) + Speed (1.0*2=2.0) + Meta (~0.8)
    assert res["final_score"] > 8.0
    assert res["cefr_points"] == 4.0


def test_score_video_wrong_level():
    """Test scoring for a video that is too advanced (C2 for B2)."""
    video = {"duration_min": 10, "view_count": 50000, "title": "Hard C2"}
    target_level = "B2"

    res = score_video(
        video=video,
        transcript_text="word " * 1300,
        cefr_label="C2",
        cefr_numeric=CEFR_TO_INT["C2"],  # 5 vs 3 -> dist 2
        target_level=target_level,
        target_min_duration=5,
        target_max_duration=25,
        vibe_score=0.9,
    )

    # CEFR dist 2 -> 0.4 score * 4.0 = 1.6 points
    assert res["cefr_points"] == 1.6
    assert res["final_score"] < 8.0


def test_score_video_i_plus_one():
    """Test 'i+1' logic: C1 video for B2 student should score well."""
    video = {"duration_min": 15, "view_count": 2000, "title": "Challenge C1"}
    target_level = "B2"

    res = score_video(
        video=video,
        transcript_text="word " * 1500,
        cefr_label="C1",
        cefr_numeric=CEFR_TO_INT["C1"],  # 4 vs 3 -> dist 1 (up)
        target_level=target_level,
        target_min_duration=5,
        target_max_duration=25,
        vibe_score=0.8,
    )

    # CEFR dist 1 up -> 0.9 score * 4.0 = 3.6 points
    assert res["cefr_points"] == 3.6
    assert res["final_score"] > 7.0


# --- FILTERING & REGEX TESTS ---


def test_sensitive_topics_regex():
    # "ass" should NOT match "class"
    video = {"title": "English Class", "description": "Learn quickly"}
    sensitive = ["ass"]
    is_safe, reason = check_sensitive_topics(video, sensitive)
    assert is_safe is True

    # "ass" SHOULD match "kick ass"
    video = {"title": "Kick Ass English", "description": ""}
    is_safe, reason = check_sensitive_topics(video, sensitive)
    assert is_safe is False


def test_topic_match_scoring_profile():
    # Svetlana likes parenting, dislikes gaming
    likes = ["parenting"]
    dislikes = ["gaming"]

    # Gaming video
    vid1 = {"title": "Minecraft Gaming", "description": ""}
    score1, _ = calculate_topic_match_score(vid1, likes, dislikes)
    assert score1 == -0.5

    # Parenting video
    vid2 = {"title": "Parenting Tips", "description": ""}
    score2, _ = calculate_topic_match_score(vid2, likes, dislikes)
    assert score2 == 0.5


def test_format_validation():
    preferred = ["vlog"]
    avoid = ["shorts"]

    # Vlog
    vid1 = {"title": "My Daily Vlog"}
    is_valid, bonus, _ = validate_format(vid1, preferred, avoid)
    assert is_valid is True
    assert bonus == 0.3

    # Shorts
    vid2 = {"title": "Funny Shorts"}
    is_valid, _, _ = validate_format(vid2, preferred, avoid)
    assert is_valid is False

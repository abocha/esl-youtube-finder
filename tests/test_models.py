import pytest
from finder.models import StudentProfile


def test_simple_profile_compatibility():
    """Test backward compatibility with simple profile."""
    simple_json = """{
      "name": "Test Student",
      "cefr": {"current": "B2"},
      "interests": ["technology", "travel"],
      "video_preferences": {"min_duration_min": 3}
    }"""

    profile = StudentProfile.model_validate_json(simple_json)

    assert profile.name == "Test Student"
    assert profile.target_level == "B2"  # Default target is B2 if not specified
    assert profile.cefr.current == "B2"

    queries = profile.get_search_queries(max_queries=5)
    assert len(queries) > 0
    assert "technology" in queries or "travel" in queries


def test_rich_profile_parsing():
    """Test parsing of a complex 'rich' profile."""
    rich_json = """{
      "name": "Svetlana",
      "student_name": "Svetlana",
      "native_language": "Russian",
      "learning_language": "English",
      "cefr": {
        "current": "B1",
        "target": "B2",
        "confidence": 0.9,
        "evidence": "Can hold extended conversations."
      },
      "profile_summary": "Svetlana is a Russian-speaking mother.",
      "topic_preferences": {
        "strong_likes": ["parenting", "business"],
        "dislikes": ["gaming"],
        "sensitive_or_avoid": ["health issues"]
      },
      "interests": [
        {"topic_keywords": ["mom life"], "weight": 1.0}
      ],
      "youtube_search_profile": {
        "primary_topics": [
          {"name": "Parenting", "yt_queries": ["mom vlog"], "weight": 1.0}
        ],
        "avoid_keywords": ["gaming"]
      },
      "video_preferences": {
        "preferred_formats": ["vlog"],
        "avoid_formats": ["shorts"]
      },
      "seed_queries": ["day in the life"]
    }"""

    profile = StudentProfile.model_validate_json(rich_json)

    assert profile.name == "Svetlana"
    assert profile.cefr.current == "B1"
    assert profile.cefr.target == "B2"
    assert "parenting" in profile.topic_preferences.strong_likes
    assert "gaming" in profile.topic_preferences.dislikes
    assert "health issues" in profile.topic_preferences.sensitive_or_avoid

    # Check query generation
    queries = profile.get_search_queries(max_queries=10)
    assert "day in the life" in queries
    assert "mom vlog" in queries


def test_weighted_query_selection():
    """Test that weighted queries are prioritized correctly."""
    weighted_json = """{
      "name": "Test",
      "youtube_search_profile": {
        "primary_topics": [
          {"name": "High", "yt_queries": ["high1", "high2"], "weight": 1.0}
        ],
        "secondary_topics": [
          {"name": "Low", "yt_queries": ["low1"], "weight": 0.1}
        ]
      },
      "seed_queries": ["seed"]
    }"""

    profile = StudentProfile.model_validate_json(weighted_json)
    queries = profile.get_search_queries(max_queries=10)

    # Seed and high weight should be first
    top_queries = queries[:3]
    assert "seed" in top_queries
    assert "high1" in top_queries or "high2" in top_queries

import pytest
from unittest.mock import MagicMock
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

@pytest.fixture
def mock_youtube_client():
    client = MagicMock()
    return client

@pytest.fixture
def mock_transcript_fetcher():
    fetcher = MagicMock()
    return fetcher

@pytest.fixture
def sample_profile_json():
    return '''
    {
        "name": "Test Student",
        "cefr": {"current": "B1"},
        "interests": ["coding", "python"],
        "avoid": {"keywords": ["rust"]},
        "video_preferences": {"min_duration_min": 5, "max_duration_min": 15}
    }
    '''

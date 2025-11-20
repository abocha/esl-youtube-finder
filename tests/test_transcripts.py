import pytest
from unittest.mock import MagicMock, patch
from finder.transcripts import TranscriptFetcher, TranscriptResult

@pytest.fixture
def fetcher(tmp_path):
    with patch('finder.transcripts.TRANSCRIPT_CACHE_DIR', tmp_path):
        return TranscriptFetcher()

def test_cache_hit(fetcher):
    # Setup cache
    video_id = "test_vid"
    cache_file = fetcher.cache_dir / f"{video_id}.txt"
    cache_file.write_text("Cached text", encoding="utf-8")
    
    result = fetcher.fetch(video_id)
    assert result.text == "Cached text"
    assert result.source == "cache"

@patch('finder.transcripts.YouTubeTranscriptApi')
def test_youtube_api_success(mock_api, fetcher):
    mock_transcript = MagicMock()
    mock_transcript.fetch.return_value = [{'text': 'Hello world'}]
    
    mock_list = MagicMock()
    mock_list.find_transcript.return_value = mock_transcript
    mock_api.list_transcripts.return_value = mock_list
    
    result = fetcher.fetch("vid_123")
    assert result.text == "Hello world"
    assert result.source == "youtube_api"

@patch('finder.transcripts.YouTubeTranscriptApi')
def test_cleaning_logic(mock_api, fetcher):
    # Test cleaning of timestamps and artifacts
    raw_text = "Hello [00:01] world. [Music] Speaker 1: Hi."
    
    mock_transcript = MagicMock()
    mock_transcript.fetch.return_value = [{'text': raw_text}]
    mock_list = MagicMock()
    mock_list.find_transcript.return_value = mock_transcript
    mock_api.list_transcripts.return_value = mock_list
    
    result = fetcher.fetch("vid_clean")
    # Expect: "Hello world. Hi." (collapsed spaces)
    assert "Hello world." in result.text
    assert "Hi." in result.text
    assert "[00:01]" not in result.text
    assert "[Music]" not in result.text
    assert "Speaker 1:" not in result.text

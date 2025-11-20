import pytest
from unittest.mock import MagicMock, patch
from finder.pipeline import ESLSearchPipeline

@patch('finder.pipeline.build_youtube_client')
@patch('finder.pipeline.TranscriptFetcher')
@patch('finder.pipeline.VibeChecker')
def test_pipeline_run_basic(mock_vibe_cls, mock_fetcher_cls, mock_yt_builder, sample_profile_json):
    # Setup Mocks
    mock_yt = MagicMock()
    mock_yt_builder.return_value = mock_yt
    
    # Mock Search
    # We need to mock search_videos_for_queries which is imported in pipeline
    # But since it's a standalone function, we should patch where it's used or the function itself
    pass

@patch('finder.pipeline.search_videos_for_queries')
@patch('finder.pipeline.build_youtube_client')
@patch('finder.pipeline.TranscriptFetcher')
@patch('finder.pipeline.VibeChecker')
def test_pipeline_flow(mock_vibe_cls, mock_fetcher_cls, mock_yt_builder, mock_search, sample_profile_json):
    # 1. Mock Search Results
    mock_search.return_value = [
        {
            "video_id": "v1", 
            "title": "Python Tutorial", 
            "duration_min": 10, 
            "view_count": 1000,
            "channel": "Code",
            "description": "Learn Python",
            "publish_date": "2023-01-01"
        }
    ]
    
    # 2. Mock Transcript
    mock_fetcher_instance = mock_fetcher_cls.return_value
    mock_fetcher_instance.fetch.return_value = MagicMock(text="Python is great.", source="youtube_api")
    
    # 3. Mock Vibe
    mock_vibe_instance = mock_vibe_cls.return_value
    mock_vibe_instance.check.return_value = 0.8
    
    # Run Pipeline
    pipeline = ESLSearchPipeline()
    results, stats = pipeline.run(
        profile_json=sample_profile_json,
        max_results_per_query=5,
        max_queries=2,
        max_transcripts=1,
        allow_paid=False
    )
    
    assert len(results) == 1
    assert results[0]['video_id'] == 'v1'
    assert results[0]['cefr_label'] != 'N/A'
    assert stats.transcript_success_count == 1

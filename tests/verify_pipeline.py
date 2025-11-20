import logging
import sys
from unittest.mock import MagicMock, patch
from finder.pipeline import ESLSearchPipeline

# Setup logging
logging.basicConfig(level=logging.INFO)

def get_mock_yt_client():
    mock = MagicMock()
    # Mock search response
    mock.search.return_value = [
        {
            "video_id": "test_vid_1",
            "title": "Test Video Python",
            "description": "A video about Python",
            "channel": "Test Channel",
            "duration_min": 5.0,
            "view_count": 1000,
            "publish_date": "2023-01-01"
        }
    ]
    return mock

def get_mock_transcript_fetcher(*args, **kwargs):
    mock = MagicMock()
    mock_transcript = MagicMock()
    mock_transcript.text = "This is a dummy transcript about Python programming."
    mock.fetch.return_value = mock_transcript
    return mock

def verify():
    print("Initializing Pipeline...")
    
    # Patch the client builder and TranscriptFetcher
    with patch('finder.pipeline.build_youtube_client', side_effect=get_mock_yt_client), \
         patch('finder.pipeline.TranscriptFetcher', side_effect=get_mock_transcript_fetcher):
        try:
            pipeline = ESLSearchPipeline()
        except Exception as e:
            print(f"Failed to init pipeline: {e}")
            sys.exit(1)

        print("Pipeline Initialized. Running dry run with MOCK YouTube...")
        
        profile_json = '''
        {
            "name": "Test",
            "cefr": {"current": "B1"},
            "interests": ["python programming"],
            "avoid": {"keywords": []},
            "video_preferences": {"min_duration_min": 1, "max_duration_min": 10}
        }
        '''
        
        try:
            # Run with minimal constraints to be fast
            results, stats = pipeline.run(
                profile_json=profile_json,
                max_results_per_query=1,
                max_queries=1,
                max_transcripts=1,
                allow_paid=False
            )
            print(f"Success! Found {len(results)} videos.")
            print(f"Stats: {stats}")
        except Exception as e:
            print(f"Pipeline run failed: {e}")
            sys.exit(1)

if __name__ == "__main__":
    verify()

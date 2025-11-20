import pytest
from finder.ui_utils import get_status_html


def test_status_html_success():
    stats = {
        "final_count": 10,
        "raw_count": 50,
        "transcript_success_count": 8,
        "total_time": 12.34,
    }
    html = get_status_html(stats, success=True)

    assert "Analysis Complete" in html
    assert "Found <b>10</b> recommendations" in html
    assert "12.34s" in html
    assert "color: #022c22" in html  # Emerald-900


def test_status_html_fallback():
    stats = {
        "final_count": 5,
        "raw_count": 20,
        "transcript_success_count": 0,  # No transcripts
        "total_time": 5.0,
    }
    html = get_status_html(stats, success=True)

    assert "Metadata-Only Results" in html
    assert "Found <b>5</b> recommendations" in html


def test_status_html_error():
    html = get_status_html({}, success=False, error_msg="API Error")

    assert "Error" in html
    assert "API Error" in html
    assert "color: #991b1b" in html  # Red text color

# finder/ui_utils.py
from typing import Dict, Any

def get_status_html(stats: Dict[str, Any], success: bool = True, error_msg: str = "") -> str:
    """Generates clean, modern status cards for the UI."""
    
    if not success:
        return f"""
        <div style="background: #fee2e2 !important; color: #991b1b !important; padding: 1.5rem; border-radius: 0.5rem; border-left: 6px solid #ef4444; font-family: sans-serif;">
            <h3 style="margin:0 0 0.5rem 0; display:flex; align-items:center; color: #991b1b !important;">❌ Error</h3>
            <p style="margin:0; color: #991b1b !important;">{error_msg}</p>
        </div>
        """

    # Success or Fallback State
    is_fallback = stats.get("transcript_success_count", 0) == 0
    
    color_bg = "#ecfdf5" if not is_fallback else "#eef2ff" # Emerald-50 or Indigo-50
    color_text = "#022c22" if not is_fallback else "#312e81" # Emerald-900 or Indigo-900
    color_border = "#10b981" if not is_fallback else "#6366f1"
    icon = "🎉" if not is_fallback else "⚠️"
    title = "Analysis Complete" if not is_fallback else "Metadata-Only Results"
    
    sub_msg = (
        f"Analyzed <b>{stats['transcript_success_count']}</b> transcripts." 
        if not is_fallback else 
        "Could not fetch transcripts. Showing best matches based on metadata."
    )

    return f"""
    <div style="background: {color_bg} !important; color: {color_text} !important; padding: 1.5rem; border-radius: 0.5rem; border-left: 6px solid {color_border}; font-family: sans-serif; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
        <div style="display:flex; justify-content:space-between; align-items:start;">
            <div>
                <h3 style="margin:0 0 0.5rem 0; font-size: 1.25rem; color: {color_text} !important;">{icon} {title}</h3>
                <p style="margin:0; opacity:0.9; color: {color_text} !important;">Found <b>{stats['final_count']}</b> recommendations from <b>{stats['raw_count']}</b> candidates.</p>
                <p style="margin:0.5rem 0 0 0; font-size: 0.9rem; opacity: 0.8; color: {color_text} !important;">{sub_msg}</p>
            </div>
            <div style="text-align:right; font-size:0.85rem; opacity:0.7; color: {color_text} !important;">
                ⏱️ {stats['total_time']:.2f}s
            </div>
        </div>
    </div>
    """
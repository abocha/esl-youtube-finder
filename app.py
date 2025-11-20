# app.py
import os
import sys
import logging
import tempfile
import warnings
from datetime import datetime, timezone

# Suppress Gradio/Starlette deprecation warning
warnings.filterwarnings(
    "ignore", category=DeprecationWarning, message=".*HTTP_422_UNPROCESSABLE_ENTITY.*"
)

import gradio as gr
import pandas as pd
from dataclasses import asdict

# Import clean modules (Ensure finder/pipeline.py and finder/ui_utils.py exist)
from finder.pipeline import ESLSearchPipeline
from finder.ui_utils import get_status_html
from terminal_logger import TerminalLogger

# --- Setup Logging ---
os.makedirs("logs", exist_ok=True)
timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(f"logs/esl_finder_{timestamp}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
app_logger = TerminalLogger("esl_finder.app")

# --- Initialize Pipeline ---
try:
    pipeline = ESLSearchPipeline()
    app_logger.info("Pipeline initialized successfully.")
except Exception as e:
    app_logger.error(f"Critical: Failed to init pipeline: {e}")
    sys.exit(1)


def find_videos_ui(
    profile_json: str,
    max_res: int,
    max_queries: int,
    max_trans: int,
    allow_paid: bool,
    progress=gr.Progress(),
):
    """Gradio wrapper for the logic pipeline."""
    try:
        results, stats = pipeline.run(
            profile_json, max_res, max_queries, max_trans, allow_paid, progress
        )

        # Convert stats to dict for the UI helper
        stats_dict = asdict(stats)
        status_html = get_status_html(stats_dict, success=True)

        # Format for DataTable
        table_data = []
        for r in results:
            # Parse WPM and Vibe for display (default to 0/Neutral if missing)
            wpm = r.get("wpm", 0)
            vibe = r.get("vibe_score", 0.5)
            vibe_display = f"{int(vibe * 100)}%"

            # Get component scores for new 10-point system
            cefr_pts = r.get("cefr_points", 0.0)
            vibe_pts = r.get("vibe_points", 0.0)
            speed_pts = r.get("speed_points", 0.0)
            meta_pts = r.get("meta_points", 0.0)

            row = [
                round(r.get("final_score", 0), 2),
                r.get("cefr_label", "N/A"),
                f"{cefr_pts:.1f}",  # NEW: CEFR points
                f"{vibe_pts:.1f}",  # NEW: Quality points
                f"{speed_pts:.1f}",  # NEW: Speed points
                wpm,  # WPM value
                r.get("title", "Unknown"),
                f"https://youtu.be/{r['video_id']}",
                round(r.get("duration_min", 0), 1),
                r.get("view_count", 0),
                r.get("transcript_source", "N/A"),
                r.get("score_reason", ""),
            ]
            table_data.append(row)

        return status_html, table_data

    except Exception as e:
        app_logger.exception("Search failed")
        return get_status_html({}, success=False, error_msg=str(e)), []


# --- Export Handlers ---


def export_csv(df):
    """Export DataFrame to CSV."""
    if df is None or df.empty:
        return None

    # Create a named temp file that persists until closed/deleted
    # Gradio handles the file serving
    fd, path = tempfile.mkstemp(suffix=".csv")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            df.to_csv(f, index=False)
        return path
    except Exception as e:
        app_logger.error(f"CSV Export failed: {e}")
        return None


def export_md(df):
    """Export DataFrame to Markdown."""
    if df is None or df.empty:
        return None

    fd, path = tempfile.mkstemp(suffix=".md")

    # Manual MD table construction to avoid 'tabulate' dependency
    try:
        headers = list(df.columns)
        lines = [
            f"# ESL YouTube Finder Results - {datetime.now().strftime('%Y-%m-%d')}\n",
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
        ]

        for _, row in df.iterrows():
            # Sanitize cells for MD table
            clean_row = [str(x).replace("|", "\\|").replace("\n", " ") for x in row]
            lines.append("| " + " | ".join(clean_row) + " |")

        content = "\n".join(lines)

        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        return path
    except Exception as e:
        app_logger.error(f"MD Export failed: {e}")
        return None


# --- UI Definition ---
# Custom CSS to force proper colors in the status card
custom_css = """
/* Force text color inheritance and override Gradio theme */
#status-card div,
#status-card h3, 
#status-card p,
#status-card b,
#status-card span {
    color: inherit !important;
}

/* Ensure the parent container respects its inline styles */
#status-card > div {
    background: inherit !important;
    color: inherit !important;
}
"""

with gr.Blocks(title="ESL YouTube Finder", theme=gr.themes.Soft(), css=custom_css) as demo:  # type: ignore
    gr.Markdown("# 🎓 ESL YouTube Finder\nSearch, Transcript & CEFR Pipeline")

    with gr.Row():
        # Left Column: Controls
        with gr.Column(scale=1):
            profile_input = gr.Textbox(
                label="Student Profile (JSON)",
                lines=15,
                value='{\n  "name": "Student",\n  "cefr": {"current": "B2"},\n  "interests": ["technology", "travel"],\n  "video_preferences": {"min_duration_min": 3}\n}',
            )

            with gr.Group():
                max_res = gr.Slider(5, 50, value=10, step=1, label="Results per Query")
                max_queries = gr.Slider(
                    1, 10, value=5, step=1, label="Max YouTube Queries"
                )
                max_trans = gr.Slider(1, 20, value=5, step=1, label="Max Transcripts")
                allow_paid = gr.Checkbox(
                    label="Allow Paid APIs (Supadata)", value=False
                )

            btn_run = gr.Button("🚀 Find Videos", variant="primary", size="lg")

        # Right Column: Results
        with gr.Column(scale=2):
            status_output = gr.HTML(label="Status", elem_id="status-card")
            table_output = gr.Dataframe(
                headers=[
                    "Score /10",
                    "CEFR",
                    "C-Pts",
                    "Q-Pts",
                    "S-Pts",
                    "WPM",
                    "Title",
                    "Link",
                    "Min",
                    "Views",
                    "Source",
                    "Reason",
                ],
                datatype=[
                    "number",
                    "str",
                    "str",
                    "str",
                    "str",
                    "number",
                    "str",
                    "markdown",
                    "number",
                    "number",
                    "str",
                    "str",
                ],
                interactive=False,
                wrap=True,
            )

            # Export Section
            with gr.Row():
                btn_csv = gr.Button("📄 Export CSV")
                btn_md = gr.Button("📝 Export Markdown")

            with gr.Row():
                csv_file = gr.File(label="CSV Download")
                md_file = gr.File(label="MD Download")

    # Wiring
    btn_run.click(
        fn=find_videos_ui,
        inputs=[profile_input, max_res, max_queries, max_trans, allow_paid],
        outputs=[status_output, table_output],
    )

    btn_csv.click(fn=export_csv, inputs=table_output, outputs=csv_file)
    btn_md.click(fn=export_md, inputs=table_output, outputs=md_file)

if __name__ == "__main__":
    demo.launch()

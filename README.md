---
title: Esl Youtube Finder LLM
emoji: 🌖
colorFrom: indigo
colorTo: pink
sdk: gradio
sdk_version: 5.49.1
python_version: 3.12.3
app_file: app.py
pinned: false
short_description: Find the perfect video for your ESL student
---

# ESL YouTube Finder

A Gradio tool for finding YouTube videos that fit a specific ESL learner, not just a generic CEFR level.

Given a student profile, the app generates search queries, gathers candidates from YouTube, retrieves transcripts through a fallback chain, estimates language difficulty, scores content fit, and ranks the results with an explanation of why each video may work.

## Why this exists

Finding a useful classroom video is usually a multi-constraint search problem:

- the topic has to interest this particular learner;
- the language should be close to the learner's current CEFR level;
- the pace and length need to be workable;
- captions and transcripts are not reliably available through one source;
- YouTube API quota and transcript-provider failures make brute-force search expensive.

This project turns those constraints into a repeatable pipeline rather than a sequence of manual tabs.

## Pipeline

```text
Student profile (JSON)
        |
        v
query generation
        |
        v
YouTube Data API search
        |
        v
metadata filtering + ranking
        |
        v
transcript fallback chain
        |
        +--> local cache
        +--> youtube-transcript-api
        +--> yt-dlp
        +--> pytubefix
        +--> Supadata (optional paid fallback)
        |
        v
CEFR + pace + topic + quality analysis
        |
        v
final score /10 + explanation
        |
        +--> Gradio table
        +--> CSV export
        +--> Markdown export
```

The transcript layer is deliberately redundant because transcript access is the least reliable part of the workflow.

## What it evaluates

The ranking pipeline combines several signals instead of treating CEFR as the whole problem:

- **language level**: estimated CEFR distance from the learner's target level;
- **speaking pace**: words per minute;
- **topic fit**: profile interests and dislikes;
- **format fit**: preferred and avoided video formats;
- **metadata quality**: duration and other candidate-level signals;
- **content quality / "vibe"**: optional local-model scoring against learner context.

The UI exposes component scores so the final ranking is inspectable rather than a single opaque number.

## Student profile

The app accepts a JSON profile describing the learner and video constraints. A minimal example:

```json
{
  "name": "Student",
  "cefr": {
    "current": "B2"
  },
  "interests": [
    {
      "topic_keywords": ["technology", "travel"],
      "weight": 1.0
    }
  ],
  "video_preferences": {
    "min_duration_min": 4,
    "max_duration_min": 20
  }
}
```

The exact profile model is richer than this example and supports weighted interests, sensitive/avoided topics, preferred formats, and format exclusions.

## Stack

- Python 3.12
- Gradio
- YouTube Data API v3
- youtube-transcript-api
- yt-dlp + pytubefix transcript fallbacks
- Transformers / PyTorch for optional local-model content scoring
- CEFR estimation utilities
- pytest

## Local setup

Create and activate a virtual environment, then install the runtime dependencies:

```bash
python -m venv .venv
pip install -r requirements.txt
```

Copy the environment template:

```bash
cp .env.example .env
```

On PowerShell:

```powershell
Copy-Item .env.example .env
```

At minimum, set `YOUTUBE_API_KEY` in `.env`.

Then run:

```bash
python app.py
```

Gradio will print the local URL in the terminal.

## Configuration

`finder/config.py` contains the runtime settings. The most useful environment variables are:

| Variable | Purpose |
| --- | --- |
| `YOUTUBE_API_KEY` | Required key for YouTube Data API search and metadata. |
| `SUPADATA_API_KEY` | Optional paid transcript fallback. |
| `ENABLE_VIBE_CHECK` | Enable/disable local-model content-quality scoring. |
| `MODEL_ID` | Hugging Face model used by the vibe checker. |
| `VIBE_MAX_LENGTH` | Maximum transcript length passed to the vibe model. |

The default vibe model is `microsoft/Phi-4-mini-instruct`. Disable the vibe check if you want a lighter setup.

## Development

Run the test suite with:

```bash
pytest
```

Useful implementation modules:

```text
finder/
  profile.py         # profile parsing + query extraction
  youtube_client.py  # YouTube search + metadata
  transcripts.py     # transcript fallback chain + cache
  cefr.py            # language-level estimation
  vibe.py            # optional local-model quality signal
  scoring.py         # component and final scoring
  pipeline.py        # end-to-end orchestration
```

See [design.md](design.md) for the reasoning behind the search, transcript, and scoring strategy.

## Practical limitations

- YouTube search quality and API quota affect the candidate pool.
- Transcript access can fail or be rate-limited despite the fallback chain.
- Local-model scoring is significantly heavier than the rest of the pipeline.
- CEFR estimation is a heuristic signal, not a formal proficiency assessment.

Those constraints are part of the project rather than hidden edge cases: the pipeline tracks transcript attempts, successes, filtering, and final result counts so failures are visible.

# ESL YouTube Finder – Transcript & Scoring Pipeline (v3, with pytubefix)

> Goal: reliably find **level‑appropriate, interesting YouTube videos** for a specific ESL student – under real‑world constraints (fragile transcripts, rate limits, limited credits).

We design everything around three core questions:

1. **Q1: What makes a “good video” for this student?**  
2. **Q2: How do we *search* YouTube so that good candidates even appear?**  
3. **Q3: How do we *score & rank* candidates using noisy metadata + fragile transcripts?**

The rest of the document is just: definitions → pipeline → transcript layer → scoring → knobs.

---

## 1. Notation & basic objects

### 1.1 CEFR encoding

We map CEFR labels to numbers for distance calculations:

- A1=1, A2=2, B1=3, B2=4, C1=5, C2=6  → `CEFR_TO_NUM[label]`
- For a video `v`:
  - predicted label: `L(v) ∈ {A1..C2}`
  - numeric: `n(v) = CEFR_TO_NUM[L(v)]`
- For student profile: target level `L*`, `n* = CEFR_TO_NUM[L*]`.
- **Distance:** `d_cefr(v) = |n(v) − n*|`.

### 1.2 Video metadata record

We treat a video as a dict‑like record:

```python
Video = {
  "video_id": str,
  "title": str,
  "description": str,
  "channel": str,
  "tags": list[str],
  "duration_min": float,
  "view_count": int,
  "publish_date": datetime | None,
  # scores attached later:
  "metadata_score": float,
  "metadata_reason": str,
  "cefr_label": str | None,
  "cefr_confidence": float | None,
  "cefr_distance": float | None,
  "final_score": float | None,
}
```

We don’t over‑formalise with dataclasses yet, but conceptually this is the shape.

---

## 2. Student profile model (what we know about the learner)

`profile.json` is our **single source of truth** about the learner and their preferences.

### 2.1 Minimal schema (v3)

```jsonc
{
  "name": "Luiza",
  "cefr": { "current": "B2" },
  "interests": [
    { "topic_keywords": ["work-life balance", "burnout", "remote work"], "weight": 1.0 },
    { "topic_keywords": ["psychology", "mental health"], "weight": 0.9 },
    { "topic_keywords": ["books", "reading", "booktube"], "weight": 0.8 },
    { "topic_keywords": ["daily life", "vlogs", "routines"], "weight": 0.6 }
  ],
  "avoid": {
    "keywords": ["kids", "nursery rhymes", "minecraft", "asmr"],
    "channels": [],
    "genres": ["music videos", "pure comedy sketches"]
  },
  "video_preferences": {
    "min_duration_min": 4,
    "max_duration_min": 22,
    "prefer_playlists": false
  }
}
```

### 2.2 How to refine the profile over time

Later we can:

- Feed **lesson transcripts** (you already store them) into Gemini / LLM to:
  - extract top recurring topics, collocations, tasks she enjoys;
  - generate candidate `topic_keywords` and `avoid.keywords` automatically.
- Add attributes like:
  - `preferred_speaker_gender`, `accent_preferences`, `energy_level` (calm vs hyper), etc.

The point: **all future heuristics must be describable using only this profile + video data.**

---

## 3. Q1 – What makes a “good video” for this student?

We define **three buckets of criteria**:

1. **Language match** – CEFR difficulty near her level.
2. **Content match** – topics, tone, genre she’ll actually want to watch.
3. **Technical shape** – length, structure, presence of captions.

### 3.1 Language match

For a candidate video `v`:

- We want `d_cefr(v) = |n(v) − n*|` to be small.
- Default targets:
  - `d_cefr(v) ∈ {0, 1}` → **ideal**, core set.
  - `d_cefr(v) = 2` → “stretch / warm‑up / passive listening” material.

### 3.2 Content match

Signals we like:

- Title/description/tags mention weighted `topic_keywords` from profile.
- No hard matches from `profile.avoid.keywords / channels / genres`.
- Thumbnail + title suggest **non‑clickbait, non‑sensational** content.

### 3.3 Technical shape

We prefer videos that:

- Stay within `[min_duration, max_duration]` (e.g. 4–22 minutes).  
  We can encode a duration utility function:

```text
Let t = duration_min.

f_dur(t) =
  -1.0, if t < min_duration
  +1.0, if min_duration ≤ t ≤ max_duration
  -0.5, if t > max_duration and t ≤ 1.5 * max_duration
  -1.0, if t > 1.5 * max_duration
```

- Have **English captions** (native or auto‑generated).  
- Have a reasonable view count and not be 15‑year‑old SD uploads.

All this becomes features in the metadata score.

---

## 4. Q2 – Generating robust YouTube queries

### 4.1 Query templates

We don’t rely on a single query. Instead, we build **K distinct queries** from:

```text
query = [interest_topic] + [format_phrase] + [soft CEFR hint]
```

Examples:

- `"work life balance vlog B2 English"`
- `"burnout story time subtitles on"`
- `"morning routine remote worker english subtitles"`
- `"booktube reading vlog clear english"`

Format phrases (configurable list):

- `"vlog"`, `"storytime"`, `"talk"`, `"podcast"`, `"q&a"`, `"advice"`, `"explained"`, etc.

We then cycle through interests × formats to get a **diverse query set** and avoid over‑fitting to only parenting/business.

### 4.2 Using the profile weights

For each interest `i` with weight `w_i` we can:

- allocate `⌈K * w_i / Σw⌉` queries;
- include at least one **general adult life** interest for any profile, e.g. `"daily life"`, `"week in my life"`, `"routines"`.

### 4.3 Search strategy

Per query we:

1. call YouTube Search API (or pytubefix search tools later if needed);  
2. collect top `R` videos (e.g. `R=10`);  
3. deduplicate by `video_id` across all queries.

Result: pool of `M` raw candidates (e.g. `M ≈ 50–80`).

---

## 5. Metadata scoring (no transcripts yet)

We assign each raw video a **metadata score** `S_meta(v)` before we touch transcripts.

### 5.1 Features

Let:

- `F_topic(v)` ∈ [−2, +3] – how well title/description/tags match profile interests vs avoid‑lists.
- `F_dur(v)` ∈ [−1, +1] – from `f_dur(t)` above.
- `F_views(v)` ∈ [−0.5, +0.5] – reward “normal” popularity, penalise ultra‑low / suspicious.
- `F_format(v)` ∈ [−1, +2] – based on format phrases: `vlog`, `podcast`, `shorts`, etc.

Example scoring formula:

```text
S_meta(v) =
  w_topic  * F_topic(v)  +
  w_dur    * F_dur(v)    +
  w_views  * F_views(v)  +
  w_format * F_format(v)

Typical weights:
  w_topic  = 1.5
  w_dur    = 1.0
  w_views  = 0.5
  w_format = 1.0
```

### 5.2 Why this matters

- `S_meta` is **cheap** (no transcripts).  
- We’ll use it to decide **which videos even deserve transcript attempts**, given that transcript fetching is fragile and limited.

---

## 6. Selecting videos for transcript fetching

We choose a small subset `T ⊂ videos` for expensive transcript work.

### 6.1 Basic rule

1. Sort videos descending by `S_meta(v)`.  
2. Take the top `N_primary` (e.g. 10–15).  
3. Optionally add a few **exploration** candidates from lower ranks that cover:
   - under‑represented interests,
   - or slightly off duration range but very on‑topic.

So `|T| = N_transcripts ≈ 10–20`, configurable.

### 6.2 Motivation

- We accept that **transcripts are the scarce resource**, not GPU/LLM time.  
- So **only good metadata candidates are allowed to “burn” transcript attempts**.

---

## 7. Transcript Provider Layer (pytubefix + yt‑dlp + Supadata)

We treat transcripts as coming from a **pluggable provider stack**:

```text
p1 = pytubefix captions      (main path)
p2 = yt-dlp subtitles        (fallback)
p3 = Supadata API            (last-resort, credit-limited)
```

The app never cares *how* we got the text – it just calls:

```python
text, source, meta = get_transcript(video_id)
```

and gets either `(None, "none", {...})` or a text string.

### 7.1 Provider P1 – pytubefix captions (preferred)

pytubefix can:

- grab captions for a YouTube URL: `yt = YouTube(url); captions = yt.captions`;  
- list available languages;  
- access native and auto‑generated tracks, e.g. `'en'` and `'a.en'`;  
- convert to plain text via a helper like `generate_txt_captions()` or `save_captions()`.

That gives us plain transcript text without extra scraping logic. fileciteturn13file0L1-L35

**Strategy:**

1. Build URL: `url = f"https://www.youtube.com/watch?v={video_id}"`.
2. `yt = YouTube(url)` inside a `try/except` that handles `VideoUnavailable`, `AgeRestrictedError`, `BotDetection`, etc. fileciteturn13file0L356-L413
3. Prefer caption tracks in this order:
   - `'en'` (user‑uploaded English)
   - `'a.en'` (auto English)
   - any caption whose name suggests English (e.g. `"English"`, `"English (auto-generated)"`).
4. Convert to text (plain, not SRT) and return.

If no usable English captions: provider returns `(None, "pytubefix", {"reason": "no_en_caption"})`.

### 7.2 Provider P2 – yt‑dlp subtitles fallback

If pytubefix fails or yields no English captions:

- Use yt‑dlp with options roughly like:
  - `--write-auto-subs`, `--sub-lang en`, `--skip-download`, `--sub-format vtt/srt`, etc.
- Parse resulting VTT/SRT into plain text.

We call this only for the same `T` videos (top metadata candidates) and with backoff/sleep to not anger YouTube.

### 7.3 Provider P3 – Supadata (credit‑limited last resort)

Supadata gives an HTTP API that can:

- fetch transcripts by URL with modes `native / auto / generate`;  
- rate‑limit 1 req/s on the free plan, 100 credits/month;  
- each transcript fetch costs 1 credit, AI‑generated minutes cost extra.

We use Supadata only when:

- both pytubefix and yt‑dlp failed; **and**
- the video is really high‑value by metadata score (top X); **and**
- we haven’t spent our monthly “Supadata budget” (e.g. 30–50 credits reserved for this tool).

That way “scarce” Supadata credits are spent only on **golden candidates**.

### 7.4 Caching layer for transcripts

We must cache per video_id:

```jsonc
{
  "video_id": "GWwwLXU9nTs",
  "text_path": "cache/transcripts/GWwwLXU9nTs.txt",
  "provider": "pytubefix",   // or yt-dlp / supadata
  "lang": "en",
  "last_checked": "2025-11-16T15:00:00Z",
  "checksum": "sha256:..."   // optional
}
```

Cache rules:

- Before any provider call, check local cache.  If exists → return immediately.
- On successful provider call, write transcript to `cache/transcripts/{video_id}.txt` and update index.
- Optionally keep a **small SQLite/JSON index** to query by `video_id` quickly.

---

## 8. Transcript post‑processing & sampling

Once we get full captions, we need a **clean sample** for the CEFR model.

### 8.1 Cleaning

Steps:

1. Remove timestamps / markup (if we got SRT/VTT).  
2. Strip extra spaces, join short lines.  
3. Drop system messages like `[Music]`, `[Applause]`.

### 8.2 Sampling strategy

We don’t have to feed the full transcript; we can pick a “representative slice”. For a transcript as sequence of tokens `T[0..N-1]`:

- Let max token length for model input be `L_max` (e.g. 512–1024 tokens).  
- Choose a window somewhere in the **middle 60%** of the video to avoid intros/outros:

```text
start = floor(0.2 * N)
end   = ceil(0.8 * N)

sample = middle[start : start + L_max]
```

If `N < L_max`, just use full text.

Result: a sample that reflects typical speech rate and complexity.

---

## 9. CEFR inference

We use a Hugging Face text classification pipeline, e.g. `AbdulSami/bert-base-cased-cefr`.

For a transcript sample `sample_text`:

```python
probs = cefr_clf(sample_text)  # list of {"label": "B2", "score": 0.81}, etc.
L_hat = argmax_label(probs)
conf  = max_score(probs)
```

We then compute:

- `n(v) = CEFR_TO_NUM[L_hat]`  
- `d_cefr(v) = |n(v) − n*|`  
- store `cefr_label`, `cefr_confidence`, `cefr_distance` in the `Video` record.

---

## 10. Q3 – Combining metadata & CEFR into a final score

We now have for each video `v`:

- `S_meta(v)` – metadata‑only score;  
- `d_cefr(v)` – distance from target level;  
- `conf(v)` – model confidence for `L_hat` (0–1).

### 10.1 CEFR penalty term

We define a CEFR adjustment term:

```text
S_cefr(v) = a * (1 − d_cefr(v) / D_max) + b * (conf(v) − 0.5)

where:
  D_max = 3 (we cap distance),
  a     = 2.0  (weight for closeness),
  b     = 1.0  (weight for confidence).
```

Interpretation:

- If `d_cefr = 0` and `conf = 0.9`, then `S_cefr ≈ 2.0 + 0.4 = 2.4` (strong boost).  
- If `d_cefr = 2` and `conf = 0.6`, then `S_cefr ≈ 2*(1 − 2/3) + 0.1 ≈ 0.77` (mild boost).  
- If `d_cefr ≥ 3`, we can clamp `S_cefr` to a small or even negative value.

### 10.2 Final score

```text
S_final(v) = S_meta(v) + w_cefr * S_cefr(v)

with e.g. w_cefr = 1.2
```

We then:

1. Filter out videos with `d_cefr(v) > D_cutoff` (e.g. 2.5) if we want a strict set.  
2. Sort remaining videos by `S_final(v)` descending.  
3. Return top `K_result` (e.g. 10–15) to the UI.

The UI can separately show:

- `metadata_reason` (why metadata liked it);  
- `cefr_label` and `cefr_distance`;  
- transcript source (`pytubefix / yt-dlp / supadata / none`).

---

## 11. Weak points & how this design addresses them

### 11.1 Search quality

**Risk:** profile → queries might still lean too much into parenting/business.

Mitigations:

- Always include some **generic adult life** queries in `interests`.  
- For each student, maintain a tiny “curated” list of *approved channels*; add queries like `"<channel name> work life balance"` where you already trust style.
- Long‑term: use lesson transcripts + LLM to refine `profile.interests` instead of manually guessing.

### 11.2 Transcript fragility

**Risk:** YouTube keeps breaking transcript endpoints, IP bans, etc.

Mitigations in v3 design:

- We rely on **pytubefix**, which actively tracks YouTube changes and exposes captions API.
- We have a **yt‑dlp** fallback for subtitles when pytubefix fails.
- We have a **Supadata** fallback for “must‑have” videos, within credit limits.
- We aggressively **cache transcripts** per video_id to avoid repeated calls.

### 11.3 Over‑engineering vs usefulness

We keep things grounded in the three core questions:

- If a feature doesn’t clearly improve **search**, **language match**, or **content match**, it’s optional.
- We aim for **few interpretable weights** rather than a giant opaque scoring function.

---

## 12. Config knobs you can actually tweak as a teacher

Exposed settings (via config or UI sliders):

- `N_queries` – how many search queries to run.  
- `R_per_query` – raw results per query.
- `N_transcripts` – how many top metadata videos get transcript attempts.
- `D_cutoff` – max acceptable CEFR distance.
- `w_topic, w_dur, w_views, w_format, w_cefr` – scoring weights (small curated set).
- Provider toggles:
  - enable/disable `pytubefix`, `yt-dlp`, `supadata` individually.  
  - monthly Supadata quota.

These give you **control without rewriting code**.

---

## 13. Next steps before coding

1. Finalise **profile.json** for the current student (manually + LLM‑aided from lesson transcripts).
2. Choose default numeric values for:
   - `N_queries`, `R_per_query`, `N_transcripts`, `D_cutoff`, weights.  
3. Implement a minimal `TranscriptProvider` abstraction with the 3 providers and on‑disk cache.  
4. Wire everything into the existing app with simple logging to see:
   - which provider was used,  
   - where failures happen,  
   - how scores distribute.

Once this is stable, we can iterate on:

- more nuanced profile modelling,  
- UI enhancements,  
- and – if needed – more sophisticated scoring. But the backbone is already coherent and robust for real‑world YouTube chaos.

# YouTube Channel Analytics & BigQuery ETL Pipeline

This repository runs a daily Python ETL job via GitHub Actions to track long-form video performance and daily view velocity for the `@TylerBlanchard` YouTube channel (51 long-form uploads, 280.5M+ views since Nov 30, 2024).

* **Live Looker Studio Dashboard:** [Tyler Blanchard — Long-Form YouTube Strategy & Velocity](PASTE_YOUR_LOOKER_STUDIO_LINK_HERE)

> **Data Privacy & Public API Note:** All performance metrics in this repository (`views`, `likes`, `comments`, `duration`, `published_at`) are **100% public data** retrieved via the public YouTube Data API v3 (`snippet`, `statistics`, and `contentDetails` endpoints), paired with custom content taxonomy tags (`dim_video_metadata.csv`). No proprietary or private YouTube Studio data (such as internal retention curves, click-through rates, or revenue/RPM) is stored in this repository.

## Why I Built This
The public YouTube Data API v3 provides raw view, like, and comment counts, but it does not track creative metadata—such as video topic, format structure, content mechanic, or whether a video is a sequel in a recurring series. In addition, mixing YouTube Shorts with 20-minute videos skews channel benchmarks because they run on different discovery algorithms.

To solve both problems, this pipeline:
1. Queries the YouTube Data API v3 every morning at 10:30 AM PT via GitHub Actions.
2. Parses ISO-8601 duration strings (`PT19M2S` -> `1142` seconds) and filters out all YouTube Shorts (`<= 180` seconds).
3. Joins live API metrics (`fact_youtube_performance.csv`) with my manual content classification table (`dim_video_metadata.csv`) and updates Google BigQuery.
4. Appends a daily snapshot to `fact_youtube_daily_snapshots` in BigQuery (using an idempotent delete-before-insert guard) to track which back-catalog videos are surging each day.

## Repository Structure
The repository is intentionally kept minimal so the code, schema, and SQL queries are easy to review:

* **`youtube_channel_export.py`** — Daily Python ETL script executed by GitHub Actions (`.github/workflows/daily_youtube_etl.yml`).
* **`tyler_bigquery_analysis.sql`** — BigQuery Standard SQL script containing the normalized view definitions (`vw_tyler_complete`, `vw_daily_velocity`) and 14 analytical queries.
* **`fact_youtube_performance.csv`** — Normalized Fact table containing public API metrics for the 51 long-form releases.
* **`dim_video_metadata.csv`** — Normalized Dimension table containing 17 custom taxonomy attributes per video (`primary_topic`, `format_category`, `series`, `content_mechanic`, `sequel_number`, etc.).

## Key Takeaways from the Data
| Area Analyzed | Finding | Impact on Content Strategy |
| :--- | :--- | :--- |
| **Video Length Tiers** | Videos under 15 mins average **6.10M views** (n=14), compared to **5.65M** for 15–20 mins (n=20) and **4.80M** for over 20 mins (n=17). | Tighter edits under 15 minutes outperform 20+ minute cuts by ~27% on average. |
| **Topic Benchmarks** | **History** (8.08M avg, n=5), **Myths** (6.76M avg, n=4), and **Movies & Pop Culture** (6.68M avg, n=7) lead all categories. | High-volume categories like *Death & Danger* (14 videos, 4.87M avg) are reliable fillers, but *History* and *Myths* drive the highest per-video return. |
| **Sequel Decay (`LAG`)** | Broad listicles (*10 Things You Didn't Know Could Kill You*) grew **+171%** on Part 2 (4.68M -> 12.69M), while narrow concepts (*Deadly Alarm Clocks*, *Childhood Myths*) dropped **68%–81%** on Part 2. | Only greenlight Part 2 sequels for broad umbrella formats rather than one-off novelty tests. |
| **Back-Catalog Velocity** | Tracking daily view deltas revealed a **+976K view surge** on *Deadly Weapons From Horror Movies* (2025) during Oct 2026. | Releasing two new Horror videos in Oct 2026 created a halo spike on the previous year's Horror upload. |

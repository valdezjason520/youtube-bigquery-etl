# YouTube Channel Analytics & BigQuery ETL Pipeline

This repository runs a daily Python ETL job via GitHub Actions to track long-form video performance and daily view velocity for the `@TylerBlanchard` YouTube channel (51 long-form uploads, 280.5M+ views since Nov 30, 2024).

## Why I Built This
YouTube Studio and the public YouTube Data API v3 provide raw engagement metrics (views, likes, comments, duration), but they don't track creative metadata—such as video topic, format structure, content mechanic, or whether a video is a sequel in a recurring series. 

On top of that, mixing YouTube Shorts with 20-minute videos skews channel benchmarks because they run on different discovery algorithms.

To solve both issues, this pipeline:
1. Pulls daily channel stats from the YouTube Data API v3 (`channels`, `playlistItems`, and `videos` endpoints).
2. Parses ISO-8601 duration strings (`PT19M2S` -> `1142` seconds) and filters out all YouTube Shorts (`<= 180` seconds).
3. Joins the live API numbers with my manual content classification table (`dim_video_metadata.csv`) and pushes normalized tables to Google BigQuery every morning at 10:30 AM PT.
4. Appends a daily snapshot to `fact_youtube_daily_snapshots` to track which back-catalog videos are surging on any given day.

## BigQuery Schema (`tyler_youtube`)
Instead of overwriting one flat spreadsheet, the data is split into a normalized schema in BigQuery and joined via SQL views for Looker Studio:

* `fact_youtube_performance` — Latest API metrics (`video_id`, `title`, `published_at`, `views`, `likes`, `comments`, `duration`, `duration_seconds`, `extracted_at`).
* `dim_video_metadata` — Static creative tags (`primary_topic`, `secondary_topic`, `format_category`, `series`, `content_mechanic`, `inspiration_source`, `subject_type`, `is_sequel`, `sequel_number`, plus binary category flags).
* `fact_youtube_daily_snapshots` — Append-only daily log (`snapshot_date`, `video_id`, `views`, `likes`, `comments`). Includes an idempotent delete-before-insert check so re-running the script on the same day never duplicates rows.
* `vw_tyler_complete` & `vw_daily_velocity` — BigQuery views joining the Fact and Dimension tables and calculating daily view gains (`LAG()`) for dashboard reporting.

## Key Takeaways from the Data
| Area Analyzed | Finding | Impact on Content Strategy |
| :--- | :--- | :--- |
| **Video Length Tiers** | Videos under 15 mins average **6.10M views** (n=14), compared to **5.65M** for 15–20 mins (n=20) and **4.80M** for over 20 mins (n=17). | Tighter edits under 15 minutes outperform 20+ minute cuts by ~27% on average. |
| **Topic Benchmarks** | **History** (8.08M avg, n=5), **Myths** (6.76M avg, n=4), and **Movies & Pop Culture** (6.68M avg, n=7) lead all categories. | High-volume categories like *Death & Danger* (14 videos, 4.87M avg) are reliable fillers, but *History* and *Myths* drive the highest per-video return. |
| **Sequel Decay (`LAG`)** | Broad listicles (*10 Things You Didn't Know Could Kill You*) grew **+171%** on Part 2 (4.68M -> 12.69M), while narrow concepts (*Deadly Alarm Clocks*, *Childhood Myths*) dropped **68%–81%** on Part 2. | Only greenlight Part 2 sequels for broad umbrella formats rather than one-off novelty tests. |
| **Back-Catalog Velocity** | Tracking daily view deltas revealed a **+976K view surge** on *Deadly Weapons From Horror Movies* (2025) during Oct 2026. | Releasing two new Horror videos in Oct 2026 created a halo spike on the previous year's Horror upload. |

## Repo Files
* `youtube_channel_export.py` — Main daily ETL script executed by GitHub Actions.
* `backfill_snapshots.py` — Utility script used to seed `fact_youtube_daily_snapshots` from older CSV exports and generate `tableau_youtube_velocity.csv`.
* `tyler_bigquery_analysis.sql` — BigQuery SQL script containing the view definitions (`vw_tyler_complete`, `vw_daily_velocity`) and 14 analysis queries.
* `.github/workflows/daily_youtube_etl.yml` — GitHub Actions cron workflow (`0 17 * * *` UTC).

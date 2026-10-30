# Automated YouTube Data API v3 to Google BigQuery ETL Pipeline

An automated daily cloud ETL pipeline (**Python**, **GitHub Actions**, **Google BigQuery**, **Looker Studio**) that extracts public performance metrics from the YouTube Data API v3, filters out short-form uploads via ISO-8601 duration parsing, and joins dynamic engagement data with a custom 17-column content taxonomy schema.

## Architecture & Data Model (Normalized Star Schema)
* **`youtube_channel_export.py`**: Scheduled daily at 10:30 AM PT via GitHub Actions (`.github/workflows/daily_youtube_etl.yml`). Queries `channels`, `playlistItems`, and `videos` endpoints, excludes Shorts (`duration_seconds <= 180`), and pushes to BigQuery using idempotent `DELETE` + `APPEND` snapshot guards.
* **`fact_youtube_performance`**: Latest long-form engagement metrics (`views`, `likes`, `comments`, `duration_seconds`, `published_at`).
* **`dim_video_metadata`**: Normalized creative classification table (`primary_topic`, `format_category`, `series`, `content_mechanic`, `sequel_number`).
* **`fact_youtube_daily_snapshots`**: Append-only historical log powering daily view velocity and back-catalog surge tracking.
* **`tyler_bigquery_analysis.sql`**: 14 BigQuery Standard SQL queries & views (`vw_tyler_complete`, `vw_daily_velocity`) utilizing `LAG()`, `DENSE_RANK()`, and moving averages.

## Key Analytical Findings (51 Long-Form Releases | 280.5M+ Views)
1. **The Sub-15-Minute Duration Sweet Spot:** Videos **Under 15 Mins** average **6.1M views** (+27% higher than videos **Over 20 Mins** at **4.8M views**).
2. **Topic Efficiency vs. Production Volume:** **History** (**8.1M avg views**) and **Myths** (**6.8M avg views**) generate the highest per-video return despite lower upload volume than **Death & Danger** (**4.9M avg views** across 14 videos).
3. **Franchise Sequel Growth vs. Fatigue (`LAG` Window Function):** Broad listicle franchises (*10 Things You Didn't Know Could Kill You*) grew **+171%** on Part 2 (4.7M to 12.7M views), whereas narrow novelty concepts (*Deadly Alarm Clocks*, *Childhood Myths*) experienced **68% to 81% sequel decay**.
4. **Back-Catalog Halo Velocity:** Daily snapshot tracking identified **+976K to +1.4M view surges** on evergreen History and seasonal Horror releases months after initial publication.

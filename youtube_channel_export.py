import os
import re
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests

API_BASE = "https://www.googleapis.com/youtube/v3"
API_KEY = os.getenv("YOUTUBE_API_KEY")
CHANNEL_HANDLE = "@TylerBlanchard"
START_DATE = "2024-11-30"

# BigQuery Cloud Configuration
BQ_PROJECT_ID = os.getenv("BQ_PROJECT_ID", "project-044ba905-1ee9-4d03-a90")
BQ_DATASET_ID = "tyler_youtube"

# Input file: Script will automatically check for .xlsx first, then .csv
METADATA_XLSX_INPUT = "tyler_metadata_complete.xlsx"
METADATA_CSV_INPUT = "tyler_metadata_complete.csv"

# Normalized Output Files for BigQuery
FACT_OUTPUT_FILE = "fact_youtube_performance.csv"
DIM_OUTPUT_FILE = "dim_video_metadata.csv"

# Denormalized Backup File (Joined)
MERGED_OUTPUT_FILE = "tyler_metadata_complete_clean.csv"

# Minimum duration in seconds to qualify as Long-Form (180s = 3 minutes)
MIN_LONGFORM_SECONDS = 180

# The 5 long-form videos published between Sept 19 and Oct 24, 2026
NEW_OCT_2026_METADATA = [
    {
        "video_id": "wbKETxNuEyQ",
        "primary_topic": "Death & Danger",
        "secondary_topic": "Work / Occupations",
        "format_category": "I Tested",
        "series": "Work Accidents",
        "content_mechanic": "Case Recreation / Demonstration",
        "inspiration_source": "Real Life",
        "subject_type": "Workplace Hazard",
        "is_sequel": 0,
        "sequel_number": 1,
        "is_movie_based": 0,
        "is_game_based": 0,
        "is_myth_based": 0,
        "is_history_based": 0,
        "is_product_test": 0,
        "is_collaboration": 0,
        "notes": "Workplace accident recreations",
    },
    {
        "video_id": "6CGafK3QGo0",
        "primary_topic": "Death & Danger",
        "secondary_topic": "Shopping / Retail",
        "format_category": "I Tested",
        "series": "Strange Deaths",
        "content_mechanic": "Case Recreation / Demonstration",
        "inspiration_source": "Real Life",
        "subject_type": "Everyday Hazard",
        "is_sequel": 0,
        "sequel_number": 1,
        "is_movie_based": 0,
        "is_game_based": 0,
        "is_myth_based": 0,
        "is_history_based": 0,
        "is_product_test": 0,
        "is_collaboration": 0,
        "notes": "Retail and shopping hazard recreations",
    },
    {
        "video_id": "DlSAwOm8Xeg",
        "primary_topic": "Movies & Pop Culture",
        "secondary_topic": "Horror Movies",
        "format_category": "I Tested",
        "series": "Movie Deaths",
        "content_mechanic": "Real-World Recreation",
        "inspiration_source": "Movies",
        "subject_type": "Movie Death Scene",
        "is_sequel": 1,
        "sequel_number": 4,
        "is_movie_based": 1,
        "is_game_based": 0,
        "is_myth_based": 0,
        "is_history_based": 0,
        "is_product_test": 0,
        "is_collaboration": 0,
        "notes": "4th installment in Movie Deaths series (Horror-specific)",
    },
    {
        "video_id": "7He8APXWeJA",
        "primary_topic": "Movies & Pop Culture",
        "secondary_topic": "Horror Movies",
        "format_category": "I Tested",
        "series": "Movie Traps",
        "content_mechanic": "Real-World Recreation",
        "inspiration_source": "Movies",
        "subject_type": "Booby Trap",
        "is_sequel": 1,
        "sequel_number": 2,
        "is_movie_based": 1,
        "is_game_based": 0,
        "is_myth_based": 0,
        "is_history_based": 0,
        "is_product_test": 0,
        "is_collaboration": 0,
        "notes": "Horror movie trap recreations (2nd installment in Movie Traps)",
    },
    {
        "video_id": "JCnh-RfNkU4",
        "primary_topic": "Weapons",
        "secondary_topic": "Horror Movies",
        "format_category": "I Tested",
        "series": "Movie Weapons",
        "content_mechanic": "Real-World Recreation",
        "inspiration_source": "Movies",
        "subject_type": "Weapon",
        "is_sequel": 1,
        "sequel_number": 3,
        "is_movie_based": 1,
        "is_game_based": 0,
        "is_myth_based": 0,
        "is_history_based": 0,
        "is_product_test": 0,
        "is_collaboration": 0,
        "notes": "3rd installment in Movie Weapons series (2nd Horror Weapons video)",
    },
]

# Explicit fixes for episodes in tyler_metadata_complete.xlsx that didn't have "(again)" in the title
EXPLICIT_SEQUEL_FIXES = {
    # Movie Deaths: DaBTiMG2ruM (1) -> zV3rEIfx7ng (2) -> wHBenumLrYQ (3) -> DlSAwOm8Xeg (4)
    "wHBenumLrYQ": {"sequel_number": 3, "is_sequel": 1},
    # Movie Weapons: l__66zN-I1w (1, Spy) -> HPeCewlBMZs (2, Horror 1) -> JCnh-RfNkU4 (3, Horror 2)
    "HPeCewlBMZs": {"sequel_number": 2, "is_sequel": 1},
    "JCnh-RfNkU4": {"sequel_number": 3, "is_sequel": 1},
}

DIM_COLUMNS = [
    "video_id",
    "primary_topic",
    "secondary_topic",
    "format_category",
    "series",
    "content_mechanic",
    "inspiration_source",
    "subject_type",
    "is_sequel",
    "sequel_number",
    "is_movie_based",
    "is_game_based",
    "is_myth_based",
    "is_history_based",
    "is_product_test",
    "is_collaboration",
    "notes",
]


def parse_iso8601_duration(duration_str: str) -> tuple[str, int]:
    """Convert YouTube ISO-8601 duration (e.g., 'PT19M2S') into ('HH:MM:SS', total_seconds)."""
    if not duration_str:
        return "00:00:00", 0

    match = re.match(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$", duration_str)
    if not match:
        return "00:00:00", 0

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)

    total_seconds = (hours * 3600) + (minutes * 60) + seconds
    formatted_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return formatted_time, total_seconds


def api_get(endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
    """Send a GET request to the YouTube Data API v3 and return JSON."""
    url = f"{API_BASE}/{endpoint}"
    response = requests.get(url, params=params, timeout=30)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        print("YouTube API request failed:")
        print(response.text)
        raise exc
    return response.json()


def get_channel_info(handle: str) -> tuple[str, str]:
    """Return channel ID and uploads playlist ID for a YouTube handle."""
    data = api_get(
        "channels",
        {
            "part": "contentDetails,snippet",
            "forHandle": handle,
            "key": API_KEY,
        },
    )
    if not data.get("items"):
        raise ValueError(f"No channel found for handle: {handle}")

    channel = data["items"][0]
    channel_id = channel["id"]
    channel_title = channel["snippet"]["title"]
    uploads_playlist_id = channel["contentDetails"]["relatedPlaylists"]["uploads"]

    print(f"Channel: {channel_title} ({channel_id})")
    return channel_id, uploads_playlist_id


def get_uploaded_video_ids(uploads_playlist_id: str) -> list[str]:
    """Retrieve all video IDs from a channel's uploads playlist."""
    video_ids = []
    next_page_token = None

    while True:
        params = {
            "part": "contentDetails",
            "playlistId": uploads_playlist_id,
            "maxResults": 50,
            "key": API_KEY,
        }
        if next_page_token:
            params["pageToken"] = next_page_token

        data = api_get("playlistItems", params)
        for item in data.get("items", []):
            video_ids.append(item["contentDetails"]["videoId"])

        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break

    print(f"Found {len(video_ids)} total uploaded videos on channel.")
    return video_ids


def get_video_information(video_ids: list[str]) -> list[dict[str, Any]]:
    """Retrieve snippet, statistics, and contentDetails (duration) in batches of 50."""
    videos = []

    for start in range(0, len(video_ids), 50):
        batch = video_ids[start : start + 50]
        data = api_get(
            "videos",
            {
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(batch),
                "key": API_KEY,
            },
        )

        for video in data.get("items", []):
            snippet = video.get("snippet", {})
            statistics = video.get("statistics", {})
            content_details = video.get("contentDetails", {})

            iso_duration = content_details.get("duration", "")
            duration_hhmmss, duration_seconds = parse_iso8601_duration(iso_duration)

            videos.append(
                {
                    "video_id": video["id"],
                    "title": snippet.get("title"),
                    "published_at": snippet.get("publishedAt"),
                    "views": int(statistics.get("viewCount", 0)),
                    "likes": int(statistics.get("likeCount", 0)),
                    "comments": int(statistics.get("commentCount", 0)),
                    "duration": duration_hhmmss,
                    "duration_seconds": duration_seconds,
                }
            )

    return videos


def build_clean_dimension_table() -> pd.DataFrame:
    """Load manual metadata from .xlsx or .csv, standardize columns, and output dim_video_metadata."""
    if os.path.exists(METADATA_XLSX_INPUT):
        print(f"Loading metadata from {METADATA_XLSX_INPUT}...")
        df_meta = pd.read_excel(METADATA_XLSX_INPUT)
    elif os.path.exists(METADATA_CSV_INPUT):
        print(f"Loading metadata from {METADATA_CSV_INPUT}...")
        df_meta = pd.read_csv(METADATA_CSV_INPUT)
    elif os.path.exists(DIM_OUTPUT_FILE):
        print(f"Loading existing {DIM_OUTPUT_FILE}...")
        df_meta = pd.read_csv(DIM_OUTPUT_FILE)
    else:
        raise FileNotFoundError(
            f"Could not find {METADATA_XLSX_INPUT} or {METADATA_CSV_INPUT} in current folder."
        )

    # 1. Rename 'format' -> 'format_category' to prevent SQL reserved keyword issues
    if "format" in df_meta.columns and "format_category" not in df_meta.columns:
        df_meta = df_meta.rename(columns={"format": "format_category"})

    # 2. Keep only the 17 Dimension columns (strip old API columns like views, duration, title)
    available_dim_cols = [c for c in DIM_COLUMNS if c in df_meta.columns]
    df_dim = df_meta[available_dim_cols].drop_duplicates(subset=["video_id"]).copy()

    # 3. Append the 5 new Sept/Oct 2026 long-form videos if they aren't already in the file
    df_new_oct = pd.DataFrame(NEW_OCT_2026_METADATA)
    existing_ids = set(df_dim["video_id"].astype(str))
    df_to_add = df_new_oct[~df_new_oct["video_id"].isin(existing_ids)]
    if not df_to_add.empty:
        print(f"Auto-appending {len(df_to_add)} new Oct 2026 long-form metadata rows...")
        df_dim = pd.concat([df_dim, df_to_add], ignore_index=True)

    # 4. Clean trailing whitespace on all string columns (Pandas 3.1+ compatible)
    str_cols = df_dim.select_dtypes(include=["object", "str"]).columns
    for col in str_cols:
        df_dim[col] = df_dim[col].astype(str).str.strip().replace({"nan": None, "None": "None"})

    # 5. Standardize duplicate category labels in secondary_topic
    if "secondary_topic" in df_dim.columns:
        df_dim["secondary_topic"] = df_dim["secondary_topic"].replace(
            {
                "Creator / Boxing": "Boxing / Creator",
                "Torture / Punishment": "Punishment / Torture",
            }
        )

    # 6. Standardize sequel_number & apply explicit sequel overrides (Movie Deaths #3, Movie Weapons #2 & #3)
    df_dim["sequel_number"] = pd.to_numeric(df_dim["sequel_number"], errors="coerce").fillna(1).astype(int)
    for vid, fixes in EXPLICIT_SEQUEL_FIXES.items():
        if vid in df_dim["video_id"].values:
            for col_name, val in fixes.items():
                df_dim.loc[df_dim["video_id"] == vid, col_name] = val

    df_dim["is_sequel"] = (df_dim["sequel_number"] > 1).astype(int)

    # 7. Ensure all binary flag columns are clean integers
    flag_cols = [
        "is_movie_based",
        "is_game_based",
        "is_myth_based",
        "is_history_based",
        "is_product_test",
        "is_collaboration",
    ]
    for col in flag_cols:
        if col in df_dim.columns:
            df_dim[col] = pd.to_numeric(df_dim[col], errors="coerce").fillna(0).astype(int)

    # 8. QA Check: Alert if any series with sequels (max sequel_number > 1) has duplicate episode numbers
    sequel_series = df_dim.groupby("series")["sequel_number"].max()
    active_sequel_series = sequel_series[sequel_series > 1].index.tolist()
    dups = df_dim[
        df_dim["series"].isin(active_sequel_series)
        & df_dim.duplicated(subset=["series", "sequel_number"], keep=False)
    ]
    if not dups.empty:
        print("\n[QA WARNING] Duplicate sequel_number detected in an active sequel series:")
        print(dups[["video_id", "series", "sequel_number", "notes"]])

    return df_dim


def push_tables_to_bigquery(df_fact: pd.DataFrame, df_dim: pd.DataFrame) -> None:
    """Push latest Fact/Dim tables (replace) AND append today's snapshot to history table."""
    if not BQ_PROJECT_ID or BQ_PROJECT_ID == "your-gcp-project-id-here":
        print("\n[SKIPPED] Set BQ_PROJECT_ID to enable automatic BigQuery cloud uploads.")
        return

    import pandas_gbq
    from google.cloud import bigquery

    fact_table_id = f"{BQ_DATASET_ID}.fact_youtube_performance"
    dim_table_id = f"{BQ_DATASET_ID}.dim_video_metadata"
    snapshot_table_id = f"{BQ_DATASET_ID}.fact_youtube_daily_snapshots"

    print(f"\nPushing normalized tables to BigQuery project '{BQ_PROJECT_ID}'...")

    # 1. Replace Latest Fact & Dimension Tables
    pandas_gbq.to_gbq(df_fact, fact_table_id, project_id=BQ_PROJECT_ID, if_exists="replace")
    print(f"  -> Updated latest Fact table: {fact_table_id} ({len(df_fact)} rows)")

    pandas_gbq.to_gbq(df_dim, dim_table_id, project_id=BQ_PROJECT_ID, if_exists="replace")
    print(f"  -> Updated Dimension table: {dim_table_id} ({len(df_dim)} rows)")

    # 2. Prepare Today's Daily Snapshot (adds snapshot_date column as STRING YYYY-MM-DD)
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    df_snapshot = df_fact.copy()
    df_snapshot.insert(0, "snapshot_date", today_str)

    # 3. Idempotency Guard: Delete today's rows if the script already ran earlier today
    client = bigquery.Client(project=BQ_PROJECT_ID)
    delete_sql = f"""
        DELETE FROM `{BQ_PROJECT_ID}.{snapshot_table_id}`
        WHERE CAST(snapshot_date AS STRING) = '{today_str}'
    """
    try:
        client.query(delete_sql).result()
    except Exception:
        # Table doesn't exist yet on the very first run; pandas_gbq will create it below
        pass

    # 4. Append Today's Snapshot to the Historical Table
    pandas_gbq.to_gbq(df_snapshot, snapshot_table_id, project_id=BQ_PROJECT_ID, if_exists="append")
    print(f"  -> Logged daily history snapshot ({today_str}) to {snapshot_table_id}")


def main():
    if not API_KEY:
        raise ValueError("YOUTUBE_API_KEY environment variable is not set.")

    print("Starting Normalized YouTube-to-BigQuery ETL pipeline...")
    _, uploads_playlist_id = get_channel_info(CHANNEL_HANDLE)
    video_ids = get_uploaded_video_ids(uploads_playlist_id)
    videos = get_video_information(video_ids)

    cutoff = datetime.fromisoformat(f"{START_DATE}T00:00:00+00:00")
    extracted_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    longform_videos = []
    for video in videos:
        published_dt = datetime.fromisoformat(
            video["published_at"].replace("Z", "+00:00")
        )
        # Filter strictly to long-form videos (> 180 seconds) published on/after START_DATE
        if published_dt >= cutoff and video["duration_seconds"] > MIN_LONGFORM_SECONDS:
            longform_videos.append(
                {
                    "video_id": video["video_id"],
                    "title": video["title"],
                    "published_at": published_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "views": video["views"],
                    "likes": video["likes"],
                    "comments": video["comments"],
                    "duration": video["duration"],
                    "duration_seconds": video["duration_seconds"],
                    "video_url": f"https://www.youtube.com/watch?v={video['video_id']}",
                    "extracted_at": extracted_at,
                }
            )

    longform_videos.sort(key=lambda x: x["published_at"], reverse=True)

    # 1. Save Normalized FACT Table (API Metrics)
    df_fact = pd.DataFrame(longform_videos)
    df_fact.to_csv(FACT_OUTPUT_FILE, index=False, encoding="utf-8")
    print(f"[1/3] Saved Normalized Fact Table ({len(df_fact)} rows) -> {FACT_OUTPUT_FILE}")

    # 2. Save Normalized DIMENSION Table (Manual Metadata)
    df_dim = build_clean_dimension_table()
    df_dim.to_csv(DIM_OUTPUT_FILE, index=False, encoding="utf-8")
    print(f"[2/3] Saved Normalized Dimension Table ({len(df_dim)} rows) -> {DIM_OUTPUT_FILE}")

    # 3. Save Denormalized Joined Table (Local Backup & Tableau CSV)
    df_merged = pd.merge(df_fact, df_dim, on="video_id", how="left")
    df_merged.to_csv(MERGED_OUTPUT_FILE, index=False, encoding="utf-8")
    print(f"[3/3] Saved Joined Backup Table ({len(df_merged)} rows) -> {MERGED_OUTPUT_FILE}")

    # Alert if any future long-form video needs manual tags in dim_video_metadata.csv
    untagged = df_merged[df_merged["primary_topic"].isna()]
    if not untagged.empty:
        print(f"\n[ACTION NEEDED] {len(untagged)} new long-form video(s) need metadata tags:")
        for _, row in untagged.iterrows():
            print(f"  - {row['video_id']} | {row['published_at']} | {row['title']}")
    else:
        print("\nAll long-form videos are 100% matched with metadata tags!")

    # 4. Push directly to Google BigQuery
    push_tables_to_bigquery(df_fact, df_dim)


if __name__ == "__main__":
    main()

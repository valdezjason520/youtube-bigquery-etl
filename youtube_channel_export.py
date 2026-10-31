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

BQ_PROJECT_ID = os.getenv("BQ_PROJECT_ID", "project-044ba905-1ee9-4d03-a90")
BQ_DATASET_ID = "tyler_youtube"

METADATA_XLSX_INPUT = "tyler_metadata_complete.xlsx"
METADATA_CSV_INPUT = "tyler_metadata_complete.csv"

FACT_OUTPUT_FILE = "fact_youtube_performance.csv"
DIM_OUTPUT_FILE = "dim_video_metadata.csv"
MERGED_OUTPUT_FILE = "tyler_metadata_complete_clean.csv"

# Exclude Shorts (<= 180s) so they don't skew long-form view benchmarks
MIN_LONGFORM_SECONDS = 180

# Metadata tags for long-form uploads added after the initial Sept 2026 Excel sheet
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

# Patch sequel numbers for episodes where the title didn't literally include "(again)"
EXPLICIT_SEQUEL_FIXES = {
    "wHBenumLrYQ": {"sequel_number": 3, "is_sequel": 1},  # Brutal Movie Deaths (Part 3)
    "HPeCewlBMZs": {"sequel_number": 2, "is_sequel": 1},  # Horror Movie Weapons 1 (Part 2 of Movie Weapons)
    "JCnh-RfNkU4": {"sequel_number": 3, "is_sequel": 1},  # Horror Movie Weapons 2 (Part 3 of Movie Weapons)
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
    """Parse YouTube ISO-8601 duration string (e.g. 'PT19M2S') into ('HH:MM:SS', seconds)."""
    if not duration_str:
        return "00:00:00", 0

    match = re.match(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$", duration_str)
    if not match:
        return "00:00:00", 0

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)

    total_seconds = (hours * 3600) + (minutes * 60) + seconds
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}", total_seconds


def api_get(endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
    url = f"{API_BASE}/{endpoint}"
    response = requests.get(url, params=params, timeout=30)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        print(f"API request failed ({endpoint}): {response.text}")
        raise exc
    return response.json()


def get_channel_info(handle: str) -> tuple[str, str]:
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
    uploads_playlist_id = channel["contentDetails"]["relatedPlaylists"]["uploads"]

    print(f"Channel: {channel['snippet']['title']} ({channel_id})")
    return channel_id, uploads_playlist_id


def get_uploaded_video_ids(uploads_playlist_id: str) -> list[str]:
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

    print(f"Fetched {len(video_ids)} total video IDs from uploads playlist.")
    return video_ids


def get_video_information(video_ids: list[str]) -> list[dict[str, Any]]:
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

            duration_hhmmss, duration_seconds = parse_iso8601_duration(
                content_details.get("duration", "")
            )

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
    if os.path.exists(METADATA_XLSX_INPUT):
        df_meta = pd.read_excel(METADATA_XLSX_INPUT)
    elif os.path.exists(METADATA_CSV_INPUT):
        df_meta = pd.read_csv(METADATA_CSV_INPUT)
    elif os.path.exists(DIM_OUTPUT_FILE):
        df_meta = pd.read_csv(DIM_OUTPUT_FILE)
    else:
        raise FileNotFoundError("Missing metadata input file (.xlsx or .csv).")

    if "format" in df_meta.columns and "format_category" not in df_meta.columns:
        df_meta = df_meta.rename(columns={"format": "format_category"})

    available_dim_cols = [c for c in DIM_COLUMNS if c in df_meta.columns]
    df_dim = df_meta[available_dim_cols].drop_duplicates(subset=["video_id"]).copy()

    # Append recent long-form rows not yet in the base Excel file
    df_new_oct = pd.DataFrame(NEW_OCT_2026_METADATA)
    existing_ids = set(df_dim["video_id"].astype(str))
    df_to_add = df_new_oct[~df_new_oct["video_id"].isin(existing_ids)]
    if not df_to_add.empty:
        df_dim = pd.concat([df_dim, df_to_add], ignore_index=True)

    str_cols = df_dim.select_dtypes(include=["object", "str"]).columns
    for col in str_cols:
        df_dim[col] = df_dim[col].astype(str).str.strip().replace({"nan": None, "None": "None"})

    if "secondary_topic" in df_dim.columns:
        df_dim["secondary_topic"] = df_dim["secondary_topic"].replace(
            {
                "Creator / Boxing": "Boxing / Creator",
                "Torture / Punishment": "Punishment / Torture",
            }
        )

    df_dim["sequel_number"] = (
        pd.to_numeric(df_dim["sequel_number"], errors="coerce").fillna(1).astype(int)
    )
    for vid, fixes in EXPLICIT_SEQUEL_FIXES.items():
        if vid in df_dim["video_id"].values:
            for col_name, val in fixes.items():
                df_dim.loc[df_dim["video_id"] == vid, col_name] = val

    df_dim["is_sequel"] = (df_dim["sequel_number"] > 1).astype(int)

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

    # Check for duplicate episode numbers within any active multi-part series
    sequel_series = df_dim.groupby("series")["sequel_number"].max()
    active_sequel_series = sequel_series[sequel_series > 1].index.tolist()
    dups = df_dim[
        df_dim["series"].isin(active_sequel_series)
        & df_dim.duplicated(subset=["series", "sequel_number"], keep=False)
    ]
    if not dups.empty:
        print("\nWarning: duplicate sequel_number found in series:")
        print(dups[["video_id", "series", "sequel_number"]])

    return df_dim


def push_tables_to_bigquery(df_fact: pd.DataFrame, df_dim: pd.DataFrame) -> None:
    if not BQ_PROJECT_ID:
        print("BQ_PROJECT_ID not set; skipping BigQuery upload.")
        return

    import pandas_gbq
    from google.cloud import bigquery

    fact_table_id = f"{BQ_DATASET_ID}.fact_youtube_performance"
    dim_table_id = f"{BQ_DATASET_ID}.dim_video_metadata"
    snapshot_table_id = f"{BQ_DATASET_ID}.fact_youtube_daily_snapshots"

    print(f"Uploading tables to BigQuery ({BQ_PROJECT_ID})...")
    pandas_gbq.to_gbq(df_fact, fact_table_id, project_id=BQ_PROJECT_ID, if_exists="replace")
    pandas_gbq.to_gbq(df_dim, dim_table_id, project_id=BQ_PROJECT_ID, if_exists="replace")

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    df_snapshot = df_fact.copy()
    df_snapshot.insert(0, "snapshot_date", today_str)

    # Delete existing rows for today before appending so same-day re-runs stay idempotent
    client = bigquery.Client(project=BQ_PROJECT_ID)
    delete_sql = f"""
        DELETE FROM `{BQ_PROJECT_ID}.{snapshot_table_id}`
        WHERE CAST(snapshot_date AS STRING) = '{today_str}'
    """
    try:
        client.query(delete_sql).result()
    except Exception:
        pass

    pandas_gbq.to_gbq(df_snapshot, snapshot_table_id, project_id=BQ_PROJECT_ID, if_exists="append")
    print(f"Logged daily snapshot ({today_str}, {len(df_snapshot)} rows) to {snapshot_table_id}.")


def main():
    if not API_KEY:
        raise ValueError("YOUTUBE_API_KEY environment variable is not set.")

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

    df_fact = pd.DataFrame(longform_videos)
    df_fact.to_csv(FACT_OUTPUT_FILE, index=False, encoding="utf-8")

    df_dim = build_clean_dimension_table()
    df_dim.to_csv(DIM_OUTPUT_FILE, index=False, encoding="utf-8")

    df_merged = pd.merge(df_fact, df_dim, on="video_id", how="left")
    df_merged.to_csv(MERGED_OUTPUT_FILE, index=False, encoding="utf-8")
    print(f"Saved local CSVs ({len(df_fact)} fact rows, {len(df_dim)} dim rows).")

    untagged = df_merged[df_merged["primary_topic"].isna()]
    if not untagged.empty:
        print(f"\nUntagged long-form videos ({len(untagged)}):")
        for _, row in untagged.iterrows():
            print(f"  - {row['video_id']} | {row['published_at']} | {row['title']}")

    push_tables_to_bigquery(df_fact, df_dim)


if __name__ == "__main__":
    main()

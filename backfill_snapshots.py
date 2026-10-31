import os
import pandas as pd
import pandas_gbq

BQ_PROJECT_ID = os.getenv("BQ_PROJECT_ID", "project-044ba905-1ee9-4d03-a90")
BQ_DATASET_ID = "tyler_youtube"
SNAPSHOT_TABLE_ID = f"{BQ_DATASET_ID}.fact_youtube_daily_snapshots"

FACT_FILE = "fact_youtube_performance.csv"
DIM_FILE = "dim_video_metadata.csv"

# Historical API pulls used to seed the daily snapshot table
CANDIDATE_FILES = [
    ("tyler_metadata_complete.csv", "2026-09-18"),
    ("tyler_videos_2024-11-30_to_present.csv", "2026-09-18"),
    ("tyler_videos_2024-11-30_to_present1.csv", "2026-10-17"),
    ("fact_youtube_performance.csv", "2026-10-28"),
]


def normalize_snapshot(df_raw: pd.DataFrame, fallback_date: str, ref_map: dict) -> pd.DataFrame:
    rows = []
    for _, r in df_raw.iterrows():
        vid = str(r.get("video_id", "")).strip()
        if vid not in ref_map:
            continue

        ext_at = str(r.get("extracted_at", "")).strip()
        if not ext_at or ext_at in ("nan", "None"):
            ext_at = f"{fallback_date} 00:00:00"
        snap_date = ext_at[:10]

        ref = ref_map[vid]
        rows.append(
            {
                "snapshot_date": snap_date,
                "video_id": vid,
                "title": ref["title"],
                "published_at": ref["published_at"],
                "views": int(r["views"]),
                "likes": int(r["likes"]) if "likes" in r and pd.notna(r["likes"]) else 0,
                "comments": int(r["comments"]) if "comments" in r and pd.notna(r["comments"]) else 0,
                "duration": ref["duration"],
                "duration_seconds": int(ref["duration_seconds"]),
                "video_url": ref["video_url"],
                "extracted_at": ext_at,
            }
        )
    return pd.DataFrame(rows)


def main():
    if not os.path.exists(FACT_FILE):
        raise FileNotFoundError(f"Missing {FACT_FILE}. Run youtube_channel_export.py first.")

    df_fact = pd.read_csv(FACT_FILE)
    ref_map = df_fact.set_index("video_id")[
        ["title", "published_at", "duration", "duration_seconds", "video_url"]
    ].to_dict("index")

    all_snapshots = []
    for filename, fallback_date in CANDIDATE_FILES:
        if os.path.exists(filename):
            print(f"Reading snapshot from {filename}...")
            df_raw = pd.read_csv(filename)
            all_snapshots.append(normalize_snapshot(df_raw, fallback_date, ref_map))

    df_history = pd.concat(all_snapshots, ignore_index=True)
    df_history = df_history.drop_duplicates(subset=["snapshot_date", "video_id"], keep="last")
    df_history = df_history.sort_values(["snapshot_date", "published_at"], ascending=[True, False])

    print("\nSnapshot counts by date:")
    print(df_history.groupby("snapshot_date")["video_id"].count())

    df_history.to_csv("daily_snapshots_history.csv", index=False)

    # Export latest period velocity deltas for local Tableau workbook
    df_vel = df_history.sort_values(["video_id", "snapshot_date"]).copy()
    df_vel["prev_views"] = df_vel.groupby("video_id")["views"].shift(1)
    df_vel["prev_date"] = df_vel.groupby("video_id")["snapshot_date"].shift(1)
    df_vel = df_vel[df_vel["prev_views"].notna()].copy()

    df_vel["days_elapsed"] = (
        pd.to_datetime(df_vel["snapshot_date"]) - pd.to_datetime(df_vel["prev_date"])
    ).dt.days.clip(lower=1)
    df_vel["views_gained"] = (df_vel["views"] - df_vel["prev_views"]).astype(int)
    df_vel["views_gained_per_day"] = (
        (df_vel["views_gained"] / df_vel["days_elapsed"]).round(0).astype(int)
    )
    df_vel["pct_surge"] = ((df_vel["views_gained"] / df_vel["prev_views"]) * 100).round(2)

    if os.path.exists(DIM_FILE):
        df_dim = pd.read_csv(DIM_FILE)
        df_vel = pd.merge(df_vel, df_dim, on="video_id", how="left")

    df_vel = df_vel[df_vel["snapshot_date"] == df_vel["snapshot_date"].max()]
    df_vel.to_csv("tableau_youtube_velocity.csv", index=False)

    print(f"\nUploading {len(df_history)} snapshot rows to {SNAPSHOT_TABLE_ID}...")
    pandas_gbq.to_gbq(
        df_history,
        destination_table=SNAPSHOT_TABLE_ID,
        project_id=BQ_PROJECT_ID,
        if_exists="replace",
    )
    print("Snapshot backfill complete.")


if __name__ == "__main__":
    main()

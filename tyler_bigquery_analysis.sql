-- =================================================================================
-- STEP 0: CREATE NORMALIZED STAR-SCHEMA VIEW IN BIGQUERY
-- Joins fact_youtube_performance (f) and dim_video_metadata (d) on video_id
-- =================================================================================

CREATE OR REPLACE VIEW `tyler_youtube.vw_tyler_complete` AS
SELECT
    f.video_id,
    f.title,
    CAST(f.published_at AS TIMESTAMP) AS published_at,
    f.views,
    f.likes,
    f.comments,
    f.duration,
    f.duration_seconds,
    f.video_url,
    CAST(f.extracted_at AS TIMESTAMP) AS extracted_at,
    d.primary_topic,
    d.secondary_topic,
    d.format_category,
    d.series,
    d.content_mechanic,
    d.inspiration_source,
    d.subject_type,
    d.is_sequel,
    d.sequel_number,
    d.is_movie_based,
    d.is_game_based,
    d.is_myth_based,
    d.is_history_based,
    d.is_product_test,
    d.is_collaboration,
    d.notes
FROM `tyler_youtube.fact_youtube_performance` AS f
INNER JOIN `tyler_youtube.dim_video_metadata` AS d
    ON f.video_id = d.video_id;


-- =================================================================================
-- PART 1: EXPLORATORY CHANNEL PERFORMANCE ANALYSIS (BIGQUERY STANDARD SQL)
-- =================================================================================

-- 1. Best performing primary topics by average views (in millions)
SELECT 
    primary_topic,
    COUNT(*) AS video_count,
    ROUND(AVG(views) / 1000000, 2) AS avg_views_millions
FROM `tyler_youtube.vw_tyler_complete`
GROUP BY primary_topic
ORDER BY avg_views_millions DESC;

-- 2. Best performing format categories
SELECT 
    format_category,
    COUNT(*) AS video_count,
    ROUND(AVG(views) / 1000000, 2) AS avg_views_millions
FROM `tyler_youtube.vw_tyler_complete`
GROUP BY format_category
ORDER BY avg_views_millions DESC;

-- 3. Top performing recurring series (minimum 2 episodes)
SELECT 
    series,
    COUNT(*) AS video_count,
    ROUND(AVG(views) / 1000000, 2) AS avg_views_millions
FROM `tyler_youtube.vw_tyler_complete`
WHERE series != 'None' AND series IS NOT NULL
GROUP BY series
HAVING COUNT(*) > 1
ORDER BY avg_views_millions DESC
LIMIT 5;

-- 4. Comparing category flags (Movie-Based, Game-Based, Product Test)
SELECT 
    'Movie-Based' AS category,
    is_movie_based AS flag,
    COUNT(*) AS video_count,
    ROUND(AVG(views) / 1000000, 2) AS avg_views_millions
FROM `tyler_youtube.vw_tyler_complete`
GROUP BY is_movie_based
UNION ALL
SELECT 
    'Game-Based' AS category,
    is_game_based AS flag,
    COUNT(*) AS video_count,
    ROUND(AVG(views) / 1000000, 2) AS avg_views_millions
FROM `tyler_youtube.vw_tyler_complete`
GROUP BY is_game_based
UNION ALL
SELECT 
    'Product Test' AS category,
    is_product_test AS flag,
    COUNT(*) AS video_count,
    ROUND(AVG(views) / 1000000, 2) AS avg_views_millions
FROM `tyler_youtube.vw_tyler_complete`
GROUP BY is_product_test;

-- 5. Performance of Sequels vs. Original/Standalone videos
SELECT 
    CASE 
        WHEN is_sequel = 1 OR sequel_number >= 2 THEN 'Sequel' 
        ELSE 'Original / Standalone' 
    END AS content_type,
    COUNT(*) AS video_count,
    ROUND(AVG(views) / 1000000, 2) AS avg_views_millions
FROM `tyler_youtube.vw_tyler_complete`
GROUP BY content_type
ORDER BY avg_views_millions DESC;

-- 6. Top 5 highest-performing videos across the channel
SELECT 
    title, 
    primary_topic, 
    secondary_topic,
    format_category, 
    series, 
    ROUND(views / 1000000, 2) AS views_millions
FROM `tyler_youtube.vw_tyler_complete`
ORDER BY views DESC
LIMIT 5;

-- 7. Viewership by video duration tier
SELECT 
    CASE 
        WHEN duration_seconds / 60.0 < 15 THEN 'Under 15 Mins'
        WHEN duration_seconds / 60.0 BETWEEN 15 AND 20 THEN '15-20 Mins'
        ELSE 'Over 20 Mins'
    END AS duration_tier,
    COUNT(*) AS video_count,
    ROUND(AVG(views) / 1000000, 2) AS avg_views_millions
FROM `tyler_youtube.vw_tyler_complete`
GROUP BY duration_tier
ORDER BY avg_views_millions DESC;

-- 8. Performance by content mechanic
SELECT 
    content_mechanic,
    COUNT(*) AS video_count,
    ROUND(AVG(views) / 1000000, 2) AS avg_views_millions
FROM `tyler_youtube.vw_tyler_complete`
GROUP BY content_mechanic
ORDER BY avg_views_millions DESC;

-- 9. Collaborations vs. Solo videos
SELECT 
    CASE 
        WHEN is_collaboration = 1 THEN 'Collaboration' 
        ELSE 'Solo' 
    END AS video_type,
    COUNT(*) AS video_count,
    ROUND(AVG(views) / 1000000, 2) AS avg_views_millions
FROM `tyler_youtube.vw_tyler_complete`
GROUP BY video_type
ORDER BY avg_views_millions DESC;

-- 10. Publishing day of week vs. average views
SELECT 
    FORMAT_TIMESTAMP('%A', published_at) AS publish_day,
    COUNT(*) AS video_count,
    ROUND(AVG(views) / 1000000, 2) AS avg_views_millions
FROM `tyler_youtube.vw_tyler_complete`
GROUP BY publish_day
ORDER BY avg_views_millions DESC;


-- =================================================================================
-- PART 2: ADVANCED WINDOW FUNCTION QUERIES (FOR TECHNICAL INTERVIEWS)
-- =================================================================================

-- 11. WINDOW FUNCTION: Topic Baseline Benchmarking & Outlier Detection
SELECT 
    title,
    primary_topic,
    format_category,
    ROUND(views / 1000000, 2) AS views_millions,
    ROUND(AVG(views) OVER (PARTITION BY primary_topic) / 1000000, 2) AS topic_avg_millions,
    ROUND(
        SAFE_DIVIDE(
            views - AVG(views) OVER (PARTITION BY primary_topic),
            AVG(views) OVER (PARTITION BY primary_topic)
        ) * 100, 
        1
    ) AS pct_vs_topic_benchmark,
    DENSE_RANK() OVER (PARTITION BY primary_topic ORDER BY views DESC) AS rank_in_topic
FROM `tyler_youtube.vw_tyler_complete`
ORDER BY primary_topic, rank_in_topic;

-- 12. WINDOW FUNCTION: Franchise & Sequel Fatigue Tracking (ROW_NUMBER + LAG)
WITH series_progression AS (
    SELECT 
        series,
        title,
        published_at,
        ROW_NUMBER() OVER (PARTITION BY series ORDER BY published_at ASC) AS series_installment,
        views,
        LAG(views) OVER (PARTITION BY series ORDER BY published_at ASC) AS prev_episode_views
    FROM `tyler_youtube.vw_tyler_complete`
    WHERE series IS NOT NULL AND series != 'None'
)
SELECT 
    series,
    series_installment,
    title,
    ROUND(views / 1000000, 2) AS views_millions,
    ROUND(prev_episode_views / 1000000, 2) AS prev_ep_millions,
    ROUND(SAFE_DIVIDE(views - prev_episode_views, prev_episode_views) * 100, 1) AS ep_over_ep_growth_pct
FROM series_progression
WHERE prev_episode_views IS NOT NULL
ORDER BY ep_over_ep_growth_pct DESC;

-- 13. WINDOW FUNCTION: Rolling 3-Video Channel Momentum (Moving Average)
SELECT 
    published_at,
    title,
    primary_topic,
    ROUND(views / 1000000, 2) AS views_millions,
    ROUND(
        AVG(views) OVER (
            ORDER BY published_at ASC 
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) / 1000000, 
        2
    ) AS rolling_3_video_avg_millions
FROM `tyler_youtube.vw_tyler_complete`
ORDER BY published_at DESC;

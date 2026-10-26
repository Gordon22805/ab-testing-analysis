-- 03. Сегментный анализ: conversion rate A против B по device и traffic_source.

WITH segmented AS (
    SELECT
        device AS segment,
        experiment_group,
        COUNT(*)                                   AS users,
        SUM(CASE WHEN purchased THEN 1 ELSE 0 END) AS purchasers
    FROM events
    WHERE experiment_id = 'cta_buy_now_2026_09'
    GROUP BY device, experiment_group
),
pivoted AS (
    SELECT
        segment,
        MAX(CASE WHEN experiment_group = 'control' THEN users END)                AS users_control,
        MAX(CASE WHEN experiment_group = 'treatment' THEN users END)              AS users_treatment,
        MAX(CASE WHEN experiment_group = 'control' THEN purchasers END)           AS purchasers_control,
        MAX(CASE WHEN experiment_group = 'treatment' THEN purchasers END)         AS purchasers_treatment
    FROM segmented
    GROUP BY segment
)
SELECT
    segment,
    users_control,
    users_treatment,
    ROUND(purchasers_control * 1.0 / NULLIF(users_control, 0) * 100, 3)   AS cr_control_pct,
    ROUND(purchasers_treatment * 1.0 / NULLIF(users_treatment, 0) * 100, 3) AS cr_treatment_pct,
    ROUND(
        (
            (purchasers_treatment * 1.0 / NULLIF(users_treatment, 0))
            - (purchasers_control * 1.0 / NULLIF(users_control, 0))
        ) * 100, 3)                                                        AS abs_diff_pp
FROM pivoted
ORDER BY users_control DESC;

-- 02. Основная метрика: conversion rate по группам и разница между ними.

WITH by_group AS (
    SELECT
        experiment_group,
        COUNT(*)                                          AS users,
        SUM(CASE WHEN purchased THEN 1 ELSE 0 END)        AS purchasers,
        SUM(CASE WHEN added_to_cart THEN 1 ELSE 0 END)    AS cart_users,
        SUM(revenue)                                      AS revenue
    FROM events
    WHERE experiment_id = 'cta_buy_now_2026_09'
    GROUP BY experiment_group
),
rates AS (
    SELECT
        experiment_group,
        users,
        purchasers,
        purchasers * 1.0 / NULLIF(users, 0)              AS conversion_rate,
        cart_users * 1.0 / NULLIF(users, 0)              AS add_to_cart_rate,
        purchasers * 1.0 / NULLIF(cart_users, 0)         AS purchase_rate,
        revenue * 1.0 / NULLIF(users, 0)                 AS revenue_per_user,
        revenue * 1.0 / NULLIF(purchasers, 0)            AS revenue_per_purchaser
    FROM by_group
)
SELECT
    c.experiment_group                                          AS control_group,
    t.experiment_group                                          AS treatment_group,
    ROUND(c.conversion_rate * 100, 3)                           AS cr_control_pct,
    ROUND(t.conversion_rate * 100, 3)                           AS cr_treatment_pct,
    ROUND((t.conversion_rate - c.conversion_rate) * 100, 3)     AS abs_diff_pp,
    ROUND((t.conversion_rate - c.conversion_rate) / NULLIF(c.conversion_rate, 0) * 100, 2) AS relative_lift_pct,
    ROUND((t.add_to_cart_rate - c.add_to_cart_rate) * 100, 3)   AS atc_diff_pp,
    ROUND((t.purchase_rate - c.purchase_rate) * 100, 3)         AS purchase_rate_diff_pp,
    ROUND(t.revenue_per_purchaser, 2)                           AS aov_treatment
FROM rates c
JOIN rates t ON t.experiment_group = 'treatment'
WHERE c.experiment_group = 'control';

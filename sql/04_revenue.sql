-- 04. Выручка на пользователя и вклад источников трафика в общую выручку.

-- 04a: деньги по группам
SELECT
    experiment_group,
    COUNT(*)                                      AS users,
    SUM(CASE WHEN purchased THEN 1 ELSE 0 END)    AS purchasers,
    ROUND(SUM(revenue), 2)                        AS revenue,
    ROUND(SUM(revenue) / NULLIF(COUNT(*), 0), 2)  AS revenue_per_user,
    ROUND(
        SUM(revenue) * 1.0 / NULLIF(SUM(CASE WHEN purchased THEN 1 ELSE 0 END), 0), 2
    )                                             AS revenue_per_purchaser
FROM events
WHERE experiment_id = 'cta_buy_now_2026_09'
GROUP BY experiment_group
ORDER BY experiment_group;

-- 04b: доля источника трафика в выручке (оконная функция нужна, чтобы получить знаменатель без второго запроса)
SELECT
    traffic_source,
    COUNT(*)                                                AS users,
    ROUND(SUM(revenue), 2)                                  AS revenue,
    ROUND(100 * SUM(revenue) / NULLIF(SUM(SUM(revenue)) OVER (), 0), 2) AS revenue_share_pct
FROM events
WHERE experiment_id = 'cta_buy_now_2026_09'
GROUP BY traffic_source
ORDER BY revenue DESC;

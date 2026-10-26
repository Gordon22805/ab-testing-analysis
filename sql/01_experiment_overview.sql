-- 01. Обзор эксперимента: объём, период, группы.

WITH exposure AS (
    SELECT
        e.experiment_group,
        COUNT(*)              AS users,
        MIN(e.session_date)   AS first_session,
        MAX(e.session_date)   AS last_session,
        SUM(CASE WHEN e.viewed_product THEN 1 ELSE 0 END) AS viewers
    FROM events e
    WHERE e.experiment_id = 'cta_buy_now_2026_09'
    GROUP BY e.experiment_group
)
SELECT
    x.experiment_group,
    x.users,
    x.viewers,
    ROUND(x.viewers * 1.0 / NULLIF(x.users, 0), 4) AS view_rate,
    x.first_session,
    x.last_session,
    ex.name,
    ex.primary_metric,
    ex.status
FROM exposure x
JOIN experiments ex ON ex.experiment_id = 'cta_buy_now_2026_09'
ORDER BY x.experiment_group;

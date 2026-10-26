-- Схема для хранения результата A/B-эксперимента.
-- Гранулярность events: одна строка = один пользователь в одном эксперименте.

CREATE TABLE experiments (
    experiment_id   TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    start_date      DATE NOT NULL,
    end_date        DATE NOT NULL,
    primary_metric  TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'running'
);

CREATE TABLE users (
    user_id         TEXT PRIMARY KEY,
    first_seen_date DATE,
    country         TEXT,
    visitor_type    TEXT
);

CREATE TABLE events (
    event_id         BIGSERIAL PRIMARY KEY,
    user_id          TEXT NOT NULL REFERENCES users (user_id),
    experiment_id    TEXT NOT NULL REFERENCES experiments (experiment_id),
    experiment_group TEXT NOT NULL CHECK (experiment_group IN ('control', 'treatment')),
    session_date     DATE NOT NULL,
    device           TEXT NOT NULL,
    traffic_source   TEXT NOT NULL,
    viewed_product   BOOLEAN NOT NULL,
    added_to_cart    BOOLEAN NOT NULL,
    purchased        BOOLEAN NOT NULL,
    revenue          NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (revenue >= 0),
    session_duration INTEGER NOT NULL,
    CONSTRAINT one_group_per_user UNIQUE (user_id, experiment_id)
);

CREATE INDEX idx_events_experiment_group ON events (experiment_id, experiment_group);
CREATE INDEX idx_events_session_date ON events (session_date);

CREATE VIEW experiment_summary AS
SELECT
    e.experiment_id,
    e.experiment_group,
    COUNT(*)                                   AS users,
    SUM(CASE WHEN e.purchased THEN 1 ELSE 0 END) AS purchasers,
    ROUND(SUM(CASE WHEN e.purchased THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0), 4) AS conversion_rate,
    SUM(e.revenue)                             AS revenue,
    ROUND(SUM(e.revenue) / NULLIF(COUNT(*), 0), 2) AS revenue_per_user
FROM events e
GROUP BY e.experiment_id, e.experiment_group;

CREATE TABLE IF NOT EXISTS schedules (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    description  TEXT,
    start_at     TEXT NOT NULL,
    end_at       TEXT,
    all_day      INTEGER DEFAULT 0,
    category     TEXT DEFAULT 'general',
    remind_at    TEXT,
    status       TEXT DEFAULT 'active' CHECK(status IN ('active','completed','cancelled')),
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    recurrence   TEXT,
    parent_id    INTEGER,
    FOREIGN KEY (parent_id) REFERENCES schedules(id)
);

CREATE INDEX IF NOT EXISTS idx_schedules_start ON schedules(start_at);
CREATE INDEX IF NOT EXISTS idx_schedules_status ON schedules(status);
CREATE INDEX IF NOT EXISTS idx_schedules_remind ON schedules(remind_at);
CREATE INDEX IF NOT EXISTS idx_schedules_parent ON schedules(parent_id);

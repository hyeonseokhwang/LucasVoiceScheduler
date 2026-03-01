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

-- Challenges
CREATE TABLE IF NOT EXISTS challenges (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    description     TEXT,
    target_amount   INTEGER NOT NULL DEFAULT 0,
    current_amount  INTEGER NOT NULL DEFAULT 0,
    deadline        TEXT NOT NULL,
    status          TEXT DEFAULT 'active' CHECK(status IN ('active','completed','failed','cancelled')),
    milestones      TEXT,  -- JSON array: [{title, due_date, status}]
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_challenges_status ON challenges(status);
CREATE INDEX IF NOT EXISTS idx_challenges_deadline ON challenges(deadline);

-- Earnings (수익 기록)
CREATE TABLE IF NOT EXISTS earnings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    challenge_id    INTEGER NOT NULL,
    amount          INTEGER NOT NULL,
    source          TEXT,
    date            TEXT NOT NULL,
    note            TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (challenge_id) REFERENCES challenges(id)
);

CREATE INDEX IF NOT EXISTS idx_earnings_challenge ON earnings(challenge_id);
CREATE INDEX IF NOT EXISTS idx_earnings_date ON earnings(date);

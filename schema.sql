
-- SoraLink SQLite schema
-- Timestamps are UTC Unix milliseconds stored as INTEGER.
-- Apply with foreign keys enabled on every database connection.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS seat_invites (
    seat_label       TEXT PRIMARY KEY,
    invite_code_hash TEXT NOT NULL UNIQUE,
    is_active        INTEGER NOT NULL DEFAULT 1
                     CHECK (is_active IN (0, 1)),
    created_at_ms    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id               TEXT PRIMARY KEY,
    role             TEXT NOT NULL
                     CHECK (role IN ('passenger', 'crew')),
    seat_label       TEXT,
    token_hash       TEXT NOT NULL UNIQUE,
    created_at_ms    INTEGER NOT NULL,
    expires_at_ms    INTEGER NOT NULL,
    revoked_at_ms    INTEGER,
    CHECK (expires_at_ms > created_at_ms),
    CHECK (
        (role = 'passenger' AND seat_label IS NOT NULL)
        OR
        (role = 'crew' AND seat_label IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_sessions_expiry
    ON sessions(expires_at_ms);

CREATE TABLE IF NOT EXISTS requests (
    id                  TEXT PRIMARY KEY,
    session_id          TEXT NOT NULL,
    seat_label          TEXT NOT NULL,
    intent_id           TEXT NOT NULL CHECK (
        intent_id IN (
            'medical_help',
            'accessibility_assist',
            'safety_concern',
            'motion_sickness',
            'water_request',
            'blanket_request',
            'pillow_request',
            'bag_help',
            'headphone_request',
            'meal_inquiry',
            'tea_coffee',
            'lavatory_assist',
            'seat_issue',
            'customs_form',
            'baby_care'
        )
    ),
    priority            TEXT NOT NULL
                        CHECK (priority IN ('urgent', 'routine')),
    status              TEXT NOT NULL DEFAULT 'PENDING'
                        CHECK (
                            status IN (
                                'PENDING',
                                'ACKNOWLEDGED',
                                'COMPLETED'
                            )
                        ),
    created_at_ms       INTEGER NOT NULL,
    updated_at_ms       INTEGER NOT NULL,
    acknowledged_at_ms  INTEGER,
    completed_at_ms     INTEGER,
    acknowledged_by     TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (acknowledged_by) REFERENCES sessions(id),
    CHECK (updated_at_ms >= created_at_ms),
    CHECK (
        (status = 'PENDING'
            AND acknowledged_at_ms IS NULL
            AND completed_at_ms IS NULL)
        OR
        (status = 'ACKNOWLEDGED'
            AND acknowledged_at_ms IS NOT NULL
            AND completed_at_ms IS NULL)
        OR
        (status = 'COMPLETED'
            AND acknowledged_at_ms IS NOT NULL
            AND completed_at_ms IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_requests_queue
    ON requests(status, priority, created_at_ms);

CREATE INDEX IF NOT EXISTS idx_requests_passenger
    ON requests(session_id, created_at_ms DESC);

CREATE INDEX IF NOT EXISTS idx_requests_seat
    ON requests(seat_label, intent_id, status);

-- Prevent duplicate active requests for the same seat and intent.
CREATE UNIQUE INDEX IF NOT EXISTS idx_requests_no_active_duplicate
    ON requests(seat_label, intent_id)
    WHERE status IN ('PENDING', 'ACKNOWLEDGED');

CREATE TABLE IF NOT EXISTS request_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id     TEXT NOT NULL,
    actor_session_id TEXT,
    event_type     TEXT NOT NULL CHECK (
        event_type IN (
            'CREATED',
            'ACKNOWLEDGED',
            'COMPLETED',
            'FOLLOW_UP_REQUESTED'
        )
    ),
    details_json   TEXT NOT NULL DEFAULT '{}',
    created_at_ms  INTEGER NOT NULL,
    FOREIGN KEY (request_id) REFERENCES requests(id),
    FOREIGN KEY (actor_session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_request_events_history
    ON request_events(request_id, created_at_ms);

CREATE TABLE IF NOT EXISTS voice_previews (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL,
    transcript      TEXT NOT NULL,
    intent_id       TEXT,
    confidence      REAL,
    alternatives_json TEXT NOT NULL DEFAULT '[]',
    created_at_ms   INTEGER NOT NULL,
    expires_at_ms   INTEGER NOT NULL,
    consumed_at_ms  INTEGER,
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    CHECK (expires_at_ms > created_at_ms),
    CHECK (confidence IS NULL OR
           (confidence >= 0.0 AND confidence <= 1.0))
);

CREATE INDEX IF NOT EXISTS idx_voice_previews_expiry
    ON voice_previews(expires_at_ms);

CREATE TABLE IF NOT EXISTS active_broadcasts (
    id                    TEXT PRIMARY KEY,
    title                 TEXT NOT NULL,
    body                  TEXT NOT NULL,
    category              TEXT NOT NULL DEFAULT 'general',
    created_by_session_id TEXT NOT NULL,
    created_at_ms         INTEGER NOT NULL,
    expires_at_ms         INTEGER NOT NULL,
    ended_at_ms           INTEGER,
    FOREIGN KEY (created_by_session_id) REFERENCES sessions(id),
    CHECK (expires_at_ms > created_at_ms),
    CHECK (ended_at_ms IS NULL OR ended_at_ms >= created_at_ms)
);

CREATE INDEX IF NOT EXISTS idx_broadcasts_active
    ON active_broadcasts(ended_at_ms, expires_at_ms);

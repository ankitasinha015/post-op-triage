CREATE TABLE IF NOT EXISTS session (
    id TEXT PRIMARY KEY,
    surgery_type TEXT NOT NULL,
    recovery_day INTEGER NOT NULL,
    patient_name TEXT NOT NULL DEFAULT 'Patient',
    started_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS symptoms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES session(id),
    name TEXT NOT NULL,
    severity INTEGER NOT NULL CHECK (severity BETWEEN 0 AND 10),
    free_text TEXT,
    logged_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS vitals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES session(id),
    type TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    logged_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS meds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES session(id),
    med_name TEXT NOT NULL,
    dose TEXT NOT NULL,
    taken_at TEXT NOT NULL,
    logged_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES session(id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES session(id),
    severity TEXT NOT NULL CHECK (severity IN ('routine', 'monitor', 'urgent', 'critical', '911-now', 'system-error')),
    summary TEXT NOT NULL,
    signals TEXT,
    recommended_action TEXT,
    citations TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS risk_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES session(id),
    score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
    triggered_signals TEXT,
    reasoning TEXT,
    assessed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS patient_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_name TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES session(id),
    surgery_type TEXT NOT NULL,
    recovery_day INTEGER NOT NULL,
    key_findings TEXT NOT NULL,
    risk_level TEXT NOT NULL CHECK (risk_level IN ('low', 'moderate', 'high', 'critical')),
    unresolved_concerns TEXT,
    resolved_concerns TEXT,
    session_summary TEXT NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS investigation_gaps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES session(id),
    question TEXT NOT NULL,
    priority TEXT CHECK(priority IN ('high','medium','low')) DEFAULT 'medium',
    source TEXT DEFAULT 'risk_assessor',
    addressed INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

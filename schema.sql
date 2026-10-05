-- MapuaQ: Mapúa University Registrar Priority Queue Schema
-- Sprint 4 Local Deployment Schema

DROP TABLE IF EXISTS tickets;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT CHECK(role IN ('STUDENT', 'STAFF', 'ADMIN')) NOT NULL DEFAULT 'STUDENT',
    avatar_url TEXT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    student_id TEXT NOT NULL,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    request_type TEXT NOT NULL,
    request_weight REAL NOT NULL DEFAULT 1.0,
    grade_level TEXT NOT NULL,
    level_weight REAL NOT NULL DEFAULT 1.0,
    arrival_timestamp REAL NOT NULL,
    priority_score REAL NOT NULL,
    penalty_offset REAL DEFAULT 0.0,
    status TEXT CHECK(status IN ('WAITING', 'CALLED', 'IN_SERVICE', 'SERVED', 'SKIPPED', 'CANCELLED', 'INVALID')) DEFAULT 'WAITING',
    called_at REAL NULL,
    arrived_at REAL NULL,
    skipped_at REAL NULL,
    served_at REAL NULL,
    served_by INTEGER NULL,
    rejoin_used INTEGER DEFAULT 0,
    remarks TEXT,
    feedback_rating INTEGER,
    feedback_comment TEXT,
    feedback_submitted_at REAL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
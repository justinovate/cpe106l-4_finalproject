-- MapuaQ: Mapúa University Registrar Priority Queue Schema

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT CHECK(role IN ('staff', 'admin')) NOT NULL DEFAULT 'staff',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT NOT NULL,
    full_name TEXT NOT NULL,
    request_type TEXT NOT NULL,
    request_weight INTEGER NOT NULL,
    grade_level TEXT NOT NULL,
    level_weight INTEGER NOT NULL,
    arrival_timestamp REAL NOT NULL,
    priority_score REAL NOT NULL,
    status TEXT CHECK(status IN ('WAITING', 'CALLED', 'SERVED')) DEFAULT 'WAITING',
    served_at REAL NULL,
    served_by TEXT NULL,
    FOREIGN KEY (served_by) REFERENCES users (username)
);
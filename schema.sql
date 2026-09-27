-- MapuaQ: Mapúa University Registrar Priority Queue Schema
-- Separate tables for Student Accounts and Registrar Staff / Admin Accounts

CREATE TABLE IF NOT EXISTS staff_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT CHECK(role IN ('staff', 'admin')) NOT NULL DEFAULT 'staff',
    program_dept TEXT NULL,
    avatar_url TEXT DEFAULT '/static/uploads/avatars/default.png',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    program_dept TEXT NULL,
    avatar_url TEXT DEFAULT '/static/uploads/avatars/default.png',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NULL,
    student_id TEXT NOT NULL,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    request_type TEXT NOT NULL,
    request_weight INTEGER NOT NULL,
    grade_level TEXT NOT NULL,
    level_weight INTEGER NOT NULL,
    arrival_timestamp REAL NOT NULL,
    priority_score REAL NOT NULL,
    status TEXT CHECK(status IN ('WAITING', 'CALLED', 'SERVED', 'SKIPPED', 'CANCELLED')) DEFAULT 'WAITING',
    called_at REAL NULL,
    served_at REAL NULL,
    served_by TEXT NULL,
    remarks TEXT NULL,
    feedback_rating INTEGER NULL CHECK(feedback_rating BETWEEN 1 AND 5),
    feedback_comment TEXT NULL,
    feedback_submitted_at REAL NULL,
    FOREIGN KEY (user_id) REFERENCES students (id),
    FOREIGN KEY (served_by) REFERENCES staff_users (email)
);
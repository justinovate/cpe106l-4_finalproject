"""
MapuaQ System Configuration & Environment Settings
Enforces robust absolute path anchoring for SQLite DB and production defaults.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    # Flask Secret Key with robust fallback
    SECRET_KEY = os.environ.get("SECRET_KEY", "mapuaq_registrar_production_secret_key_2026_super_secure")

    # Absolute path anchoring for database persistence
    _db_env = os.environ.get("DB_NAME", "students_queue.db")
    if not os.path.isabs(_db_env):
        DB_NAME = os.path.abspath(os.path.join(BASE_DIR, _db_env))
    else:
        DB_NAME = os.path.abspath(_db_env)

    # Email Notification Configuration & Boolean Parsing
    EMAIL_DEV_MODE = os.environ.get("EMAIL_DEV_MODE", "True").strip().lower() in ("true", "1", "t", "yes")
    SMTP_SERVER = os.environ.get("SMTP_SERVER", os.environ.get("SMTP_HOST", "smtp.gmail.com"))
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "True").strip().lower() in ("true", "1", "t", "yes")
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME", os.environ.get("SMTP_USER", ""))
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", os.environ.get("SMTP_PASS", ""))
    SMTP_SENDER_NAME = os.environ.get("SMTP_SENDER_NAME", "Mapúa Registrar (MapuaQ)")
    SMTP_FROM = os.environ.get("SMTP_FROM", "no-reply@mapua.edu.ph")
    BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5000")
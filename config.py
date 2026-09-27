"""
MapuaQ System Configuration & Environment Settings
"""

import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "mapuaq_registrar_secret_key_2026_super_secure")
    DB_NAME = os.environ.get("DB_NAME", "students_queue.db")

    # Email Notification Configuration & Dual-Mode Toggle
    EMAIL_DEV_MODE = os.environ.get("EMAIL_DEV_MODE", "True").lower() in ("true", "1", "t", "yes")
    SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASS = os.environ.get("SMTP_PASS", "")
    SMTP_FROM = os.environ.get("SMTP_FROM", "no-reply@mapua.edu.ph")
    BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5000")

"""
MapuaQ Automated Email Notification Service
Supports Dual-Mode Switch (Live SMTP vs. Development/Demo Mode) with Exception Catching.
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from config import Config


def _log_mock_email(to_email: str, subject: str, body_text: str, header_label: str = "[MOCK EMAIL DISPATCH]"):
    """Prints clean terminal log for offline demonstration or fallback mode."""
    print("\n" + "=" * 50)
    print(header_label)
    print(f"TO: {to_email}")
    print(f"SUBJECT: {subject}")
    print("BODY:")
    print(body_text)
    print("-" * 50 + "\n")


def send_email(to_email: str, subject: str, body_html: str, body_text: str = None) -> bool:
    """Sends email via SMTP or falls back to console logging if DEV_MODE or SMTP fails."""
    if Config.EMAIL_DEV_MODE:
        _log_mock_email(to_email, subject, body_text or body_html, "[MOCK EMAIL DISPATCH - DEV MODE]")
        return True

    if not Config.SMTP_USERNAME or not Config.SMTP_PASSWORD:
        _log_mock_email(to_email, subject, body_text or body_html, "[MOCK EMAIL DISPATCH - NO CREDS]")
        return True

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{Config.SMTP_SENDER_NAME} <{Config.SMTP_FROM}>"
        msg["To"] = to_email

        if body_text:
            msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT, timeout=10) as server:
            if Config.SMTP_USE_TLS:
                server.starttls()
            server.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)
            server.sendmail(Config.SMTP_FROM, to_email, msg.as_string())
        return True
    except Exception as exc:
        _log_mock_email(to_email, subject, body_text or body_html, f"[SMTP ERROR FALLBACK - {exc}]")
        return False


def notify_ticket_created(ticket_data: dict, base_url: str = None) -> bool:
    base_url = base_url or Config.BASE_URL
    subject = f"MapúaQ Ticket Issued - #{ticket_data['id']}"
    body = f"Hello {ticket_data['full_name']},\n\nYour ticket #{ticket_data['id']} for {ticket_data['request_type']} has been issued.\nView status: {base_url}/ticket/{ticket_data['id']}"
    return send_email(ticket_data['email'], subject, body, body)


def notify_student_called(ticket_data: dict, counter_number: str = "Counter 1", base_url: str = None) -> bool:
    base_url = base_url or Config.BASE_URL
    subject = f"MapúaQ Ticket Called - #{ticket_data['id']}"
    body = f"Hello {ticket_data['full_name']},\n\nYour ticket #{ticket_data['id']} has been called! Please proceed to {counter_number}.\nView status: {base_url}/ticket/{ticket_data['id']}"
    return send_email(ticket_data['email'], subject, body, body)
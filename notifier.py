"""
MapuaQ Automated Email Notification Service
Supports Dual-Mode Switch (Live SMTP vs. Development/Demo Mode) with Exception Catching.
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from config import Config

load_dotenv()


def _log_mock_email(to_email: str, subject: str, body_text: str, header_label: str = "[MOCK EMAIL DISPATCH]"):
    """Prints clean terminal log for offline demonstration or fallback mode."""
    print("\n" + "=" * 50)
    print(header_label)
    print(f"TO: {to_email}")
    print(f"SUBJECT: {subject}")
    print("BODY:")
    print(body_text)
    print("-" * 50 + "\n")


def _send_email_async(to_email: str, subject: str, body_text: str, body_html: str = None) -> bool:
    """
    Internal email dispatch handler.
    If EMAIL_DEV_MODE is True or SMTP_USERNAME is empty, logs formatted mock email to terminal.
    If EMAIL_DEV_MODE is False, connects via SMTP. On error, logs exception and falls back safely.
    """
    if not to_email:
        return False

    dev_mode = Config.EMAIL_DEV_MODE

    # Development / Demo Mode or Missing Credentials -> Terminal Mock Log
    if dev_mode or not Config.SMTP_USERNAME:
        if not dev_mode and not Config.SMTP_USERNAME:
            print("[SMTP WARNING] SMTP_USERNAME is blank. Falling back to Dev/Demo Mode.")
        _log_mock_email(to_email, subject, body_text, "[MOCK EMAIL DISPATCH]")
        return True

    # Live Outbound SMTP Delivery
    try:
        msg = MIMEMultipart("alternative")
        sender_name = Config.SMTP_SENDER_NAME or "Mapúa Registrar (MapuaQ)"
        sender_from = Config.SMTP_FROM or Config.SMTP_USERNAME
        msg["From"] = f"{sender_name} <{sender_from}>"
        msg["To"] = to_email
        msg["Subject"] = subject

        msg.attach(MIMEText(body_text, "plain"))
        if body_html:
            msg.attach(MIMEText(body_html, "html"))

        smtp_server = Config.SMTP_SERVER or "smtp.gmail.com"
        smtp_port = int(Config.SMTP_PORT or 587)

        with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
            if Config.SMTP_USE_TLS:
                server.starttls()
            if Config.SMTP_USERNAME and Config.SMTP_PASSWORD:
                server.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)
            server.send_message(msg)

        print(f"[SMTP SUCCESS] Live email delivered to {to_email}")
        return True
    except Exception as e:
        print(f"[SMTP ERROR] Delivery failed to {to_email}: {e}")
        # Log mock email as terminal fallback to prevent application crashes
        _log_mock_email(to_email, subject, body_text, f"[SMTP ERROR FALLBACK - {e}]")
        return False


def notify_ticket_created(ticket_data: dict, base_url: str = None) -> bool:
    """Dispatched when student submits priority check-in."""
    base_url = base_url or Config.BASE_URL
    ticket_id = ticket_data.get("id")
    email = ticket_data.get("email")
    name = ticket_data.get("full_name", "Student")
    req_type = ticket_data.get("request_type", "Registrar Request")
    est_wait = ticket_data.get("estimated_wait_mins", 0)
    tracking_link = f"{base_url}/ticket/{ticket_id}"

    subject = f"MapúaQ Queue Ticket #{ticket_id} Confirmed — Priority Check-In"
    body_text = f"Dear {name},\n\nYour Mapúa Registrar priority check-in has been successfully submitted!\n\nTICKET DETAILS:\n- Ticket Number: #{ticket_id}\n- Request Type: {req_type}\n- Estimated Wait Time: ~{est_wait} minutes\n\nTrack status:\n{tracking_link}\n\nBest regards,\nMapúa University Registrar Office\n"
    return _send_email_async(email, subject, body_text)


def notify_student_called(ticket_data: dict, counter_number: str = "Counter 1", base_url: str = None) -> bool:
    """Dispatched when staff calls a student to the counter."""
    base_url = base_url or Config.BASE_URL
    ticket_id = ticket_data.get("id")
    email = ticket_data.get("email")
    name = ticket_data.get("full_name", "Student")
    req_type = ticket_data.get("request_type", "Registrar Request")
    tracking_link = f"{base_url}/ticket/{ticket_id}"

    subject = f"URGENT: Your Ticket #{ticket_id} is Being Called at {counter_number}"
    body_text = f"Dear {name},\n\nURGENT: Your Registrar Queue Ticket #{ticket_id} is NOW BEING CALLED at {counter_number}!\n\nTrack status:\n{tracking_link}\n\nBest regards,\nMapúa University Registrar Office\n"
    return _send_email_async(email, subject, body_text)


def notify_student_skipped(ticket_data: dict, base_url: str = None) -> bool:
    """Dispatched when staff marks ticket as SKIPPED (No-Show)."""
    base_url = base_url or Config.BASE_URL
    ticket_id = ticket_data.get("id")
    email = ticket_data.get("email")
    name = ticket_data.get("full_name", "Student")
    rejoin_link = f"{base_url}/ticket/{ticket_id}"

    subject = f"Notice: You missed your queue window for Ticket #{ticket_id}"
    body_text = f"Dear {name},\n\nYou were called for Ticket #{ticket_id}, but were marked as SKIPPED (No-Show).\nRe-join link:\n{rejoin_link}\n\nBest regards,\nMapúa University Registrar Office\n"
    return _send_email_async(email, subject, body_text)


def notify_ticket_served(ticket_data: dict, base_url: str = None) -> bool:
    """Dispatched when staff marks ticket as SERVED."""
    base_url = base_url or Config.BASE_URL
    ticket_id = ticket_data.get("id")
    email = ticket_data.get("email")
    name = ticket_data.get("full_name", "Student")
    feedback_link = f"{base_url}/ticket/{ticket_id}"

    subject = f"Mapúa Registrar Service Completed — Share Your Feedback for Ticket #{ticket_id}"
    body_text = f"Dear {name},\n\nYour Mapúa Registrar transaction for Ticket #{ticket_id} has been completed!\nRate your experience:\n{feedback_link}\n\nBest regards,\nMapúa University Registrar Office\n"
    return _send_email_async(email, subject, body_text)


def send_password_reset_notice(to_email: str, full_name: str, temp_password: str, base_url: str = None) -> bool:
    """Dispatched when a temporary password is generated."""
    base_url = base_url or Config.BASE_URL
    login_link = f"{base_url}/login"

    subject = "MapuaQ Security Notice: Your Temporary Password"
    body_text = f"Dear {full_name},\n\nA temporary password has been generated for your MapúaQ account: {temp_password}\n\nLog in here:\n{login_link}\n\nBest regards,\nMapúa University Registrar Office\n"
    return _send_email_async(to_email, subject, body_text)


def send_welcome_account_notice(to_email: str, full_name: str, account_id: str, default_password: str, verification_token: str, role: str = "student", base_url: str = None) -> bool:
    """Dispatched when Admin provisions a new account."""
    base_url = base_url or Config.BASE_URL
    verify_link = f"{base_url}/verify-email/{verification_token}"

    subject = "Welcome to MapúaQ — Account Provisioned & Email Verification Required"
    body_text = f"Dear {full_name},\n\nWelcome to MapúaQ! Your account has been provisioned.\nDefault Password: {default_password}\nVerify email:\n{verify_link}\n\nBest regards,\nMapúa University Registrar Office\n"
    return _send_email_async(to_email, subject, body_text)
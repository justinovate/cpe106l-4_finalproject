"""
MapuaQ Automated Email Notification Service
Supports Dual-Mode Switch (Live SMTP vs. Development/Demo Mode)
Dispatches asynchronous notifications for queue lifecycle events.
"""

import os
import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import flash
from config import Config


def _send_email_async(to_email: str, subject: str, body_text: str, body_html: str = None) -> bool:
    """
    Internal non-blocking email dispatch handler.
    If EMAIL_DEV_MODE is True, logs formatted output to terminal.
    If EMAIL_DEV_MODE is False, sends SMTP email via background thread with error handling.
    """
    if not to_email:
        return False

    if Config.EMAIL_DEV_MODE:
        # Development / Demo Mode Output
        print("\n" + "=" * 50)
        print("[MOCK EMAIL DISPATCH]")
        print(f"TO: {to_email}")
        print(f"SUBJECT: {subject}")
        print("BODY:")
        print(body_text)
        print("-" * 50 + "\n")

        # Flash lightweight UI banner in active Flask session if inside request context
        try:
            flash(f"📧 [DEMO EMAIL SENT] Notification dispatched to {to_email}", "info")
        except RuntimeError:
            pass  # Outside request context (e.g. background worker or test runner)
        return True

    # Live SMTP Mode — Asynchronous Background Thread Execution
    def smtp_worker():
        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = Config.SMTP_FROM
            msg["To"] = to_email
            msg["Subject"] = subject

            msg.attach(MIMEText(body_text, "plain"))
            if body_html:
                msg.attach(MIMEText(body_html, "html"))

            with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=10) as server:
                server.starttls()
                if Config.SMTP_USER and Config.SMTP_PASS:
                    server.login(Config.SMTP_USER, Config.SMTP_PASS)
                server.send_message(msg)
            print(f"[SMTP SUCCESS] Email sent to {to_email}")
        except Exception as e:
            print(f"[SMTP ERROR] Failed to send email to {to_email}: {e}")

    threading.Thread(target=smtp_worker, daemon=True).start()
    try:
        flash(f"📧 Email notification dispatched to {to_email}", "success")
    except RuntimeError:
        pass
    return True


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
    body_text = f"""Dear {name},

Your Mapúa Registrar priority check-in has been successfully submitted!

TICKET DETAILS:
- Ticket Number: #{ticket_id}
- Request Type: {req_type}
- Estimated Wait Time: ~{est_wait} minutes

Track your live ticket status in real-time here:
{tracking_link}

Please keep your Mapúa Student ID ready when your ticket is called.

Best regards,
Mapúa University Registrar Office
"""
    body_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
        <div style="background-color: #800000; color: white; padding: 15px; border-radius: 6px 6px 0 0; text-align: center;">
            <h2 style="margin: 0;">MapúaQ Priority Queuing System</h2>
            <p style="margin: 5px 0 0 0; opacity: 0.8;">Ticket Confirmation Notice</p>
        </div>
        <div style="padding: 20px; background-color: #ffffff;">
            <p>Dear <strong>{name}</strong>,</p>
            <p>Your Mapúa Registrar priority check-in has been successfully submitted!</p>
            
            <div style="background-color: #f8f9fa; border-left: 4px solid #800000; padding: 15px; margin: 20px 0;">
                <h3 style="margin-top: 0; color: #800000;">Ticket #{ticket_id}</h3>
                <p style="margin: 5px 0;"><strong>Request Type:</strong> {req_type}</p>
                <p style="margin: 5px 0;"><strong>Estimated Wait:</strong> ~{est_wait} mins</p>
            </div>

            <p style="text-align: center; margin-top: 25px;">
                <a href="{tracking_link}" style="background-color: #800000; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">
                    📱 View Live Status Screen
                </a>
            </p>
        </div>
    </div>
    """
    return _send_email_async(email, subject, body_text, body_html)


def notify_student_called(ticket_data: dict, counter_number: str = "Counter 1", base_url: str = None) -> bool:
    """Dispatched when staff calls a student to the counter."""
    base_url = base_url or Config.BASE_URL
    ticket_id = ticket_data.get("id")
    email = ticket_data.get("email")
    name = ticket_data.get("full_name", "Student")
    req_type = ticket_data.get("request_type", "Registrar Request")
    tracking_link = f"{base_url}/ticket/{ticket_id}"

    subject = f"URGENT: Your Ticket #{ticket_id} is Being Called at {counter_number}"
    body_text = f"""Dear {name},

URGENT: Your Registrar Queue Ticket #{ticket_id} is NOW BEING CALLED at {counter_number}!

Service Request: {req_type}

IMPORTANT GRACE PERIOD NOTICE:
You have a 5-MINUTE GRACE WINDOW to report to {counter_number} with your valid Mapúa Student ID. If you do not report within 5 minutes, your ticket will be marked as SKIPPED (No-Show).

Track status live:
{tracking_link}

Best regards,
Mapúa University Registrar Office
"""
    body_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
        <div style="background-color: #28a745; color: white; padding: 15px; border-radius: 6px 6px 0 0; text-align: center;">
            <h2 style="margin: 0;">📢 NOW SERVING!</h2>
            <p style="margin: 5px 0 0 0; opacity: 0.9;">Ticket #{ticket_id} Called</p>
        </div>
        <div style="padding: 20px; background-color: #ffffff;">
            <p>Dear <strong>{name}</strong>,</p>
            <p style="font-size: 1.1rem; color: #28a745; font-weight: bold;">
                Your Ticket #{ticket_id} is NOW BEING CALLED at {counter_number}!
            </p>
            
            <div style="background-color: #fff3cd; border: 1px solid #ffeba2; padding: 15px; margin: 20px 0; border-radius: 5px;">
                <h4 style="margin-top: 0; color: #856404;">⏱️ 5-Minute Grace Window Active</h4>
                <p style="margin: 0; color: #856404;">
                    Please report to {counter_number} immediately with your valid Mapúa Student ID.
                </p>
            </div>

            <p style="text-align: center; margin-top: 25px;">
                <a href="{tracking_link}" style="background-color: #28a745; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">
                    📱 Open Counter Directions
                </a>
            </p>
        </div>
    </div>
    """
    return _send_email_async(email, subject, body_text, body_html)


def notify_student_skipped(ticket_data: dict, base_url: str = None) -> bool:
    """Dispatched when staff marks ticket as SKIPPED (No-Show)."""
    base_url = base_url or Config.BASE_URL
    ticket_id = ticket_data.get("id")
    email = ticket_data.get("email")
    name = ticket_data.get("full_name", "Student")
    rejoin_link = f"{base_url}/ticket/{ticket_id}"

    subject = f"Notice: You missed your queue window for Ticket #{ticket_id}"
    body_text = f"""Dear {name},

Notice: You were called for Ticket #{ticket_id}, but were marked as SKIPPED (No-Show) due to no response within the 5-minute call window.

1-CHANCE PENALTY RE-JOIN WINDOW:
You have 15 MINUTES from the time of call to re-enter the queue. Click the link below to activate your single re-join chance (+2.0 priority score penalty offset):

{rejoin_link}

Note: If you do not re-join within 15 minutes, your ticket will be automatically CANCELLED.

Best regards,
Mapúa University Registrar Office
"""
    body_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
        <div style="background-color: #ffc107; color: #212529; padding: 15px; border-radius: 6px 6px 0 0; text-align: center;">
            <h2 style="margin: 0;">⚠️ Call Window Missed</h2>
            <p style="margin: 5px 0 0 0;">Ticket #{ticket_id}</p>
        </div>
        <div style="padding: 20px; background-color: #ffffff;">
            <p>Dear <strong>{name}</strong>,</p>
            <p>You missed your counter call for Ticket #{ticket_id}.</p>
            
            <div style="background-color: #f8f9fa; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0;">
                <h4 style="margin-top: 0;">🔄 15-Minute Re-Join Allowance Active</h4>
                <p style="margin: 0;">
                    You have 1 chance to re-enter the queue with a +2.0 priority score penalty offset.
                </p>
            </div>

            <p style="text-align: center; margin-top: 25px;">
                <a href="{rejoin_link}" style="background-color: #ffc107; color: #212529; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">
                    🔄 Re-Join Queue Now
                </a>
            </p>
        </div>
    </div>
    """
    return _send_email_async(email, subject, body_text, body_html)


def notify_ticket_served(ticket_data: dict, base_url: str = None) -> bool:
    """Dispatched when staff marks ticket as SERVED."""
    base_url = base_url or Config.BASE_URL
    ticket_id = ticket_data.get("id")
    email = ticket_data.get("email")
    name = ticket_data.get("full_name", "Student")
    req_type = ticket_data.get("request_type", "Registrar Request")
    remarks = ticket_data.get("remarks", "Processed successfully")
    feedback_link = f"{base_url}/ticket/{ticket_id}"

    subject = f"Mapúa Registrar Service Completed — Share Your Feedback for Ticket #{ticket_id}"
    body_text = f"""Dear {name},

Your Mapúa Registrar transaction for Ticket #{ticket_id} ({req_type}) has been completed!

REMARKS FROM REGISTRAR COUNTER:
{remarks}

WE VALUE YOUR FEEDBACK:
Please take 30 seconds to rate your service experience (1-5 stars) and leave any comments:
{feedback_link}

Thank you for using MapúaQ!

Best regards,
Mapúa University Registrar Office
"""
    body_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
        <div style="background-color: #800000; color: white; padding: 15px; border-radius: 6px 6px 0 0; text-align: center;">
            <h2 style="margin: 0;">✓ Service Completed</h2>
            <p style="margin: 5px 0 0 0; opacity: 0.8;">Ticket #{ticket_id}</p>
        </div>
        <div style="padding: 20px; background-color: #ffffff;">
            <p>Dear <strong>{name}</strong>,</p>
            <p>Your transaction for <strong>{req_type}</strong> has been marked completed.</p>
            
            <div style="background-color: #f8f9fa; border-left: 4px solid #800000; padding: 15px; margin: 20px 0;">
                <p style="margin: 0;"><strong>Counter Remarks:</strong> {remarks}</p>
            </div>

            <h4 style="text-align: center; margin-top: 25px;">Rate Your Experience (1-5 Stars)</h4>
            <p style="text-align: center;">
                <a href="{feedback_link}" style="background-color: #800000; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">
                    ⭐ Leave Service Feedback
                </a>
            </p>
        </div>
    </div>
    """
    return _send_email_async(email, subject, body_text, body_html)

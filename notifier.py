"""
MapuaQ Automated Email Notification Service
Supports Dual-Mode Switch (Live SMTP vs. Development/Demo Mode) with Graceful Fallback.
Dispatches notifications for queue lifecycle events, security password resets, and account email verification.
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from config import Config

# Ensure environment variables are parsed upon module load
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
    If EMAIL_DEV_MODE is True or SMTP_USERNAME is empty, logs formatted mock email to terminal and returns True.
    If EMAIL_DEV_MODE is False, connects via SMTP, sends email, and returns True on success, False on error.
    """
    if not to_email:
        return False

    dev_mode = Config.EMAIL_DEV_MODE

    # Development / Demo Mode or Missing Credentials -> Mock Log
    if dev_mode or not Config.SMTP_USERNAME:
        if not dev_mode and not Config.SMTP_USERNAME:
            print("[SMTP WARNING] SMTP_USERNAME is blank. Falling back to Dev/Demo Mode.")
        _log_mock_email(to_email, subject, body_text, "[MOCK EMAIL DISPATCH]")
        return True

    # Live SMTP Mode
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

        with smtplib.SMTP(smtp_server, smtp_port, timeout=12) as server:
            if Config.SMTP_USE_TLS:
                server.starttls()
            if Config.SMTP_USERNAME and Config.SMTP_PASSWORD:
                server.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)
            server.send_message(msg)

        print(f"[SMTP SUCCESS] Live email delivered to {to_email}")
        return True
    except Exception as e:
        print(f"[SMTP ERROR] Delivery failed to {to_email}: {e}")
        # Log mock email as terminal fallback
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


def send_password_reset_notice(to_email: str, full_name: str, temp_password: str, base_url: str = None) -> bool:
    """Dispatched when a temporary password is generated for account security recovery."""
    base_url = base_url or Config.BASE_URL
    login_link = f"{base_url}/login"

    subject = "MapuaQ Security Notice: Your Temporary Password"
    body_text = f"""Dear {full_name},

MapuaQ Security Notice: A temporary password has been generated for your MapúaQ account.

YOUR TEMPORARY PASSWORD:
{temp_password}

SECURITY INSTRUCTIONS:
1. Log in to your MapúaQ account using your temporary password here:
   {login_link}
2. For account security, you will be prompted to change your password immediately upon logging in.

If you did not request a password reset, please contact the Mapúa Registrar Office immediately.

Best regards,
Mapúa University Registrar Office
"""
    body_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
        <div style="background-color: #800000; color: white; padding: 15px; border-radius: 6px 6px 0 0; text-align: center;">
            <h2 style="margin: 0;">🔒 Security Notice: Temporary Password</h2>
            <p style="margin: 5px 0 0 0; opacity: 0.9;">Mapúa Registrar Account Security</p>
        </div>
        <div style="padding: 20px; background-color: #ffffff;">
            <p>Dear <strong>{full_name}</strong>,</p>
            <p>A temporary password has been issued for your MapúaQ account.</p>
            
            <div style="background-color: #f8f9fa; border: 2px dashed #800000; padding: 15px; margin: 20px 0; text-align: center; border-radius: 6px;">
                <small style="color: #666; font-weight: bold; text-transform: uppercase;">Temporary Password</small>
                <div style="font-family: 'Courier New', monospace; font-size: 1.8rem; font-weight: bold; color: #800000; letter-spacing: 3px; margin-top: 5px;">
                    {temp_password}
                </div>
            </div>

            <p><strong>Required Action:</strong> Please log in using your temporary password and update your password immediately.</p>

            <p style="text-align: center; margin-top: 25px;">
                <a href="{login_link}" style="background-color: #800000; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">
                    🔑 Log In &amp; Change Password
                </a>
            </p>
            <p style="font-size: 0.85rem; color: #777; margin-top: 20px; text-align: center;">
                If you did not request a password reset, please notify Mapúa Registrar Administration immediately.
            </p>
        </div>
    </div>
    """
    return _send_email_async(to_email, subject, body_text, body_html)


def send_welcome_account_notice(to_email: str, full_name: str, account_id: str, default_password: str, verification_token: str, role: str = "student", base_url: str = None) -> bool:
    """Dispatched when Admin provisions a new student or staff account with default credentials and email verification link."""
    base_url = base_url or Config.BASE_URL
    verify_link = f"{base_url}/verify-email/{verification_token}"
    login_link = f"{base_url}/login"

    subject = "Welcome to MapúaQ — Account Provisioned & Email Verification Required"
    body_text = f"""Dear {full_name},

Welcome to MapúaQ! Your official Mapúa Registrar priority queuing account has been provisioned.

YOUR ACCOUNT DETAILS:
- Account Role: {role.capitalize()}
- Mapúa Email / Username: {to_email}
- Account ID: {account_id}
- Default Assigned Password: {default_password}

EMAIL VERIFICATION REQUIRED:
Please verify your email address to activate your account by clicking the link below:
{verify_link}

Once verified, you can log in to MapúaQ using your credentials here:
{login_link}

For security, we recommend updating your password upon your first login.

Best regards,
Mapúa University Registrar Office
"""
    body_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
        <div style="background-color: #800000; color: white; padding: 15px; border-radius: 6px 6px 0 0; text-align: center;">
            <h2 style="margin: 0;">Welcome to MapúaQ</h2>
            <p style="margin: 5px 0 0 0; opacity: 0.9;">Account Provisioning &amp; Verification Notice</p>
        </div>
        <div style="padding: 20px; background-color: #ffffff;">
            <p>Dear <strong>{full_name}</strong>,</p>
            <p>Your official Mapúa Registrar account has been created.</p>
            
            <div style="background-color: #f8f9fa; border-left: 4px solid #800000; padding: 15px; margin: 20px 0;">
                <h4 style="margin-top: 0; color: #800000;">Account Credentials</h4>
                <p style="margin: 5px 0;"><strong>Role:</strong> {role.capitalize()}</p>
                <p style="margin: 5px 0;"><strong>Mapúa Email:</strong> {to_email}</p>
                <p style="margin: 5px 0;"><strong>Student / Account ID:</strong> {account_id}</p>
                <p style="margin: 5px 0;"><strong>Default Password:</strong> <code style="background-color: #eee; padding: 2px 6px; border-radius: 4px; color: #800000; font-weight: bold;">{default_password}</code></p>
            </div>

            <div style="background-color: #fff3cd; border: 1px solid #ffeba2; padding: 15px; margin: 20px 0; border-radius: 5px; text-align: center;">
                <h4 style="margin-top: 0; color: #856404;">✉️ Action Required: Verify Email Address</h4>
                <p style="margin-bottom: 15px; color: #856404;">Please click the button below to verify your email address and activate your account.</p>
                <a href="{verify_link}" style="background-color: #800000; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">
                    ✓ Verify Email Address Now
                </a>
            </div>

            <p style="font-size: 0.85rem; color: #777; margin-top: 20px; text-align: center;">
                Or log in directly at <a href="{login_link}" style="color: #800000;">{login_link}</a>
            </p>
        </div>
    </div>
    """
    return _send_email_async(to_email, subject, body_text, body_html)

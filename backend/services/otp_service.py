"""
OTP Service for SATYA project.
Handles OTP generation, hashing, storage, email sending, verification, and cleanup.
"""

import datetime
import logging
import os
import secrets
import string
import threading

from bson import ObjectId
from flask import current_app
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash

from database import get_db
from vault.audit import AuditLogger

logger = logging.getLogger(__name__)

OTP_EXPIRY_MINUTES = 5
MAX_VERIFY_ATTEMPTS = 5
MAX_RESEND_ATTEMPTS = 3


class OTPService:
    """Secure OTP generation, storage, email delivery, and verification."""

    # ── OTP Generation & Hashing ──────────────────────────────────────────

    @staticmethod
    def generate_otp():
        """Generate a cryptographically secure 6-digit OTP."""
        return "".join(secrets.choice(string.digits) for _ in range(6))

    @staticmethod
    def hash_otp(otp):
        return generate_password_hash(otp)

    @staticmethod
    def verify_otp_hash(otp, otp_hash):
        return check_password_hash(otp_hash, otp)

    # ── Email HTML Template ───────────────────────────────────────────────

    @staticmethod
    def _build_email_html(otp, purpose):
        purpose_text = {
            "document_verification": "Document Verification",
            "eligibility_check": "Eligibility Check",
        }.get(purpose, "Verification")

        return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:40px 0;">
<tr><td align="center">
<table width="480" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">
  <tr><td style="background:linear-gradient(135deg,#1e40af,#3b82f6);padding:32px;text-align:center;">
    <h1 style="margin:0;color:#ffffff;font-size:28px;font-weight:800;letter-spacing:1px;">SATYA</h1>
    <p style="margin:8px 0 0;color:#bfdbfe;font-size:13px;">AI Based Government Scheme Eligibility System</p>
  </td></tr>
  <tr><td style="padding:40px 32px;">
    <h2 style="margin:0 0 8px;color:#0f172a;font-size:22px;font-weight:700;text-align:center;">Your Verification Code</h2>
    <p style="margin:0 0 24px;color:#64748b;font-size:14px;text-align:center;">for {purpose_text}</p>
    <div style="background:#f8fafc;border:2px dashed #cbd5e1;border-radius:12px;padding:24px;text-align:center;margin:0 0 24px;">
      <span style="font-size:36px;font-weight:800;letter-spacing:12px;color:#1e40af;font-family:monospace;">{otp}</span>
    </div>
    <p style="margin:0 0 8px;color:#ef4444;font-size:14px;font-weight:600;text-align:center;">⏱ This code expires in 5 minutes</p>
    <p style="margin:0;color:#94a3b8;font-size:13px;text-align:center;">If you did not request this code, please ignore this email.</p>
  </td></tr>
  <tr><td style="background:#f8fafc;padding:20px 32px;text-align:center;border-top:1px solid #e2e8f0;">
    <p style="margin:0;color:#94a3b8;font-size:12px;">SATYA - AI Based Government Scheme Eligibility System</p>
    <p style="margin:4px 0 0;color:#cbd5e1;font-size:11px;">This is an automated message. Please do not reply.</p>
  </td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""

    # ── Send Email ────────────────────────────────────────────────────────

    @staticmethod
    def _send_email(email, otp, purpose):
        """Send OTP email via Flask-Mail. Returns True on success."""
        try:
            print(f"[OTP DEBUG] Preparing to send email to recipient: {email}")
            mail = Mail(current_app)
            html_body = OTPService._build_email_html(otp, purpose)
            msg = Message(
                subject="SATYA Verification Code",
                recipients=[email],
                html=html_body,
            )
            print(f"[OTP DEBUG] Sending message via mail.send...")
            mail.send(msg)
            print(f"[OTP DEBUG] mail.send() returned successfully for {email}")
            logger.info("[OTP] Email sent to %s for purpose=%s", email, purpose)
            return True
        except Exception as exc:
            print(f"[OTP DEBUG] Exception during mail.send() to {email}: {exc}")
            import traceback
            traceback.print_exc()
            logger.error("[OTP] Failed to send email to %s: %s", email, exc, exc_info=True)
            return False

    # ── Send OTP (generate + store + email) ───────────────────────────────

    @staticmethod
    def send_otp(user_id, email, purpose, document_id=None, ip_address="", user_agent=""):
        db = get_db()
        if db is None:
            return {"success": False, "message": "Database unavailable"}

        # Cleanup any previous unverified OTPs for this user+purpose
        db.email_otps.delete_many({
            "user_id": str(user_id),
            "purpose": purpose,
            "verified": False,
        })

        otp = OTPService.generate_otp()
        otp_hash = OTPService.hash_otp(otp)
        now = datetime.datetime.utcnow()

        otp_doc = {
            "user_id": str(user_id),
            "email": email,
            "otp_hash": otp_hash,
            "purpose": purpose,
            "document_id": str(document_id) if document_id else None,
            "created_at": now,
            "expires_at": now + datetime.timedelta(minutes=OTP_EXPIRY_MINUTES),
            "verified": False,
            "attempt_count": 0,
            "resend_count": 0,
            "ip_address": ip_address,
            "user_agent": user_agent,
        }

        result = db.email_otps.insert_one(otp_doc)
        otp_id = str(result.inserted_id)

        # Audit log (before email attempt)
        AuditLogger.record("otp_sent", user_id, {
            "email": email,
            "purpose": purpose,
            "document_id": document_id,
            "otp_id": otp_id,
            "ip_address": ip_address,
        }, document_id=document_id)

        # Send email in a background thread so the API returns IMMEDIATELY.
        # SMTP can block for 20-60 seconds — never block the request thread.
        app_ctx = current_app._get_current_object()
        def _send_in_background():
            with app_ctx.app_context():
                sent = OTPService._send_email(email, otp, purpose)
                if not sent:
                    logger.warning("[OTP] Background email delivery failed for otp_id=%s email=%s", otp_id, email)
                else:
                    logger.info("[OTP] Background email delivered to %s otp_id=%s", email, otp_id)

        t = threading.Thread(target=_send_in_background, daemon=True)
        t.start()

        masked_email = OTPService._mask_email(email)
        return {
            "success": True,
            "message": f"OTP sent to {masked_email}",
            "otp_id": otp_id,
            "masked_email": masked_email,
        }

    # ── Verify OTP ────────────────────────────────────────────────────────

    @staticmethod
    def verify_otp(otp_id, otp_code, ip_address="", user_agent=""):
        db = get_db()
        if db is None:
            return {"success": False, "message": "Database unavailable"}

        try:
            otp_doc = db.email_otps.find_one({"_id": ObjectId(otp_id)})
        except Exception:
            return {"success": False, "message": "Invalid OTP session"}

        if not otp_doc:
            return {"success": False, "message": "OTP session not found. Please request a new code."}

        # Check expiry
        if datetime.datetime.utcnow() > otp_doc["expires_at"]:
            db.email_otps.delete_one({"_id": ObjectId(otp_id)})
            return {"success": False, "message": "OTP has expired. Please request a new code."}

        # Check attempts
        if otp_doc["attempt_count"] >= MAX_VERIFY_ATTEMPTS:
            db.email_otps.delete_one({"_id": ObjectId(otp_id)})
            AuditLogger.record("otp_max_attempts", otp_doc["user_id"], {
                "otp_id": otp_id, "purpose": otp_doc["purpose"], "ip_address": ip_address,
            })
            return {"success": False, "message": "Too many failed attempts. Please request a new code."}

        # Increment attempt count
        db.email_otps.update_one(
            {"_id": ObjectId(otp_id)},
            {"$inc": {"attempt_count": 1}}
        )

        # Verify hash
        if not OTPService.verify_otp_hash(otp_code, otp_doc["otp_hash"]):
            remaining = MAX_VERIFY_ATTEMPTS - otp_doc["attempt_count"] - 1
            if remaining <= 0:
                db.email_otps.delete_one({"_id": ObjectId(otp_id)})
                AuditLogger.record("otp_max_attempts", otp_doc["user_id"], {
                    "otp_id": otp_id, "purpose": otp_doc["purpose"], "ip_address": ip_address,
                })
                return {"success": False, "message": "Too many failed attempts. Please request a new code."}

            AuditLogger.record("otp_verify_failed", otp_doc["user_id"], {
                "otp_id": otp_id, "purpose": otp_doc["purpose"],
                "remaining_attempts": remaining, "ip_address": ip_address,
            })
            return {"success": False, "message": f"Invalid OTP. {remaining} attempt(s) remaining."}

        # Success — delete OTP record
        db.email_otps.delete_one({"_id": ObjectId(otp_id)})

        AuditLogger.record("otp_verified", otp_doc["user_id"], {
            "otp_id": otp_id, "purpose": otp_doc["purpose"],
            "email": otp_doc["email"], "ip_address": ip_address,
        }, document_id=otp_doc.get("document_id"))

        return {"success": True, "message": "OTP verified successfully"}

    # ── Resend OTP ────────────────────────────────────────────────────────

    @staticmethod
    def resend_otp(otp_id, ip_address="", user_agent=""):
        db = get_db()
        if db is None:
            return {"success": False, "message": "Database unavailable"}

        try:
            otp_doc = db.email_otps.find_one({"_id": ObjectId(otp_id)})
        except Exception:
            return {"success": False, "message": "Invalid OTP session"}

        if not otp_doc:
            return {"success": False, "message": "OTP session not found."}

        if otp_doc["resend_count"] >= MAX_RESEND_ATTEMPTS:
            return {"success": False, "message": "Maximum resend attempts reached. Please start over."}

        # Generate new OTP
        new_otp = OTPService.generate_otp()
        new_hash = OTPService.hash_otp(new_otp)
        now = datetime.datetime.utcnow()

        db.email_otps.update_one(
            {"_id": ObjectId(otp_id)},
            {"$set": {
                "otp_hash": new_hash,
                "expires_at": now + datetime.timedelta(minutes=OTP_EXPIRY_MINUTES),
                "attempt_count": 0,
            }, "$inc": {"resend_count": 1}}
        )

        AuditLogger.record("otp_resent", otp_doc["user_id"], {
            "otp_id": otp_id, "purpose": otp_doc["purpose"],
            "resend_count": otp_doc["resend_count"] + 1,
            "ip_address": ip_address,
        })

        # Send in background thread — never block the resend response
        app_ctx = current_app._get_current_object()
        resend_email = otp_doc["email"]
        resend_purpose = otp_doc["purpose"]
        def _resend_in_background():
            with app_ctx.app_context():
                sent = OTPService._send_email(resend_email, new_otp, resend_purpose)
                if not sent:
                    logger.warning("[OTP] Background resend failed for otp_id=%s", otp_id)

        t = threading.Thread(target=_resend_in_background, daemon=True)
        t.start()

        return {"success": True, "message": "New OTP sent successfully"}

    # ── Cleanup ───────────────────────────────────────────────────────────

    @staticmethod
    def cleanup_expired():
        db = get_db()
        if db is None:
            return 0
        result = db.email_otps.delete_many({
            "expires_at": {"$lt": datetime.datetime.utcnow()},
            "verified": False,
        })
        return result.deleted_count

    # ── Utility ───────────────────────────────────────────────────────────

    @staticmethod
    def _mask_email(email):
        if not email or "@" not in email:
            return email
        local, domain = email.rsplit("@", 1)
        if len(local) <= 2:
            masked_local = local[0] + "***"
        else:
            masked_local = local[0] + "*" * (len(local) - 2) + local[-1]
        return f"{masked_local}@{domain}"

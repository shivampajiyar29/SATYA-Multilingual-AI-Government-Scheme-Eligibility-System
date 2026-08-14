"""
OTP Routes for the SATYA project.
Provides endpoints for sending, verifying, and resending email OTPs.
"""

from flask import Blueprint, request, jsonify
import logging

from bson import ObjectId
from database import get_db
from services.otp_service import OTPService

from routes.auth import token_required

logger = logging.getLogger(__name__)
otp_bp = Blueprint("otp", __name__)


@otp_bp.route("/send", methods=["POST"])
@token_required
def send_otp(current_user_id, current_user_role):
    """Send OTP to the logged-in user's registered email."""
    try:
        data = request.get_json(silent=True) or {}
        purpose = data.get("purpose")
        document_id = data.get("document_id")

        if not purpose:
            return jsonify({"success": False, "message": "purpose is required"}), 400

        if purpose not in ("document_verification", "eligibility_check"):
            return jsonify({"success": False, "message": "Invalid purpose"}), 400

        # Look up user email from MongoDB — never trust frontend
        db = get_db()
        if db is None:
            return jsonify({"success": False, "message": "Database unavailable"}), 500

        user = db.users.find_one({"_id": ObjectId(current_user_id)})
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404

        email = user.get("email")
        if not email:
            return jsonify({"success": False, "message": "No email registered for this account"}), 400

        ip_address = request.remote_addr or ""
        user_agent = request.headers.get("User-Agent", "")

        # Cleanup expired OTPs
        OTPService.cleanup_expired()

        result = OTPService.send_otp(
            user_id=str(current_user_id),
            email=email,
            purpose=purpose,
            document_id=document_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        status_code = 200 if result["success"] else 500
        return jsonify(result), status_code

    except Exception as e:
        logger.error("[OTP] Error in send_otp: %s", e)
        return jsonify({"success": False, "message": "Internal server error"}), 500


@otp_bp.route("/verify", methods=["POST"])
@token_required
def verify_otp(current_user_id, current_user_role):
    """Verify an OTP code submitted by the user."""
    try:
        data = request.get_json(silent=True) or {}
        otp_id = data.get("otp_id")
        otp_code = data.get("otp_code")

        if not otp_id or not otp_code:
            return jsonify({"success": False, "message": "otp_id and otp_code are required"}), 400

        db = get_db()
        if db is None:
            return jsonify({"success": False, "message": "Database unavailable"}), 500

        try:
            otp_doc = db.email_otps.find_one({"_id": ObjectId(otp_id)})
        except Exception:
            return jsonify({"success": False, "message": "Invalid OTP session"}), 400

        if not otp_doc:
            return jsonify({"success": False, "message": "OTP session not found. Please request a new code."}), 400

        # Enforce that the OTP session belongs to the current user
        if otp_doc.get("user_id") != str(current_user_id):
            return jsonify({"success": False, "message": "Unauthorized OTP session"}), 403

        ip_address = request.remote_addr or ""
        user_agent = request.headers.get("User-Agent", "")

        result = OTPService.verify_otp(
            otp_id=otp_id,
            otp_code=str(otp_code).strip(),
            ip_address=ip_address,
            user_agent=user_agent,
        )

        status_code = 200 if result["success"] else 400
        return jsonify(result), status_code

    except Exception as e:
        logger.error("[OTP] Error in verify_otp: %s", e)
        return jsonify({"success": False, "message": "Internal server error"}), 500


@otp_bp.route("/resend", methods=["POST"])
@token_required
def resend_otp(current_user_id, current_user_role):
    """Resend OTP to the user's email."""
    try:
        data = request.get_json(silent=True) or {}
        otp_id = data.get("otp_id")

        if not otp_id:
            return jsonify({"success": False, "message": "otp_id is required"}), 400

        db = get_db()
        if db is None:
            return jsonify({"success": False, "message": "Database unavailable"}), 500

        try:
            otp_doc = db.email_otps.find_one({"_id": ObjectId(otp_id)})
        except Exception:
            return jsonify({"success": False, "message": "Invalid OTP session"}), 400

        if not otp_doc:
            return jsonify({"success": False, "message": "OTP session not found."}), 400

        # Enforce that the OTP session belongs to the current user
        if otp_doc.get("user_id") != str(current_user_id):
            return jsonify({"success": False, "message": "Unauthorized OTP session"}), 403

        ip_address = request.remote_addr or ""
        user_agent = request.headers.get("User-Agent", "")

        result = OTPService.resend_otp(
            otp_id=otp_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        status_code = 200 if result["success"] else 400
        return jsonify(result), status_code

    except Exception as e:
        logger.error("[OTP] Error in resend_otp: %s", e)
        return jsonify({"success": False, "message": "Internal server error"}), 500

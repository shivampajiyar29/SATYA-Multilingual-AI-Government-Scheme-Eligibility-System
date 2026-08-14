import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  Shield,
  CheckCircle2,
  RefreshCw,
  Loader2,
  XCircle,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import API_BASE_URL from "../config/api";

/**
 * Reusable OTP Verification Modal.
 *
 * @param {Object} props
 * @param {boolean} props.isOpen
 * @param {Function} props.onClose
 * @param {Function} props.onVerified - called after OTP is verified successfully
 * @param {string}   props.userId
 * @param {string}   props.purpose - 'document_verification' | 'eligibility_check'
 * @param {string}   [props.documentId]
 */
export default function OTPVerificationModal({
  isOpen,
  onClose,
  onVerified,
  userId,
  purpose,
  documentId,
}) {
  const [otpId, setOtpId] = useState(null);
  const [maskedEmail, setMaskedEmail] = useState("");
  const [digits, setDigits] = useState(["", "", "", "", "", ""]);
  const [timer, setTimer] = useState(300);
  const [resendCount, setResendCount] = useState(0);
  const [canResend, setCanResend] = useState(false);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  const inputRefs = useRef([]);
  const timerRef = useRef(null);
  const resendTimerRef = useRef(null);

  // ── Send OTP on open ────────────────────────────────────────────────
  useEffect(() => {
    if (isOpen && !otpId && !success) {
      sendOtp();
    }
    return () => {
      clearInterval(timerRef.current);
      clearTimeout(resendTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  // ── Countdown Timer ─────────────────────────────────────────────────
  useEffect(() => {
    if (!otpId || success) return;
    setTimer(300);
    clearInterval(timerRef.current);
    timerRef.current = setInterval(() => {
      setTimer((prev) => {
        if (prev <= 1) {
          clearInterval(timerRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timerRef.current);
  }, [otpId, success]);

  // ── Resend cooldown (30 sec after send) ─────────────────────────────
  useEffect(() => {
    if (!otpId) return;
    setCanResend(false);
    clearTimeout(resendTimerRef.current);
    resendTimerRef.current = setTimeout(() => setCanResend(true), 30000);
    return () => clearTimeout(resendTimerRef.current);
  }, [otpId]);

  // ── Reset state when modal closes ───────────────────────────────────
  useEffect(() => {
    if (!isOpen) {
      setOtpId(null);
      setMaskedEmail("");
      setDigits(["", "", "", "", "", ""]);
      setTimer(300);
      setResendCount(0);
      setCanResend(false);
      setLoading(false);
      setSending(false);
      setError("");
      setSuccess(false);
      clearInterval(timerRef.current);
      clearTimeout(resendTimerRef.current);
    }
  }, [isOpen]);

  // ── API: Send OTP ───────────────────────────────────────────────────
  const sendOtp = useCallback(async () => {
    setSending(true);
    setError("");
    // Abort after 15 seconds so the modal never freezes indefinitely
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000);
    try {
      const token = localStorage.getItem("satya_token");
      const headers = { "Content-Type": "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;

      const res = await fetch(`${API_BASE_URL}/api/otp/send`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          user_id: userId,
          purpose,
          document_id: documentId,
        }),
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      const data = await res.json();
      if (data.success) {
        setOtpId(data.otp_id);
        setMaskedEmail(data.masked_email || "");
      } else {
        setError(data.message || "Failed to send OTP");
      }
    } catch (err) {
      clearTimeout(timeoutId);
      if (err.name === "AbortError") {
        setError(
          "Request timed out. Please check your connection and try again.",
        );
      } else {
        setError("Failed to connect to server. Please try again.");
      }
    } finally {
      setSending(false);
    }
  }, [userId, purpose, documentId]);

  // ── API: Verify OTP ────────────────────────────────────────────────
  const verifyOtp = useCallback(
    async (code) => {
      setLoading(true);
      setError("");
      try {
        const token = localStorage.getItem("satya_token");
        const headers = { "Content-Type": "application/json" };
        if (token) headers.Authorization = `Bearer ${token}`;

        const res = await fetch(`${API_BASE_URL}/api/otp/verify`, {
          method: "POST",
          headers,
          body: JSON.stringify({ otp_id: otpId, otp_code: code }),
        });
        const data = await res.json();
        if (data.success) {
          setSuccess(true);
          clearInterval(timerRef.current);
          setTimeout(() => {
            onVerified();
          }, 1500);
        } else {
          setError(data.message || "Invalid OTP");
          setDigits(["", "", "", "", "", ""]);
          setTimeout(() => inputRefs.current[0]?.focus(), 100);
        }
      } catch (err) {
        setError("Verification failed. Please try again.");
      } finally {
        setLoading(false);
      }
    },
    [otpId, onVerified],
  );

  // ── API: Resend OTP ────────────────────────────────────────────────
  const resendOtp = useCallback(async () => {
    if (!canResend || resendCount >= 3) return;
    setSending(true);
    setError("");
    try {
      const token = localStorage.getItem("satya_token");
      const headers = { "Content-Type": "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;

      const res = await fetch(`${API_BASE_URL}/api/otp/resend`, {
        method: "POST",
        headers,
        body: JSON.stringify({ otp_id: otpId }),
      });
      const data = await res.json();
      if (data.success) {
        setResendCount((prev) => prev + 1);
        setDigits(["", "", "", "", "", ""]);
        setError("");
        setCanResend(false);
        clearTimeout(resendTimerRef.current);
        resendTimerRef.current = setTimeout(() => setCanResend(true), 30000);
        setTimer(300);
      } else {
        setError(data.message || "Failed to resend OTP");
      }
    } catch (err) {
      setError("Failed to resend OTP.");
    } finally {
      setSending(false);
    }
  }, [otpId, canResend, resendCount]);

  // ── Input handlers ─────────────────────────────────────────────────
  const handleChange = (index, value) => {
    if (!/^\d*$/.test(value)) return;
    const newDigits = [...digits];
    newDigits[index] = value.slice(-1);
    setDigits(newDigits);
    setError("");

    if (value && index < 5) {
      inputRefs.current[index + 1]?.focus();
    }

    // Auto-verify when all 6 filled
    const code = newDigits.join("");
    if (code.length === 6 && newDigits.every((d) => d !== "")) {
      verifyOtp(code);
    }
  };

  const handleKeyDown = (index, e) => {
    if (e.key === "Backspace" && !digits[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
  };

  const handlePaste = (e) => {
    e.preventDefault();
    const pasted = e.clipboardData
      .getData("text")
      .replace(/\D/g, "")
      .slice(0, 6);
    if (pasted.length === 6) {
      const newDigits = pasted.split("");
      setDigits(newDigits);
      inputRefs.current[5]?.focus();
      verifyOtp(pasted);
    }
  };

  // ── Format timer ───────────────────────────────────────────────────
  const formatTimer = (s) => {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m}:${sec.toString().padStart(2, "0")}`;
  };

  if (!isOpen) return null;

  // ── Success State ──────────────────────────────────────────────────
  if (success) {
    return (
      <div style={styles.overlay} onClick={onClose}>
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          onClick={(e) => e.stopPropagation()}
          style={styles.card}
        >
          <div style={{ textAlign: "center", padding: "40px 20px" }}>
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ type: "spring", stiffness: 300, damping: 20 }}
            >
              <div
                style={{
                  width: 80,
                  height: 80,
                  borderRadius: "50%",
                  background: "#dcfce7",
                  display: "grid",
                  placeItems: "center",
                  margin: "0 auto 20px",
                }}
              >
                <CheckCircle2 size={40} color="#16a34a" />
              </div>
            </motion.div>
            <h2
              style={{
                margin: "0 0 8px",
                fontSize: 24,
                fontWeight: 800,
                color: "#166534",
              }}
            >
              Verified Successfully
            </h2>
            <p style={{ margin: 0, color: "#64748b", fontSize: 14 }}>
              Your identity has been confirmed.
            </p>
          </div>
        </motion.div>
      </div>
    );
  }

  // ── Main OTP UI ────────────────────────────────────────────────────
  return (
    <div style={styles.overlay} onClick={onClose}>
      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 20, scale: 0.97 }}
        onClick={(e) => e.stopPropagation()}
        style={styles.card}
      >
        {/* Header */}
        <div style={{ textAlign: "center", marginBottom: 24 }}>
          <div
            style={{
              width: 52,
              height: 52,
              borderRadius: 16,
              background: "#dbeafe",
              display: "grid",
              placeItems: "center",
              margin: "0 auto 16px",
            }}
          >
            <Shield size={26} color="#2563eb" />
          </div>
          <h2
            style={{
              margin: "0 0 6px",
              fontSize: 22,
              fontWeight: 800,
              color: "#0f172a",
            }}
          >
            OTP Verification
          </h2>
          <p style={{ margin: 0, fontSize: 14, color: "#64748b" }}>
            {sending
              ? "Sending verification code..."
              : maskedEmail
                ? `Enter the 6-digit code sent to ${maskedEmail}`
                : "Preparing to send verification code..."}
          </p>
        </div>

        {/* Loading while sending */}
        {sending && (
          <div style={{ textAlign: "center", padding: "20px 0" }}>
            <Loader2
              size={32}
              color="#2563eb"
              style={{ animation: "spin 1s linear infinite" }}
            />
            <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
            <p style={{ marginTop: 12, color: "#64748b", fontSize: 14 }}>
              Sending verification code...
            </p>
          </div>
        )}

        {/* Error when send failed and not yet started */}
        {!sending && !otpId && error && (
          <div style={{ textAlign: "center", padding: "20px 0" }}>
            <XCircle size={36} color="#dc2626" style={{ marginBottom: 12 }} />
            <p
              style={{
                color: "#dc2626",
                fontSize: 14,
                fontWeight: 600,
                margin: "0 0 16px",
              }}
            >
              {error}
            </p>
            <button
              onClick={() => {
                setError("");
                sendOtp();
              }}
              style={{
                background: "#2563eb",
                color: "#fff",
                border: "none",
                borderRadius: 8,
                padding: "10px 24px",
                fontWeight: 700,
                fontSize: 14,
                cursor: "pointer",
              }}
            >
              Retry
            </button>
          </div>
        )}

        {/* OTP Inputs */}
        {!sending && otpId && (
          <>
            <div
              style={{
                display: "flex",
                justifyContent: "center",
                gap: 10,
                marginBottom: 16,
              }}
            >
              {digits.map((digit, i) => (
                <input
                  key={i}
                  ref={(el) => (inputRefs.current[i] = el)}
                  type="text"
                  inputMode="numeric"
                  maxLength={1}
                  value={digit}
                  onChange={(e) => handleChange(i, e.target.value)}
                  onKeyDown={(e) => handleKeyDown(i, e)}
                  onPaste={i === 0 ? handlePaste : undefined}
                  disabled={loading}
                  autoFocus={i === 0}
                  style={{
                    width: 48,
                    height: 56,
                    fontSize: 24,
                    fontWeight: 700,
                    textAlign: "center",
                    border: `2px solid ${error ? "#fca5a5" : "#e2e8f0"}`,
                    borderRadius: 12,
                    outline: "none",
                    background: "#f8fafc",
                    color: "#0f172a",
                    transition: "border-color 0.2s",
                  }}
                  onFocus={(e) => (e.target.style.borderColor = "#2563eb")}
                  onBlur={(e) =>
                    (e.target.style.borderColor = error ? "#fca5a5" : "#e2e8f0")
                  }
                />
              ))}
            </div>

            {/* Error */}
            {error && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  justifyContent: "center",
                  color: "#dc2626",
                  fontSize: 13,
                  fontWeight: 600,
                  marginBottom: 12,
                }}
              >
                <XCircle size={16} /> {error}
              </div>
            )}

            {/* Timer + Resend */}
            <div style={{ textAlign: "center", marginBottom: 20 }}>
              {timer > 0 ? (
                <span style={{ color: "#64748b", fontSize: 14 }}>
                  Code expires in{" "}
                  <strong style={{ color: timer < 60 ? "#dc2626" : "#2563eb" }}>
                    {formatTimer(timer)}
                  </strong>
                </span>
              ) : (
                <span
                  style={{ color: "#dc2626", fontSize: 14, fontWeight: 600 }}
                >
                  Code expired. Please resend.
                </span>
              )}
            </div>

            {/* Resend Button */}
            <div style={{ textAlign: "center", marginBottom: 20 }}>
              <button
                onClick={resendOtp}
                disabled={!canResend || resendCount >= 3 || sending}
                style={{
                  background: "none",
                  border: "none",
                  cursor: canResend && resendCount < 3 ? "pointer" : "default",
                  color: canResend && resendCount < 3 ? "#2563eb" : "#94a3b8",
                  fontSize: 13,
                  fontWeight: 600,
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                <RefreshCw size={14} />
                {resendCount >= 3
                  ? "No resends remaining"
                  : canResend
                    ? `Resend Code (${3 - resendCount} left)`
                    : "Resend available shortly..."}
              </button>
            </div>

            {/* Loading indicator during verify */}
            {loading && (
              <div style={{ textAlign: "center", marginBottom: 16 }}>
                <Loader2
                  size={24}
                  color="#2563eb"
                  style={{ animation: "spin 1s linear infinite" }}
                />
              </div>
            )}

            {/* Action Buttons */}
            <div style={{ display: "flex", justifyContent: "center", gap: 12 }}>
              <button
                onClick={onClose}
                style={{
                  padding: "10px 20px",
                  borderRadius: 8,
                  border: "1px solid #e2e8f0",
                  background: "#ffffff",
                  color: "#475569",
                  fontWeight: 600,
                  cursor: "pointer",
                  fontSize: 14,
                }}
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  const code = digits.join("");
                  if (code.length === 6) verifyOtp(code);
                }}
                disabled={digits.some((d) => d === "") || loading}
                style={{
                  padding: "10px 24px",
                  borderRadius: 8,
                  border: "none",
                  background:
                    digits.every((d) => d !== "") && !loading
                      ? "#2563eb"
                      : "#94a3b8",
                  color: "#ffffff",
                  fontWeight: 600,
                  cursor:
                    digits.every((d) => d !== "") && !loading
                      ? "pointer"
                      : "default",
                  fontSize: 14,
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                }}
              >
                <Shield size={16} /> Verify OTP
              </button>
            </div>
          </>
        )}
      </motion.div>
    </div>
  );
}

const styles = {
  overlay: {
    position: "fixed",
    inset: 0,
    background: "rgba(15,23,42,0.4)",
    backdropFilter: "blur(8px)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 16,
    zIndex: 9999,
  },
  card: {
    background: "#ffffff",
    borderRadius: 24,
    padding: 32,
    boxShadow: "0 25px 50px -12px rgba(15,23,42,0.25)",
    width: 440,
    maxWidth: "calc(100vw - 32px)",
  },
};

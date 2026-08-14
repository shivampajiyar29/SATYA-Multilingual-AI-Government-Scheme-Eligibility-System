from flask import Flask, jsonify
from flask_cors import CORS
from flask_mail import Mail
from database import init_db
from routes.auth import auth_bp
from routes.schemes import schemes_bp
from routes.chatbot import chatbot_bp
from routes.verification import verification_bp
from routes.scraper_status import scraper_bp
from routes.admin import admin_bp
from routes.vault_routes import vault_bp
from routes.eligibility_routes import eligibility_bp
from routes.otp_routes import otp_bp
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# Flask-Mail Configuration
app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "smtp.gmail.com")
app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", 587))
app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS", "True").lower() in ("true", "1", "yes")
app.config["MAIL_USE_SSL"] = os.getenv("MAIL_USE_SSL", "False").lower() in ("true", "1", "yes")
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME", "")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD", "")
app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER", "")

# Log loaded mail config (excluding password)
print("[MAIL CONFIG] SERVER:", app.config["MAIL_SERVER"])
print("[MAIL CONFIG] PORT:", app.config["MAIL_PORT"])
print("[MAIL CONFIG] USE_TLS:", app.config["MAIL_USE_TLS"])
print("[MAIL CONFIG] USERNAME:", app.config["MAIL_USERNAME"])
print("[MAIL CONFIG] DEFAULT_SENDER:", app.config["MAIL_DEFAULT_SENDER"])
mail = Mail(app)

# Initialize Database
try:
    init_db(app)
    print("MongoDB Connected Successfully")
except Exception as e:
    print(f"Failed to connect to MongoDB: {e}")

# Register Blueprints
app.register_blueprint(auth_bp, url_prefix="/api/auth")
app.register_blueprint(schemes_bp, url_prefix="/api/schemes")
app.register_blueprint(chatbot_bp, url_prefix="/api/chatbot")
app.register_blueprint(verification_bp, url_prefix="/api/verify")
app.register_blueprint(scraper_bp, url_prefix="/api/scraper")
app.register_blueprint(admin_bp, url_prefix="/api/admin")
app.register_blueprint(vault_bp, url_prefix="/api/vault")
app.register_blueprint(eligibility_bp, url_prefix="/api/eligibility")
app.register_blueprint(otp_bp, url_prefix="/api/otp")

@app.route("/")
def home():
    return jsonify({"message": "Welcome to SATYA Backend API!"})

if __name__ == "__main__":
    app.run(debug=True, port=5000)

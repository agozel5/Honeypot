import os
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-key")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///honeypot.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    DASHBOARD_USERNAME = os.getenv("DASHBOARD_USERNAME")
    DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD")

    ENABLE_IP_GEO = os.getenv("ENABLE_IP_GEO", "false").lower() == "true"
    GEO_PROVIDER = os.getenv("GEO_PROVIDER", "ipapi")
    GEO_IPINFO_TOKEN = os.getenv("GEO_IPINFO_TOKEN", "")

    # QR token eklendi
    QR_SECRET_TOKEN = os.getenv("QR_SECRET_TOKEN", "bu_cok_gizli_token123")

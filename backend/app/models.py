from datetime import datetime, timezone
from sqlalchemy import Column, Integer, Float, String, Boolean, Text, DateTime, LargeBinary
from app.database import Base


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="Display name")
    email = Column(String(255), nullable=False, unique=True, comment="Windsurf login email")
    encrypted_password = Column(Text, nullable=True, comment="Fernet-encrypted password for web login")
    api_key = Column(String(512), nullable=True, comment="Windsurf API Key (sk-ws-...)")
    firebase_id_token = Column(Text, nullable=True, comment="Firebase ID token captured from web login")
    auth_snapshot = Column(LargeBinary, nullable=True, comment="Serialized auth entries from state.vscdb")
    is_active = Column(Boolean, default=False, nullable=False, comment="Currently active account")
    plan_type = Column(String(50), nullable=True, comment="Plan type: Free trial, Pro, etc.")
    display_name = Column(String(100), nullable=True, comment="Name shown on Windsurf profile")
    daily_quota_pct = Column(Float, nullable=True, comment="Daily quota remaining percentage 0-100")
    weekly_quota_pct = Column(Float, nullable=True, comment="Weekly quota remaining percentage 0-100")
    extra_balance = Column(String(20), nullable=True, comment="Extra usage balance e.g. $0.00")
    plan_expiry = Column(String(50), nullable=True, comment="Plan expiry date text e.g. 'Mar 28, 2026'")
    quota_total = Column(Integer, nullable=True, comment="Total quota credits (legacy)")
    quota_used = Column(Integer, nullable=True, comment="Used quota credits (legacy)")
    quota_updated_at = Column(DateTime, nullable=True, comment="Last quota refresh time")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

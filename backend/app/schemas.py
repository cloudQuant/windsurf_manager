from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr


class AccountCreate(BaseModel):
    name: str
    email: str
    password: Optional[str] = None
    api_key: Optional[str] = None


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    api_key: Optional[str] = None


class AccountOut(BaseModel):
    id: int
    name: str
    email: str
    api_key: Optional[str] = None
    is_active: bool
    has_auth_snapshot: bool
    plan_type: Optional[str] = None
    display_name: Optional[str] = None
    daily_quota_pct: Optional[float] = None
    weekly_quota_pct: Optional[float] = None
    extra_balance: Optional[str] = None
    plan_expiry: Optional[str] = None
    quota_total: Optional[int] = None
    quota_used: Optional[int] = None
    quota_updated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class QuotaOut(BaseModel):
    account_id: int
    name: str
    daily_quota_pct: Optional[float] = None
    weekly_quota_pct: Optional[float] = None
    extra_balance: Optional[str] = None
    quota_total: Optional[int] = None
    quota_used: Optional[int] = None
    quota_remaining: Optional[int] = None
    quota_updated_at: Optional[datetime] = None


class ImportResult(BaseModel):
    success: bool
    message: str
    account: Optional[AccountOut] = None


class ActivateResult(BaseModel):
    success: bool
    message: str
    ide_switched: bool
    web_logged_in: bool

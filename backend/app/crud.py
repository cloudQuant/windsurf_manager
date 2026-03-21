import os
from typing import Optional, List
from sqlalchemy.orm import Session
from cryptography.fernet import Fernet

from app.models import Account

FERNET_KEY = os.environ.get("WINDSURF_MANAGER_KEY", None)
KEY_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "fernet.key")


def _get_fernet() -> Fernet:
    global FERNET_KEY
    if FERNET_KEY is None:
        os.makedirs(os.path.dirname(KEY_FILE_PATH), exist_ok=True)
        if os.path.exists(KEY_FILE_PATH):
            with open(KEY_FILE_PATH, "rb") as f:
                FERNET_KEY = f.read().decode().strip()
        else:
            FERNET_KEY = Fernet.generate_key().decode()
            with open(KEY_FILE_PATH, "wb") as f:
                f.write(FERNET_KEY.encode())
        os.environ["WINDSURF_MANAGER_KEY"] = FERNET_KEY
    return Fernet(FERNET_KEY if isinstance(FERNET_KEY, bytes) else FERNET_KEY.encode())


def encrypt_password(password: str) -> str:
    return _get_fernet().encrypt(password.encode()).decode()


def decrypt_password(encrypted: str) -> str:
    return _get_fernet().decrypt(encrypted.encode()).decode()


def get_accounts(db: Session) -> List[Account]:
    return db.query(Account).order_by(Account.id).all()


def get_account(db: Session, account_id: int) -> Optional[Account]:
    return db.query(Account).filter(Account.id == account_id).first()


def get_account_by_email(db: Session, email: str) -> Optional[Account]:
    return db.query(Account).filter(Account.email == email).first()


def get_active_account(db: Session) -> Optional[Account]:
    return db.query(Account).filter(Account.is_active == True).first()


def create_account(db: Session, name: str, email: str,
                   password: Optional[str] = None,
                   api_key: Optional[str] = None,
                   firebase_id_token: Optional[str] = None,
                   auth_snapshot: Optional[bytes] = None,
                   is_active: bool = False) -> Account:
    account = Account(
        name=name,
        email=email,
        encrypted_password=encrypt_password(password) if password else None,
        api_key=api_key,
        firebase_id_token=firebase_id_token,
        auth_snapshot=auth_snapshot,
        is_active=is_active,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def update_account(db: Session, account_id: int,
                   name: Optional[str] = None,
                   email: Optional[str] = None,
                   password: Optional[str] = None,
                   api_key: Optional[str] = None,
                   firebase_id_token: Optional[str] = None,
                   auth_snapshot: Optional[bytes] = None) -> Optional[Account]:
    account = get_account(db, account_id)
    if not account:
        return None
    if name is not None:
        account.name = name
    if email is not None:
        account.email = email
    if password is not None:
        account.encrypted_password = encrypt_password(password)
    if api_key is not None:
        account.api_key = api_key
    if firebase_id_token is not None:
        account.firebase_id_token = firebase_id_token
    if auth_snapshot is not None:
        account.auth_snapshot = auth_snapshot
    db.commit()
    db.refresh(account)
    return account


def delete_account(db: Session, account_id: int) -> bool:
    account = get_account(db, account_id)
    if not account:
        return False
    db.delete(account)
    db.commit()
    return True


def set_active_account(db: Session, account_id: int) -> Optional[Account]:
    db.query(Account).filter(Account.is_active == True).update({"is_active": False})
    account = get_account(db, account_id)
    if not account:
        return None
    account.is_active = True
    db.commit()
    db.refresh(account)
    return account


def update_quota(db: Session, account_id: int,
                 quota_total: Optional[int], quota_used: Optional[int]) -> Optional[Account]:
    from datetime import datetime, timezone
    account = get_account(db, account_id)
    if not account:
        return None
    account.quota_total = quota_total
    account.quota_used = quota_used
    account.quota_updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(account)
    return account


def update_account_profile(db: Session, account_id: int,
                           display_name: Optional[str] = None,
                           plan_type: Optional[str] = None,
                           daily_quota_pct: Optional[float] = None,
                           weekly_quota_pct: Optional[float] = None,
                           extra_balance: Optional[str] = None,
                           plan_expiry: Optional[str] = None,
                           api_key: Optional[str] = None) -> Optional[Account]:
    from datetime import datetime, timezone
    account = get_account(db, account_id)
    if not account:
        return None
    if display_name is not None:
        account.display_name = display_name
    if plan_type is not None:
        account.plan_type = plan_type
    if daily_quota_pct is not None:
        account.daily_quota_pct = daily_quota_pct
    if weekly_quota_pct is not None:
        account.weekly_quota_pct = weekly_quota_pct
    if extra_balance is not None:
        account.extra_balance = extra_balance
    if plan_expiry is not None:
        account.plan_expiry = plan_expiry
    if api_key is not None:
        account.api_key = api_key
    account.quota_updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(account)
    return account

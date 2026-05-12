from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app import crud, schemas
from app.services import account_service

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def _account_to_out(account) -> schemas.AccountOut:
    return schemas.AccountOut(
        id=account.id,
        name=account.name,
        email=account.email,
        api_key=account.api_key,
        is_active=account.is_active,
        has_auth_snapshot=account.auth_snapshot is not None and len(account.auth_snapshot) > 0,
        plan_type=account.plan_type,
        display_name=account.display_name,
        daily_quota_pct=account.daily_quota_pct,
        weekly_quota_pct=account.weekly_quota_pct,
        extra_balance=account.extra_balance,
        plan_expiry=account.plan_expiry,
        quota_total=account.quota_total,
        quota_used=account.quota_used,
        quota_updated_at=account.quota_updated_at,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


@router.get("", response_model=List[schemas.AccountOut])
def list_accounts(db: Session = Depends(get_db)):
    accounts = crud.get_accounts(db)
    return [_account_to_out(a) for a in accounts]


@router.post("", response_model=schemas.AccountOut, status_code=201)
def create_account(data: schemas.AccountCreate, db: Session = Depends(get_db)):
    existing = crud.get_account_by_email(db, data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    account = crud.create_account(
        db, name=data.name, email=data.email,
        password=data.password, api_key=data.api_key,
    )
    return _account_to_out(account)


@router.put("/{account_id}", response_model=schemas.AccountOut)
def update_account(account_id: int, data: schemas.AccountUpdate, db: Session = Depends(get_db)):
    account = crud.update_account(
        db, account_id,
        name=data.name, email=data.email,
        password=data.password, api_key=data.api_key,
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return _account_to_out(account)


@router.delete("/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    result = account_service.delete_account(db, account_id)
    if not result["success"]:
        raise HTTPException(status_code=404, detail="Account not found")
    return result


@router.post("/{account_id}/activate", response_model=schemas.ActivateResult)
async def activate_account(account_id: int, db: Session = Depends(get_db)):
    result = await account_service.activate_account(db, account_id)
    return schemas.ActivateResult(**result)


@router.get("/{account_id}/quota", response_model=schemas.QuotaOut)
async def get_quota(account_id: int, db: Session = Depends(get_db)):
    result = await account_service.refresh_quota(db, account_id)
    account = crud.get_account(db, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    if result.get("success"):
        remaining = None
        quota_total = result.get("quota_total")
        quota_used = result.get("quota_used")
        if quota_total is not None and quota_used is not None:
            remaining = quota_total - quota_used
        return schemas.QuotaOut(
            account_id=account.id,
            name=result.get("display_name") or account.name,
            daily_quota_pct=result.get("daily_quota_pct"),
            weekly_quota_pct=result.get("weekly_quota_pct"),
            extra_balance=result.get("extra_balance"),
            quota_total=quota_total,
            quota_used=quota_used,
            quota_remaining=remaining,
            quota_updated_at=account.quota_updated_at,
        )
    if not account.encrypted_password:
        raise HTTPException(status_code=400, detail="No password stored. Please save the account password first.")
    raise HTTPException(status_code=500, detail=result.get("message", "Quota refresh failed"))


@router.post("/refresh-all-quotas")
async def refresh_all_quotas(db: Session = Depends(get_db)):
    return await account_service.refresh_all_quotas(db)


@router.post("/refresh-all-status")
async def refresh_all_status(db: Session = Depends(get_db)):
    result = await account_service.refresh_all_status(db)
    return result


@router.put("/{account_id}/profile")
def update_profile(account_id: int, data: dict, db: Session = Depends(get_db)):
    account = crud.update_account_profile(
        db, account_id,
        display_name=data.get("display_name"),
        plan_type=data.get("plan_type"),
        daily_quota_pct=data.get("daily_quota_pct"),
        weekly_quota_pct=data.get("weekly_quota_pct"),
        extra_balance=data.get("extra_balance"),
        api_key=data.get("api_key"),
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return _account_to_out(account)

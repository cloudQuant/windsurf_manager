"""
Account service: orchestrates import, activate (local + web), quota refresh.
"""
import os
import re
from pathlib import Path
from typing import Dict, Optional

from dotenv import dotenv_values, unset_key
from sqlalchemy.orm import Session

from app import crud
from app.services import windsurf_local, windsurf_web


_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
_ENV_ACCOUNT_PATTERN = re.compile(r"WINDSURF_ACCOUNT_\d+$")


def _split_env_account(value: str) -> tuple[Optional[str], Optional[str]]:
    parts = re.split(r"\s{2,}", value.strip(), maxsplit=1)
    if len(parts) != 2:
        return None, None
    return parts[0].strip(), parts[1].strip()


def _remove_env_accounts(email: str) -> int:
    target_email = (email or "").strip().lower()
    if not target_email or not _ENV_PATH.exists():
        return 0

    removed = 0
    for key, value in dotenv_values(_ENV_PATH).items():
        if key is None or value is None or not _ENV_ACCOUNT_PATTERN.match(key):
            continue
        parsed_email, _ = _split_env_account(value)
        if not parsed_email or parsed_email.lower() != target_email:
            continue
        unset_key(str(_ENV_PATH), key)
        os.environ.pop(key, None)
        removed += 1

    return removed


def import_current(db: Session) -> Dict:
    """Import the currently logged-in Windsurf account."""
    result = windsurf_local.import_current_account()
    if not result["success"]:
        return result

    imported_email = result.get("email") or (result.get("name", "") + "@imported")
    existing = crud.get_account_by_email(db, imported_email)
    if existing:
        crud.update_account(
            db, existing.id,
            name=result.get("name") or existing.name,
            email=imported_email,
            api_key=result.get("api_key"),
            auth_snapshot=result.get("auth_snapshot"),
        )
        crud.update_account_profile(
            db, existing.id,
            display_name=result.get("name"),
            api_key=result.get("api_key"),
        )
        return {
            "success": True,
            "message": f"Updated existing account: {existing.name}",
            "account_id": existing.id,
        }

    account = crud.create_account(
        db,
        name=result["name"],
        email=imported_email,
        api_key=result.get("api_key"),
        auth_snapshot=result.get("auth_snapshot"),
        is_active=True,
    )
    crud.update_account_profile(
        db, account.id,
        display_name=result.get("name"),
        api_key=result.get("api_key"),
    )
    return {
        "success": True,
        "message": result["message"],
        "account_id": account.id,
    }


def delete_account(db: Session, account_id: int) -> Dict:
    account = crud.get_account(db, account_id)
    if not account:
        return {"success": False, "message": "Account not found", "env_entries_removed": 0}

    env_entries_removed = _remove_env_accounts(account.email)
    if not crud.delete_account(db, account_id):
        return {"success": False, "message": "Account not found", "env_entries_removed": env_entries_removed}

    entry_label = "entry" if env_entries_removed == 1 else "entries"
    message = "Account deleted"
    if env_entries_removed:
        message = f"Account deleted and removed {env_entries_removed} .env {entry_label}"

    return {
        "success": True,
        "message": message,
        "env_entries_removed": env_entries_removed,
    }


def bind_current_local_account(db: Session, account_id: int) -> Dict:
    """Bind the currently logged-in local Windsurf auth snapshot to a target account."""
    account = crud.get_account(db, account_id)
    if not account:
        return {"success": False, "message": "Account not found"}

    result = windsurf_local.import_current_account()
    if not result["success"]:
        return result

    current_email = (result.get("email") or "").strip().lower()
    target_email = (account.email or "").strip().lower()

    if current_email and target_email and current_email != target_email:
        return {
            "success": False,
            "message": f"Current local Windsurf account is {result.get('email')}, but target account is {account.email}. Please log into the target account in the local Windsurf app first, then bind again.",
            "account_id": account.id,
        }

    crud.update_account(
        db,
        account.id,
        name=account.name,
        email=account.email,
        api_key=result.get("api_key") or account.api_key,
        auth_snapshot=result.get("auth_snapshot"),
    )
    crud.update_account_profile(
        db,
        account.id,
        display_name=result.get("name") or account.display_name,
        api_key=result.get("api_key") or account.api_key,
    )

    return {
        "success": True,
        "message": f"Bound current local Windsurf login to {account.email}",
        "account_id": account.id,
    }


def auto_bind_local_account(db: Session, account_id: int, timeout_seconds: int = 180) -> Dict:
    account = crud.get_account(db, account_id)
    if not account:
        return {"success": False, "message": "Account not found"}

    prepared = windsurf_local.prepare_local_login()
    if not prepared.get("success"):
        return prepared

    detected = windsurf_local.wait_for_local_account(account.email, timeout_seconds=timeout_seconds)
    if not detected.get("success"):
        return {
            "success": False,
            "message": prepared.get("message", "Prepared local login") + " " + detected.get("message", "Failed to detect local login"),
            "account_id": account.id,
        }

    crud.update_account(
        db,
        account.id,
        name=account.name,
        email=account.email,
        api_key=detected.get("api_key") or account.api_key,
        auth_snapshot=detected.get("auth_snapshot"),
    )
    crud.update_account_profile(
        db,
        account.id,
        display_name=detected.get("name") or account.display_name,
        api_key=detected.get("api_key") or account.api_key,
    )

    return {
        "success": True,
        "message": prepared.get("message", "Prepared local login") + f" Auto-bound local Windsurf login to {account.email}",
        "account_id": account.id,
    }


def _resolve_local_template_snapshot(db: Session) -> tuple[Optional[bytes], str]:
    current = windsurf_local.import_current_account()
    if current.get("success") and current.get("auth_snapshot"):
        return current["auth_snapshot"], "current local Windsurf session"

    for account in crud.get_accounts(db):
        if account.auth_snapshot:
            return account.auth_snapshot, f"stored snapshot from {account.email}"

    return None, ""


async def bootstrap_all_local_snapshots(db: Session) -> Dict:
    template_snapshot, template_source = _resolve_local_template_snapshot(db)
    if not template_snapshot:
        return {
            "success": False,
            "message": "No local Windsurf auth template is available. Please ensure Windsurf is logged in once locally or bind at least one account snapshot first.",
            "results": [],
        }

    results = []
    success_count = 0
    for account in crud.get_accounts(db):
        item = {
            "account_id": account.id,
            "email": account.email,
            "name": account.name,
            "success": False,
            "message": "",
        }

        if not account.encrypted_password:
            item["message"] = "No password stored"
            results.append(item)
            continue

        try:
            password = crud.decrypt_password(account.encrypted_password)
        except Exception:
            item["message"] = "Stored password could not be decrypted"
            results.append(item)
            continue

        sync_result = await windsurf_web.sync_account_state(account.email, password)
        if not sync_result.get("success"):
            item["message"] = sync_result.get("message", "Web sync failed")
            results.append(item)
            continue

        api_key = sync_result.get("api_key")
        auth_snapshot = None
        snapshot_message = ""
        if api_key:
            snapshot_result = windsurf_local.build_auth_snapshot_from_template(
                template_snapshot,
                api_key,
                display_name=sync_result.get("display_name") or account.display_name or account.name,
                email=account.email,
                api_server_url=sync_result.get("api_server_url"),
            )
            if snapshot_result.get("success"):
                auth_snapshot = snapshot_result.get("auth_snapshot")
                snapshot_message = snapshot_result.get("message", "")
            else:
                snapshot_message = snapshot_result.get("message", "")

        crud.update_account(
            db,
            account.id,
            name=account.name,
            email=account.email,
            api_key=api_key or account.api_key,
            firebase_id_token=sync_result.get("firebase_id_token") or account.firebase_id_token,
            auth_snapshot=auth_snapshot or account.auth_snapshot,
        )
        crud.update_account_profile(
            db,
            account.id,
            display_name=sync_result.get("display_name") or account.display_name,
            plan_type=sync_result.get("plan_type"),
            daily_quota_pct=sync_result.get("daily_quota_pct"),
            weekly_quota_pct=sync_result.get("weekly_quota_pct"),
            extra_balance=sync_result.get("extra_balance"),
            api_key=api_key or account.api_key,
        )

        item["success"] = bool(api_key and auth_snapshot)
        item["message"] = " | ".join(
            part for part in [
                sync_result.get("message"),
                sync_result.get("register_message"),
                snapshot_message if api_key else "No apiKey extracted",
            ]
            if part
        )
        if item["success"]:
            success_count += 1
        results.append(item)

    return {
        "success": success_count > 0,
        "message": f"Bootstrapped {success_count}/{len(results)} accounts using template from {template_source}",
        "results": results,
    }


async def activate_account(db: Session, account_id: int) -> Dict:
    """Log into the target Windsurf web account in the default browser."""
    account = crud.get_account(db, account_id)
    if not account:
        return {"success": False, "message": "Account not found", "ide_switched": False, "web_logged_in": False}

    ide_switched = False
    web_logged_in = False
    local_msg = "Skipped local IDE switch"

    if not account.encrypted_password:
        return {
            "success": False,
            "message": "IDE: Skipped local IDE switch | Web: No password stored, cannot log into Windsurf web in the default browser",
            "ide_switched": False,
            "web_logged_in": False,
        }

    try:
        password = crud.decrypt_password(account.encrypted_password)
    except Exception:
        return {
            "success": False,
            "message": "IDE: Skipped local IDE switch | Web: Stored password could not be decrypted",
            "ide_switched": False,
            "web_logged_in": False,
        }

    web_result = windsurf_web.login_in_default_browser(account.email, password)
    web_logged_in = web_result.get("success", False)
    web_msg = web_result.get("message", "Default browser login failed")

    if web_logged_in:
        crud.set_active_account(db, account_id)

    return {
        "success": web_logged_in,
        "message": f"IDE: {local_msg} | Web: {web_msg}",
        "ide_switched": ide_switched,
        "web_logged_in": web_logged_in,
    }


async def refresh_quota(db: Session, account_id: int) -> Dict:
    """Refresh quota for a single account."""
    account = crud.get_account(db, account_id)
    if not account:
        return {"success": False, "message": "Account not found"}

    if account.encrypted_password:
        try:
            password = crud.decrypt_password(account.encrypted_password)
        except Exception:
            return {"success": False, "message": "Stored password could not be decrypted. Please re-save the account password."}
        result = await windsurf_web.scrape_quota(account.email, password)
        if result["success"]:
            crud.update_account_profile(
                db, account_id,
                display_name=result.get("display_name"),
                plan_type=result.get("plan_type"),
                daily_quota_pct=result.get("daily_quota_pct"),
                weekly_quota_pct=result.get("weekly_quota_pct"),
                extra_balance=result.get("extra_balance"),
                plan_expiry=result.get("plan_expiry"),
                api_key=result.get("api_key"),
            )
            crud.update_account(
                db, account_id,
                firebase_id_token=result.get("firebase_id_token") or account.firebase_id_token,
            )
            crud.update_quota(db, account_id, result.get("quota_total"), result.get("quota_used"))
            return result
        return result

    return {"success": False, "message": "No password stored, cannot query quota"}


async def refresh_all_quotas(db: Session) -> Dict:
    """Refresh quota for all accounts."""
    accounts = crud.get_accounts(db)
    results = []
    for acc in accounts:
        r = await refresh_quota(db, acc.id)
        results.append({"account_id": acc.id, "name": acc.name, **r})
    return {"success": True, "results": results}


async def refresh_all_status(db: Session) -> Dict:
    """Refresh status (quota + expiry + plan) for all accounts using Playwright headless."""
    accounts = crud.get_accounts(db)
    results = []
    success_count = 0
    for acc in accounts:
        item = {"account_id": acc.id, "email": acc.email, "success": False, "message": ""}
        if not acc.encrypted_password:
            item["message"] = "No password stored"
            results.append(item)
            continue
        try:
            password = crud.decrypt_password(acc.encrypted_password)
        except Exception:
            item["message"] = "Password decryption failed"
            results.append(item)
            continue
        try:
            result = await windsurf_web.scrape_quota(acc.email, password)
            if result.get("success"):
                crud.update_account_profile(
                    db, acc.id,
                    display_name=result.get("display_name"),
                    plan_type=result.get("plan_type"),
                    daily_quota_pct=result.get("daily_quota_pct"),
                    weekly_quota_pct=result.get("weekly_quota_pct"),
                    extra_balance=result.get("extra_balance"),
                    plan_expiry=result.get("plan_expiry"),
                    api_key=result.get("api_key"),
                )
                crud.update_account(
                    db, acc.id,
                    firebase_id_token=result.get("firebase_id_token") or acc.firebase_id_token,
                )
                crud.update_quota(db, acc.id, result.get("quota_total"), result.get("quota_used"))
                item["success"] = True
                item["message"] = "Status refreshed"
                success_count += 1
            else:
                item["message"] = result.get("message", "Scrape failed")
        except Exception as e:
            item["message"] = f"Error: {e}"
        results.append(item)
    return {
        "success": success_count > 0,
        "success_count": success_count,
        "total_count": len(accounts),
        "message": f"Refreshed {success_count}/{len(accounts)} accounts",
        "results": results,
    }

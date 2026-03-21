"""
Windsurf local IDE auth management.
Reads/writes auth entries in state.vscdb for account switching.
"""
import base64
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import time
import urllib.parse
from typing import Dict, Optional, Tuple

STATE_VSCDB_PATH = os.path.expanduser(
    "~/Library/Application Support/Windsurf/User/globalStorage/state.vscdb"
)

AUTH_KEYS_PATTERNS = [
    "windsurfAuthStatus",
    "windsurf_auth-",
    "codeium.windsurf",
    "codeium.windsurf-windsurf_auth",
    "jg.windsurf-free",
    "windsurf.settings.cachedPlanInfo",
    "windsurf.pendingApiKeyMigration",
]

SECRET_KEYS_PATTERNS = [
    'secret://{"extensionId":"codeium.windsurf","key":"windsurf_auth.sessions"}',
    'secret://{"extensionId":"codeium.windsurf","key":"windsurf_auth.apiServerUrl"}',
]

SESSION_SECRET_KEY = 'secret://{"extensionId":"codeium.windsurf","key":"windsurf_auth.sessions"}'
API_SERVER_SECRET_KEY = 'secret://{"extensionId":"codeium.windsurf","key":"windsurf_auth.apiServerUrl"}'
PENDING_API_KEY_MIGRATION_KEY = "windsurf.pendingApiKeyMigration"
AUTH_LOGIN_COMMAND_TITLE = "Windsurf: Log in"
AUTH_TOKEN_COMMAND_TITLE = "Windsurf: Provide Auth Token (Backup Login)"
AUTH_CALLBACK_URI_PREFIX = "windsurf://codeium.windsurf"
WINDSURF_BUNDLE_ID = "com.exafunction.windsurf"

logger = logging.getLogger(__name__)


def _get_all_auth_keys(conn: sqlite3.Connection) -> Dict[str, bytes]:
    """Read all auth-related key-value pairs from state.vscdb."""
    cursor = conn.cursor()
    results = {}

    for pattern in AUTH_KEYS_PATTERNS:
        cursor.execute(
            "SELECT key, value FROM ItemTable WHERE key LIKE ?",
            (f"%{pattern}%",)
        )
        for key, value in cursor.fetchall():
            results[key] = value if isinstance(value, bytes) else (value.encode() if value else b"")

    for key in SECRET_KEYS_PATTERNS:
        cursor.execute("SELECT key, value FROM ItemTable WHERE key = ?", (key,))
        row = cursor.fetchone()
        if row:
            results[row[0]] = row[1] if isinstance(row[1], bytes) else (row[1].encode() if row[1] else b"")

    return results


def _parse_auth_status(raw: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract apiKey and user name from windsurfAuthStatus JSON."""
    try:
        data = json.loads(raw)
        api_key = data.get("apiKey")
        return api_key, data.get("userStatusProtoBinaryBase64")
    except (json.JSONDecodeError, TypeError):
        return None, None


def _extract_user_info_from_status_proto(status_b64: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Best-effort extraction of display name and email from protobuf-like base64 payload."""
    if not status_b64:
        return None, None
    try:
        raw = base64.b64decode(status_b64)
    except Exception:
        return None, None

    email_match = re.search(rb'(?<![A-Za-z0-9._%+-])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![A-Za-z])', raw)
    email = email_match.group(1).decode("utf-8", errors="ignore") if email_match else None

    chunks = [
        chunk.decode("utf-8", errors="ignore").strip()
        for chunk in re.split(rb'[^\x20-\x7E]+', raw)
        if len(chunk) >= 3
    ]
    name = None
    for chunk in chunks:
        if email and email in chunk:
            continue
        if chunk.startswith("sk-ws-"):
            continue
        if "MODEL_" in chunk:
            continue
        if re.fullmatch(r'[0-9a-fA-F-]{24,}', chunk):
            continue
        if any(c.isalpha() for c in chunk):
            name = chunk
            break

    return name, email


def _find_user_name(auth_keys: Dict[str, bytes]) -> Optional[str]:
    """Find the user name from windsurf_auth-{name} keys."""
    for key in auth_keys:
        if key.startswith("windsurf_auth-") and not key.endswith("-usages"):
            prefix = "windsurf_auth-"
            name = key[len(prefix):]
            if name and name != "" and "codeium" not in key:
                return name
    return None


def _extract_email_from_free_key(auth_keys: Dict[str, bytes]) -> Optional[str]:
    raw = auth_keys.get("jg.windsurf-free")
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="ignore")
    try:
        data = json.loads(raw)
    except Exception:
        return None
    history = data.get("accountHistory")
    if isinstance(history, list):
        for entry in history:
            if isinstance(entry, dict) and entry.get("mail"):
                return str(entry.get("mail"))
    return None


def import_current_account() -> Dict:
    """Read current Windsurf auth state and return account info + snapshot."""
    if not os.path.exists(STATE_VSCDB_PATH):
        return {"success": False, "message": f"state.vscdb not found at {STATE_VSCDB_PATH}"}

    conn = sqlite3.connect(STATE_VSCDB_PATH)
    try:
        auth_keys = _get_all_auth_keys(conn)
        if not auth_keys:
            return {"success": False, "message": "No auth entries found in state.vscdb"}

        auth_status_raw = auth_keys.get("windsurfAuthStatus", b"")
        if isinstance(auth_status_raw, bytes):
            auth_status_raw = auth_status_raw.decode("utf-8", errors="replace")

        api_key, user_status_b64 = _parse_auth_status(auth_status_raw)
        proto_name, proto_email = _extract_user_info_from_status_proto(user_status_b64)
        free_key_email = _extract_email_from_free_key(auth_keys)
        user_name = _find_user_name(auth_keys) or proto_name

        snapshot = {}
        for k, v in auth_keys.items():
            if isinstance(v, bytes):
                try:
                    snapshot[k] = v.decode("utf-8")
                except UnicodeDecodeError:
                    import base64
                    snapshot[k] = {"__b64__": base64.b64encode(v).decode()}
            else:
                snapshot[k] = v

        snapshot_bytes = json.dumps(snapshot, ensure_ascii=False).encode("utf-8")

        return {
            "success": True,
            "message": f"Imported account: {user_name or 'unknown'}",
            "name": user_name or "Windsurf User",
            "email": free_key_email or proto_email,
            "api_key": api_key,
            "auth_snapshot": snapshot_bytes,
        }
    finally:
        conn.close()


def clear_local_auth() -> Dict:
    """Remove current Windsurf auth-related keys from local state."""
    if not os.path.exists(STATE_VSCDB_PATH):
        return {"success": False, "message": "state.vscdb not found"}

    backup_path = _backup_state_db()
    conn = sqlite3.connect(STATE_VSCDB_PATH)
    try:
        cursor = conn.cursor()
        existing = _get_all_auth_keys(conn)
        for key in existing:
            cursor.execute("DELETE FROM ItemTable WHERE key = ?", (key,))
        conn.commit()
        return {
            "success": True,
            "message": f"Cleared local Windsurf auth. Backup at {backup_path}",
        }
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": f"Failed to clear local auth: {e}"}
    finally:
        conn.close()


def build_auth_snapshot_from_template(snapshot_bytes: bytes, api_key: str, display_name: Optional[str] = None, email: Optional[str] = None, api_server_url: Optional[str] = None) -> Dict:
    """Best-effort synthesis of a local auth snapshot using a provided local auth template."""
    if not snapshot_bytes:
        return {"success": False, "message": "Template snapshot is empty"}

    try:
        snapshot = json.loads(snapshot_bytes.decode("utf-8"))
    except Exception as e:
        return {"success": False, "message": f"Failed to parse template snapshot: {e}"}

    snapshot.pop(SESSION_SECRET_KEY, None)
    snapshot.pop(API_SERVER_SECRET_KEY, None)

    auth_status_raw = snapshot.get("windsurfAuthStatus")
    if not isinstance(auth_status_raw, str):
        return {"success": False, "message": "Template snapshot missing windsurfAuthStatus"}

    try:
        auth_status = json.loads(auth_status_raw)
    except Exception as e:
        return {"success": False, "message": f"Invalid template auth status: {e}"}

    auth_status["apiKey"] = api_key
    if api_server_url:
        auth_status["apiServerUrl"] = api_server_url
    snapshot["windsurfAuthStatus"] = json.dumps(auth_status, ensure_ascii=False)

    free_key_raw = snapshot.get("jg.windsurf-free")
    if isinstance(free_key_raw, str):
        try:
            free_key = json.loads(free_key_raw)
            if isinstance(free_key, dict):
                history = free_key.get("accountHistory")
                entry = history[0] if isinstance(history, list) and history and isinstance(history[0], dict) else {}
                entry["apiKey"] = api_key
                if email:
                    entry["mail"] = email
                entry["apiServerUrl"] = api_server_url or entry.get("apiServerUrl") or "https://server.self-serve.windsurf.com"
                entry["timestamp"] = int(time.time() * 1000)
                free_key["accountHistory"] = [entry]
                snapshot["jg.windsurf-free"] = json.dumps(free_key, ensure_ascii=False)
        except Exception:
            pass

    if api_server_url:
        codeium_raw = snapshot.get("codeium.windsurf")
        if isinstance(codeium_raw, str):
            try:
                codeium_state = json.loads(codeium_raw)
                if isinstance(codeium_state, dict):
                    codeium_state["apiServerUrl"] = api_server_url
                    snapshot["codeium.windsurf"] = json.dumps(codeium_state, ensure_ascii=False)
            except Exception:
                pass

    snapshot.pop("windsurf.settings.cachedPlanInfo", None)

    if display_name:
        renamed = {}
        for key, value in snapshot.items():
            if key.startswith("windsurf_auth-") and not key.startswith(f"windsurf_auth-{display_name}"):
                suffix = ""
                if key.endswith("-usages"):
                    suffix = "-usages"
                renamed[f"windsurf_auth-{display_name}{suffix}"] = value
            else:
                renamed[key] = value
        snapshot = renamed

    return {
        "success": True,
        "message": "Built local auth snapshot from current template and apiKey",
        "auth_snapshot": json.dumps(snapshot, ensure_ascii=False).encode("utf-8"),
    }


def build_auth_snapshot_from_api_key(api_key: str, display_name: Optional[str] = None, email: Optional[str] = None, api_server_url: Optional[str] = None) -> Dict:
    """Best-effort synthesis of a local auth snapshot using the current local auth as a template."""
    current = import_current_account()
    if not current.get("success"):
        return {"success": False, "message": "No current local Windsurf auth available as template"}

    snapshot_bytes = current.get("auth_snapshot")
    if not snapshot_bytes:
        return {"success": False, "message": "Current local Windsurf auth snapshot is empty"}

    return build_auth_snapshot_from_template(
        snapshot_bytes,
        api_key,
        display_name=display_name,
        email=email,
        api_server_url=api_server_url,
    )


def _backup_state_db():
    """Create a timestamped backup of state.vscdb before modification."""
    if os.path.exists(STATE_VSCDB_PATH):
        backup_dir = os.path.join(os.path.dirname(STATE_VSCDB_PATH), "backups")
        os.makedirs(backup_dir, exist_ok=True)
        ts = int(time.time())
        backup_path = os.path.join(backup_dir, f"state.vscdb.bak.{ts}")
        shutil.copy2(STATE_VSCDB_PATH, backup_path)
        return backup_path
    return None


def restore_auth_snapshot(snapshot_bytes: bytes) -> Dict:
    """Write auth snapshot back to state.vscdb to switch local IDE account."""
    if not os.path.exists(STATE_VSCDB_PATH):
        return {"success": False, "message": "state.vscdb not found"}

    try:
        snapshot = json.loads(snapshot_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return {"success": False, "message": f"Invalid snapshot data: {e}"}

    auth_status_preview = None
    try:
        auth_status_preview = json.loads(snapshot.get("windsurfAuthStatus", "{}"))
    except Exception:
        auth_status_preview = None
    logger.info(
        "restore_auth_snapshot: parsed snapshot keys=%s apiKey=%s",
        sorted(snapshot.keys()),
        (auth_status_preview or {}).get("apiKey", "")[:24],
    )

    snapshot.pop(SESSION_SECRET_KEY, None)
    snapshot.pop(API_SERVER_SECRET_KEY, None)

    backup_path = _backup_state_db()

    conn = sqlite3.connect(STATE_VSCDB_PATH)
    try:
        cursor = conn.cursor()

        existing = _get_all_auth_keys(conn)
        if "codeium.windsurf" not in snapshot and existing.get("codeium.windsurf"):
            preserved = existing.get("codeium.windsurf")
            if isinstance(preserved, bytes):
                try:
                    snapshot["codeium.windsurf"] = preserved.decode("utf-8")
                except UnicodeDecodeError:
                    snapshot["codeium.windsurf"] = {"__b64__": base64.b64encode(preserved).decode()}
            else:
                snapshot["codeium.windsurf"] = preserved
        if API_SERVER_SECRET_KEY not in snapshot and existing.get(API_SERVER_SECRET_KEY):
            preserved = existing.get(API_SERVER_SECRET_KEY)
            if isinstance(preserved, bytes):
                snapshot[API_SERVER_SECRET_KEY] = {"__b64__": base64.b64encode(preserved).decode()}
            else:
                snapshot[API_SERVER_SECRET_KEY] = preserved
        logger.info(
            "restore_auth_snapshot: existing keys=%s final keys=%s",
            sorted(existing.keys()),
            sorted(snapshot.keys()),
        )
        for key in existing:
            cursor.execute("DELETE FROM ItemTable WHERE key = ?", (key,))

        for key, value in snapshot.items():
            if isinstance(value, dict) and "__b64__" in value:
                raw = base64.b64decode(value["__b64__"])
            elif isinstance(value, str):
                raw = value
            else:
                raw = json.dumps(value)
            cursor.execute(
                "INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)",
                (key, raw)
            )

        conn.commit()
        cursor.execute("SELECT value FROM ItemTable WHERE key = ?", ("windsurfAuthStatus",))
        row = cursor.fetchone()
        stored_api_key = ""
        if row:
            stored_raw = row[0].decode("utf-8", errors="ignore") if isinstance(row[0], bytes) else row[0]
            try:
                stored_api_key = json.loads(stored_raw).get("apiKey", "")[:24]
            except Exception:
                stored_api_key = ""
        logger.info("restore_auth_snapshot: committed apiKey=%s", stored_api_key)
        return {
            "success": True,
            "message": f"Auth restored. Backup at {backup_path}",
        }
    except Exception as e:
        logger.exception("restore_auth_snapshot failed")
        conn.rollback()
        return {"success": False, "message": f"Failed to restore auth: {e}"}
    finally:
        conn.close()


def kill_windsurf() -> bool:
    """Attempt to gracefully close Windsurf."""
    try:
        subprocess.run(["pkill", "-f", "Windsurf"], timeout=5, capture_output=True)
        time.sleep(1)
        return True
    except Exception:
        return False


def start_windsurf() -> bool:
    """Start Windsurf application."""
    try:
        subprocess.Popen(["open", "-a", "Windsurf"])
        return True
    except Exception:
        return False


def is_windsurf_running() -> bool:
    """Check whether Windsurf is currently running."""
    try:
        result = subprocess.run(["pgrep", "-x", "Windsurf"], timeout=5, capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            return True
        result = subprocess.run(["pgrep", "-f", "/Applications/Windsurf.app/Contents/MacOS"], timeout=5, capture_output=True, text=True)
        return result.returncode == 0 and bool(result.stdout.strip())
    except Exception:
        return False


def reload_windsurf_window() -> Dict:
    """Reload the current Windsurf window without killing the process."""
    script = [
        'tell application "Windsurf" to activate',
        'delay 0.2',
        'tell application "System Events"',
        'if not (exists process "Windsurf") then error "Windsurf is not running"',
        'tell process "Windsurf"',
        'keystroke "p" using {command down, shift down}',
        'delay 0.2',
        'keystroke ">Developer: Reload Window"',
        'delay 0.2',
        'key code 36',
        'end tell',
        'end tell',
    ]
    try:
        cmd = ["osascript"]
        for line in script:
            cmd.extend(["-e", line])
        result = subprocess.run(cmd, timeout=15, capture_output=True, text=True)
        if result.returncode == 0:
            logger.info("reload_windsurf_window: success")
            return {"success": True, "message": "Reloaded running Windsurf window"}
        stderr = (result.stderr or result.stdout or "").strip()
        logger.warning("reload_windsurf_window: failed stderr=%s", stderr)
        return {"success": False, "message": f"Auth written, but failed to reload running Windsurf window: {stderr or 'unknown osascript error'}"}
    except Exception as e:
        logger.exception("reload_windsurf_window failed")
        return {"success": False, "message": f"Auth written, but failed to reload running Windsurf window: {e}"}


def run_windsurf_command(command_title: str, post_enter_delay: float = 0.3) -> Dict:
    script = [
        'tell application "Windsurf" to activate',
        'delay 0.3',
        'tell application "System Events"',
        'if not (exists process "Windsurf") then error "Windsurf is not running"',
        'tell process "Windsurf"',
        'keystroke "p" using {command down, shift down}',
        'delay 0.3',
        f'keystroke "{command_title}"',
        'delay 0.3',
        'key code 36',
        f'delay {post_enter_delay}',
        'end tell',
        'end tell',
    ]
    try:
        cmd = ["osascript"]
        for line in script:
            cmd.extend(["-e", line])
        result = subprocess.run(cmd, timeout=20, capture_output=True, text=True)
        if result.returncode == 0:
            return {"success": True, "message": f"Executed Windsurf command: {command_title}"}
        stderr = (result.stderr or result.stdout or "").strip()
        return {"success": False, "message": f"Failed to execute Windsurf command {command_title}: {stderr or 'unknown osascript error'}"}
    except Exception as e:
        logger.exception("run_windsurf_command failed")
        return {"success": False, "message": f"Failed to execute Windsurf command {command_title}: {e}"}


def login_with_auth_token(auth_token: str) -> Dict:
    if not auth_token:
        return {"success": False, "message": "Firebase auth token is empty"}

    started = False
    if not is_windsurf_running():
        started = start_windsurf()
        if not started:
            return {"success": False, "message": "Failed to start Windsurf for auth-token login"}
        time.sleep(4)

    try:
        subprocess.run(["pbcopy"], input=auth_token, text=True, check=True, timeout=5)
    except Exception as e:
        logger.exception("login_with_auth_token: failed to copy token")
        return {"success": False, "message": f"Failed to copy auth token to clipboard: {e}"}

    command_result = run_windsurf_command(AUTH_TOKEN_COMMAND_TITLE, post_enter_delay=1.5)
    if not command_result["success"]:
        return command_result
    script = [
        'tell application "Windsurf" to activate',
        'delay 0.5',
        'tell application "System Events"',
        'if not (exists process "Windsurf") then error "Windsurf is not running"',
        'tell process "Windsurf"',
        'keystroke "v" using {command down}',
        'delay 0.2',
        'key code 36',
        'end tell',
        'end tell',
    ]
    try:
        cmd = ["osascript"]
        for line in script:
            cmd.extend(["-e", line])
        result = subprocess.run(cmd, timeout=20, capture_output=True, text=True)
        if result.returncode == 0:
            logger.warning("login_with_auth_token: submitted token started=%s", started)
            return {
                "success": True,
                "message": command_result["message"] + " Submitted auth token to running Windsurf" + (" after starting the app" if started else ""),
            }
        stderr = (result.stderr or result.stdout or "").strip()
        logger.warning("login_with_auth_token: failed stderr=%s", stderr)
        return {"success": False, "message": f"Failed to submit auth token in Windsurf: {stderr or 'unknown osascript error'}"}
    except Exception as e:
        logger.exception("login_with_auth_token failed")
        return {"success": False, "message": f"Failed to submit auth token in Windsurf: {e}"}


def login_with_auth_callback(auth_token: str) -> Dict:
    if not auth_token:
        return {"success": False, "message": "Firebase auth token is empty"}

    started = False
    if not is_windsurf_running():
        started = start_windsurf()
        if not started:
            return {"success": False, "message": "Failed to start Windsurf for auth callback login"}
        time.sleep(4)

    command_result = run_windsurf_command(AUTH_LOGIN_COMMAND_TITLE, post_enter_delay=1.0)
    if not command_result["success"]:
        return command_result

    callback_url = f"{AUTH_CALLBACK_URI_PREFIX}#access_token={urllib.parse.quote(auth_token, safe='')}"
    try:
        result = subprocess.run(["open", "-b", WINDSURF_BUNDLE_ID, callback_url], timeout=10, capture_output=True, text=True)
        if result.returncode == 0:
            logger.warning("login_with_auth_callback: opened callback uri")
            return {
                "success": True,
                "message": command_result["message"] + " Opened Windsurf auth callback URI" + (" after starting the app" if started else ""),
            }
        stderr = (result.stderr or result.stdout or "").strip()
        logger.warning("login_with_auth_callback: failed stderr=%s", stderr)
        return {"success": False, "message": f"Failed to open Windsurf auth callback URI: {stderr or 'unknown open error'}"}
    except Exception as e:
        logger.exception("login_with_auth_callback failed")
        return {"success": False, "message": f"Failed to open Windsurf auth callback URI: {e}"}


def switch_local_ide_with_auth_token(auth_token: str, expected_api_key: Optional[str] = None) -> Dict:
    previous_api_key = None
    previous = import_current_account()
    if previous.get("success"):
        previous_api_key = previous.get("api_key")

    submitted = login_with_auth_token(auth_token)
    if not submitted["success"]:
        submitted = login_with_auth_callback(auth_token)
        if not submitted["success"]:
            return submitted
    if expected_api_key:
        waited = wait_for_local_api_key(expected_api_key, timeout_seconds=45)
        if waited["success"]:
            return {
                "success": True,
                "message": submitted["message"] + " " + waited["message"],
            }
        changed = wait_for_local_api_key_change(previous_api_key, timeout_seconds=5)
        if changed["success"]:
            return {
                "success": True,
                "message": submitted["message"] + " " + waited["message"] + " " + changed["message"],
            }
        return {
            "success": False,
            "message": submitted["message"] + " " + waited["message"] + " " + changed["message"],
        }
    changed = wait_for_local_api_key_change(previous_api_key, timeout_seconds=45)
    if changed["success"]:
        return {
            "success": True,
            "message": submitted["message"] + " " + changed["message"],
        }
    return {
        "success": False,
        "message": submitted["message"] + " " + changed["message"],
    }


def switch_local_ide(snapshot_bytes: bytes) -> Dict:
    """Seamless local IDE switch: write auth -> reload current window or open the app."""
    logger.info("switch_local_ide: starting")
    result = restore_auth_snapshot(snapshot_bytes)
    if not result["success"]:
        logger.warning("switch_local_ide: restore failed message=%s", result["message"])
        return result

    if is_windsurf_running():
        logger.info("switch_local_ide: Windsurf running, attempting reload")
        reloaded = reload_windsurf_window()
        if reloaded["success"]:
            return {
                "success": True,
                "message": result["message"] + " " + reloaded["message"],
            }
        logger.warning("switch_local_ide: reload failed message=%s", reloaded["message"])
        return reloaded

    started = start_windsurf()
    logger.info("switch_local_ide: Windsurf not running, started=%s", started)
    return {
        "success": True,
        "message": result["message"] + (" Windsurf started." if started else " Please open Windsurf manually."),
    }


def queue_api_key_migration(api_key: str) -> Dict:
    """Write Windsurf's pending API key migration flag for the running auth session."""
    if not os.path.exists(STATE_VSCDB_PATH):
        return {"success": False, "message": "state.vscdb not found"}

    backup_path = _backup_state_db()
    conn = sqlite3.connect(STATE_VSCDB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)",
            (PENDING_API_KEY_MIGRATION_KEY, api_key),
        )
        conn.commit()
        logger.warning("queue_api_key_migration: queued apiKey=%s", api_key[:24])
        return {
            "success": True,
            "message": f"Queued API key migration. Backup at {backup_path}",
        }
    except Exception as e:
        conn.rollback()
        logger.exception("queue_api_key_migration failed")
        return {"success": False, "message": f"Failed to queue API key migration: {e}"}
    finally:
        conn.close()


def wait_for_local_api_key(api_key: str, timeout_seconds: int = 20, poll_interval: float = 1.0) -> Dict:
    """Poll local Windsurf auth state until the target api key becomes active."""
    deadline = time.time() + timeout_seconds
    last_seen = None

    while time.time() < deadline:
        result = import_current_account()
        if result.get("success"):
            current_api_key = result.get("api_key") or ""
            last_seen = current_api_key[:24] if current_api_key else None
            if current_api_key == api_key:
                return {
                    "success": True,
                    "message": "Local Windsurf auth now reflects the target apiKey",
                }
        time.sleep(poll_interval)

    return {
        "success": False,
        "message": f"Timed out waiting for local Windsurf auth to switch to target apiKey. Last seen: {last_seen or 'none'}",
    }


def wait_for_local_api_key_change(previous_api_key: Optional[str], timeout_seconds: int = 45, poll_interval: float = 1.0) -> Dict:
    deadline = time.time() + timeout_seconds
    previous_api_key = previous_api_key or ""
    last_seen = None

    while time.time() < deadline:
        result = import_current_account()
        if result.get("success"):
            current_api_key = result.get("api_key") or ""
            last_seen = current_api_key[:24] if current_api_key else None
            if current_api_key and current_api_key != previous_api_key:
                return {
                    "success": True,
                    "message": f"Local Windsurf auth switched to a new apiKey: {current_api_key[:24]}",
                }
        time.sleep(poll_interval)

    return {
        "success": False,
        "message": f"Timed out waiting for local Windsurf auth to change apiKey. Last seen: {last_seen or 'none'}",
    }


def switch_local_ide_via_api_key_migration(api_key: str) -> Dict:
    """Switch the running Windsurf auth session using the extension's pending API key migration path."""
    queued = queue_api_key_migration(api_key)
    if not queued["success"]:
        return queued

    if is_windsurf_running():
        logger.warning("switch_local_ide_via_api_key_migration: Windsurf running, reloading window")
        reloaded = reload_windsurf_window()
        if not reloaded["success"]:
            return reloaded
        waited = wait_for_local_api_key(api_key)
        if waited["success"]:
            return {
                "success": True,
                "message": queued["message"] + " " + reloaded["message"] + " " + waited["message"],
            }
        return waited

    started = start_windsurf()
    logger.warning("switch_local_ide_via_api_key_migration: Windsurf not running, started=%s", started)
    waited = wait_for_local_api_key(api_key, timeout_seconds=30)
    if waited["success"]:
        return {
            "success": True,
            "message": queued["message"] + (" Windsurf started." if started else " Please open Windsurf manually.") + " " + waited["message"],
        }
    return waited


def prepare_local_login() -> Dict:
    """Prepare local Windsurf for a fresh login by clearing auth and restarting the app."""
    kill_windsurf()
    time.sleep(2)
    cleared = clear_local_auth()
    if not cleared["success"]:
        return cleared
    started = start_windsurf()
    return {
        "success": True,
        "message": cleared["message"] + (" Windsurf restarted and is ready for sign-in." if started else " Local auth cleared. Please start Windsurf manually."),
    }


def wait_for_local_account(email: Optional[str] = None, timeout_seconds: int = 180, poll_interval: float = 2.0) -> Dict:
    """Poll local Windsurf auth state until a login is detected, optionally matching a target email."""
    deadline = time.time() + timeout_seconds
    normalized_target = (email or "").strip().lower()
    last_message = "Waiting for local Windsurf login"

    while time.time() < deadline:
        result = import_current_account()
        if result.get("success"):
            current_email = (result.get("email") or "").strip().lower()
            if normalized_target:
                if current_email == normalized_target:
                    return result
                if current_email:
                    last_message = f"Detected local Windsurf login for {current_email}, waiting for {normalized_target}"
            else:
                return result
        time.sleep(poll_interval)

    return {"success": False, "message": last_message + f". Timed out after {timeout_seconds} seconds."}


def switch_local_ide_with_api_key(api_key: str, display_name: Optional[str] = None, email: Optional[str] = None, api_server_url: Optional[str] = None) -> Dict:
    """Fallback local IDE switch when only api_key is available."""
    migration_result = switch_local_ide_via_api_key_migration(api_key)
    if migration_result["success"]:
        return migration_result

    snapshot_result = build_auth_snapshot_from_api_key(api_key, display_name=display_name, email=email, api_server_url=api_server_url)
    if not snapshot_result["success"]:
        return migration_result
    snapshot_switch = switch_local_ide(snapshot_result["auth_snapshot"])
    if snapshot_switch["success"]:
        return {
            "success": True,
            "message": migration_result["message"] + f" Fallback snapshot restore succeeded: {snapshot_switch['message']}",
        }
    return {
        "success": False,
        "message": migration_result["message"] + f" Fallback snapshot restore also failed: {snapshot_switch['message']}",
    }

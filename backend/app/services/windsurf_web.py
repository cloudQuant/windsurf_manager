"""
Windsurf web login & quota scraping via Playwright.
"""
import asyncio
import gzip
import json
import os
import plistlib
import re
import subprocess
import time
from typing import Dict, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request

LOGIN_URL = "https://windsurf.com/account/login"
PROFILE_URL = "https://windsurf.com/profile"
USAGE_URL = "https://windsurf.com/subscription/usage"
CHROME_BUNDLE_ID = "com.google.chrome"
CHROME_APP_NAME = "Google Chrome"
LAUNCH_SERVICES_PLIST = os.path.expanduser("~/Library/Preferences/com.apple.LaunchServices/com.apple.launchservices.secure.plist")
WINDSURF_LOGOUT_JS = 'document.querySelector("body > div.flex.min-h-screen.flex-col > div > div > div.sticky.top-0.col-span-1.hidden.h-screen.shrink-0.flex-col.pb-6.pt-28.md\\\\:pt-36.lg\\\\:flex > div > div.mt-auto.flex.flex-col.gap-1.px-4 > div").click()'


async def _new_context(headless: bool = False, channel: Optional[str] = None):
    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    launch_kwargs = {"headless": headless}
    if channel:
        launch_kwargs["channel"] = channel
    browser = await pw.chromium.launch(**launch_kwargs)
    context = await browser.new_context()
    return pw, browser, context


def _default_browser_bundle_id() -> Optional[str]:
    if not os.path.exists(LAUNCH_SERVICES_PLIST):
        return None
    try:
        with open(LAUNCH_SERVICES_PLIST, "rb") as fh:
            data = plistlib.load(fh)
        for item in data.get("LSHandlers", []):
            if item.get("LSHandlerURLScheme") == "https":
                return item.get("LSHandlerRoleAll")
    except Exception:
        return None
    return None


def _run_osascript(lines: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    command = ["osascript"]
    for line in lines:
        command.extend(["-e", line])
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout)


def _copy_to_clipboard(text: str) -> None:
    subprocess.run(["pbcopy"], input=text, text=True, check=True, timeout=10)


def _chrome_open_url_in_new_tab(url: str) -> Dict:
    lines = [
        f'tell application "{CHROME_APP_NAME}"',
        'activate',
        'if (count of windows) = 0 then make new window',
        'tell front window',
        f'make new tab at end of tabs with properties {{URL:{json.dumps(url)}}}',
        'set active tab index to (count of tabs)',
        'end tell',
        'end tell',
    ]
    try:
        result = _run_osascript(lines)
        if result.returncode == 0:
            return {"success": True, "message": f"Opened {url} in Google Chrome"}
        stderr = (result.stderr or result.stdout or "").strip()
        return {"success": False, "message": f"Failed to open Google Chrome tab: {stderr or 'unknown osascript error'}"}
    except Exception as exc:
        return {"success": False, "message": f"Failed to open Google Chrome tab: {exc}"}


def _chrome_set_active_tab_url(url: str) -> Dict:
    lines = [
        f'tell application "{CHROME_APP_NAME}" to set URL of active tab of front window to {json.dumps(url)}',
    ]
    try:
        result = _run_osascript(lines)
        if result.returncode == 0:
            return {"success": True, "message": f"Opened {url} in active Chrome tab"}
        stderr = (result.stderr or result.stdout or "").strip()
        return {"success": False, "message": f"Failed to navigate active Google Chrome tab: {stderr or 'unknown osascript error'}"}
    except Exception as exc:
        return {"success": False, "message": f"Failed to navigate active Google Chrome tab: {exc}"}


def _chrome_get_active_tab_url() -> Dict:
    lines = [
        f'tell application "{CHROME_APP_NAME}" to get URL of active tab of front window',
    ]
    try:
        result = _run_osascript(lines)
        if result.returncode == 0:
            return {"success": True, "url": (result.stdout or "").strip()}
        stderr = (result.stderr or result.stdout or "").strip()
        return {"success": False, "message": f"Failed to read active Google Chrome tab URL: {stderr or 'unknown osascript error'}"}
    except Exception as exc:
        return {"success": False, "message": f"Failed to read active Google Chrome tab URL: {exc}"}


def _wait_for_active_tab_url(predicate, timeout_seconds: int, description: str) -> Dict:
    deadline = time.time() + timeout_seconds
    last_url = ""
    last_message = ""
    while time.time() < deadline:
        current = _chrome_get_active_tab_url()
        if not current.get("success"):
            last_message = current.get("message") or last_message
            time.sleep(1)
            continue
        last_url = current.get("url") or ""
        if predicate(last_url.lower()):
            return {"success": True, "url": last_url, "message": f"Reached {description}"}
        time.sleep(1)
    if last_url:
        return {"success": False, "url": last_url, "message": f"Timed out waiting for {description}; last URL was {last_url or 'unknown'}"}
    return {"success": False, "url": last_url, "message": last_message or f"Timed out waiting for {description}"}


def _launch_google_chrome(url: str) -> Dict:
    try:
        subprocess.Popen(["open", "-a", CHROME_APP_NAME, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"success": True, "message": f"Opened {url} in Google Chrome"}
    except Exception as exc:
        return {"success": False, "message": f"Failed to open Google Chrome: {exc}"}


def _run_google_chrome_system_events(lines: list[str], timeout: int = 30) -> Dict:
    try:
        script = [
            f'tell application "{CHROME_APP_NAME}" to activate',
            'tell application "System Events"',
            f'  tell process "{CHROME_APP_NAME}"',
            *lines,
            '  end tell',
            'end tell',
        ]
        result = _run_osascript(script, timeout=timeout)
        if result.returncode == 0:
            return {"success": True, "message": "Drove Google Chrome via System Events"}
        stderr = (result.stderr or result.stdout or "").strip()
        return {"success": False, "message": f"Failed to drive Google Chrome via System Events: {stderr or 'unknown osascript error'}"}
    except Exception as exc:
        return {"success": False, "message": f"Failed to drive Google Chrome via System Events: {exc}"}


def _navigate_chrome_to(url: str) -> Dict:
    result = _chrome_open_url_in_new_tab(url)
    if not result.get("success"):
        result = _launch_google_chrome(url)
    return result


def _chrome_execute_js(js_code: str) -> Dict:
    lines = [
        f'tell application "{CHROME_APP_NAME}"',
        '  tell front window',
        '    tell active tab',
        f'      set jsResult to execute javascript {json.dumps(js_code)}',
        '    end tell',
        '  end tell',
        'end tell',
        'return jsResult',
    ]
    try:
        result = _run_osascript(lines, timeout=15)
        if result.returncode == 0:
            return {"success": True, "result": (result.stdout or "").strip(), "message": "Executed JS in Chrome"}
        stderr = (result.stderr or result.stdout or "").strip()
        return {"success": False, "message": f"Failed to execute JS in Chrome: {stderr or 'unknown error'}"}
    except Exception as exc:
        return {"success": False, "message": f"Failed to execute JS in Chrome: {exc}"}


def _build_windsurf_login_js(email: str, password: str) -> str:
    import json as _json
    return (
        "(()=>{"
        "const s=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;"
        "const e=document.querySelector('input[name=\"email\"],input[type=\"email\"]');"
        "const p=document.querySelector('input[type=\"password\"]');"
        "if(!e||!p)return;"
        f"s.call(e,{_json.dumps(email)});"
        "e.dispatchEvent(new Event('input',{bubbles:true}));"
        f"s.call(p,{_json.dumps(password)});"
        "p.dispatchEvent(new Event('input',{bubbles:true}));"
        "setTimeout(()=>{"
        "const b=[...document.querySelectorAll('button')].find(b=>/^log in$/i.test(b.textContent.trim()));"
        "if(b)b.click()"
        "},500)"
        "})()"
    )


def _login_in_default_browser_chrome(email: str, password: str) -> Dict:
    nav = _navigate_chrome_to(USAGE_URL)
    if not nav.get("success"):
        return nav

    page_load = _wait_for_active_tab_url(
        lambda url: "windsurf.com" in url,
        timeout_seconds=15,
        description="Windsurf page load",
    )
    if not page_load.get("success"):
        return {
            "success": False,
            "message": f"Failed to navigate to Windsurf in Google Chrome: {page_load.get('message', 'unknown')}",
        }

    time.sleep(3)

    current = _chrome_get_active_tab_url()
    current_url = (current.get("url") or "").lower() if current.get("success") else ""
    logout_message = "No logout needed"

    if "/account/login" not in current_url:
        logout_exec = _chrome_execute_js(WINDSURF_LOGOUT_JS)
        if not logout_exec.get("success"):
            return {
                "success": False,
                "message": f"Failed to trigger logout in Google Chrome: {logout_exec['message']}",
            }

        login_wait = _wait_for_active_tab_url(
            lambda url: "/account/login" in url,
            timeout_seconds=30,
            description="Windsurf login page after logout",
        )
        if not login_wait.get("success"):
            return {
                "success": False,
                "message": f"Logout was triggered but did not redirect to the login page: {login_wait['message']}",
            }
        logout_message = "Logged out current Windsurf web session"

    time.sleep(2)

    login_js = _build_windsurf_login_js(email, password)
    login_exec = _chrome_execute_js(login_js)
    if not login_exec.get("success"):
        return {
            "success": False,
            "message": f"{logout_message} | Failed to fill login form: {login_exec['message']}",
        }

    completed = _wait_for_active_tab_url(
        lambda url: url.startswith("https://windsurf.com/") and "/account/login" not in url,
        timeout_seconds=40,
        description="Windsurf account page after login",
    )
    if not completed.get("success"):
        return {
            "success": False,
            "message": f"{logout_message} | Login form submitted for {email}, but did not leave the login page: {completed['message']}",
        }

    return {
        "success": True,
        "message": f"{logout_message} | Logged into Windsurf web for {email} in your default Google Chrome session.",
    }


def _login_in_default_browser_sync(email: str, password: str) -> Dict:
    bundle_id = _default_browser_bundle_id()
    if bundle_id and bundle_id != CHROME_BUNDLE_ID:
        try:
            subprocess.run(["open", LOGIN_URL], timeout=10, capture_output=True, text=True)
            return {
                "success": True,
                "message": f"Opened Windsurf login in your default browser, but automatic credential entry currently supports Google Chrome only. Please finish logging into {email} manually.",
            }
        except Exception as exc:
            return {"success": False, "message": f"Failed to open Windsurf login in the default browser: {exc}"}

    return _login_in_default_browser_chrome(email, password)


async def login_in_default_browser(email: str, password: str) -> Dict:
    return await asyncio.to_thread(_login_in_default_browser_sync, email, password)


def _extract_api_key(text: str) -> str | None:
    match = re.search(r'(sk-ws-[A-Za-z0-9_-]+)', text)
    return match.group(1) if match else None


def _parse_percentage(text: str | None) -> float | None:
    if not text:
        return None
    match = re.search(r'(\d+(?:\.\d+)?)\s*%', text)
    return float(match.group(1)) if match else None


def _find_first_email(values: list[str]) -> str | None:
    for value in values:
        if re.fullmatch(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', value):
            return value
    return None


def _normalize_plan_type(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.lower()
    if "free trial" in lowered:
        return "Free trial"
    if lowered == "trial" or lowered.startswith("trial"):
        return "Trial"
    if "enterprise" in lowered:
        return "Enterprise"
    if "team" in lowered:
        return "Team"
    if lowered == "pro" or lowered.startswith("pro"):
        return "Pro"
    if "individual" in lowered:
        return "Individual"
    return value


async def _extract_storage_text(page) -> str:
    payload = await page.evaluate(
        """() => JSON.stringify({
            localStorage: Object.fromEntries(Object.entries(localStorage)),
            sessionStorage: Object.fromEntries(Object.entries(sessionStorage))
        })"""
    )
    return payload or ""


def _encode_varint(value: int) -> bytes:
    out = bytearray()
    while True:
        chunk = value & 0x7F
        value >>= 7
        if value:
            out.append(chunk | 0x80)
        else:
            out.append(chunk)
            return bytes(out)


def _decode_varint(payload: bytes, offset: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while offset < len(payload):
        byte = payload[offset]
        offset += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, offset
        shift += 7
    raise ValueError("Unexpected end of protobuf varint")


def _encode_proto_string(field_number: int, value: str) -> bytes:
    raw = value.encode("utf-8")
    key = (field_number << 3) | 2
    return bytes([key]) + _encode_varint(len(raw)) + raw


def _unwrap_connect_payload(payload: bytes) -> bytes:
    if len(payload) < 5:
        return payload
    offset = 0
    while offset + 5 <= len(payload):
        flags = payload[offset]
        frame_len = int.from_bytes(payload[offset + 1:offset + 5], "big")
        offset += 5
        if offset + frame_len > len(payload):
            return payload
        frame = payload[offset:offset + frame_len]
        offset += frame_len
        if flags & 0x02:
            continue
        return frame
    return payload


def _decode_register_user_response(payload: bytes) -> Dict[str, Optional[str]]:
    raw = _unwrap_connect_payload(payload)
    offset = 0
    parsed: Dict[str, Optional[str]] = {
        "api_key": None,
        "name": None,
        "api_server_url": None,
    }
    field_map = {
        1: "api_key",
        2: "name",
        3: "api_server_url",
    }

    while offset < len(raw):
        key, offset = _decode_varint(raw, offset)
        field_number = key >> 3
        wire_type = key & 0x07
        if wire_type == 2:
            length, offset = _decode_varint(raw, offset)
            value = raw[offset:offset + length]
            offset += length
            mapped = field_map.get(field_number)
            if mapped:
                parsed[mapped] = value.decode("utf-8", errors="ignore")
        elif wire_type == 0:
            _, offset = _decode_varint(raw, offset)
        elif wire_type == 1:
            offset += 8
        elif wire_type == 5:
            offset += 4
        else:
            raise ValueError(f"Unsupported protobuf wire type: {wire_type}")

    return parsed


def _register_user_sync(firebase_id_token: str) -> Dict:
    endpoint = "https://register.windsurf.com/exa.seat_management_pb.SeatManagementService/RegisterUser"
    request_payload = _encode_proto_string(1, firebase_id_token)
    connect_payload = b"\x00" + len(request_payload).to_bytes(4, "big") + request_payload
    attempts = [
        {
            "content_type": "application/proto",
            "body": request_payload,
            "headers": {"Connect-Protocol-Version": "1"},
        },
        {
            "content_type": "application/connect+proto",
            "body": connect_payload,
            "headers": {"Connect-Protocol-Version": "1"},
        },
    ]
    failures: list[str] = []

    for attempt in attempts:
        headers = {
            "Content-Type": attempt["content_type"],
            "Accept": "application/proto, application/connect+proto",
            "Accept-Encoding": "identity",
            **attempt["headers"],
        }
        req = urllib_request.Request(endpoint, data=attempt["body"], headers=headers, method="POST")
        try:
            with urllib_request.urlopen(req, timeout=30) as resp:
                payload = resp.read()
                if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                    payload = gzip.decompress(payload)
                parsed = _decode_register_user_response(payload)
                if parsed.get("api_key"):
                    return {
                        "success": True,
                        "message": "Exchanged Firebase auth token for Windsurf apiKey",
                        **parsed,
                    }
                failures.append(f"{attempt['content_type']}: missing api_key in response")
        except urllib_error.HTTPError as exc:
            body = exc.read()
            if exc.headers.get("Content-Encoding", "").lower() == "gzip":
                body = gzip.decompress(body)
            failures.append(f"{attempt['content_type']}: HTTP {exc.code} {body[:200]!r}")
        except Exception as exc:
            failures.append(f"{attempt['content_type']}: {exc}")

    return {
        "success": False,
        "message": "registerUser exchange failed: " + " | ".join(failures),
        "api_key": None,
        "name": None,
        "api_server_url": None,
    }


async def _register_user(firebase_id_token: str) -> Dict:
    return await asyncio.to_thread(_register_user_sync, firebase_id_token)


async def _extract_firebase_auth(page) -> Dict:
    return await page.evaluate(
        """async () => {
            const out = {
                firebase_id_token: null,
                firebase_email: null,
                firebase_uid: null,
            };
            if (!('indexedDB' in window) || !indexedDB.databases) {
                return out;
            }
            const dbs = await indexedDB.databases();
            if (!dbs.find((db) => db.name === 'firebaseLocalStorageDb')) {
                return out;
            }
            const db = await new Promise((resolve, reject) => {
                const req = indexedDB.open('firebaseLocalStorageDb');
                req.onsuccess = () => resolve(req.result);
                req.onerror = () => reject(req.error);
            });
            const tx = db.transaction('firebaseLocalStorage', 'readonly');
            const store = tx.objectStore('firebaseLocalStorage');
            const rows = await new Promise((resolve, reject) => {
                const req = store.getAll();
                req.onsuccess = () => resolve(req.result);
                req.onerror = () => reject(req.error);
            });
            db.close();
            const authUser = rows.find((row) => String(row?.fbase_key || '').includes('firebase:authUser'));
            const value = authUser?.value || {};
            out.firebase_id_token = value?.stsTokenManager?.accessToken || null;
            out.firebase_email = value?.email || null;
            out.firebase_uid = value?.uid || null;
            return out;
        }"""
    )


async def _login(page, email: str, password: str) -> Dict:
    await page.goto(LOGIN_URL, timeout=60000, wait_until="networkidle")

    try:
        await page.wait_for_selector('input[placeholder="Enter your email address"]', state="visible", timeout=30000)
    except Exception:
        await asyncio.sleep(10)
        await page.wait_for_selector('input[placeholder="Enter your email address"]', state="visible", timeout=30000)

    await page.locator('input[placeholder="Enter your email address"]').fill(email)
    await page.locator('input[placeholder="Enter your password"]').fill(password)
    await page.locator('button:has-text("Log in")').first.click()
    await asyncio.sleep(8)

    url = page.url
    body = (await page.text_content("body") or "").lower()

    if any(word in body for word in ["invalid", "incorrect", "wrong password"]) and "login" in url.lower():
        return {"success": False, "message": "Login failed: invalid credentials"}

    if "login" in url.lower():
        await asyncio.sleep(4)
        url = page.url

    if "login" in url.lower():
        return {"success": False, "message": f"Login failed: still on login page ({url})"}

    return {"success": True, "message": f"Logged in as {email}", "url": url}


async def _scrape_profile(page) -> Dict:
    await page.goto(PROFILE_URL, timeout=30000, wait_until="networkidle")
    await page.wait_for_selector("main", timeout=15000)
    await asyncio.sleep(1)

    profile_data = await page.evaluate(
        """() => {
            const root = document.querySelector('main');
            const texts = Array.from(root?.querySelectorAll('h1, h2, h3, h4, h5, p, div, span') || [])
                .map((node) => (node.textContent || '').trim())
                .filter(Boolean);
            return {
                heading: root?.querySelector('h1')?.textContent?.trim() || null,
                texts: Array.from(new Set(texts)),
            };
        }"""
    )

    body = "\n".join(profile_data.get("texts") or [])
    display_name = profile_data.get("heading") or None

    plan_type = _normalize_plan_type(
        next(
            (
                value for value in (profile_data.get("texts") or [])
                if any(token in value.lower() for token in ["trial", "pro", "team", "enterprise", "individual"])
            ),
            None,
        )
    )

    storage_text = await _extract_storage_text(page)
    html = await page.content()
    api_key = _extract_api_key(body) or _extract_api_key(storage_text) or _extract_api_key(html)

    return {
        "display_name": display_name,
        "plan_type": plan_type,
        "api_key": api_key,
    }


async def _scrape_usage(page) -> Dict:
    await page.goto(USAGE_URL, timeout=30000, wait_until="networkidle")
    await page.wait_for_selector("text=Your daily quota", timeout=15000)
    await page.wait_for_selector("text=Your weekly quota", timeout=15000)
    await asyncio.sleep(1)

    daily_text = None
    weekly_text = None
    extra_balance = None

    try:
        daily_text = await page.locator("xpath=//p[normalize-space()='Your daily quota']/following-sibling::p[1]").first.text_content(timeout=5000)
    except Exception:
        daily_text = None

    try:
        weekly_text = await page.locator("xpath=//p[normalize-space()='Your weekly quota']/following-sibling::p[1]").first.text_content(timeout=5000)
    except Exception:
        weekly_text = None

    try:
        extra_balance = await page.locator("xpath=//p[normalize-space()='Extra usage balance available']/following-sibling::p[1]").first.text_content(timeout=5000)
    except Exception:
        extra_balance = None

    if daily_text is None or weekly_text is None or extra_balance is None:
        usage_data = await page.evaluate(
            """() => {
                const blocks = Array.from(document.querySelectorAll('main div'))
                    .map((container) => Array.from(container.querySelectorAll('p, span, div, h1, h2, h3, h4, h5'))
                        .map((node) => (node.textContent || '').trim())
                        .filter(Boolean))
                    .filter((values) => values.length > 0);

                const findValue = (label) => {
                    for (const values of blocks) {
                        const idx = values.indexOf(label);
                        if (idx !== -1 && values[idx + 1]) return values[idx + 1];
                    }
                    return null;
                };

                return {
                    dailyQuota: findValue('Your daily quota'),
                    weeklyQuota: findValue('Your weekly quota'),
                    extraBalance: findValue('Extra usage balance available'),
                };
            }"""
        )
        daily_text = daily_text or usage_data.get("dailyQuota")
        weekly_text = weekly_text or usage_data.get("weeklyQuota")
        extra_balance = extra_balance or usage_data.get("extraBalance")

    daily_quota_pct = _parse_percentage((daily_text or "").strip())
    weekly_quota_pct = _parse_percentage((weekly_text or "").strip())

    if extra_balance:
        extra_balance = extra_balance.strip()
    if extra_balance and not re.fullmatch(r'\$[\d.]+', extra_balance):
        balance_match = re.search(r'\$[\d.]+', extra_balance)
        extra_balance = balance_match.group(0) if balance_match else None

    plan_expiry = None
    try:
        plan_expiry = await page.evaluate(
            """() => {
                const body = document.body?.innerText || '';
                // Look for patterns like "renews on Mar 28, 2026" or "expires Mar 28, 2026"
                const patterns = [
                    /(?:renews?|expires?|expir(?:es|ation)|ends?|valid until|through)\\s+(?:on\\s+)?([A-Z][a-z]{2,8}\\s+\\d{1,2},?\\s+\\d{4})/i,
                    /([A-Z][a-z]{2,8}\\s+\\d{1,2},?\\s+\\d{4})\\s*(?:renewal|expir)/i,
                    /\\b(\\d{4}[-/]\\d{2}[-/]\\d{2})\\b/,
                ];
                for (const p of patterns) {
                    const m = body.match(p);
                    if (m) return m[1].trim();
                }
                // Fallback: find any date near "plan" or "subscription" text
                const nodes = document.querySelectorAll('p, span, div');
                for (const node of nodes) {
                    const t = (node.textContent || '').trim();
                    if (t.length > 5 && t.length < 100) {
                        const dm = t.match(/([A-Z][a-z]{2,8}\\s+\\d{1,2},?\\s+\\d{4})/);
                        if (dm) return dm[1].trim();
                    }
                }
                return null;
            }"""
        )
    except Exception:
        plan_expiry = None

    quota_total = None
    quota_used = None

    return {
        "daily_quota_pct": daily_quota_pct,
        "weekly_quota_pct": weekly_quota_pct,
        "extra_balance": extra_balance,
        "plan_expiry": plan_expiry,
        "quota_total": quota_total,
        "quota_used": quota_used,
    }


async def sync_account_state(email: str, password: str) -> Dict:
    pw = None
    browser = None
    context = None
    try:
        pw, browser, context = await _new_context(headless=True)
        page = await context.new_page()

        login_result = await _login(page, email, password)
        if not login_result["success"]:
            return login_result

        profile = await _scrape_profile(page)
        usage = await _scrape_usage(page)
        firebase_auth = await _extract_firebase_auth(page)
        register_result = {"success": False, "message": "No Firebase auth token found"}
        firebase_id_token = firebase_auth.get("firebase_id_token")
        if firebase_id_token:
            register_result = await _register_user(firebase_id_token)
        api_key = profile.get("api_key") or register_result.get("api_key")
        display_name = profile.get("display_name") or register_result.get("name")

        return {
            "success": True,
            "message": f"Logged in and synced account state for {email}",
            **profile,
            **usage,
            "display_name": display_name,
            "api_key": api_key,
            "firebase_id_token": firebase_id_token,
            "firebase_email": firebase_auth.get("firebase_email"),
            "firebase_uid": firebase_auth.get("firebase_uid"),
            "api_server_url": register_result.get("api_server_url"),
            "register_message": register_result.get("message"),
        }
    except Exception as e:
        return {"success": False, "message": f"Web sync error: {e}"}
    finally:
        if context:
            try:
                await context.close()
            except Exception:
                pass
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
        if pw:
            try:
                await pw.stop()
            except Exception:
                pass


async def web_login(email: str, password: str) -> Dict:
    return await login_in_default_browser(email, password)


async def scrape_quota(email: str, password: str) -> Dict:
    result = await sync_account_state(email, password)
    if not result["success"]:
        return result
    return {
        "success": True,
        "quota_total": result.get("quota_total"),
        "quota_used": result.get("quota_used"),
        "daily_quota_pct": result.get("daily_quota_pct"),
        "weekly_quota_pct": result.get("weekly_quota_pct"),
        "extra_balance": result.get("extra_balance"),
        "plan_expiry": result.get("plan_expiry"),
        "api_key": result.get("api_key"),
        "firebase_id_token": result.get("firebase_id_token"),
        "display_name": result.get("display_name"),
        "plan_type": result.get("plan_type"),
        "message": "Quota scraped from windsurf.com",
    }


async def close_browser():
    return None

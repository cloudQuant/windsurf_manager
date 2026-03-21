"""
Batch auto-login script for Windsurf accounts.
Logs into each account on windsurf.com via Playwright.
After successful login, scrapes profile info + quota from Usage page,
then updates the backend database via API.
"""
import asyncio
import os
import re
import requests
from playwright.async_api import async_playwright

ACCOUNTS = [
    ("Account-01", "c1nh34snml@zfkisry.shop", "=sTf80TmTVCW.}vM"),
    ("Account-02", "aprz3hm8pq@zfkisry.shop", "V*3R)xAsbn:k2B6C"),
    ("Account-03", "94u4nwyxll@zfkisry.shop", "!H%C*h3%.T5e#glZ"),
    ("Account-04", "71dwtfvxtt@zfkisry.shop", "xV@&UTYv*27&vmOJ"),
    ("Account-05", "8fsjhv9if8@rvjyzpo.shop", "(Ug@4?85-OIo:aFl"),
    ("Account-06", "kd0tupna7u@rvjyzpo.shop", "0)v)d-1uOywNxQpM"),
    ("Account-07", "nvt9om8l73@rvjyzpo.shop", "LnFOQzpn81_t+$3o"),
    ("Account-08", "giqqgcz3tr@rvjyzpo.shop", "8Z^.PwBz[Rn7D1Hp"),
    ("Account-09", "g6e0nou7rb@rvjyzpo.shop", "%2M18z0..QZAv^w{"),
    ("Account-10", "6f5aktnkka@rvjyzpo.shop", "M?010za3HN..d*qY"),
]

LOGIN_URL = "https://windsurf.com/account/login"
PROFILE_URL = "https://windsurf.com/profile"
USAGE_URL = "https://windsurf.com/subscription/usage"
API_BASE = "http://127.0.0.1:8001/api/accounts"
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "login_screenshots")


def find_account_id(email: str) -> int | None:
    """Find account ID by email from backend API."""
    try:
        r = requests.get(API_BASE)
        for acc in r.json():
            if acc["email"] == email:
                return acc["id"]
    except Exception:
        pass
    return None


def update_backend(account_id: int, profile_data: dict):
    """Push scraped profile/quota data to backend API."""
    try:
        requests.put(f"{API_BASE}/{account_id}/profile", json=profile_data)
    except Exception as e:
        print(f"    [warn] Failed to update backend: {e}")


async def scrape_profile(page) -> dict:
    """Scrape display_name and plan_type from the profile page."""
    info = {}
    try:
        await page.goto(PROFILE_URL, timeout=30000)
        await asyncio.sleep(2)
        body = await page.text_content("body") or ""

        # Try to find h1 with profile name
        h1 = page.locator("h1").first
        try:
            info["display_name"] = (await h1.text_content(timeout=5000) or "").strip()
        except Exception:
            pass

        # Plan type - look for common plan tags
        for plan in ["Free trial", "Pro", "Team", "Enterprise", "Individual"]:
            if plan.lower() in body.lower():
                info["plan_type"] = plan
                break
    except Exception as e:
        print(f"    [warn] Profile scrape error: {e}")
    return info


async def scrape_usage(page) -> dict:
    """Scrape daily/weekly quota and extra balance from the usage page."""
    info = {}
    try:
        await page.goto(USAGE_URL, timeout=30000)
        await asyncio.sleep(2)
        body = await page.text_content("body") or ""

        # Parse "XX.XX% remaining" patterns
        pct_matches = re.findall(r'([\d.]+)%\s*remaining', body)
        if len(pct_matches) >= 1:
            info["daily_quota_pct"] = float(pct_matches[0])
        if len(pct_matches) >= 2:
            info["weekly_quota_pct"] = float(pct_matches[1])

        # Parse extra balance "$X.XX"
        balance_match = re.search(r'\$[\d.]+', body)
        if balance_match:
            info["extra_balance"] = balance_match.group(0)

    except Exception as e:
        print(f"    [warn] Usage scrape error: {e}")
    return info


async def login_one(browser, name: str, email: str, password: str) -> dict:
    """Login a single account in a fresh isolated context, scrape profile+quota."""
    context = await browser.new_context()
    page = await context.new_page()
    try:
        await page.goto(LOGIN_URL, timeout=60000)

        # Wait for email input (handles Cloudflare wait)
        try:
            await page.wait_for_selector(
                'input[placeholder="Enter your email address"]',
                state="visible", timeout=30000
            )
        except Exception:
            await asyncio.sleep(10)
            try:
                await page.wait_for_selector(
                    'input[placeholder="Enter your email address"]',
                    state="visible", timeout=30000
                )
            except Exception:
                os.makedirs(SCREENSHOT_DIR, exist_ok=True)
                await page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"{name}_blocked.png"))
                return {"name": name, "email": email, "status": "BLOCKED",
                        "detail": "Login form not found (Cloudflare?)"}

        # Fill credentials
        await page.locator('input[placeholder="Enter your email address"]').fill(email)
        await asyncio.sleep(0.3)
        await page.locator('input[placeholder="Enter your password"]').fill(password)
        await asyncio.sleep(0.3)
        await page.locator('button:has-text("Log in")').first.click()

        # Wait for redirect
        await asyncio.sleep(6)

        url = page.url
        body_text = (await page.text_content("body") or "").lower()

        os.makedirs(SCREENSHOT_DIR, exist_ok=True)

        # Check if login failed
        error_keywords = ["invalid", "incorrect", "wrong password"]
        if any(kw in body_text for kw in error_keywords) and "login" in url.lower():
            await page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"{name}_fail.png"))
            return {"name": name, "email": email, "status": "FAIL",
                    "detail": "Credentials rejected"}

        # Check if still on login page (slow redirect)
        if "login" in url.lower():
            await asyncio.sleep(4)
            url = page.url

        if "login" in url.lower():
            await page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"{name}_stuck.png"))
            return {"name": name, "email": email, "status": "FAIL",
                    "detail": f"Still on login page: {url}"}

        # === LOGIN SUCCESS — scrape profile + usage ===
        await page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"{name}_login_ok.png"))

        profile = await scrape_profile(page)
        usage = await scrape_usage(page)
        await page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"{name}_usage.png"))

        # Merge and push to backend
        scraped = {**profile, **usage}

        account_id = find_account_id(email)
        if account_id:
            update_backend(account_id, scraped)
            detail_parts = []
            if profile.get("display_name"):
                detail_parts.append(f"name={profile['display_name']}")
            if profile.get("plan_type"):
                detail_parts.append(f"plan={profile['plan_type']}")
            if usage.get("daily_quota_pct") is not None:
                detail_parts.append(f"daily={usage['daily_quota_pct']}%")
            if usage.get("weekly_quota_pct") is not None:
                detail_parts.append(f"weekly={usage['weekly_quota_pct']}%")
            return {"name": name, "email": email, "status": "OK",
                    "detail": f"Logged in, updated DB: {', '.join(detail_parts)}",
                    "scraped": scraped}
        else:
            return {"name": name, "email": email, "status": "OK",
                    "detail": f"Logged in but account not found in DB",
                    "scraped": scraped}

    except Exception as e:
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        try:
            await page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"{name}_error.png"))
        except Exception:
            pass
        return {"name": name, "email": email, "status": "ERROR", "detail": str(e)[:200]}
    finally:
        await context.close()


async def main():
    total = len(ACCOUNTS)
    print(f"=== Windsurf Batch Login & Scrape ({total} accounts) ===")
    print(f"Backend API: {API_BASE}")
    print(f"Screenshots: {SCREENSHOT_DIR}\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)

        results = []
        for i, (name, email, password) in enumerate(ACCOUNTS, 1):
            print(f"[{i}/{total}] {name} ({email})...", flush=True)
            result = await login_one(browser, name, email, password)
            results.append(result)

            icon = {"OK": "+", "FAIL": "x", "ERROR": "!", "BLOCKED": "#"}.get(result["status"], "?")
            print(f"  [{icon}] {result['status']} — {result['detail']}")

            if i < total:
                await asyncio.sleep(3)

        await browser.close()

    # Summary
    print(f"\n{'='*70}")
    print(f"{'STATUS':8s} {'NAME':12s} {'EMAIL':32s} DETAIL")
    print(f"{'='*70}")
    for r in results:
        print(f"{r['status']:8s} {r['name']:12s} {r['email']:32s} {r.get('detail','')}")

    ok = sum(1 for r in results if r["status"] == "OK")
    print(f"\nTotal: {total}  |  OK: {ok}  |  Failed: {total - ok}")


if __name__ == "__main__":
    asyncio.run(main())

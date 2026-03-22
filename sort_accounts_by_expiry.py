#!/usr/bin/env python3
"""
Sort accounts in 账号密码.md and backend/.env by plan_expiry (ascending).

Usage:
    python sort_accounts_by_expiry.py

Accounts without expiry are placed at the end.
Accounts are grouped by expiry date with blank lines between groups.
"""

import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "backend" / "data" / "windsurf_manager.db"
MD_PATH = BASE_DIR / "账号密码.md"
ENV_PATH = BASE_DIR / "backend" / ".env"


def load_expiry_map() -> dict[str, str | None]:
    """Read email -> plan_expiry from the SQLite database."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT email, plan_expiry FROM accounts")
    mapping = {row[0].strip(): row[1] for row in cursor.fetchall()}
    conn.close()
    return mapping


def parse_expiry(expiry: str | None) -> datetime:
    """Parse 'Mar 28, 2026' style date; return far-future for missing values."""
    if not expiry:
        return datetime(9999, 12, 31)
    try:
        return datetime.strptime(expiry.strip(), "%b %d, %Y")
    except ValueError:
        return datetime(9999, 12, 31)


# ---------------------------------------------------------------------------
# 账号密码.md
# ---------------------------------------------------------------------------

def sort_md(expiry_map: dict[str, str | None]) -> None:
    if not MD_PATH.exists():
        print(f"[skip] {MD_PATH} not found")
        return

    text = MD_PATH.read_text(encoding="utf-8")
    entries: list[tuple[str, str, str | None]] = []  # (email, password, expiry)

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = re.split(r"\s{2,}", line, maxsplit=1)
        if len(parts) == 2:
            email, pwd = parts[0].strip(), parts[1].strip()
            entries.append((email, pwd, expiry_map.get(email)))

    entries.sort(key=lambda x: parse_expiry(x[2]))

    # Group by expiry
    groups: list[tuple[str, list[tuple[str, str]]]] = []
    for email, pwd, expiry in entries:
        key = expiry or "NO_EXPIRY"
        if groups and groups[-1][0] == key:
            groups[-1][1].append((email, pwd))
        else:
            groups.append((key, [(email, pwd)]))

    lines: list[str] = []
    for i, (_key, items) in enumerate(groups):
        if i > 0:
            lines.append("")
        for email, pwd in items:
            lines.append(f"{email}  {pwd}")

    MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[done] {MD_PATH}  — {len(entries)} accounts sorted")


# ---------------------------------------------------------------------------
# backend/.env
# ---------------------------------------------------------------------------

def sort_env(expiry_map: dict[str, str | None]) -> None:
    if not ENV_PATH.exists():
        print(f"[skip] {ENV_PATH} not found")
        return

    text = ENV_PATH.read_text(encoding="utf-8")
    account_pattern = re.compile(r'WINDSURF_ACCOUNT_\d+="(.+?)"')

    other_lines: list[str] = []
    account_entries: list[tuple[str, str, str | None]] = []

    for line in text.splitlines():
        m = account_pattern.match(line)
        if m:
            value = m.group(1)
            parts = re.split(r"\s{2,}", value.strip(), maxsplit=1)
            if len(parts) == 2:
                email, pwd = parts[0].strip(), parts[1].strip()
                account_entries.append((email, pwd, expiry_map.get(email)))
                continue
        if not line.startswith("WINDSURF_ACCOUNT_"):
            other_lines.append(line)

    account_entries.sort(key=lambda x: parse_expiry(x[2]))

    out_lines = list(other_lines)
    if out_lines and out_lines[-1].strip():
        out_lines.append("")
    for idx, (email, pwd, _) in enumerate(account_entries, 1):
        out_lines.append(f'WINDSURF_ACCOUNT_{idx:02d}="{email}  {pwd}"')

    ENV_PATH.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"[done] {ENV_PATH}  — {len(account_entries)} accounts sorted")


# ---------------------------------------------------------------------------

def main() -> None:
    if not DB_PATH.exists():
        print(f"[error] Database not found: {DB_PATH}")
        return

    expiry_map = load_expiry_map()
    print(f"Loaded {len(expiry_map)} accounts from database\n")

    sort_md(expiry_map)
    sort_env(expiry_map)

    print("\nAll done.")


if __name__ == "__main__":
    main()

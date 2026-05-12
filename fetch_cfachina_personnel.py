import csv
import json
import math
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://www.cfachina.org/orc-report/api/basic/personInfo"
COMP_ID = "0078"
PAGE_SIZE = 20
TIMEOUT = 20
RETRIES = 3
OUTPUT_CSV = Path("cfachina_personnel_0078.csv")


def post_json(url: str, params: dict, timeout: int = TIMEOUT):
    data = urlencode(params).encode("utf-8")
    req = Request(
        url,
        data=data,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Origin": "https://www.cfachina.org",
            "Referer": "https://www.cfachina.org/informationpublicity/futurescompanyinformantionpublicity/qhgsjbqk/qhgsxxgsxqy/?id=0078&organId=G01007&index=3",
        },
        method="POST",
    )
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_page(page_no: int):
    last_error = None
    for attempt in range(1, RETRIES + 1):
        try:
            return post_json(
                API,
                {
                    "pageNo": page_no,
                    "pageSize": PAGE_SIZE,
                    "compId": COMP_ID,
                    "flag": "",
                },
            )
        except Exception as e:
            last_error = e
            if attempt < RETRIES:
                time.sleep(1.5 * attempt)
    raise last_error


def main():
    first = fetch_page(1)
    data = first.get("data") or {}
    total = int(data.get("total") or 0)
    pages = math.ceil(total / PAGE_SIZE) if total else 0
    rows = list(data.get("dataList") or [])

    for page_no in range(2, pages + 1):
        page_data = fetch_page(page_no)
        rows.extend((page_data.get("data") or {}).get("dataList") or [])
        print(f"已抓取分页: {page_no}/{pages}")

    fields = [
        "name",
        "sex",
        "certNo",
        "analystCertNo",
        "department",
        "duty",
        "hireDate",
        "personId",
    ]

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})

    print(f"总人数: {total}")
    print(f"总分页: {pages}")
    print(f"实际写入: {len(rows)}")
    print(f"输出文件: {OUTPUT_CSV.resolve()}")


if __name__ == "__main__":
    main()

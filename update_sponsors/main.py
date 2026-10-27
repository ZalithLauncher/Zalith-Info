#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import sys
import time
import hashlib

import requests
from datetime import datetime, timedelta, timezone

AFDIAN_USER_ID = os.environ.get("AFDIAN_USER_ID")
AFDIAN_TOKEN = os.environ.get("AFDIAN_TOKEN")

# 爱发电会拦截部分海外数据中心 IP，返回非 JSON 的拦截页，两个官方域名互为备援
AFDIAN_API_HOSTS = ("https://afdian.com", "https://ifdian.net")
AFDIAN_ORDER_API_PATH = "/api/open/query-order"
AFDIAN_SPONSOR_API_PATH = "/api/open/query-sponsor"
AFDIAN_PLAN_API_PATH = "/api/open/query-plan"

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
    " (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
}
REQUEST_RETRY = 3
REQUEST_RETRY_INTERVAL = 2

BEIJING_TZ = timezone(timedelta(hours=8))
LAUNCHER_SPONSOR_FILE = "launcher_sponsor.json"
MONTHLY_FILE = "monthly_sponsors.json"


def get_params(page=1, per_page=100):
    return json.dumps({"page": page, "per_page": per_page})


def make_sign(token: str, user_id: str, params: str, ts: int) -> str:
    raw_str = f"{token}" f"params{params}" f"ts{ts}" f"user_id{user_id}"

    md5_obj = hashlib.md5(raw_str.encode("utf-8"))
    sign = md5_obj.hexdigest()
    return sign


def make_payload(params: str) -> dict:
    ts = int(time.time())
    return {
        "user_id": AFDIAN_USER_ID,
        "params": params,
        "ts": ts,
        "sign": make_sign(
            token=AFDIAN_TOKEN, user_id=AFDIAN_USER_ID, params=params, ts=ts
        ),
    }


def request_api(api_path: str, payload: dict) -> dict:
    attempts = len(AFDIAN_API_HOSTS) * REQUEST_RETRY
    for attempt in range(1, attempts + 1):
        url = AFDIAN_API_HOSTS[(attempt - 1) % len(AFDIAN_API_HOSTS)] + api_path
        try:
            response = requests.post(
                url, json=payload, timeout=10, headers=REQUEST_HEADERS
            )
            return response.json()
        except requests.RequestException as exc:
            print(f"[WARN] Request to {url} failed (attempt {attempt}): {exc}")
        except ValueError:
            print(
                f"[WARN] {url} returned a non-JSON body (attempt {attempt}): "
                f"status={response.status_code} body={response.text[:300]!r}"
            )
        time.sleep(REQUEST_RETRY_INTERVAL)

    print(f"[ERROR] Cannot get information from {api_path} after {attempts} attempts")
    sys.exit(1)


def fetch_data(api_path: str, per_page=50):
    page = 1
    retry_count = 0
    results = []

    while True:
        params = get_params(page=page, per_page=per_page)
        data = request_api(api_path, make_payload(params))

        if data.get("ec") != 200:
            retry_count += 1
            print(f"[WARN] API returned error (attempt {retry_count}): {data}")
            if retry_count >= 3:
                print(f"[ERROR] Cannot get information from {api_path}")
                sys.exit(1)
            time.sleep(2)
            continue

        results.extend(data.get("data", {}).get("list", []))

        if data.get("data", {}).get("total_page") == page:
            break

        page += 1

    return results


def fetch_plans(plan_ids):
    plans = {}
    for plan_id in plan_ids:
        params = json.dumps({"plan_id": plan_id})
        data = request_api(AFDIAN_PLAN_API_PATH, make_payload(params))
        if data.get("ec") == 200:
            plan = data.get("data", {}).get("plan", {})
            raw_price = plan.get("price")
            plans[plan_id] = {
                "name": plan.get("name", ""),
                "price": float(raw_price) if raw_price is not None else None,
            }
        else:
            print(f"[WARN] query-plan failed for {plan_id}: {data}")
    return plans


def build_sponsor_map(sponsor_items):
    sponsor_map = {}
    for item in sponsor_items:
        user = item.get("user", {})
        if user.get("user_id"):
            sponsor_map[user["user_id"]] = user
    return sponsor_map


def beijing_month(ts: int) -> str:
    return datetime.fromtimestamp(ts, BEIJING_TZ).strftime("%Y-%m")


def beijing_date(ts: int) -> str:
    return datetime.fromtimestamp(ts, BEIJING_TZ).strftime("%Y/%m/%d")


def previous_month(month: str) -> str:
    year, mon = int(month[:4]), int(month[5:7])
    if mon == 1:
        return f"{year - 1}-12"
    return f"{year}-{mon - 1:02d}"


def build_monthly_entries(orders, sponsor_map, plans):
    entries = []
    for item in orders:
        user = sponsor_map.get(item.get("user_id"))
        plan_id = item.get("plan_id") or ""
        if plan_id:
            plan_info = plans.get(plan_id)
            plan_name = plan_info["name"] if plan_info else ""
            plan_price = plan_info["price"] if plan_info else None
        else:
            plan_name = "自选金额"
            plan_price = float(item.get("total_amount"))
        entries.append(
            {
                "user": {
                    "name": user["name"] if user else "匿名赞助者",
                    "avatar": user["avatar"] if user else "",
                },
                "time": beijing_date(item["create_time"]),
                "plan": {
                    "id": plan_id,
                    "name": plan_name,
                    "price": plan_price,
                    "total_amount": float(item.get("total_amount")),
                    "show_amount": float(item.get("show_amount")),
                    "count": item.get("month", 1),
                },
            }
        )
    return entries


def update_monthly_sponsors(order_items, sponsor_map):
    paid_orders = [o for o in order_items if o.get("status") == 2]
    if not paid_orders:
        print("[INFO] No successful orders found; monthly file left unchanged.")
        return

    current = beijing_month(max(o["create_time"] for o in paid_orders))
    last = previous_month(current)
    current_orders = [
        o for o in paid_orders if beijing_month(o["create_time"]) == current
    ]
    last_orders = [
        o for o in paid_orders if beijing_month(o["create_time"]) == last
    ]

    plan_ids = sorted(
        {o["plan_id"] for o in current_orders + last_orders if o.get("plan_id")}
    )
    plans = fetch_plans(plan_ids)

    with open(MONTHLY_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "month": current,
                "sponsors": build_monthly_entries(current_orders, sponsor_map, plans),
                "last_month": {
                    "month": last,
                    "list": build_monthly_entries(last_orders, sponsor_map, plans),
                },
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(
        f"[INFO] Successfully updated {MONTHLY_FILE}: settled {last}"
        f" ({len(last_orders)} entries), current {current}"
        f" ({len(current_orders)} entries)."
    )


def update_launcher_sponsor(order_items, sponsor_map):
    orders = []
    for item in order_items:
        user = sponsor_map.get(item.get("user_id"))
        orders.append(
            {
                "name": user["name"],
                "time": datetime.fromtimestamp(
                    item.get("create_time")
                ).strftime("%Y/%m/%d"),
                "identifier": item.get("out_trade_no"),
                "avatar": user["avatar"],
                "amount": float(item.get("total_amount")),
            }
        )

    if os.path.exists(LAUNCHER_SPONSOR_FILE):
        with open(LAUNCHER_SPONSOR_FILE, "r", encoding="utf-8") as file:
            local_sponsor_content = json.loads(file.read())
            local_sponsor_list = local_sponsor_content.get("sponsors", [])

        updated_sponsor_list_correct = []
        for new_order in orders:
            new_identifier = new_order["identifier"]
            found = False
            for old_order in reversed(local_sponsor_list):
                old_identifier = old_order["identifier"]
                if new_identifier == old_identifier:
                    old_order["avatar"] = new_order["avatar"]
                    updated_sponsor_list_correct.append(old_order)
                    found = True
                    break
            if not found:
                print(f"[INFO] New data has been added to the list: {new_identifier}")
                updated_sponsor_list_correct.append(new_order)

        orders = updated_sponsor_list_correct

    with open(LAUNCHER_SPONSOR_FILE, "w", encoding="utf-8") as f:
        json.dump({"sponsors": orders}, f, ensure_ascii=False, indent=2)

    print(
        "[INFO] Successfully updated launcher_sponsor.json with sponsors data from AFDian."
    )


def main():
    sponsor_items = fetch_data(AFDIAN_SPONSOR_API_PATH)
    order_items = fetch_data(AFDIAN_ORDER_API_PATH)

    if not order_items:
        print("No order data fetched or API error.")
        return

    sponsor_map = build_sponsor_map(sponsor_items)

    update_launcher_sponsor(order_items, sponsor_map)
    update_monthly_sponsors(order_items, sponsor_map)


if __name__ == "__main__":
    main()

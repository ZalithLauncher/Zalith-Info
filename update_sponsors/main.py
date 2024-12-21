#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import sys
import time
import hashlib

import requests
from datetime import datetime

AFDIAN_USER_ID = os.environ.get("AFDIAN_USER_ID")
AFDIAN_TOKEN = os.environ.get("AFDIAN_TOKEN")

AFDIAN_ORDER_API_URL = "https://afdian.com/api/open/query-order"
AFDIAN_SPONSOR_API_URL = "https://afdian.com/api/open/query-sponsor"


def get_params(page=1, per_page=100):
    return json.dumps({"page": page, "per_page": per_page})


def make_sign(token: str, user_id: str, params: str, ts: int) -> str:
    raw_str = f"{token}" f"params{params}" f"ts{ts}" f"user_id{user_id}"

    md5_obj = hashlib.md5(raw_str.encode("utf-8"))
    sign = md5_obj.hexdigest()
    return sign


def fetch_data(api_url: str, process_item_func, per_page=50):
    page = 1
    count = 1
    results = []

    while True:
        params = get_params(page=page, per_page=per_page)
        ts = int(time.time())

        sign = make_sign(
            token=AFDIAN_TOKEN, user_id=AFDIAN_USER_ID, params=params, ts=ts
        )

        payload = {
            "user_id": AFDIAN_USER_ID,
            "params": params,
            "ts": ts,
            "sign": sign,
        }

        response = requests.post(api_url, json=payload, timeout=10)
        data = response.json()

        if count >= 4:
            print(f"[ERROR] Cannot get information from {api_url}")
            print(data)
            sys.exit(1)
        count += 1

        item_list = data.get("data", {}).get("list", [])
        for item in item_list:
            processed_item = process_item_func(item)
            if processed_item:
                results.append(processed_item)

        if data.get("data", {}).get("total_page") == page:
            break

        page += 1

    return results


def process_sponsor(item):
    user = item.get("user", {})
    return {
        "user_id": user.get("user_id"),
        "user_name": user.get("name"),
    }


def process_order(item, sponsor_map):
    user_id = item.get("user_id")
    pay_time = item.get("create_time")
    pay_amount = item.get("total_amount")

    user_name = sponsor_map.get(user_id, None)

    return {
        "name": user_name,
        "time": datetime.fromtimestamp(pay_time).strftime("%Y/%m/%d"),
        "amount": float(pay_amount),
    }


def fetch_sponsors():
    sponsors = fetch_data(AFDIAN_SPONSOR_API_URL, process_sponsor)
    return {sponsor["user_id"]: sponsor["user_name"] for sponsor in sponsors}


def fetch_orders():
    sponsor_map = fetch_sponsors()
    return fetch_data(
        AFDIAN_ORDER_API_URL,
        lambda item: process_order(item, sponsor_map)
    )



def main():
    orders_data = fetch_orders()
    if not orders_data:
        print("No order data fetched or API error.")
        return

    result_json = {"sponsors": orders_data}

    with open("launcher_sponsor.json", "w", encoding="utf-8") as f:
        json.dump(result_json, f, ensure_ascii=False, indent=2)

    print(
        "[INFO] Successfully updated launcher_sponsor.json with sponsors data from AFDian."
    )


if __name__ == "__main__":
    main()

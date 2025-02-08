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
        "avatar": user.get("avatar"),
    }


def process_order(item, sponsors):
    out_trade_no = item.get("out_trade_no")
    user_id = item.get("user_id")
    pay_time = item.get("create_time")
    pay_amount = item.get("total_amount")

    sponsor_name_map = {
        sponsor["user_id"]: {
            "name": sponsor["user_name"],
            "avatar": sponsor["avatar"]
        } for sponsor in sponsors
    }
    user = sponsor_name_map.get(user_id, None)

    return {
        "name": user["name"],
        "time": datetime.fromtimestamp(pay_time).strftime("%Y/%m/%d"),
        "identifier": out_trade_no,
        "avatar": user["avatar"],
        "amount": float(pay_amount),
    }


def fetch_orders():
    sponsors = fetch_data(AFDIAN_SPONSOR_API_URL, process_sponsor)
    return fetch_data(
        AFDIAN_ORDER_API_URL,
        lambda item: process_order(item, sponsors)
    )



def main():
    orders_data = fetch_orders()

    if not orders_data:
        print("No order data fetched or API error.")
        return

    sponsor_file = "launcher_sponsor.json"

    if os.path.exists(sponsor_file):
        with open(sponsor_file, 'r', encoding='utf-8') as file:
            local_sponsor_content = json.loads(file.read())
            local_sponsor_list = local_sponsor_content.get("sponsors", [])

        updated_sponsor_list_correct = []
        for new_order in orders_data:
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

        orders_data = updated_sponsor_list_correct

    result_json = {"sponsors": orders_data}

    with open(sponsor_file, "w", encoding="utf-8") as f:
        json.dump(result_json, f, ensure_ascii=False, indent=2)

    print(
        "[INFO] Successfully updated launcher_sponsor.json with sponsors data from AFDian."
    )


if __name__ == "__main__":
    main()

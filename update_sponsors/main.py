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

AFDIAN_API_URL = "https://afdian.com/api/open/query-sponsor"


def get_params(page=1, per_page=100):
    return json.dumps({"page": page, "per_page": per_page})


def make_sign(token: str, user_id: str, params: str, ts: int) -> str:
    raw_str = f"{token}" f"params{params}" f"ts{ts}" f"user_id{user_id}"

    md5_obj = hashlib.md5(raw_str.encode("utf-8"))
    sign = md5_obj.hexdigest()
    return sign


def fetch_sponsors():
    page = 1
    count = 1
    all_sponsors = []

    while True:
        params = get_params(page=page, per_page=50)
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

        response = requests.post(AFDIAN_API_URL, json=payload, timeout=10)
        data = response.json()
        if count >= 4:
            print("[ERROR] Cannot get information from AFDian")
            print(data)
            sys.exit(1)
        count += 1

        sponsor_list = data.get("data", {}).get("list", [])

        for sponsor in sponsor_list:
            name = sponsor.get("user").get("name")
            pay_time = sponsor.get("last_pay_time")
            pay_amount = sponsor.get("current_plan").get("price", 0.0)

            all_sponsors.append(
                {
                    "name": name,
                    "time": datetime.fromtimestamp(pay_time).strftime("%Y/%m/%d"),
                    "amount": float(pay_amount),
                }
            )
        if data.get("data", {}).get("total_page") is page:
            break

        page += 1

    return all_sponsors


def main():
    sponsors_data = fetch_sponsors()
    if not sponsors_data:
        print("No sponsor data fetched or API error.")
        return

    result_json = {"sponsors": sponsors_data}

    with open("launcher_sponsor.json", "w", encoding="utf-8") as f:
        json.dump(result_json, f, ensure_ascii=False, indent=2)

    print(
        "[INFO] Successfully updated launcher_sponsor.json with sponsors data from AFDian."
    )


if __name__ == "__main__":
    main()

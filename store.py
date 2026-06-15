# -*- coding: utf-8 -*-
"""Kho dữ liệu nguồn hàng — JSON file đơn giản (data/listings.json)."""
import json
import os

DB = os.path.join(os.path.dirname(__file__), "data", "listings.json")


def load():
    if not os.path.exists(DB):
        return []
    with open(DB, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def save(items):
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    with open(DB, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

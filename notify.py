# -*- coding: utf-8 -*-
"""
Quét lô MỚI (so với lần refresh trước) khớp hồ sơ khách -> ping Telegram.
Chạy trong container sau khi nạp data mới:
  docker exec -e BOT_TOKEN=... -e CHAT_ID=... bds-agent python /app/notify.py
Lần đầu chỉ lưu snapshot (chưa báo). Từ lần 2 trở đi báo lô mới khớp.
"""
import os, json, urllib.parse, urllib.request
import app_bundle as A

TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT = os.environ.get("CHAT_ID", "")
SNAP = "/app/data/.prev_ids.json"


def send(txt):
    if not (TOKEN and CHAT):
        print("Thiếu BOT_TOKEN/CHAT_ID"); return
    data = urllib.parse.urlencode({"chat_id": CHAT, "text": txt}).encode()
    urllib.request.urlopen("https://api.telegram.org/bot" + TOKEN + "/sendMessage", data=data, timeout=20)


items = A.load()
cur = {it.get("id") for it in items if it.get("id")}
prev = set(json.load(open(SNAP))) if os.path.exists(SNAP) else None
json.dump(list(cur), open(SNAP, "w"))  # cập nhật snapshot

if prev is None:
    print("Lần đầu: đã lưu snapshot, chưa báo."); raise SystemExit

new_ids = cur - prev
new_codes = {it["code"] for it in items if it.get("id") in new_ids}
if not new_codes:
    print("Không có lô mới."); raise SystemExit

new_items = [it for it in items if it.get("code") in new_codes]
alerts = []
for c in A.load_customers():
    res = A._filter(new_items, A.parse_query(c["need"]))
    if res:
        res.sort(key=lambda it: (it.get("gia_trieu") is None, it.get("gia_trieu") or 0))
        codes = ", ".join(it["code"] for it in res[:8])
        alerts.append(f"🔔 {c['name']} — {len(res)} lô MỚI khớp ({c['need']}): {codes}")

print(f"Lô mới: {len(new_codes)} | khách khớp: {len(alerts)}")
if alerts:
    send("🆕 LÔ MỚI KHỚP KHÁCH:\n" + "\n".join(alerts) + "\n(Nhắn mã TK để xem chi tiết + SĐT)")
    print("Đã gửi cảnh báo.")

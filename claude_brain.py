# -*- coding: utf-8 -*-
"""
NÂNG CẤP: thay "bộ não" rule-based bằng Claude thật.
Đây là minh hoạ bài 14.01 ("swap ToyLLM for a real provider") và 14.17
(Claude Agent SDK). VÒNG LẶP trong agent.py KHÔNG đổi — chỉ thay hàm quyết định.

Cài: pip install anthropic   (và đặt ANTHROPIC_API_KEY)
Dùng: sửa agent.py -> import brain_decide từ file này thay vì hàm rule-based.
"""
import json
import os

TOOLS_DESC = """
Bạn là trợ lý quản lý nguồn hàng bất động sản. Có 3 tool:
- add_listing(text): lưu một tin rao nhà/đất.
- search_listings(query): tìm nguồn theo yêu cầu.
- stats(): thống kê kho.
Nhìn tin nhắn cuối của user, trả về JSON:
{"action":"add_listing|search_listings|stats|finish","arg":"...","answer":"..."}
- Nếu là tin rao -> add_listing. Nếu là câu hỏi -> search_listings.
- Nếu lượt cuối là kết quả tool (role=tool) -> finish, answer = diễn đạt lại tự nhiên.
"""


def brain_decide(buffer):
    """Cùng chữ ký với hàm rule-based trong agent.py -> thay 1-1."""
    from anthropic import Anthropic  # import trễ để không bắt buộc cài

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    convo = "\n".join(f"[{m['role']}] {m['content']}" for m in buffer[-8:])
    msg = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=400,
        system=TOOLS_DESC,
        messages=[{"role": "user", "content": convo}],
    )
    raw = msg.content[0].text.strip()
    raw = raw[raw.find("{"): raw.rfind("}") + 1]
    d = json.loads(raw)
    if d["action"] == "finish":
        return ("finish", d.get("answer", ""))
    return ("action", d["action"], d.get("arg", ""))

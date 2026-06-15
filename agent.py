# -*- coding: utf-8 -*-
"""
Agent nguồn hàng BĐS — minh hoạ Agent Loop (bài 14.01) với 5 thành phần:
  1) message buffer   2) tool registry   3) stop condition
  4) turn budget      5) observation formatter

Bộ não (brain) hiện là rule-based router. Muốn thông minh hơn: thay hàm
`brain_decide` bằng 1 lời gọi Claude (xem claude_brain.py) — vòng lặp giữ nguyên.
"""
import sys
from extractor import strip_accents
from tools import REGISTRY

MAX_TURNS = 5  # (4) turn budget — chặn loop vô tận


def looks_like_listing(text: str) -> bool:
    t = strip_accents(text)
    rao_kw = ["ban ", "ban\n", "can ban", "chinh chu", "lien he", "lh ", "gia ",
              "dien tich", "dt ", "so do", "sodo", "m2", "mat tien"]
    has_kw = any(k in t for k in rao_kw)
    has_digit = any(c.isdigit() for c in text)
    is_question = "?" in text or t.strip().startswith(("co ", "tim", "lo nao", "co lo", "list"))
    return has_kw and has_digit and not is_question


def brain_decide(buffer):
    """
    (Bộ não) Nhìn buffer -> quyết định: gọi tool (action) hay trả lời (finish).
    Trả: ('action', tool_name, arg)  HOẶC  ('finish', text)
    """
    last = buffer[-1]
    # Nếu lượt cuối là observation (kết quả tool) -> chốt, trả cho user.
    if last["role"] == "tool":
        return ("finish", last["content"])

    text = last["content"]
    t = strip_accents(text)

    if any(k in t for k in ["thong ke", "bao nhieu nguon", "co bao nhieu", "/stats"]):
        return ("action", "stats", "")
    if looks_like_listing(text):
        return ("action", "add_listing", text)
    # còn lại coi là câu hỏi tìm nguồn
    return ("action", "search_listings", text)


def run_turn(buffer, user_text, verbose=True):
    """Một lần xử lý input user qua trọn vòng lặp Observe→Think→Act→...→Stop."""
    buffer.append({"role": "user", "content": user_text})  # (1) buffer phình
    for _ in range(MAX_TURNS):                              # (4) turn budget
        decision = brain_decide(buffer)
        if decision[0] == "finish":                         # (3) stop condition
            answer = decision[1]
            buffer.append({"role": "assistant", "content": answer})
            return answer
        _, tool_name, arg = decision
        fn = REGISTRY.get(tool_name)
        if verbose:
            print(f"   🤔 Think→Act: gọi tool `{tool_name}`")
        obs = fn(arg) if fn else f"[lỗi] không có tool {tool_name}"
        # (5) observation formatter: kết quả tool -> chuỗi cho lượt sau
        buffer.append({"role": "tool", "content": obs})
    return "Hết turn budget mà chưa chốt được."


SEED = [
    "Bán đất nền Sóc Sơn 100m2 hướng Đông Nam, giá 1.8 tỷ, sổ đỏ chính chủ. LH 0987654321",
    "Cần bán nhà phố Hà Đông 60m2, 4 tầng, giá 5.5 tỷ, liên hệ 0911222333",
    "Bán đất thổ cư Đông Anh 80m2 giá 2 tỷ, mặt tiền 5m, 0905111222",
    "Chính chủ bán đất nông nghiệp Ba Vì 1 sào (360m2) giá 850 triệu. LH 0966777888",
    "Bán chung cư Long Biên 70m2 2PN giá 3.2 tỷ hướng Tây Nam 0900123456",
]


def demo():
    import store
    store.save([])  # reset kho cho demo sạch
    buf = []
    print("=== NẠP 5 tin nguồn hàng (giả lập từ Zalo) ===")
    for tin in SEED:
        print("👤", tin[:55], "...")
        print("🤖", run_turn(buf, tin, verbose=False), "\n")
    print("=== HỎI TỰ NHIÊN ===")
    for q in ["Có lô nào ở Sóc Sơn dưới 2 tỷ không?",
              "Tìm đất Đông Anh trên 70m2",
              "Nhà phố dưới 6 tỷ",
              "thống kê nguồn hàng"]:
        print("👤", q)
        print("🤖", run_turn(buf, q), "\n")


def repl():
    print("Agent nguồn hàng BĐS. Dán tin rao để LƯU, hoặc hỏi tự nhiên để TÌM.")
    print("Gõ 'thống kê' để xem kho, Ctrl+C để thoát.\n")
    buf = []
    while True:
        try:
            txt = input("👤 ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nTạm biệt.")
            break
        if not txt:
            continue
        print("🤖", run_turn(buf, txt), "\n")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    else:
        repl()

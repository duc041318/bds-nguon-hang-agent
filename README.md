# 🏘️ Agent Nguồn Hàng BĐS

Trợ lý lưu & tra cứu nguồn hàng nhà/đất bằng ngôn ngữ tự nhiên — **chạy ngay, không cần API key**.
Đây là bản áp dụng thực tế của 2 bài học: **Agent Loop** (14.01) + **Claude Agent SDK** (14.17).

## Dùng nhanh
```bash
cd bds-nguon-hang-agent
set PYTHONIOENCODING=utf-8      # Windows (PowerShell: $env:PYTHONIOENCODING="utf-8")
python agent.py --demo         # xem demo nạp 5 tin + hỏi tự nhiên
python agent.py                # chế độ chat: dán tin rao để LƯU, hỏi để TÌM
```

### Ví dụ
- **Lưu:** `Bán đất nền Sóc Sơn 100m2 hướng Đông Nam, giá 1.8 tỷ. LH 0987654321`
- **Hỏi:** `Có lô nào ở Sóc Sơn dưới 2 tỷ không?` → trả về đúng lô khớp
- **Thống kê:** `thống kê nguồn hàng`

## Đây là Agent Loop thật — 5 thành phần (bài 14.01)
| # | Thành phần | Ở đâu trong code |
|---|-----------|------------------|
| 1 | Message buffer | `buffer` trong `run_turn` (agent.py) |
| 2 | Tool registry | `REGISTRY` (tools.py): `add_listing`, `search_listings`, `stats` |
| 3 | Stop condition | `decision[0] == "finish"` |
| 4 | Turn budget | `MAX_TURNS = 5` |
| 5 | Observation formatter | kết quả tool → chuỗi đẩy lại buffer |

Luồng mỗi lượt: **user → Think (brain chọn tool) → Act (chạy tool) → Observation → Finish (trả lời)**.

## Cấu trúc
```
bds-nguon-hang-agent/
├── agent.py         # Agent Loop + CLI (--demo / chat)
├── tools.py         # Tool registry (lưu/tìm/thống kê)
├── extractor.py     # "Bộ não" rule-based: tách giá/diện tích/vị trí/loại/hướng/SĐT
├── claude_brain.py  # NÂNG CẤP: thay bộ não bằng Claude (1 hàm, vòng lặp giữ nguyên)
├── store.py         # Kho JSON
└── data/listings.json
```

## Nâng cấp lên Claude (đúng bài học)
Bài 14.01 dạy: *"thay ToyLLM bằng provider thật là có agent production"*. Ở đây:
1. `pip install anthropic`, đặt `ANTHROPIC_API_KEY`.
2. Trong `agent.py` đổi `from tools import REGISTRY` + dùng `brain_decide` của **claude_brain.py** thay hàm rule-based.
3. Vòng lặp, tool, kho — **không đổi gì**. Đây chính là điểm cốt lõi của Agent Loop.

## Hướng phát triển tiếp (gắn dự án Zalo của anh)
- **Nguồn vào tự động:** nối n8n đọc nhóm Zalo "BDS Hà Nội Gold" → gọi `add_listing` cho mỗi tin.
- **Hỏi qua Zalo:** webhook tin nhắn → `search_listings` → trả lời.
- **Trùng/đã bán:** thêm tool `mark_sold`, dedupe theo SĐT + vị trí.
- **Bộ não Claude:** trích xuất chính xác hơn (giá "1ty750", "giá TL", viết tắt) so với regex.
```

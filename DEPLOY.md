# 🚀 Deploy: n8n + Agent BĐS + Telegram (VPS Hostinger)

Kiến trúc:
```
Telegram bot  ──►  n8n (Telegram Trigger)  ──HTTP──►  Agent API (FastAPI)  ──►  listings.json
      ▲                                                       │
      └──────────────  n8n gửi trả lời  ◄────────────────────┘
```

> ⚠️ **Các bước tạo tài khoản / nhập mật khẩu / token là anh tự làm** (mình không thao tác credential giúp được). Chỗ nào "ANH LÀM" là anh bấm.

---

## Bước 1 — Cài n8n trên VPS Hostinger  *(ANH LÀM)*
Hostinger có template VPS cài sẵn n8n:
1. hPanel → **VPS** → VPS của anh → **OS & Panel** (hoặc "Operating System") → chọn template **n8n** → cài.
2. Sau khi cài xong, mở `https://<IP-VPS>:5678` (hoặc domain Hostinger gán).
3. Lần đầu vào → **Set up owner account**: nhập **email `ducnv041318@gmail.com`** + mật khẩu anh tự đặt → đây chính là "tạo nick".

> Nếu template chạy n8n bằng Docker sẵn, ghi lại **tên network Docker** của n8n: `docker network ls` (thường `root_default` hoặc tương tự) — cần ở Bước 3.

## Bước 2 — Tạo Telegram bot  *(ANH LÀM)*
1. Mở Telegram, chat với **@BotFather** → `/newbot` → đặt tên + username.
2. BotFather trả về **bot token** (dạng `123456:ABC...`). Giữ kỹ.

## Bước 3 — Đưa Agent API lên VPS
SSH vào VPS rồi:
```bash
# copy thư mục bds-nguon-hang-agent lên VPS (scp/git). Ví dụ đặt ở /opt/bds-agent
cd /opt/bds-agent

# tạo file .env (đổi token bí mật)
cp .env.example .env
nano .env        # đặt API_TOKEN=<chuỗi ngẫu nhiên>, N8N_HOST=<IP hoặc domain>
```

**Cách A — chưa có n8n, dựng cả cụm bằng compose này:**
```bash
docker compose up -d --build
# n8n: http://<IP>:5678 , agent nội bộ: http://agent:8000
```

**Cách B — đã dùng n8n template Hostinger, chỉ thêm agent:**
```bash
docker build -t bds-agent .
docker run -d --name bds-agent --restart unless-stopped \
  --network <ten-network-n8n> \
  -e API_TOKEN=<chuỗi bí mật> \
  -v /opt/bds-agent/data:/app/data \
  bds-agent
# n8n giờ gọi được http://bds-agent:8000  (tên container = hostname trong network)
```
Kiểm tra:
```bash
docker exec -it n8n wget -qO- http://agent:8000/health   # hoặc http://bds-agent:8000/health
# kỳ vọng: {"ok":true}
```

## Bước 4 — Cấu hình trong n8n  *(ANH LÀM phần credential)*
1. n8n → **Credentials → New → Telegram API** → dán **bot token** (Bước 2) → Save.
2. Đặt biến môi trường `API_TOKEN` cho n8n **trùng** với token agent (để header khớp). Nếu dùng compose Cách A, thêm `- API_TOKEN=${API_TOKEN}` vào service `n8n` rồi `docker compose up -d`.
3. **Import workflow**: n8n → **Workflows → Import from File** → chọn `n8n-workflow-telegram.json`.
4. Mở workflow → ở 2 node Telegram, chọn lại **credential** vừa tạo. Kiểm tra node "Goi Agent API" URL = `http://agent:8000/message` (Cách A) hoặc `http://bds-agent:8000/message` (Cách B).
5. **Activate** workflow (bật góc trên phải). n8n tự đăng ký webhook Telegram (cần n8n chạy HTTPS / `WEBHOOK_URL` đúng).

## Bước 5 — Test thật
- Nhắn cho bot: `Bán đất nền Sóc Sơn 100m2 hướng Đông Nam giá 1.8 tỷ 0987654321`
  → bot trả: `Đã lưu nguồn hàng: ...`
- Nhắn: `có lô nào Sóc Sơn dưới 2 tỷ không?`
  → bot trả danh sách khớp.
- Nhắn: `thống kê nguồn hàng` → trả số liệu.

---

## Lưu ý vận hành
- **Bảo mật:** agent KHÔNG mở port ra internet (chỉ n8n nội bộ gọi qua Docker network). Giữ `API_TOKEN`.
- **Backup data:** chỉ cần copy `data/listings.json`.
- **Nâng cấp bộ não:** muốn trích xuất chính xác hơn (viết tắt, "giá TL", "1ty750") → bật `claude_brain.py` (cần `ANTHROPIC_API_KEY`), thay `brain_decide` trong `agent.py`. Vòng lặp/agent không đổi.
- **Zalo:** nếu sau này có Zalo OA doanh nghiệp, thêm 1 nhánh "Zalo OA webhook → cùng node Goi Agent API". Telegram vẫn chạy song song.

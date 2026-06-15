# -*- coding: utf-8 -*-
"""
Bộ trích xuất (extractor) — đóng vai "bộ não" rule-based.
Đây chính là chỗ tương ứng `ToyLLM` trong bài 14.01:
  - Hôm nay: tách thông tin bằng regex (chạy ngay, 0 chi phí).
  - Mai mốt: thay 2 hàm parse_listing / parse_query bằng 1 lời gọi Claude
    (xem claude_brain.py) là agent thông minh hơn ngay, KHÔNG đổi vòng lặp.
"""
import re
import unicodedata


def strip_accents(s: str) -> str:
    """Bỏ dấu tiếng Việt + về chữ thường để so khớp dễ."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D").lower()


# ---- Giá: trả về số triệu VND ----
def parse_price(text: str):
    t = strip_accents(text)
    # 2 ty, 2.5 ty, 2,5 ti  -> tỷ
    m = re.search(r"(\d+[.,]?\d*)\s*(ty|ti)\b", t)
    if m:
        return float(m.group(1).replace(",", ".")) * 1000
    # 850 trieu, 850tr
    m = re.search(r"(\d+[.,]?\d*)\s*(trieu|tr)\b", t)
    if m:
        return float(m.group(1).replace(",", "."))
    return None


# ---- Diện tích: trả về m2 ----
def parse_area(text: str):
    t = strip_accents(text)
    m = re.search(r"(\d+[.,]?\d*)\s*(hecta|héc|ha)\b", t)
    if m:
        return float(m.group(1).replace(",", ".")) * 10000
    m = re.search(r"(\d+[.,]?\d*)\s*(sao)\b", t)  # sào Bắc Bộ = 360 m2
    if m:
        return float(m.group(1).replace(",", ".")) * 360
    m = re.search(r"(\d+[.,]?\d*)\s*(m2|m²|m)\b", t)
    if m:
        return float(m.group(1).replace(",", "."))
    return None


def parse_type(text: str):
    t = strip_accents(text)
    table = [
        ("dat nen", "đất nền"), ("dat tho cu", "đất thổ cư"),
        ("dat nong nghiep", "đất nông nghiệp"), ("dat", "đất"),
        ("chung cu", "chung cư"), ("can ho", "căn hộ"),
        ("nha pho", "nhà phố"), ("biet thu", "biệt thự"),
        ("nha", "nhà"), ("kho xuong", "kho xưởng"), ("nha xuong", "kho xưởng"),
    ]
    for key, label in table:
        # khớp theo ranh giới từ để tránh "khong" -> "kho", "nhanh" -> "nha"
        if re.search(r"\b" + re.escape(key) + r"\b", t):
            return label
    return None


def parse_phone(text: str):
    m = re.search(r"(0\d{9})\b", text.replace(".", "").replace(" ", ""))
    return m.group(1) if m else None


def parse_direction(text: str):
    t = strip_accents(text)
    for key, label in [("dong nam", "Đông Nam"), ("tay nam", "Tây Nam"),
                       ("dong bac", "Đông Bắc"), ("tay bac", "Tây Bắc"),
                       ("huong dong", "Đông"), ("huong tay", "Tây"),
                       ("huong nam", "Nam"), ("huong bac", "Bắc")]:
        if key in t:
            return label
    return None


# ---- Vị trí: lấy cụm sau từ khoá địa điểm, fallback = dò từ điển ----
PLACES = ["sóc sơn", "đông anh", "mê linh", "ba vì", "hoài đức", "thạch thất",
          "gia lâm", "long biên", "hà đông", "bắc ninh", "hưng yên", "hà nội"]


def parse_location(text: str):
    m = re.search(r"(?:tại|ở|khu|xã|huyện|thôn|đường|kđt)\s+([^\.,;\n]{2,40})",
                  text, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    t = strip_accents(text)
    for p in PLACES:
        if strip_accents(p) in t:
            return p.title()
    return None


def parse_listing(text: str) -> dict:
    """Tin nhắn rao thô -> bản ghi có cấu trúc."""
    return {
        "raw": text.strip(),
        "loai": parse_type(text),
        "gia_trieu": parse_price(text),
        "dien_tich_m2": parse_area(text),
        "huong": parse_direction(text),
        "vi_tri": parse_location(text),
        "lien_he": parse_phone(text),
    }


def parse_query(text: str) -> dict:
    """Câu hỏi tự nhiên -> bộ lọc."""
    t = strip_accents(text)
    price = parse_price(text)
    # vị trí trong câu hỏi: ưu tiên khớp từ điển địa danh (gọn, chính xác)
    vi_tri = None
    for p in PLACES:
        if strip_accents(p) in t:
            vi_tri = p.title()
            break
    if not vi_tri:
        vi_tri = parse_location(text)
    f = {"gia_max": None, "gia_min": None, "dt_min": None,
         "loai": parse_type(text), "vi_tri": vi_tri,
         "huong": parse_direction(text)}
    if price is not None:
        if any(k in t for k in ["duoi", "<", "toi da", "khong qua", "tam", "ngan sach"]):
            f["gia_max"] = price
        elif any(k in t for k in ["tren", ">", "tu ", "it nhat"]):
            f["gia_min"] = price
        else:
            f["gia_max"] = price  # mặc định: coi như ngân sách tối đa
    a = parse_area(text)
    if a is not None:
        f["dt_min"] = a
    # vị trí trong câu hỏi: nếu không bắt được qua từ khoá, dò từ điển trên cả câu
    if not f["vi_tri"]:
        for p in PLACES:
            if strip_accents(p) in t:
                f["vi_tri"] = p.title()
                break
    return f

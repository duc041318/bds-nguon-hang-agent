# -*- coding: utf-8 -*-
"""
Bản GỘP 1 FILE của agent nguồn hàng BĐS (extractor + tools + store + FastAPI).
Dùng để deploy lên VPS không cần git/registry: nhúng base64 vào docker-compose.
Tự chạy uvicorn ở cổng 8000. Data lưu /app/data/listings.json.
"""
import re, json, os, unicodedata
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
import uvicorn

DB = "/app/data/listings.json"
API_TOKEN = os.environ.get("API_TOKEN", "")


def strip_accents(s):
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D").lower()


def load():
    if not os.path.exists(DB):
        return []
    try:
        with open(DB, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save(items):
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    with open(DB, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def parse_price(text):
    t = strip_accents(text)
    m = re.search(r"(\d+[.,]?\d*)\s*(ty|ti)\b", t)
    if m:
        return float(m.group(1).replace(",", ".")) * 1000
    m = re.search(r"(\d+[.,]?\d*)\s*(trieu|tr)\b", t)
    if m:
        return float(m.group(1).replace(",", "."))
    return None


def parse_area(text):
    t = strip_accents(text)
    m = re.search(r"(\d+[.,]?\d*)\s*(hecta|héc|ha)\b", t)
    if m:
        return float(m.group(1).replace(",", ".")) * 10000
    m = re.search(r"(\d+[.,]?\d*)\s*(sao)\b", t)
    if m:
        return float(m.group(1).replace(",", ".")) * 360
    m = re.search(r"(\d+[.,]?\d*)\s*(m2|m²|m)\b", t)
    if m:
        return float(m.group(1).replace(",", "."))
    return None


def parse_type(text):
    t = strip_accents(text)
    table = [("dat nen", "đất nền"), ("dat tho cu", "đất thổ cư"),
             ("dat nong nghiep", "đất nông nghiệp"), ("dat", "đất"),
             ("chung cu", "chung cư"), ("can ho", "căn hộ"),
             ("nha pho", "nhà phố"), ("biet thu", "biệt thự"),
             ("nha", "nhà"), ("kho xuong", "kho xưởng"), ("nha xuong", "kho xưởng")]
    for key, label in table:
        if re.search(r"\b" + re.escape(key) + r"\b", t):
            return label
    return None


def parse_phone(text):
    m = re.search(r"(0\d{9})\b", text.replace(".", "").replace(" ", ""))
    return m.group(1) if m else None


def parse_direction(text):
    t = strip_accents(text)
    for key, label in [("dong nam", "Đông Nam"), ("tay nam", "Tây Nam"),
                       ("dong bac", "Đông Bắc"), ("tay bac", "Tây Bắc"),
                       ("huong dong", "Đông"), ("huong tay", "Tây"),
                       ("huong nam", "Nam"), ("huong bac", "Bắc")]:
        if key in t:
            return label
    return None


PLACES = ["sóc sơn", "đông anh", "mê linh", "ba vì", "hoài đức", "thạch thất",
          "gia lâm", "long biên", "hà đông", "bắc ninh", "hưng yên", "hà nội"]


def parse_location(text):
    m = re.search(r"(?:tại|ở|khu|xã|huyện|thôn|đường|kđt)\s+([^\.,;\n]{2,40})",
                  text, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    t = strip_accents(text)
    for p in PLACES:
        if strip_accents(p) in t:
            return p.title()
    return None


def parse_listing(text):
    return {"raw": text.strip(), "loai": parse_type(text), "gia_trieu": parse_price(text),
            "dien_tich_m2": parse_area(text), "huong": parse_direction(text),
            "vi_tri": parse_location(text), "lien_he": parse_phone(text)}


_STOP = set("duoi tren khoang gia tu den toi da khong qua tam ngan sach it nhat lo nao co tim trang tiep "
            "ty ti trieu tr m2 m dat nha can ho chung cu biet thu kho xuong huong dong tay nam bac "
            "mat tien so do va o khu xa huyen thon duong cua nguon hang".split())


def parse_query(text):
    t = strip_accents(text)
    page = 1
    mp = re.search(r"\btrang\s*(\d{1,3})\b", t)
    if mp:
        page = max(1, int(mp.group(1)))
    f = {"gia_max": None, "gia_min": None, "dt_min": None,
         "loai": parse_type(text), "huong": parse_direction(text), "page": page, "loc_words": []}
    # khoảng giá "X-Y tỷ" / "X đến Y tỷ"
    rng = re.search(r"(\d+[.,]?\d*)\s*(?:-|den|toi|->)\s*(\d+[.,]?\d*)\s*(ty|ti|trieu|tr)", t)
    if rng:
        lo = float(rng.group(1).replace(",", ".")); hi = float(rng.group(2).replace(",", "."))
        mul = 1000 if rng.group(3) in ("ty", "ti") else 1
        f["gia_min"], f["gia_max"] = lo * mul, hi * mul
    else:
        price = parse_price(text)
        if price is not None:
            if any(k in t for k in ["tren", ">", "tu ", "it nhat"]):
                f["gia_min"] = price
            else:
                f["gia_max"] = price
    a = parse_area(text)
    if a is not None:
        f["dt_min"] = a
    # địa danh / từ khoá còn lại (bỏ số, đơn vị, keyword) -> lọc theo raw
    f["loc_words"] = [w for w in t.split() if len(w) >= 2 and not any(c.isdigit() for c in w) and w not in _STOP]
    return f


def _fmt(it, idx=None):
    g = f"{it['gia_trieu']:.0f}tr" if it.get("gia_trieu") else "giá ?"
    dt = f"{it['dien_tich_m2']:.0f}m²" if it.get("dien_tich_m2") else "dt ?"
    parts = [p for p in [it.get("loai"), it.get("vi_tri"), dt, g, it.get("huong"), it.get("lien_he")] if p]
    code = it.get("code")
    head = f"[{code}] " if code else (f"#{idx} " if idx is not None else "")
    return head + " | ".join(str(p) for p in parts)


def detail(code):
    for it in load():
        if it.get("code") == code:
            d = it.get("detail") or {}
            cv = (" · " + d["chuc_vu"]) if d.get("chuc_vu") else ""
            return "\n".join([
                f"📋 {code} — {d.get('loai','')}",
                f"📍 {d.get('dia_chi','')}",
                f"📐 DT: {d.get('dien_tich','?')}m² (thực {d.get('dt_thuc','?')}m²)",
                f"💰 Giá: {d.get('gia','?')} tỷ",
                f"📜 Sổ: {d.get('so') or '-'}",
                f"👤 Đầu chủ: {d.get('dau_chu','')} — {d.get('sdt','')}",
                f"🏢 {d.get('phong','')}{cv}",
                f"🕒 Đăng: {d.get('ngay','')}",
                f"🗺️ {d.get('maps','')}" if d.get("maps") else "",
                f"🔗 {d.get('link','')}",
            ]).replace("\n\n", "\n")
    return f"Không tìm thấy mã {code}."


def add_listing(text):
    items = load(); rec = parse_listing(text); items.append(rec); save(items)
    return "Đã lưu nguồn hàng: " + _fmt(rec)


def search_listings(query):
    items = load(); f = parse_query(query); res = []
    for it in items:
        if f["gia_max"] is not None and (it.get("gia_trieu") is None or it["gia_trieu"] > f["gia_max"]):
            continue
        if f["gia_min"] is not None and (it.get("gia_trieu") is None or it["gia_trieu"] < f["gia_min"]):
            continue
        if f["dt_min"] is not None and (it.get("dien_tich_m2") is None or it["dien_tich_m2"] < f["dt_min"]):
            continue
        if f["huong"] and (not it.get("huong") or strip_accents(f["huong"]) not in strip_accents(it["huong"])):
            continue
        raw = strip_accents(it.get("raw", ""))
        phrase = " ".join(f["loc_words"])
        if phrase and phrase not in raw:
            continue
        res.append(it)
    if not res:
        return "Không có nguồn nào khớp. Thử: 'sóc sơn 2-3 tỷ' hoặc nới điều kiện."
    LIM = 15
    n = len(res)
    pages = (n + LIM - 1) // LIM
    page = min(f.get("page", 1), pages)
    off = (page - 1) * LIM
    chunk = res[off:off + LIM]
    head = f"Tìm thấy {n} nguồn — trang {page}/{pages}:"
    body = "\n".join(_fmt(it) for it in chunk)
    tail = f"\n→ Xem thêm: nhắn '{query.strip()} trang {page+1}'" if page < pages else ""
    return head + "\n" + body + tail


def stats():
    items = load(); by = {}
    for it in items:
        by[it.get("loai") or "?"] = by.get(it.get("loai") or "?", 0) + 1
    return f"Tổng {len(items)} nguồn. Theo loại: " + (", ".join(f"{k}: {v}" for k, v in by.items()) or "—")


def looks_like_listing(text):
    t = strip_accents(text)
    has_kw = any(k in t for k in ["ban ", "can ban", "chinh chu", "lien he", "lh ", "gia ", "dien tich", "dt ", "so do", "m2", "mat tien"])
    is_q = "?" in text or t.strip().startswith(("co ", "tim", "lo nao"))
    return has_kw and any(c.isdigit() for c in text) and not is_q


def handle(text):
    t = strip_accents(text)
    m = re.search(r"\btk\s*0*(\d{1,5})\b", t)
    if m:
        return detail("TK%04d" % int(m.group(1)))
    if any(k in t for k in ["thong ke", "bao nhieu nguon", "co bao nhieu"]):
        return stats()
    if looks_like_listing(text):
        return add_listing(text)
    return search_listings(text)


app = FastAPI(title="BĐS Agent")


class Msg(BaseModel):
    text: str


def _auth(tok):
    if API_TOKEN and tok != API_TOKEN:
        raise HTTPException(status_code=401, detail="Sai token")


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/message")
def message(m: Msg, x_api_token: str | None = Header(default=None)):
    _auth(x_api_token)
    return {"reply": handle(m.text)}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

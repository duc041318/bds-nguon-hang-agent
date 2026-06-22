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
import statistics

DB = "/app/data/listings.json"
CUST_DB = "/app/data/customers.json"
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


# Stop-set AN TOÀN: chỉ chứa từ khoá KHÔNG bao giờ là tên địa danh
# (KHÔNG để: trung, binh, gia, dinh, dong, tay, nam, bac, son... vì trùng tên xã/khu)
_STOP = set("duoi tren khoang tu den toi da khong qua tam ngan sach it nhat lo nao co tim trang tiep "
            "ty ti trieu tr m2 m mat tien va o "
            "khach khop nhu cau van goi cho can muon deal "
            "duong pho ngo ngach thon xom xa phuong huyen quan khu kdt to lo "  # tiền tố địa chỉ
            "so sd nhat re dat cao thap rong moi nho lon gia don".split())  # từ sort/sổ/giá

# Bí danh -> tên có trong kho (anh có thể bổ sung cặp old<->new)
_ALIASES = {"san bay": "noi bai", "sb noi bai": "noi bai"}

_PLACES = None


def places_vocab(items):
    global _PLACES
    if _PLACES is None:
        s = set()
        for it in items:
            for k in (it.get("vi_tri"), it.get("phuong_xa")):
                if k and len(strip_accents(k)) >= 3:
                    s.add(strip_accents(k))
        _PLACES = sorted(s, key=len, reverse=True)  # khớp cụm dài trước
    return _PLACES


def parse_query(text):
    t = strip_accents(text)
    for k, v in _ALIASES.items():
        t = t.replace(k, v)
    page = 1
    mp = re.search(r"\btrang\s*(\d{1,3})\b", t)
    if mp:
        page = max(1, int(mp.group(1)))
    f = {"gia_max": None, "gia_min": None, "dt_min": None, "dt_max": None,
         "loai": parse_type(text), "huong": parse_direction(text), "page": page,
         "loc_words": [], "q_norm": t, "ppm_max": None, "co_so": False, "sort": None}
    # giá/m²: "25tr/m2", "dưới 25/m²" -> ppm_max; tách khỏi câu để khỏi nhầm giá tổng
    text2, t2 = text, t
    mppm = re.search(r"(\d+[.,]?\d*)\s*(?:tr|trieu)?\s*/\s*m2?", t)
    if mppm:
        f["ppm_max"] = float(mppm.group(1).replace(",", "."))
        t2 = t.replace(mppm.group(0), " ")
        text2 = re.sub(r"(\d+[.,]?\d*)\s*(?:tr|trieu)?\s*/\s*m2?", " ", text, flags=re.I)
    # khoảng giá "X-Y tỷ"
    rng = re.search(r"(\d+[.,]?\d*)\s*(?:-|den|toi|->)\s*(\d+[.,]?\d*)\s*(ty|ti|trieu|tr)", t2)
    if rng:
        lo = float(rng.group(1).replace(",", ".")); hi = float(rng.group(2).replace(",", "."))
        mul = 1000 if rng.group(3) in ("ty", "ti") else 1
        f["gia_min"], f["gia_max"] = lo * mul, hi * mul
    else:
        price = parse_price(text2)
        if price is not None:
            if any(k in t2 for k in ["tren", ">", "tu ", "it nhat"]):
                f["gia_min"] = price
            else:
                f["gia_max"] = price
    ar = re.search(r"(\d+[.,]?\d*)\s*(?:-|den|toi|->)\s*(\d+[.,]?\d*)\s*m(?!i)", t2)
    if ar:
        f["dt_min"] = float(ar.group(1).replace(",", "."))
        f["dt_max"] = float(ar.group(2).replace(",", "."))
    else:
        a = parse_area(text2)
        if a is not None:
            f["dt_min"] = a
    # lọc Sổ
    if any(k in t for k in ["co so", "so do", "sodo", "co sd", "co sing"]):
        f["co_so"] = True
    # sắp xếp
    if "re/m" in t or "re tren m" in t or "don gia re" in t:
        f["sort"] = "ppm_asc"
    elif "re nhat" in t or "gia thap" in t:
        f["sort"] = "price_asc"
    elif "dat nhat" in t or "gia cao" in t:
        f["sort"] = "price_desc"
    elif "to nhat" in t or "rong nhat" in t:
        f["sort"] = "area_desc"
    elif "nho nhat" in t:
        f["sort"] = "area_asc"
    f["loc_words"] = [w for w in t2.split() if len(w) >= 2 and not any(c.isdigit() for c in w) and w not in _STOP]
    return f


def _fmt(it, medians=None):
    g = f"{it['gia_trieu']:.0f}tr" if it.get("gia_trieu") else "giá ?"
    dt = f"{it['dien_tich_m2']:.0f}m²" if it.get("dien_tich_m2") else "dt ?"
    noi = it.get("phuong_xa") or it.get("vi_tri")
    parts = [p for p in [it.get("loai"), noi, dt, g, it.get("huong"), it.get("lien_he")] if p]
    flag = ""
    if medians:
        p = _ppm(it); m = medians.get(strip_accents(it.get("vi_tri", "")))
        if p and m and p < 0.85 * m:
            flag = "🔥"
    code = it.get("code")
    head = (flag + f"[{code}] ") if code else ""
    return head + " | ".join(str(p) for p in parts)


def detail(code):
    items = load()
    for it in items:
        if it.get("code") == code:
            d = it.get("detail") or {}
            cv = (" · " + d["chuc_vu"]) if d.get("chuc_vu") else ""
            p = _ppm(it); m = area_medians(items).get(strip_accents(it.get("vi_tri", "")))
            if p and m:
                tag = "🔥 RẺ" if p < 0.85 * m else ("⬆️ cao" if p > 1.15 * m else "⚖️ hợp lý")
                ppm_line = f"📊 {p:.1f} tr/m² (TB khu ~{m:.1f}) → {tag}"
            else:
                ppm_line = ""
            return "\n".join(x for x in [
                f"📋 {code} — {d.get('loai','')}",
                f"📍 {d.get('dia_chi','')}",
                f"📐 DT: {d.get('dien_tich','?')}m² (thực {d.get('dt_thuc','?')}m²)",
                f"💰 Giá: {d.get('gia','?')} tỷ",
                ppm_line,
                f"📜 Sổ: {d.get('so') or '-'}",
                f"👤 Đầu chủ: {d.get('dau_chu','')} — {d.get('sdt','')}",
                f"🏢 {d.get('phong','')}{cv}",
                f"🕒 Đăng: {d.get('ngay','')}",
                f"🗺️ {d.get('maps','')}" if d.get("maps") else "",
                f"🔗 {d.get('link','')}",
            ] if x)
    return f"Không tìm thấy mã {code}."


def add_listing(text):
    items = load(); rec = parse_listing(text); items.append(rec); save(items)
    return "Đã lưu nguồn hàng: " + _fmt(rec)


def _loc_terms(f, items):
    """Trả list cụm BẮT BUỘC có trong raw: [tên khu/xã (nếu có)] + [phần còn lại: đường/dự án/tên]."""
    q = f.get("q_norm", "")
    terms = []; used = q
    for pv in places_vocab(items):  # từ điển khu/xã, cụm dài trước
        if pv in q:
            terms.append(pv); used = used.replace(pv, " "); break
    leftover = [w for w in used.split() if len(w) >= 2 and not any(c.isdigit() for c in w) and w not in _STOP]
    if leftover:
        terms.append(" ".join(leftover))
    return terms


def _loc_label(f, items):
    ts = _loc_terms(f, items)
    return ts[0] if ts else ""


def _filter(items, f):
    terms = _loc_terms(f, items)
    res = []
    for it in items:
        g = it.get("gia_trieu"); dt = it.get("dien_tich_m2")
        if f["gia_max"] is not None and (g is None or g > f["gia_max"]):
            continue
        if f["gia_min"] is not None and (g is None or g < f["gia_min"]):
            continue
        if f["dt_min"] is not None and (dt is None or dt < f["dt_min"]):
            continue
        if f["dt_max"] is not None and (dt is None or dt > f["dt_max"]):
            continue
        if f["huong"] and (not it.get("huong") or strip_accents(f["huong"]) not in strip_accents(it["huong"])):
            continue
        if terms:
            raw = strip_accents(it.get("raw", ""))
            if any(term not in raw for term in terms):
                continue
        if f.get("ppm_max") is not None:
            p = _ppm(it)
            if p is None or p > f["ppm_max"]:
                continue
        if f.get("co_so") and not (it.get("detail") or {}).get("so"):
            continue
        res.append(it)
    return res


def _apply_sort(res, sort):
    if sort == "price_asc":
        res.sort(key=lambda it: (it.get("gia_trieu") is None, it.get("gia_trieu") or 0))
    elif sort == "price_desc":
        res.sort(key=lambda it: it.get("gia_trieu") or 0, reverse=True)
    elif sort == "area_desc":
        res.sort(key=lambda it: it.get("dien_tich_m2") or 0, reverse=True)
    elif sort == "area_asc":
        res.sort(key=lambda it: (it.get("dien_tich_m2") is None, it.get("dien_tich_m2") or 0))
    elif sort == "ppm_asc":
        res.sort(key=lambda it: (_ppm(it) is None, _ppm(it) or 0))
    return res


def search_listings(query):
    f = parse_query(query)
    items = load()
    res = _filter(items, f)
    if not res:
        return "Không có nguồn nào khớp. Thử: 'sóc sơn 2-3 tỷ' hoặc nới điều kiện."
    _apply_sort(res, f.get("sort"))
    meds = area_medians(items)
    LIM = 15
    n = len(res)
    pages = (n + LIM - 1) // LIM
    page = min(f.get("page", 1), pages)
    off = (page - 1) * LIM
    sortlbl = {"price_asc": " · rẻ→đắt", "price_desc": " · đắt→rẻ", "area_desc": " · to→nhỏ",
               "area_asc": " · nhỏ→to", "ppm_asc": " · rẻ/m²"}.get(f.get("sort"), "")
    head = f"Tìm thấy {n} nguồn — trang {page}/{pages}{sortlbl} (🔥=rẻ so với khu):"
    body = "\n".join(_fmt(it, meds) for it in res[off:off + LIM])
    tail = f"\n→ Xem thêm: nhắn '{query.strip()} trang {page+1}'" if page < pages else ""
    return head + "\n" + body + tail


def match_customer(query):
    f = parse_query(query)
    items = load()
    res = _filter(items, f)
    relaxed = False
    if not res and (f["gia_max"] or f["dt_min"] or f["dt_max"]):
        if f["gia_max"]:
            f["gia_max"] = f["gia_max"] * 1.15
        if f["dt_min"]:
            f["dt_min"] = f["dt_min"] * 0.9
        if f["dt_max"]:
            f["dt_max"] = f["dt_max"] * 1.1
        res = _filter(items, f)
        relaxed = True
    if not res:
        return "Chưa có lô nào khớp nhu cầu khách. Thử nới khu/giá/diện tích."
    # xếp theo giá tăng dần (lô tốt giá mềm trước)
    res.sort(key=lambda it: (it.get("gia_trieu") is None, it.get("gia_trieu") or 0))
    LIM = 15
    n = len(res)
    head = f"🎯 {n} lô khớp nhu cầu khách" + (" (đã nới nhẹ điều kiện)" if relaxed else "") + " — xếp theo giá:"
    body = "\n".join(_fmt(it) for it in res[:LIM])
    tail = f"\n…còn {n - LIM} lô. Nhắn mã TK để xem chi tiết + SĐT đầu chủ." if n > LIM else "\nNhắn mã TK để xem chi tiết + SĐT đầu chủ."
    return head + "\n" + body + tail


def load_customers():
    if not os.path.exists(CUST_DB):
        return []
    try:
        with open(CUST_DB, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_customers(cs):
    os.makedirs(os.path.dirname(CUST_DB), exist_ok=True)
    with open(CUST_DB, "w", encoding="utf-8") as f:
        json.dump(cs, f, ensure_ascii=False, indent=1)


def add_customer(text):
    parts = text.split(None, 2)  # bỏ 2 từ đầu "lưu khách" (không phụ thuộc dấu)
    raw = parts[2].strip() if len(parts) > 2 else ""
    sep = "|" if "|" in raw else (":" if ":" in raw else None)
    if not sep:
        return "Cú pháp: lưu khách <tên> | <nhu cầu>\nVD: lưu khách Anh Tú | Sóc Sơn 80-100m2 dưới 2.5 tỷ"
    name, need = [p.strip() for p in raw.split(sep, 1)]
    if not name or not need:
        return "Thiếu tên hoặc nhu cầu. VD: lưu khách Anh Tú | Sóc Sơn 80-100m2 dưới 2.5 tỷ"
    cs = [c for c in load_customers() if strip_accents(c["name"]) != strip_accents(name)]
    cs.append({"name": name, "need": need})
    save_customers(cs)
    return f"✅ Đã lưu khách '{name}': {need}\n(Nhắn 'quét khách' để tìm lô khớp.)"


def list_customers():
    cs = load_customers()
    if not cs:
        return "Chưa có khách nào. Lưu: lưu khách <tên> | <nhu cầu>"
    return "👥 Khách đang theo dõi:\n" + "\n".join(f"• {c['name']}: {c['need']}" for c in cs)


def del_customer(text):
    parts = text.split(None, 2)  # bỏ "xoá khách"
    name = parts[2].strip() if len(parts) > 2 else ""
    cs = load_customers()
    new = [c for c in cs if strip_accents(c["name"]) != strip_accents(name)]
    if len(new) == len(cs):
        return f"Không thấy khách '{name}'."
    save_customers(new)
    return f"🗑️ Đã xoá khách '{name}'."


def scan_customers(new_codes=None):
    cs = load_customers()
    if not cs:
        return "Chưa có khách nào để quét. Lưu: lưu khách <tên> | <nhu cầu>"
    items = load()
    pool = [it for it in items if it.get("code") in new_codes] if new_codes is not None else items
    out = []
    for c in cs:
        res = _filter(pool, parse_query(c["need"]))
        if res:
            res.sort(key=lambda it: (it.get("gia_trieu") is None, it.get("gia_trieu") or 0))
            top = ", ".join(it.get("code") for it in res[:5])
            out.append(f"🔔 {c['name']} ({c['need']}): {len(res)} lô — {top}" + (" …" if len(res) > 5 else ""))
        else:
            out.append(f"— {c['name']}: chưa có lô khớp")
    title = "🆕 LÔ MỚI KHỚP KHÁCH:\n" if new_codes is not None else "KẾT QUẢ QUÉT KHÁCH:\n"
    return title + "\n".join(out)


def _ppm(it):
    g = it.get("gia_trieu"); dt = it.get("dien_tich_m2")
    return (g / dt) if (g and dt) else None


def area_medians(items):
    by = {}
    for it in items:
        p = _ppm(it)
        if p:
            by.setdefault(strip_accents(it.get("vi_tri", "")), []).append(p)
    return {k: statistics.median(v) for k, v in by.items() if v}


def _loc_sub(items, f):
    terms = _loc_terms(f, items)
    if not terms:
        return items
    return [it for it in items if all(term in strip_accents(it.get("raw", "")) for term in terms)]


def dinh_gia(query):
    f = parse_query(query)
    sub = _loc_sub(load(), f)
    pp = sorted(p for p in (_ppm(it) for it in sub) if p)
    if len(pp) < 3:
        return "Không đủ dữ liệu để định giá khu này (cần khu cụ thể hơn)."
    med = statistics.median(pp)
    khu = (_loc_label(f, sub) or "toàn kho").title()
    return (f"💰 Định giá {khu} ({len(pp)} lô):\n"
            f"• Trung vị: ~{med:.1f} tr/m²\n"
            f"• Thấp–cao: {pp[0]:.1f} – {pp[-1]:.1f} tr/m²\n"
            f"→ Lô < {med*0.85:.1f} tr/m² là rẻ. Nhắn 'lô rẻ {khu}' để xem.")


def lo_re(query):
    f = parse_query(query)
    items = load()
    sub = _filter(items, f)  # áp cả lọc khu/giá/dt nếu có
    if not sub:
        sub = _loc_sub(items, f)
    pp = sorted(p for p in (_ppm(it) for it in sub) if p)
    if len(pp) < 3:
        return "Không đủ dữ liệu."
    med = statistics.median(pp); thr = med * 0.85
    deals = sorted(((it, _ppm(it)) for it in sub if _ppm(it) and _ppm(it) < thr), key=lambda x: x[1])
    if not deals:
        return f"Không có lô rẻ bất thường (trung vị ~{med:.1f} tr/m²)."
    khu = (_loc_label(f, items) or "kho").title()
    lines = [f"🔥 {it['code']} | {it.get('vi_tri','')} | {it.get('dien_tich_m2'):.0f}m² | "
             f"{it.get('gia_trieu'):.0f}tr | {p:.1f}tr/m²" for it, p in deals[:15]]
    return (f"🔥 Lô rẻ {khu} (< {thr:.1f} tr/m², trung vị {med:.1f}) — {len(deals)} lô:\n"
            + "\n".join(lines) + "\nNhắn mã TK để xem chi tiết + SĐT.")


def stats():
    items = load(); by = {}
    for it in items:
        by[it.get("loai") or "?"] = by.get(it.get("loai") or "?", 0) + 1
    return f"Tổng {len(items)} nguồn. Theo loại: " + (", ".join(f"{k}: {v}" for k, v in by.items()) or "—")


def digest():
    items = load()
    n = len(items)
    by = {}
    for it in items:
        by[it.get("vi_tri") or "?"] = by.get(it.get("vi_tri") or "?", 0) + 1
    top = sorted(by.items(), key=lambda x: -x[1])[:6]
    meds = area_medians(items)
    deals = 0
    for it in items:
        p = _ppm(it); m = meds.get(strip_accents(it.get("vi_tri", "")))
        if p and m and p < 0.85 * m:
            deals += 1
    lines = [f"📊 DIGEST KHO BĐS — {n} nguồn",
             "🏘️ Khu nhiều hàng: " + ", ".join(f"{k}({v})" for k, v in top)]
    md = [f"{k} ~{meds[strip_accents(k)]:.0f}tr/m²" for k, _ in top[:4] if meds.get(strip_accents(k))]
    if md:
        lines.append("💰 Giá TB: " + ", ".join(md))
    lines.append(f"🔥 Lô giá rẻ (dưới TB khu): {deals}")
    cs = load_customers()
    if cs:
        lines.append(f"👥 {len(cs)} khách theo dõi — nhắn 'quét khách' để xem khớp.")
    lines.append("Gõ: 'sóc sơn 2-3 tỷ' · 'lô rẻ sóc sơn 80-100m2' · 'định giá <khu>'")
    return "\n".join(lines)


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
    if any(k in t for k in ["digest", "bao cao", "tong hop"]):
        return digest()
    if any(k in t for k in ["thong ke", "bao nhieu nguon", "co bao nhieu"]):
        return stats()
    if t.startswith(("luu khach", "them khach")):
        return add_customer(text)
    if t.startswith(("xoa khach", "huy khach")):
        return del_customer(text)
    if any(k in t for k in ["ds khach", "danh sach khach", "list khach"]):
        return list_customers()
    if "quet khach" in t:
        return scan_customers()
    if any(k in t for k in ["lo re", "deal", "gia re"]):
        return lo_re(text)
    if any(k in t for k in ["dinh gia", "gia m2", "gia/m2", "gia tb", "trung binh", "dinh gia"]):
        return dinh_gia(text)
    if any(k in t for k in ["khach", "khop", "nhu cau", "tu van", "goi y", "tim cho"]):
        return match_customer(text)
    if t.startswith(("luu ", "them tin", "rao ")):  # chỉ lưu khi có tiền tố rõ ràng
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

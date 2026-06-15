# -*- coding: utf-8 -*-
"""
Tool registry — thành phần #2 của Agent Loop.
Mỗi tool: nhận đối số -> làm việc -> trả về CHUỖI observation cho model đọc.
"""
import store
from extractor import parse_listing, parse_query, strip_accents


def _fmt(item: dict, idx: int = None) -> str:
    g = f"{item['gia_trieu']:.0f}tr" if item.get("gia_trieu") else "giá ?"
    dt = f"{item['dien_tich_m2']:.0f}m²" if item.get("dien_tich_m2") else "dt ?"
    parts = [p for p in [item.get("loai"), item.get("vi_tri"), dt, g,
                         item.get("huong"), item.get("lien_he")] if p]
    head = f"#{idx} " if idx is not None else ""
    return head + " | ".join(str(p) for p in parts)


def add_listing(text: str) -> str:
    """Lưu một tin rao nguồn hàng."""
    items = store.load()
    rec = parse_listing(text)
    items.append(rec)
    store.save(items)
    return "Đã lưu nguồn hàng: " + _fmt(rec)


def search_listings(query: str) -> str:
    """Tìm nguồn hàng theo câu hỏi tự nhiên."""
    items = store.load()
    f = parse_query(query)
    res = []
    for it in items:
        if f["gia_max"] is not None and (it.get("gia_trieu") is None or it["gia_trieu"] > f["gia_max"]):
            continue
        if f["gia_min"] is not None and (it.get("gia_trieu") is None or it["gia_trieu"] < f["gia_min"]):
            continue
        if f["dt_min"] is not None and (it.get("dien_tich_m2") is None or it["dien_tich_m2"] < f["dt_min"]):
            continue
        if f["loai"] and strip_accents(f["loai"]) not in strip_accents(it.get("raw", "")):
            continue
        if f["vi_tri"] and strip_accents(f["vi_tri"]) not in strip_accents(it.get("raw", "")):
            continue
        if f["huong"] and (not it.get("huong") or strip_accents(f["huong"]) not in strip_accents(it["huong"])):
            continue
        res.append(it)
    if not res:
        return f"Không có nguồn nào khớp (lọc: {f})."
    lines = [_fmt(it, i + 1) for i, it in enumerate(res)]
    return f"Tìm thấy {len(res)} nguồn:\n" + "\n".join(lines)


def stats(_: str = "") -> str:
    """Thống kê kho nguồn hàng."""
    items = store.load()
    n = len(items)
    by_type = {}
    for it in items:
        by_type[it.get("loai") or "?"] = by_type.get(it.get("loai") or "?", 0) + 1
    detail = ", ".join(f"{k}: {v}" for k, v in by_type.items())
    return f"Tổng {n} nguồn. Theo loại: {detail or '—'}"


# Đăng ký tool: tên -> hàm
REGISTRY = {
    "add_listing": add_listing,
    "search_listings": search_listings,
    "stats": stats,
}

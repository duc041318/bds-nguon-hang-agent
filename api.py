# -*- coding: utf-8 -*-
"""
HTTP API bọc quanh Agent nguồn hàng BĐS (FastAPI).
n8n gọi các endpoint này. Tái dùng nguyên agent loop trong agent.py.

Chạy local:  uvicorn api:app --host 0.0.0.0 --port 8000
"""
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
import os

from agent import run_turn
from tools import add_listing, search_listings, stats

app = FastAPI(title="BĐS Nguồn Hàng Agent API", version="1.0")

# Token bảo vệ đơn giản: đặt biến môi trường API_TOKEN, n8n gửi header X-Api-Token.
API_TOKEN = os.environ.get("API_TOKEN", "")


def _auth(token: str | None):
    if API_TOKEN and token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Sai API token")


class Msg(BaseModel):
    text: str


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/message")
def message(m: Msg, x_api_token: str | None = Header(default=None)):
    """Nhận 1 tin (rao hoặc câu hỏi) -> agent tự định tuyến tool -> trả lời."""
    _auth(x_api_token)
    reply = run_turn([], m.text, verbose=False)
    return {"reply": reply}


@app.post("/ingest")
def ingest(m: Msg, x_api_token: str | None = Header(default=None)):
    """Ép lưu (dùng khi chắc chắn là tin rao)."""
    _auth(x_api_token)
    return {"reply": add_listing(m.text)}


@app.post("/search")
def search(m: Msg, x_api_token: str | None = Header(default=None)):
    """Ép tìm (dùng khi chắc chắn là câu hỏi)."""
    _auth(x_api_token)
    return {"reply": search_listings(m.text)}


@app.get("/stats")
def stats_ep(x_api_token: str | None = Header(default=None)):
    _auth(x_api_token)
    return {"reply": stats("")}

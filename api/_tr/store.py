"""ที่เก็บข้อมูล OI ถาวรของเวอร์ชันเว็บ

- มี env BLOB_READ_WRITE_TOKEN (ได้อัตโนมัติเมื่อเชื่อม Vercel Blob กับโปรเจกต์) → เก็บใน Vercel Blob (private)
- ไม่มี → อ่านจาก seed/ ที่ติดมากับโค้ด และเขียนลงโฟลเดอร์ชั่วคราว (สำหรับรันบนเครื่อง / ยังไม่ได้เชื่อม Blob)

คีย์ที่ใช้: oi/GOLD.txt · oi/EUR.txt · oi/BTC.txt · oi/meta.json · oi/cme_btc.json
REST API ตาม @vercel/blob (API version 13): https://vercel.com/api/blob
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

import requests

SEED = Path(__file__).parent / "seed"
LOCAL = Path(os.environ.get("TR_LOCAL_STORE", Path(tempfile.gettempdir()) / "traderadar_store"))
API = os.environ.get("VERCEL_BLOB_API_URL", "https://vercel.com/api/blob")
PREFIX = "traderadar/"
_cache: dict[str, tuple[float, str | None]] = {}
CACHE_S = 60


def _token() -> str:
    return os.environ.get("BLOB_READ_WRITE_TOKEN", "").strip()


def backend() -> str:
    return "vercel-blob" if _token() else "local"


def _headers() -> dict:
    tok = _token()
    parts = tok.split("_")
    return {"authorization": f"Bearer {tok}", "x-api-version": "13",
            "x-vercel-blob-store-id": parts[3] if len(parts) > 3 else ""}


# ------------------------------------------------------------------ Vercel Blob
def _blob_put(key: str, text: str) -> None:
    h = {**_headers(), "x-vercel-blob-access": "private", "x-content-type": "text/plain; charset=utf-8",
         "x-add-random-suffix": "0", "x-allow-overwrite": "1"}
    r = requests.put(f"{API}/", params={"pathname": PREFIX + key}, data=text.encode("utf-8"), headers=h, timeout=20)
    if r.status_code >= 300:
        raise RuntimeError(f"Blob put {key}: HTTP {r.status_code} {r.text[:200]}")


def _blob_get(key: str) -> str | None:
    r = requests.get(API, params={"prefix": PREFIX + key, "limit": 5}, headers=_headers(), timeout=15)
    if r.status_code >= 300:
        raise RuntimeError(f"Blob list {key}: HTTP {r.status_code} {r.text[:200]}")
    blobs = [b for b in r.json().get("blobs", []) if b.get("pathname") == PREFIX + key]
    if not blobs:
        return None
    url = blobs[0]["url"]
    g = requests.get(url, headers={"authorization": _headers()["authorization"]}, timeout=15)
    if g.status_code >= 300:
        raise RuntimeError(f"Blob get {key}: HTTP {g.status_code}")
    return g.content.decode("utf-8")


def _blob_delete(key: str) -> None:
    requests.post(f"{API}/delete", json={"urls": [PREFIX + key]}, headers=_headers(), timeout=15)


# ------------------------------------------------------------------ public API
def get_text(key: str) -> str | None:
    now = time.time()
    if key in _cache and now - _cache[key][0] < CACHE_S:
        return _cache[key][1]
    val = None
    if backend() == "vercel-blob":
        val = _blob_get(key)
    else:
        p = LOCAL / key
        if p.exists():
            val = p.read_text(encoding="utf-8")
    if val is None:                       # ยังไม่เคยบันทึก → ใช้ข้อมูลตั้งต้นที่ติดมากับโค้ด
        s = SEED / Path(key).name
        val = s.read_text(encoding="utf-8") if s.exists() else None
    _cache[key] = (now, val)
    return val


def put_text(key: str, text: str) -> None:
    if backend() == "vercel-blob":
        _blob_put(key, text)
    else:
        p = LOCAL / key
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    _cache[key] = (time.time(), text)


def get_json(key: str, default=None):
    t = get_text(key)
    try:
        return json.loads(t) if t else default
    except ValueError:
        return default


def put_json(key: str, obj) -> None:
    put_text(key, json.dumps(obj, ensure_ascii=False, indent=1))


def self_test() -> dict:
    """เขียน-อ่าน-ลบ ไฟล์ทดสอบ เพื่อยืนยันว่าเชื่อม Blob สำเร็จ"""
    key, val = "selftest.txt", f"ok {time.time():.0f}"
    try:
        put_text(key, val)
        _cache.pop(key, None)
        back = get_text(key)
        if backend() == "vercel-blob":
            _blob_delete(key)
        return {"backend": backend(), "ok": back == val, "read": back}
    except Exception as e:  # noqa: BLE001
        return {"backend": backend(), "ok": False, "error": str(e)[:300]}

"""ดึง BTC options OI จาก Deribit (API สาธารณะ ไม่ต้อง log in)"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import requests

API = "https://www.deribit.com/api/v2/public"
MON = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def _get(path, **params):
    r = requests.get(f"{API}/{path}", params=params, timeout=20, headers={"User-Agent": "trade-radar/1.0"})
    r.raise_for_status()
    return r.json()["result"]


def exp_dt(code: str) -> datetime:
    """27NOV26 → 2026-11-27 08:00 UTC"""
    d, m, y = int(code[:-5]), MON[code[-5:-2]], 2000 + int(code[-2:])
    return datetime(y, m, d, 8, 0, tzinfo=timezone.utc)


def fetch(min_oi: float = 10_000) -> dict:
    book = _get("get_book_summary_by_currency", currency="BTC", kind="option")
    idx = _get("get_index_price", index_name="btc_usd")["index_price"]
    t_ms = int(time.time() * 1000)
    tot = {}
    for o in book:
        e = o["instrument_name"].split("-")[1]
        tot[e] = tot.get(e, 0) + o["open_interest"]
    now = datetime.now(timezone.utc) + timedelta(hours=1)
    live = {e: v for e, v in tot.items() if exp_dt(e) > now}
    fri = sorted((e for e, v in live.items() if exp_dt(e).weekday() == 4 and v >= min_oi
                  and exp_dt(e) < now + timedelta(days=14)), key=exp_dt)
    pick = fri[0] if fri else max((e for e in live if exp_dt(e) < now + timedelta(days=35)), key=lambda e: live[e])
    rows, F = {}, None
    for o in book:
        _, e, k, cp = o["instrument_name"].split("-")
        if e != pick:
            continue
        k = float(k)
        r = rows.setdefault(k, {"C": 0.0, "P": 0.0, "iv": None})
        r[cp] = o["open_interest"]
        if cp == "C" or r["iv"] is None:
            r["iv"] = o.get("mark_iv")
        F = o.get("underlying_price") or F
    ks = sorted(rows)
    iv = None
    for a, b in zip(ks, ks[1:]):
        if a <= F <= b and rows[a]["iv"] and rows[b]["iv"]:
            iv = rows[a]["iv"] + (rows[b]["iv"] - rows[a]["iv"]) * (F - a) / (b - a)
            break
    return {"expiry": pick, "exp_dt": exp_dt(pick), "exp_ms": int(exp_dt(pick).timestamp() * 1000),
            "t_ms": t_ms, "F": F, "index": idx, "iv": iv, "total": round(tot[pick]),
            "rows": [[k, rows[k]["C"], rows[k]["P"]] for k in ks if rows[k]["C"] or rows[k]["P"]]}

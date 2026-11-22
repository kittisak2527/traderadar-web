"""รวม logic ของ Trade Radar ให้เป็นบริการ JSON สำหรับ API บน Vercel
(ยกมาจาก app.py / pipeline.py ของเวอร์ชันเครื่อง ตัดส่วน Streamlit / ไฟล์ / Task Scheduler ออก)
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import data
import edges
import oi
import pine_gen
import scoring
import store
from config import ASSETS, MIN_RR, TIMEFRAMES, weights_for

TH, CT = ZoneInfo("Asia/Bangkok"), ZoneInfo("America/Chicago")
KEY_OF = {"GOLD": "XAUUSD", "EUR": "EURUSD", "BTC": "BTCUSD"}
_mem: dict[str, tuple[float, object]] = {}


def cached(key: str, ttl: int, fn, *args):
    now = time.time()
    if key in _mem and now - _mem[key][0] < ttl:
        return _mem[key][1]
    val = fn(*args)
    _mem[key] = (now, val)
    return val


def safe(label, fn, *args):
    try:
        return fn(*args), None
    except Exception as e:  # noqa: BLE001  แหล่งข้อมูลเสริมล่มได้ แต่ระบบต้องทำงานต่อ
        return None, f"{label}: {type(e).__name__} {str(e)[:120]}"


def clean(o):
    """แปลงชนิดข้อมูล numpy / NaN ให้เป็น JSON ล้วน"""
    import numpy as np
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.generic):
        o = o.item()
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    return o


def num(v, d=6):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else round(f, d)


# ------------------------------------------------------------------ BTC options (Deribit + CME ที่เก็บไว้)
def fmt(v) -> str:
    if v is None:
        return "x"
    v = round(float(v), 6)
    return str(int(v)) if v == int(v) else repr(v)


def build_loi(asset, series, e_ms, t_ms, F, iv, rows, src=None, vd=None, vc=None) -> str:
    head = f"LOI1;a={asset};s={series};e={e_ms};t={t_ms};f={fmt(F)};iv={fmt(round(iv or 0, 4))}"
    if src:
        head += f";src={src};vd={vd};vc={vc}"
    return head + "|" + "/".join(",".join(fmt(v) for v in r) for r in rows)


def _btc_snapshot() -> str:
    import deribit_fetch
    d = deribit_fetch.fetch()
    exp_date = d["exp_dt"].strftime("%Y-%m-%d")
    series = f"BTC-{d['expiry']}"
    merged = {k: [c, p] for k, c, p in d["rows"]}
    cme = store.get_json("oi/cme_btc.json")
    vc = 0
    if cme and cme.get("exp_date") == exp_date:
        n = 0
        for k, c, p in cme["rows"]:
            n += c + p
            x = merged.setdefault(k, [0.0, 0.0])
            x[0] += c * 5
            x[1] += p * 5
        vc = int(n * 5)
    rows = [[k, round(v[0], 1), round(v[1], 1)] for k, v in sorted(merged.items()) if v[0] or v[1]]
    prev = oi.load("BTCUSD")
    today = datetime.now(TH).date()
    if prev and prev["series"] == series and datetime.fromtimestamp(prev["t_ms"] / 1000, TH).date() < today:
        pv = {round(r.K, 1): (r.C, r.P) for r in prev["rows"].itertuples()}
        rows = [[k, c, p, round(c - pv.get(round(k, 1), (0, 0))[0], 1), round(p - pv.get(round(k, 1), (0, 0))[1], 1)] for k, c, p in rows]
    src = "Deribit+CME" if vc else "Deribit"
    loi = build_loi("BTC", series, d["exp_ms"], d["t_ms"], d["F"], d["iv"], rows, src=src, vd=d["total"], vc=vc)
    # เก็บ snapshot วันละครั้ง (ไว้คิด ΔOI วันถัดไป) โดยไม่ทับ snapshot ของวันนี้ที่มีอยู่แล้ว
    if not prev or prev["series"] != series or datetime.fromtimestamp(prev["t_ms"] / 1000, TH).date() < today:
        try:
            oi.save(loi)
            meta = store.get_json("oi/meta.json", {}) or {}
            meta["BTC"] = {**meta.get("BTC", {}), "series": series, "t_ms": d["t_ms"], "e_ms": d["exp_ms"], "src": src,
                           "note": f"Deribit {d['expiry']} ({d['total']:,} BTC)" + (" + CME" if vc else "")}
            store.put_json("oi/meta.json", meta)
        except Exception:  # noqa: BLE001
            pass
    return loi


def btc_snapshot() -> dict | None:
    loi, err = safe("Deribit", cached, "btc_loi", 1800, _btc_snapshot)
    if loi:
        return oi.parse(loi)
    return oi.load("BTCUSD")


def oi_snapshot(key: str):
    return btc_snapshot() if key == "BTCUSD" else oi.load(key)


# ------------------------------------------------------------------ วิเคราะห์
def bias_label(c):
    if c >= 40:
        return "ขาขึ้นแรง"
    if c >= 15:
        return "ค่อนข้างขาขึ้น"
    if c > -15:
        return "เป็นกลาง / sideway"
    if c > -40:
        return "ค่อนข้างขาลง"
    return "ขาลงแรง"


HINTS = {
    "E1": "รอให้คะแนนทิศทางรวมชัดเจนกว่านี้ (ต้องมีขนาดอย่างน้อย 20)",
    "E2": {"BUY": "รอราคาย่อลงมาในโซน Discount (ต่ำกว่า 37.5% ของกรอบ)", "SELL": "รอราคาเด้งขึ้นไปในโซน Premium (สูงกว่า 62.5% ของกรอบ)"},
    "E4": {"BUY": "รอให้ราคากวาด low เดิม (stop hunt) แล้วปิดกลับขึ้นมา", "SELL": "รอให้ราคากวาด high เดิม (stop hunt) แล้วปิดกลับลงมา"},
    "E6": f"RR ยังต่ำกว่า 1:{MIN_RR:.0f} รอราคาเข้าที่ดีกว่านี้",
}


def narrative(key, d, res, decimals):
    axes, c = d["axes"], d["composite"]
    sign = 1 if c >= 0 else -1
    support = max(axes, key=lambda k: axes[k][0] * sign)
    oppose = min(axes, key=lambda k: axes[k][0] * sign)
    f = f"{{:.{decimals}f}}"
    L = [f"ภาพรวม {ASSETS[key]['name']}: {bias_label(c)} (คะแนนรวม {c:+.0f}/100)",
         f"ปัจจัยหนุนมากที่สุด: {support} ({axes[support][0]:+.0f}) — {axes[support][1][0]}"]
    if axes[oppose][0] * sign < 0:
        L.append(f"ปัจจัยสวนทาง: {oppose} ({axes[oppose][0]:+.0f}) — {axes[oppose][1][0]}")
    if d.get("missing"):
        L.append(f"⚠️ แกนที่ขาดข้อมูล (ไม่นับในคะแนนรวม): {', '.join(d['missing'])}")
    L.append(f"จุดเข้า {res['side']}: {res['status']} (ผ่าน {res['count']}/6)")
    if res["failed_gates"]:
        for g in res["failed_gates"]:
            h = HINTS[g]
            L.append(f"  • {edges.NAMES[g]}: {h[res['side']] if isinstance(h, dict) else h}")
    else:
        L.append(f"แผน: {res['side']} {res['entry_kind']} ที่ {f.format(res['entry'])} · SL {f.format(res['sl'])} · "
                 f"TP {f.format(res['tp'])} · RR 1:{res['rr']:.1f}")
    return L


def _edge_json(res):
    return {"side": res["side"], "edges": {k: num(v, 1) for k, v in res["edges"].items()}, "passed": {k: bool(v) for k, v in res["passed"].items()},
            "detail": res["detail"], "count": res["count"], "status": res["status"], "failed_gates": res["failed_gates"],
            "entry": num(res["entry"]), "entry_kind": res["entry_kind"], "sl": num(res["sl"]), "tp": num(res["tp"]),
            "rr": num(res["rr"], 2), "range": [num(res["range"][0]), num(res["range"][1])]}


def analyze(key: str, tf: str, side_mode: str = "auto", bars: int = 220) -> dict:
    if key not in ASSETS or tf not in TIMEFRAMES:
        raise ValueError("asset/tf ไม่ถูกต้อง")
    a = ASSETS[key]
    df = cached(f"ohlc:{key}:{tf}", 30, data.ohlc, a, tf)
    errs = []
    mac, e = safe("Macro", cached, "macro", 3600, data.macro); errs.append(e)
    cot, e = safe("COT", cached, f"cot:{a['cot']}", 6 * 3600, data.cot, a["cot"], 78, a.get("cot_kind", "legacy")); errs.append(e)
    rt = None
    if key in ("XAUUSD", "EURUSD"):
        rt, e = safe("Rates (Treasury/ECB)", cached, "rates", 6 * 3600, data.rates); errs.append(e)
    deriv = fng = vol = None
    if key == "BTCUSD":
        deriv, e = safe("Binance Futures", cached, f"deriv:{tf}", 300, data.btc_derivatives, "BTCUSDT", tf); errs.append(e)
        fng, e = safe("Fear & Greed", cached, "fng", 1800, data.fear_greed); errs.append(e)
    if a["vol_symbol"] and a["vol_symbol"] != a["yf"]:
        vol, e = safe(f"Volume {a['vol_symbol']}", cached, f"vol:{a['vol_symbol']}:{tf}", 120, data.yf_ohlc, a["vol_symbol"], tf); errs.append(e)
    px = float(df.close.iloc[-1])
    basis = float(vol.close.iloc[-1]) - px if (key == "EURUSD" and vol is not None) else 0.0
    oim = oi_sr = None
    snap, e = safe("Options OI", oi_snapshot, key); errs.append(e)
    if snap:
        oim = oi.analyze(snap, px + basis)
        oi_sr = oi.score(oim, px + basis)
    d = scoring.direction(key, df, mac, cot, deriv, fng, vol, oi_sr, rt=rt, tf=tf)
    side = None if side_mode in ("auto", "อัตโนมัติ", "", None) else side_mode
    res = edges.entry_edges(df, d["composite"], side, tf)
    closed = edges.closed_bars(df, tf)
    prev = edges.entry_edges(closed.iloc[:-1], d["composite"], res["side"], "closed")
    oi_lv = []
    if oim and not oim["expired"]:
        oi_lv = [{"price": num(t["K"] - basis), "label": f"OI #{i} {t['K']:g} · {t['share']:.0f}%"} for i, t in enumerate(oim["top"][:3], 1)]
        oi_lv.append({"price": num(oim["max_pain"] - basis), "label": f"Max Pain {oim['max_pain']:g}"})
    tail = df.tail(bars)
    out = {
        "asset": key, "name": a["name"], "tf": tf, "decimals": a["decimals"], "asof": datetime.now(TH).isoformat(timespec="seconds"),
        "price": num(px), "change_pct": num((df.close.iloc[-1] / df.close.iloc[-2] - 1) * 100, 3),
        "last_bar": tail.index[-1].isoformat(),
        "candles": {"t": [i.isoformat() for i in tail.index], "o": [num(x) for x in tail.open], "h": [num(x) for x in tail.high],
                    "l": [num(x) for x in tail.low], "c": [num(x) for x in tail.close]},
        "composite": num(d["composite"], 2), "bias": bias_label(d["composite"]), "missing": d["missing"],
        "weights": d["weights"], "axes": {k: {"score": num(s, 1), "reasons": r} for k, (s, r) in d["axes"].items()},
        "edges": _edge_json(res), "prev": _edge_json(prev), "gates": sorted(edges.GATES),
        "names": edges.NAMES, "oi_levels": oi_lv, "basis": num(basis),
        "narrative": narrative(key, d, res, a["decimals"]), "errors": [x for x in errs if x],
    }
    if oim:
        out["oi"] = {"series": oim["series"], "src": oim["src"], "t_ms": oim["t_ms"], "e_ms": oim["e_ms"], "dte": num(oim["dte"], 2),
                     "expired": bool(oim["expired"]), "age_days": num(oim["age_days"], 2), "iv": num(oim["iv"], 2), "sd": num(oim["sd"]),
                     "pcr": num(oim["pcr"], 3), "max_pain": num(oim["max_pain"]), "scen": oim["scen"], "experimental": bool(oim["experimental"]),
                     "dD": num(oim["dD"], 4), "dH": num(oim["dH"], 5), "cut": num(oim["cut"], 4), "top": oim["top"],
                     "score_reasons": oi_sr[1] if oi_sr else []}
    return clean(out)


# ------------------------------------------------------------------ นำเข้า OI (LOI1) จาก gold-oi-fetch
def import_loi(text: str, fut: str | None = None, oi_date: str | None = None) -> list[dict]:
    saved = []
    meta = store.get_json("oi/meta.json", {}) or {}
    for line in text.split():
        if not line.startswith("LOI1"):
            continue
        s = oi.save(line)
        old = meta.get(s["asset"], {})
        meta[s["asset"]] = {**({"fut": old["fut"]} if old.get("fut") else {}),
                            **({"fut": fut} if fut else {}), **({"oi_date": oi_date} if oi_date else {}),
                            "series": s["series"], "t_ms": s["t_ms"], "e_ms": s["e_ms"], "n_rows": len(s["rows"]),
                            "note": "นำเข้าผ่านเว็บ (gold-oi-fetch)"}
        saved.append({"asset": s["asset"], "series": s["series"], "strikes": len(s["rows"])})
    if saved:
        store.put_json("oi/meta.json", meta)
    return saved


def import_cme_btc(obj: dict) -> None:
    store.put_json("oi/cme_btc.json", obj)
    _mem.pop("btc_loi", None)


# ------------------------------------------------------------------ Pine
def pine() -> tuple[str, list[str]]:
    meta = store.get_json("oi/meta.json", {}) or {}
    snaps = []
    for a in ("GOLD", "EUR", "BTC"):
        s = oi_snapshot(KEY_OF[a])
        if s:
            snaps.append({"asset": a, "series": s["series"], "loi": s["raw"], "t_ms": s["t_ms"], "n_rows": len(s["rows"]),
                          "fut": meta.get(a, {}).get("fut")})
    snaps.sort(key=lambda x: -x["t_ms"])
    if not snaps:
        raise RuntimeError("ยังไม่มีข้อมูล OI")
    return pine_gen.build(snaps), [f"{s['asset']} {s['series']}" for s in snaps]


# ------------------------------------------------------------------ สถานะ / แจ้งเตือนดึง OI
def expected_oi_date(at: datetime | None = None) -> str:
    d = (at or datetime.now(CT)).astimezone(CT).date() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


def status() -> dict:
    meta = store.get_json("oi/meta.json", {}) or {}
    now = datetime.now(TH)
    nms = now.timestamp() * 1000
    exp = expected_oi_date(now)
    rows = []
    for a, name in (("GOLD", "ทอง"), ("EUR", "EUR"), ("BTC", "BTC")):
        m = meta.get(a, {})
        dte = (m.get("e_ms", 0) - nms) / 86_400_000 if m.get("e_ms") else None
        if a == "BTC":
            note = "Deribit ดึงอัตโนมัติเมื่อเปิดหน้าเว็บ (แคช 30 นาที)"
            due = False
        else:
            expired = dte is not None and dte <= 0
            have = m.get("oi_date")
            due = expired or not have or have < exp
            note = (f"🔔 ถึงเวลาดึงแล้ว ({'series หมดอายุ' if expired else f'ยังไม่มี OI {exp}'}) → สั่ง Claude: ดึง OI {name}"
                    if due else f"✅ มี OI {have} แล้ว")
        rows.append({"asset": a, "series": m.get("series", "—"), "oi_date": m.get("oi_date"), "t_ms": m.get("t_ms"),
                     "e_ms": m.get("e_ms"), "dte": num(dte, 1) if dte is not None else None, "due": due, "note": note})
    return {"backend": store.backend(), "expected_oi_date": exp, "assets": rows}

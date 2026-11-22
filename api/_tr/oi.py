"""Options OI จาก mrM OI Desk (รูปแบบ LOI1) → Local OI levels, Scenario, Max Pain, คะแนน Flow

รูปแบบ: LOI1;a=GOLD;s=G4WV6;e=EXPIRY_MS;t=NOW_MS;f=F;iv=IV[;src=..;vd=..;vc=..]|K,C,P,dC,dP/...
(แถวอาจเป็น K,C,P เฉยๆ และ dC/dP อาจเป็น x = ไม่มีข้อมูล)
"""
from __future__ import annotations

import math
import time
from pathlib import Path

import pandas as pd

from config import GOLD_CUT_D, GOLD_CUT_REF_F, GOLD_CUT_SCALE, OI_STALE_DAYS

ASSET_MAP = {"XAUUSD": "GOLD", "EURUSD": "EUR", "BTCUSD": "BTC"}
CUT_H = 0.0164


def _num(x):
    return float("nan") if x in ("x", "") else float(x)


def parse(s: str) -> dict:
    s = s.strip()
    head, body = s.split("|", 1)
    parts = head.split(";")
    if parts[0] != "LOI1":
        raise ValueError("ไม่ใช่ข้อมูล LOI1")
    meta = dict(p.split("=", 1) for p in parts[1:] if "=" in p)
    rows = []
    for r in body.split("/"):
        v = r.split(",")
        if len(v) < 3:
            continue
        k, c, p = float(v[0]), _num(v[1]), _num(v[2])
        dc = _num(v[3]) if len(v) > 3 else float("nan")
        dp = _num(v[4]) if len(v) > 4 else float("nan")
        rows.append((k, c, p, dc, dp))
    df = pd.DataFrame(rows, columns=["K", "C", "P", "dC", "dP"]).sort_values("K")
    return {"asset": meta["a"], "series": meta["s"], "e_ms": int(meta["e"]), "t_ms": int(meta["t"]),
            "F": float(meta["f"]), "iv": float(meta["iv"]), "src": meta.get("src"),
            "rows": df.fillna({"C": 0, "P": 0}), "raw": s}


# ------------------------------------------------------------ เก็บ/อ่าน (Vercel Blob หรือที่เก็บชั่วคราว ผ่าน store.py)
def save(s: str) -> dict:
    import store
    snap = parse(s)
    store.put_text(f"oi/{snap['asset']}.txt", snap["raw"])
    return snap


def load(asset_key: str) -> dict | None:
    import store
    t = store.get_text(f"oi/{ASSET_MAP[asset_key]}.txt")
    return parse(t) if t else None


# ------------------------------------------------------------ คำนวณ
def _side(df, col):
    tot = df[col].sum()
    if tot <= 0:
        return 0.0, float("nan"), 0.0, 0.0
    w = df[col] / tot
    c = float((df.K * w).sum())
    d = math.sqrt(float((w * (df.K - c) ** 2).sum()))
    h = float((w ** 2).sum())
    return float(tot), c, d, h


def max_pain(df) -> float:
    ks = df.K.values
    pain = [((k - ks).clip(min=0) * df.C.values).sum() + ((ks - k).clip(min=0) * df.P.values).sum()
            for k in ks]
    return float(ks[int(pd.Series(pain).idxmin())])


def analyze(snap: dict, price_fut: float, now_ms: int | None = None) -> dict:
    """price_fut = ราคาปัจจุบันในหน่วยเดียวกับ strike (ราคา futures/forward)"""
    now_ms = now_ms or int(time.time() * 1000)
    df = snap["rows"]
    F, iv = snap["F"], snap["iv"]
    dte = (snap["e_ms"] - now_ms) / 86_400_000
    ct, cc, cd, ch = _side(df, "C")
    pt, pc, pd_, ph = _side(df, "P")
    dD, dH = cd - pd_, ch - ph
    if snap["asset"] == "GOLD":
        # ค่าเริ่มต้น 51.9 จุดตามงานวิจัย (ตรงกับ Pine) · เปิด GOLD_CUT_SCALE ใน config เพื่อปรับตามระดับราคา
        cut = GOLD_CUT_D * F / GOLD_CUT_REF_F if GOLD_CUT_SCALE else GOLD_CUT_D
    else:
        cut = 0.0127 * F
    if dD >= cut:
        scen = "S1 · SELL"
    elif dD <= -cut:
        scen = "S1 · BUY"
    elif dH >= CUT_H:
        scen = "S2 · SELL"
    elif dH <= -CUT_H:
        scen = "S2 · BUY"
    else:
        scen = "S3 · both"
    sd = price_fut * iv / 100 * math.sqrt(max(dte, 0.25) / 365)
    win = df[(df.K >= price_fut - sd) & (df.K <= price_fut + sd)].copy()
    win["T"] = win.C + win.P
    tot_win = win["T"].sum()
    top = []
    if tot_win > 0:
        for _, r in win.nlargest(5, "T").iterrows():
            top.append({"K": float(r.K), "share": float(r["T"] / tot_win * 100),
                        "C": float(r.C), "P": float(r.P)})
    has_chg = df.dC.notna().any() or df.dP.notna().any()
    return {
        "series": snap["series"], "asset": snap["asset"], "src": snap["src"],
        "t_ms": snap["t_ms"], "e_ms": snap["e_ms"], "dte": dte, "expired": dte <= 0,
        "age_days": (now_ms - snap["t_ms"]) / 86_400_000,
        "F": F, "iv": iv, "sd": sd, "call_tot": ct, "put_tot": pt,
        "pcr": pt / ct if ct else float("nan"),
        "call": (cc, cd, ch), "put": (pc, pd_, ph), "dD": dD, "dH": dH, "cut": cut,
        "scen": scen, "experimental": snap["asset"] != "GOLD",
        "max_pain": max_pain(df), "top": top,
        "dC_tot": float(df.dC.sum()) if has_chg else None,
        "dP_tot": float(df.dP.sum()) if has_chg else None,
    }


def score(m: dict, price_fut: float):
    """คะแนน -100..+100 สำหรับแกน Flow Positioning + เหตุผล"""
    tag = " (ทดลอง)" if m["experimental"] else ""
    if m["expired"]:
        return None, [f"Options OI {m['series']} หมดอายุแล้ว → ไม่นำมาคิดคะแนน (ดึง series ใหม่)"]
    base = {"S1 · SELL": -60, "S1 · BUY": 60, "S2 · SELL": -35, "S2 · BUY": 35}.get(m["scen"], 0)
    r = [f"Options OI {m['series']}: Scenario {m['scen']}{tag} · ΔD {m['dD']:+.4g} (cut {m['cut']:.4g}) · ΔHHI {m['dH']:+.4f}",
         f"Put/Call OI = {m['pcr']:.2f} · Max Pain {m['max_pain']:g} · เหลือ {m['dte']:.1f} วัน"]
    s = base
    if m["dte"] < 3:   # ใกล้หมดอายุ ราคามักถูกดึงเข้าหา Max Pain
        gap = (m["max_pain"] - price_fut) / max(m["sd"], 1e-9)
        s += max(-25, min(25, gap * 25))
        r.append(f"ใกล้หมดอายุ: ราคาอยู่{'ต่ำ' if gap > 0 else 'สูง'}กว่า Max Pain → แรงดึง{'ขึ้น' if gap > 0 else 'ลง'}")
    if m["age_days"] > OI_STALE_DAYS:
        # OI เก่า = สถานะอาจเปลี่ยนไปแล้ว → ลดน้ำหนักลงเรื่อยๆ (เหลือต่ำสุด 30% เมื่อเก่า 9 วันขึ้นไป)
        decay = max(0.3, 1 - (m["age_days"] - OI_STALE_DAYS) / 6 * 0.7)
        s *= decay
        r.append(f"⚠️ ข้อมูล OI เก่า {m['age_days']:.0f} วัน → ลดน้ำหนักเหลือ {decay * 100:.0f}%")
    if m["experimental"]:
        s *= 0.5
    return max(-100.0, min(100.0, s)), r

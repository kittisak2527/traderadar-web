"""Entry Edge Radar: เช็กลิสต์จุดเข้า 6 ข้อ (E1–E6) แบบ Smart Money Concept"""
from __future__ import annotations

import pandas as pd

from config import GATES, MIN_RR, PASS_PCT
from indicators import atr, clip, ema, swings

NAMES = {"E1": "Bias", "E2": "PD", "E3": "โซน", "E4": "Sweep", "E5": "ยืนยัน", "E6": "RR"}


def _zones(df, buy: bool, a: float):
    """หา FVG ที่ยังไม่ถูกเติม + โซน swing ล่าสุด"""
    h, l, o, c = df.high.values, df.low.values, df.open.values, df.close.values
    n, out = len(df), []
    for i in range(max(1, n - 60), n - 1):
        if buy and l[i + 1] > h[i - 1]:
            lo, hi = h[i - 1], l[i + 1]
            if i + 2 >= n or l[i + 2:].min() > lo:
                out.append((lo, hi, "Bullish FVG"))
        if not buy and h[i + 1] < l[i - 1]:
            lo, hi = h[i + 1], l[i - 1]
            if i + 2 >= n or h[i + 2:].max() < hi:
                out.append((lo, hi, "Bearish FVG"))
    sh, sl = swings(df)
    if buy and len(sl):
        j = df.index.get_loc(sl.index[-1])
        out.append((l[j], min(o[j], c[j]), "Demand (swing low)"))
    if not buy and len(sh):
        j = df.index.get_loc(sh.index[-1])
        out.append((max(o[j], c[j]), h[j], "Supply (swing high)"))
    return out


_TF_DELTA = {"15m": pd.Timedelta(minutes=15), "1h": pd.Timedelta(hours=1), "4h": pd.Timedelta(hours=4), "1d": pd.Timedelta(days=1)}


def closed_bars(df, tf: str | None):
    """ตัดแท่งสุดท้ายออกถ้ายังไม่ปิด (Binance/Yahoo ส่งแท่งที่กำลังวิ่งมาเป็นแถวสุดท้าย)
    สัญญาณโครงสร้าง (sweep / CHoCH / engulfing / โซน) ต้องดูจากแท่งที่ปิดแล้วเท่านั้น ไม่งั้นจะกะพริบกลางแท่ง"""
    if len(df) < 3 or tf == "closed":       # "closed" = ผู้เรียกตัดแท่งที่ยังวิ่งออกให้แล้ว
        return df
    delta = _TF_DELTA.get(tf or "")
    if delta is None:
        return df.iloc[:-1]
    last = df.index[-1]
    last = last.tz_localize("UTC") if last.tzinfo is None else last
    return df.iloc[:-1] if last + delta > pd.Timestamp.now(tz="UTC") else df


def entry_edges(df, composite: float, side: str | None = None, tf: str | None = None) -> dict:
    side = side or ("BUY" if composite >= 0 else "SELL")
    buy = side == "BUY"
    px = float(df.close.iloc[-1])            # ราคาสด ใช้กับตำแหน่ง PD และ RR
    df = closed_bars(df, tf)                 # โครงสร้างทั้งหมดใช้แท่งที่ปิดแล้ว
    a = float(atr(df).iloc[-1]) or 1e-9
    win = df.tail(60)
    rhi, rlo = max(float(win.high.max()), px), min(float(win.low.min()), px)
    pos = (px - rlo) / (rhi - rlo) if rhi > rlo else 0.5
    E, detail = {}, {}

    # E1 Bias — ทิศทางจากเรดาร์ TA/FA/Flow ตรงกับฝั่งที่จะเทรดหรือไม่
    agree = (composite >= 0) == buy
    E["E1"] = clip(abs(composite) / 40 * 100, 0, 100) if agree else 0.0
    detail["E1"] = (f"คะแนนรวมทิศทาง {composite:+.0f} "
                    + ("ตรงกับฝั่ง " if agree else "สวนทางกับฝั่ง ") + side)

    # E2 Premium / Discount
    p = (0.5 - pos) if buy else (pos - 0.5)
    E["E2"] = clip(p / 0.25 * 100, 0, 100)
    zone_name = "Premium" if pos > 0.5 else "Discount"
    detail["E2"] = (f"ราคาอยู่ {pos * 100:.0f}% ของกรอบ 60 แท่ง ({zone_name}); "
                    f"{'BUY ควรอยู่ต่ำกว่า 37.5% (Discount)' if buy else 'SELL ควรอยู่สูงกว่า 62.5% (Premium)'}")

    # E3 Zone — อยู่ใน/ใกล้ FVG หรือ Supply/Demand
    best, best_z = 0.0, None
    for lo, hi, lab in _zones(df, buy, a):
        d = 0 if lo <= px <= hi else min(abs(px - lo), abs(px - hi)) / a
        sc = clip(100 * (1 - d / 2), 0, 100)
        if sc > best:
            best, best_z = sc, (lo, hi, lab)
    E["E3"] = best
    detail["E3"] = (f"{best_z[2]} {best_z[0]:.5g}–{best_z[1]:.5g}" if best_z else "ไม่พบโซนที่ยังไม่ถูกใช้")

    # E4 Liquidity sweep — กวาด high/low เดิมแล้วปิดกลับ
    sh, sl = swings(df)
    levels = (sl if buy else sh).tail(8)
    E["E4"], sweep_ext = 0.0, None
    recent = df.tail(10)
    for t, L in levels.items():
        after = recent[recent.index > t]
        if after.empty:
            continue
        if buy:
            hit = after[(after.low < L) & (after.close > L)]
            gap = after.low.min() - L               # >= 0 = ยังไม่แตะ · < 0 = ทะลุไปแล้ว
        else:
            hit = after[(after.high > L) & (after.close < L)]
            gap = L - after.high.max()
        if not hit.empty:
            ext = float(hit.low.min() if buy else hit.high.max())
            later = after[after.index > hit.index[-1]]
            # หลังกวาดแล้วมีแท่งปิดเลยจุดที่กวาด = การกวาดล้มเหลว (กลายเป็นแนวแตก)
            if (buy and (later.close < ext).any()) or (not buy and (later.close > ext).any()):
                if E["E4"] < 100:
                    E["E4"] = 0.0
                    detail["E4"] = f"เคยกวาด {'low' if buy else 'high'} ที่ {L:.5g} แต่ราคาปิดเลยจุดกวาด {ext:.5g} ไปแล้ว → การกวาดล้มเหลว"
                continue
            E["E4"] = 100.0
            sweep_ext = ext
            detail["E4"] = f"กวาด {'low' if buy else 'high'} ที่ {L:.5g} แล้วปิดกลับ"
        elif gap < 0:
            # ทะลุแล้วแต่ไม่มีแท่งไหนปิดกลับ = แนวแตก (ไม่ใช่ sweep) ไม่ให้คะแนน
            detail.setdefault("E4", f"ราคาทะลุ {'low' if buy else 'high'} ที่ {L:.5g} โดยไม่ปิดกลับ → แนวแตก ไม่ใช่การกวาด")
        elif gap < 0.2 * a and E["E4"] < 25:
            E["E4"] = 25.0
            detail["E4"] = f"ราคาเข้าใกล้ liquidity ที่ {L:.5g} แต่ยังไม่กวาด"
    detail.setdefault("E4", "ยังไม่มีการกวาด liquidity")

    # E5 ยืนยัน — CHoCH/BOS หรือแท่ง engulfing
    msh, msl = swings(df.tail(30), k=2)
    last, prev = df.iloc[-1], df.iloc[-2]
    E["E5"], detail["E5"] = 0.0, "ยังไม่มีสัญญาณยืนยัน"
    ref = (msh.iloc[-1] if len(msh) else None) if buy else (msl.iloc[-1] if len(msl) else None)
    if ref is not None and ((buy and last.close > ref) or (not buy and last.close < ref)):
        E["E5"], detail["E5"] = 100.0, f"ปิด{'เหนือ' if buy else 'ใต้'} swing ย่อย {ref:.5g} (CHoCH/BOS)"
    elif buy and last.close > prev.open and last.open < prev.close and prev.close < prev.open:
        E["E5"], detail["E5"] = 50.0, "Bullish engulfing"
    elif not buy and last.close < prev.open and last.open > prev.close and prev.close > prev.open:
        E["E5"], detail["E5"] = 50.0, "Bearish engulfing"
    elif (buy and last.close > ema(df.close, 9).iloc[-1]) or (not buy and last.close < ema(df.close, 9).iloc[-1]):
        E["E5"], detail["E5"] = 25.0, "โมเมนตัมระยะสั้นเริ่มไปทางเดียวกัน (EMA9)"

    # E6 Risk:Reward — Entry / SL / TP
    entry, kind = px, "Market"
    if best_z and ((not buy and best_z[0] > px) or (buy and best_z[1] < px)) \
            and abs(px - (best_z[0] if not buy else best_z[1])) < 2 * a:
        entry, kind = (best_z[1] if buy else best_z[0]), "Limit"
    # SL: จุดกวาด liquidity > ขอบโซน (ถ้าเข้า Limit) > swing ล่าสุดที่ใกล้ที่สุด
    near_sl, near_sh = sl.tail(10), sh.tail(10)
    if kind == "Limit" and sweep_ext is None:
        sweep_ext = best_z[0] if buy else best_z[1]
    if buy:
        cand = near_sl[near_sl < entry]
        base = sweep_ext if sweep_ext is not None else (cand.max() if len(cand) else entry - 1.5 * a)
        stop = min(base, entry - 0.5 * a) - 0.2 * a
        tp = rhi
        rr = (tp - entry) / (entry - stop) if tp > entry else 0.0
    else:
        cand = near_sh[near_sh > entry]
        base = sweep_ext if sweep_ext is not None else (cand.min() if len(cand) else entry + 1.5 * a)
        stop = max(base, entry + 0.5 * a) + 0.2 * a
        tp = rlo
        rr = (entry - tp) / (stop - entry) if tp < entry else 0.0
    E["E6"] = clip(rr / 3 * 100, 0, 100)
    detail["E6"] = f"RR 1:{rr:.1f} (ขั้นต่ำ 1:{MIN_RR:.0f})"

    passed = {k: (rr >= MIN_RR if k == "E6" else v >= PASS_PCT) for k, v in E.items()}
    failed_gates = [k for k in sorted(GATES) if not passed[k]]
    count = sum(passed.values())
    if failed_gates:
        status = "⛔ ติดด่าน: " + ", ".join(NAMES[k] for k in failed_gates)
    elif count >= 5:
        status = "✅ พร้อมเข้า"
    else:
        status = "⏳ ผ่านด่านบังคับแล้ว รอเงื่อนไขเสริม"
    return {"side": side, "edges": E, "passed": passed, "detail": detail,
            "count": count, "status": status, "failed_gates": failed_gates,
            "entry": entry, "entry_kind": kind, "sl": stop, "tp": tp, "rr": rr,
            "range": (rlo, rhi)}

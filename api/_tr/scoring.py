"""เรดาร์ทิศทาง: ให้คะแนน 6 แกน (-100 = ลงแรง ... +100 = ขึ้นแรง) พร้อมเหตุผลภาษาไทย"""
from __future__ import annotations

import pandas as pd

from config import WEIGHTS, weights_for
from indicators import atr, clip, cmf, ema, macd, obv, rsi, swings


def _pct(s: pd.Series, n: int) -> float:
    s = s.dropna()
    return float(s.iloc[-1] / s.iloc[-1 - n] - 1) * 100 if len(s) > n else 0.0


def _chg(s: pd.Series, n: int) -> float:
    s = s.dropna()
    return float(s.iloc[-1] - s.iloc[-1 - n]) if len(s) > n else 0.0


# ================================================================ TA
def ta_trend(df):
    c = df.close
    e50, e200, px = ema(c, 50).iloc[-1], ema(c, 200).iloc[-1], c.iloc[-1]
    s, r = 0, []
    if e50 > e200:
        s += 40; r.append("EMA50 อยู่เหนือ EMA200 → โครงสร้างขาขึ้น")
    else:
        s -= 40; r.append("EMA50 อยู่ใต้ EMA200 → โครงสร้างขาลง")
    if px > e200:
        s += 30; r.append("ราคายืนเหนือ EMA200")
    else:
        s -= 30; r.append("ราคาอยู่ใต้ EMA200")
    hi, lo = swings(df)
    if len(hi) >= 2 and len(lo) >= 2:
        hh, hl = hi.iloc[-1] > hi.iloc[-2], lo.iloc[-1] > lo.iloc[-2]
        if hh and hl:
            s += 30; r.append("ทำ Higher High + Higher Low")
        elif not hh and not hl:
            s -= 30; r.append("ทำ Lower High + Lower Low")
        else:
            r.append("โครงสร้าง swing ผสม (sideway)")
    return clip(s), r


def ta_momentum(df):
    c = df.close
    rv = float(rsi(c).iloc[-1])
    _, _, hist = macd(c)
    a = float(atr(df).iloc[-1]) or 1e-9
    h, h_prev = float(hist.iloc[-1]), float(hist.iloc[-2])
    rsi_s = clip((rv - 50) * 2.5)
    macd_s = clip(h / a * 200)
    r = [f"RSI(14) = {rv:.1f}" + (" (overbought)" if rv > 70 else " (oversold)" if rv < 30 else ""),
         f"MACD histogram {'บวก' if h > 0 else 'ลบ'} และ{'เพิ่มขึ้น' if h > h_prev else 'ลดลง'}"]
    return clip(0.5 * rsi_s + 0.5 * macd_s), r


# ================================================================ FA
def _rchg(rt, col, n=20):
    """การเปลี่ยนแปลงของยีลด์ใน n วันทำการ (หน่วย bp) · None ถ้าไม่มีข้อมูล"""
    if rt is None or col not in rt or rt[col].dropna().shape[0] <= n:
        return None
    s = rt[col].dropna()
    return float(s.iloc[-1] - s.iloc[-1 - n]) * 100


def fa_macro(key, mac, rt=None):
    """None = ไม่มีข้อมูล (แกนนี้จะไม่ถูกนับในคะแนนรวม)"""
    if mac is None or mac.empty:
        return None, ["ไม่มีข้อมูลมหภาค"]
    dxy = _pct(mac["DXY"], 20)
    tnx = _chg(mac["US10Y"], 20)          # หน่วย: จุดเปอร์เซ็นต์ของ yield
    ndq = _pct(mac["NASDAQ"], 20)
    dxy_s, tnx_s, ndq_s = clip(dxy / 2 * 100), clip(tnx / 0.3 * 100), clip(ndq / 6 * 100)
    if key == "XAUUSD":
        real = _rchg(rt, "REAL10Y")
        if real is not None:
            # ตัวขับหลักของทองคือ Real yield (ต้นทุนเสียโอกาสของการถือทอง) ไม่ใช่ยีลด์ปกติ
            real_s = clip(real / 25 * 100)
            s = -0.6 * real_s - 0.4 * dxy_s
            r = [f"Real yield 10Y (TIPS) 20 วัน {real:+.0f}bp · ล่าสุด {rt['REAL10Y'].dropna().iloc[-1]:.2f}%",
                 f"DXY 20 วัน {dxy:+.2f}%", "หลักคิด: Real yield ลง + ดอลลาร์อ่อน หนุนทอง"]
        else:
            s = -0.5 * dxy_s - 0.5 * tnx_s
            r = [f"DXY 20 วัน {dxy:+.2f}%", f"US10Y 20 วัน {tnx:+.2f} จุด (ไม่มีข้อมูล Real yield ใช้ยีลด์ปกติแทน)",
                 "หลักคิด: ดอลลาร์อ่อน + yield ลง หนุนทอง"]
    elif key == "EURUSD":
        d2 = _rchg(rt, "EU2Y") if rt is not None else None
        u2 = _rchg(rt, "US2Y") if rt is not None else None
        if d2 is not None and u2 is not None:
            # DXY มี EUR ถึง ~58% → ใช้ DXY = นับราคา EURUSD ซ้ำ · ใช้ส่วนต่างยีลด์ EU − US แทน
            sp2 = d2 - u2
            e10, u10 = _rchg(rt, "EU10Y"), _rchg(rt, "US10Y")
            sp10 = (e10 - u10) if e10 is not None and u10 is not None else 0.0
            lvl = (rt["EU2Y"].dropna().iloc[-1] - rt["US2Y"].dropna().iloc[-1]) * 100
            s = 0.7 * clip(sp2 / 20 * 100) + 0.3 * clip(sp10 / 25 * 100)
            r = [f"ส่วนต่างยีลด์ 2Y (EU − US) {lvl:+.0f}bp · 20 วัน {sp2:+.0f}bp",
                 f"ส่วนต่าง 10Y 20 วัน {sp10:+.0f}bp",
                 "หลักคิด: ส่วนต่างแคบลง (ยีลด์ EU ไล่ขึ้นเทียบ US) = เงินไหลเข้า EUR"]
        else:
            s = -0.6 * dxy_s - 0.4 * tnx_s
            r = [f"DXY 20 วัน {dxy:+.2f}%", f"US10Y 20 วัน {tnx:+.2f} จุด",
                 "⚠️ ไม่มีข้อมูลยีลด์ ECB → ใช้ DXY แทนชั่วคราว (ซ้อนกับราคา EURUSD เอง)"]
    else:
        s = -0.4 * dxy_s + 0.6 * ndq_s
        r = [f"DXY 20 วัน {dxy:+.2f}%", f"US10Y 20 วัน {tnx:+.2f} จุด", f"NASDAQ 20 วัน {ndq:+.2f}%",
             "หลักคิด: risk-on (NASDAQ ขึ้น) + ดอลลาร์อ่อน หนุน BTC"]
    return clip(s), r


def fa_sentiment(key, mac, fng=None):
    if key == "BTCUSD":
        if fng is None:
            return None, ["ไม่มีข้อมูล Fear & Greed"]
        if fng >= 75:
            s = -(fng - 75) * 4; note = "โลภสุดขีด → ระวังกลับตัว (contrarian)"
        elif fng <= 25:
            s = (25 - fng) * 4; note = "กลัวสุดขีด → มักเป็นโซนสะสม (contrarian)"
        else:
            s = (fng - 50) * 2; note = "อยู่ในช่วงปกติ → ตามแนวโน้ม"
        return clip(s), [f"Fear & Greed = {fng}", note]
    if mac is None or mac.empty:
        return None, ["ไม่มีข้อมูล sentiment"]
    if key == "XAUUSD":
        v = float(mac["VIX"].dropna().iloc[-1]); vc = _chg(mac["VIX"], 10)
        return clip(vc / 5 * 100), [f"VIX = {v:.1f} (10 วัน {vc:+.1f})",
                                    "ความกลัวในตลาดเพิ่ม = หนุนทองในฐานะ safe haven"]
    spx = _pct(mac["SPX"], 20)
    return clip(spx / 5 * 60), [f"S&P500 20 วัน {spx:+.2f}%",
                                "risk-on หนุน EUR เล็กน้อย / risk-off หนุนดอลลาร์"]


# ================================================================ Money Flow
def _cot_score(cot):
    if cot is None or len(cot) < 6:
        return None, ["ไม่มีข้อมูล COT"]
    net, oi = cot["net"], cot["oi"].iloc[-1]
    chg4 = (net.iloc[-1] - net.iloc[-5]) / oi
    lo, hi = net.tail(52).min(), net.tail(52).max()        # 52 สัปดาห์ = ครอบคลุมทั้งรอบปี
    idx = (net.iloc[-1] - lo) / (hi - lo) * 100 if hi > lo else 50
    s = clip(chg4 / 0.05 * 100)
    group = cot.attrs.get("group", "non-commercial")
    r = [f"COT กองทุน ({group}) net {net.iloc[-1]:,.0f} สัญญา "
         f"({'เพิ่ม' if chg4 > 0 else 'ลด'} {abs(chg4) * 100:.1f}% ของ OI ใน 4 สัปดาห์)",
         f"COT Index 52 สัปดาห์ = {idx:.0f}"]
    if idx > 90:
        s -= 30; r.append("กองทุน long แน่นมาก → ระวังขายทำกำไร")
    elif idx < 10:
        s += 30; r.append("กองทุน short แน่นมาก → ระวัง short squeeze")
    r.append(f"(ข้อมูล ณ {cot.index[-1]:%d/%m/%Y} ออกทุกวันศุกร์ ล่าช้าประมาณ 3 วัน)")
    return clip(s), r


def flow_positioning(key, df, cot, deriv=None, oi_sr=None):
    cot_s, r = _cot_score(cot)
    parts = [cot_s] if cot_s is not None else []
    if oi_sr:
        oi_s, oi_r = oi_sr
        r = oi_r + r
        if oi_s is not None:
            parts.append(oi_s)
    if key == "BTCUSD" and deriv:
        s, oi = 0, deriv["oi"]
        if len(oi) >= 13:
            oi_c = (oi[-1] / oi[-13] - 1) * 100
            px_c = _pct(df.close, 12)
            if oi_c > 0 and px_c > 0:
                s += 40; r.append(f"OI {oi_c:+.1f}% พร้อมราคาขึ้น → เงินใหม่เข้าฝั่ง long")
            elif oi_c > 0 > px_c:
                s -= 40; r.append(f"OI {oi_c:+.1f}% แต่ราคาลง → เงินใหม่เข้าฝั่ง short")
            elif oi_c <= 0 < px_c:
                s += 10; r.append(f"OI {oi_c:+.1f}% ราคาขึ้น → short covering (แรงไม่ยั่งยืน)")
            else:
                s -= 10; r.append(f"OI {oi_c:+.1f}% ราคาลง → long ถูกล้างพอร์ต")
        f = deriv["funding"]
        r.append(f"Funding rate = {f * 100:.4f}%")
        if f > 0.0005:
            s -= 30; r.append("Funding สูง → long แออัด")
        elif f < -0.0002:
            s += 30; r.append("Funding ติดลบ → short แออัด")
        ls = deriv.get("ls_ratio")
        if ls:
            r.append(f"Long/Short account ratio = {ls:.2f}")
            if ls > 2: s -= 20
            elif ls < 0.8: s += 20
        parts.append(clip(s))
    if not parts:
        return None, r
    return clip(sum(parts) / len(parts)), r


def flow_volume(key, df, vol_df=None):
    if key == "BTCUSD" and "taker_buy" in df:
        t = df.tail(20)
        sell = t.volume - t.taker_buy
        ratio = float((t.taker_buy - sell).sum() / t.volume.sum())
        px = _pct(df.close, 20)
        r = [f"CVD 20 แท่ง: แรงซื้อเชิงรุก {'มากกว่า' if ratio > 0 else 'น้อยกว่า'}แรงขาย ({ratio * 100:+.1f}%)"]
        s = clip(ratio * 1000)
        if ratio > 0 > px:
            r.append("Divergence: ราคาลงแต่มีแรงซื้อสะสม → สัญญาณดูดซับ")
        elif ratio < 0 < px:
            r.append("Divergence: ราคาขึ้นแต่แรงขายเชิงรุกมากกว่า → ระวัง")
        return s, r
    d = vol_df if vol_df is not None and len(vol_df) > 30 else df
    if d.volume.sum() == 0:
        return None, ["ไม่มีข้อมูลวอลุ่ม"]
    c = float(cmf(d).iloc[-1])
    o = obv(d)
    o_up = o.iloc[-1] > o.iloc[-21]
    s = clip(c * 500) + (20 if o_up else -20)
    return clip(s), [f"Chaikin Money Flow(20) = {c:+.3f} → เงิน{'ไหลเข้า' if c > 0 else 'ไหลออก'}",
                     f"OBV 20 แท่ง{'เพิ่มขึ้น' if o_up else 'ลดลง'}"]


# ================================================================ รวมผล
def direction(key, df, mac, cot, deriv=None, fng=None, vol_df=None, oi_sr=None, rt=None, tf=None) -> dict:
    raw = {
        "TA เทรนด์": ta_trend(df),
        "TA โมเมนตัม": ta_momentum(df),
        "FA มหภาค": fa_macro(key, mac, rt),
        "FA Sentiment": fa_sentiment(key, mac, fng),
        "Flow Positioning": flow_positioning(key, df, cot, deriv, oi_sr),
        "Flow Volume": flow_volume(key, df, vol_df),
    }
    W = weights_for(tf) if tf else WEIGHTS
    # แกนที่ไม่มีข้อมูล (score = None) ไม่ถูกนับ แล้วเฉลี่ยน้ำหนักใหม่จากแกนที่เหลือ
    # (เดิมให้ 0 แต่ยังคิดน้ำหนัก → คะแนนรวมถูกดึงเข้าหาศูนย์ และด่าน E1 ไม่ผ่านแบบเงียบๆ)
    missing = [k for k, (s, _) in raw.items() if s is None]
    axes = {k: ((0.0, r + ["⚠️ ไม่มีข้อมูล → ไม่นับในคะแนนรวม"]) if s is None else (s, r)) for k, (s, r) in raw.items()}
    used = {k: w for k, w in W.items() if k not in missing}
    tot = sum(used.values())
    composite = sum(axes[k][0] * w for k, w in used.items()) / tot if tot else 0.0
    return {"axes": axes, "composite": composite, "missing": missing, "weights": W}

"""ตั้งค่าสินทรัพย์และน้ำหนักคะแนน"""

ASSETS = {
    "BTCUSD": {
        "name": "Bitcoin",
        "source": "binance",          # ราคาเรียลไทม์จาก Binance (fallback = yfinance)
        "binance": "BTCUSDT",
        "yf": "BTC-USD",
        "vol_symbol": None,           # ใช้ CVD จาก taker volume ของ Binance แทน
        "cot": "133741",              # CFTC: Bitcoin (CME)
        "decimals": 1,
    },
    "XAUUSD": {
        "name": "ทองคำ",
        "source": "yf",
        "yf": "GC=F",                 # ทองฟิวเจอร์ส COMEX (ใกล้เคียง spot ต่างกันเล็กน้อย)
        "vol_symbol": "GC=F",
        "cot": "088691",              # CFTC: Gold (COMEX)
        "cot_kind": "disagg",         # ใช้ Managed money (Disaggregated) แทน non-commercial
        "decimals": 2,
    },
    "EURUSD": {
        "name": "EUR/USD",
        "source": "yf",
        "yf": "EURUSD=X",
        "vol_symbol": "6E=F",         # Spot FX ไม่มีวอลุ่ม -> ใช้ Euro FX futures (CME)
        "cot": "099741",              # CFTC: Euro FX (CME)
        "decimals": 5,
    },
}

TIMEFRAMES = ["15m", "1h", "4h", "1d"]

# น้ำหนักของ 6 แกนในเรดาร์ทิศทาง (รวม = 100) — ค่าหลักใช้กับ 4h / 1d
WEIGHTS = {
    "TA เทรนด์": 20,
    "TA โมเมนตัม": 15,
    "FA มหภาค": 20,
    "FA Sentiment": 10,
    "Flow Positioning": 20,
    "Flow Volume": 15,
}
# ข้อมูล FA เป็นรายวัน/20 วัน จึงลดน้ำหนักลงใน timeframe สั้น แล้วยกให้ TA/Volume แทน
WEIGHTS_BY_TF = {
    "15m": {"TA เทรนด์": 25, "TA โมเมนตัม": 25, "FA มหภาค": 8, "FA Sentiment": 5, "Flow Positioning": 15, "Flow Volume": 22},
    "1h": {"TA เทรนด์": 23, "TA โมเมนตัม": 20, "FA มหภาค": 14, "FA Sentiment": 8, "Flow Positioning": 17, "Flow Volume": 18},
    "4h": WEIGHTS,
    "1d": WEIGHTS,
}


def weights_for(tf: str) -> dict:
    return WEIGHTS_BY_TF.get(tf, WEIGHTS)


# Options OI · Scenario ของทอง: 51.9 จุดมาจากงานวิจัย (ตรงกับค่าใน Pine mrM Local OI)
GOLD_CUT_D = 51.9
GOLD_CUT_SCALE = False      # True = ปรับตามราคา (51.9 × F / 4090) · ค่าเริ่มต้น False เพื่อให้ตรงกับ Pine
GOLD_CUT_REF_F = 4090.0
OI_STALE_DAYS = 3           # OI เก่ากว่านี้เริ่มลดน้ำหนักคะแนน · ลดเหลือ 30% เมื่อเก่า 9 วันขึ้นไป

# ด่านบังคับของ Entry Edge (ไม่ผ่านข้อใดข้อหนึ่ง = ห้ามเข้า)
GATES = {"E1", "E2", "E4", "E6"}
PASS_PCT = 50      # คะแนนขั้นต่ำต่อ edge ที่ถือว่า "ผ่าน"
MIN_RR = 2.0       # RR ขั้นต่ำที่ผ่านด่าน E6

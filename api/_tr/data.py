"""ดึงข้อมูลจากแหล่งฟรี (เวอร์ชันเว็บ ไม่ใช้ yfinance เพื่อให้ฟังก์ชันบน Vercel เล็กและเริ่มเร็ว)
Binance · Yahoo Finance (chart API) · US Treasury · ECB · CFTC · alternative.me
"""
from __future__ import annotations

import io
import time

import pandas as pd
import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
TIMEOUT = 12
_AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
# Yahoo: (interval, range) ต่อ timeframe · 4h สร้างจาก 1h
_YF = {"15m": ("15m", "30d"), "1h": ("60m", "180d"), "4h": ("60m", "360d"), "1d": ("1d", "3y")}


def _get(url: str, params: dict | None = None, retries: int = 2):
    for i in range(retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if i == retries - 1:
                raise
            time.sleep(1.0 * (i + 1))


# ---------------------------------------------------------------- OHLC
def _yahoo_chart(symbol: str, interval: str, rng: str) -> pd.DataFrame:
    last_err = None
    for host in ("query1", "query2"):
        try:
            j = _get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}", {"interval": interval, "range": rng})
            res = j["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            df = pd.DataFrame({"open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"],
                               "volume": q.get("volume") or [0] * len(res["timestamp"])},
                              index=pd.to_datetime(res["timestamp"], unit="s", utc=True))
            df = df.dropna(subset=["close"])
            for col in ("open", "high", "low"):
                df[col] = df[col].fillna(df["close"])
            df["volume"] = df["volume"].fillna(0)
            if interval == "1d":
                df = df[~df.index.normalize().duplicated(keep="last")]
            return df.astype(float)
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise RuntimeError(f"Yahoo ไม่มีข้อมูล {symbol}: {last_err}")


def yf_ohlc(symbol: str, tf: str) -> pd.DataFrame:
    interval, rng = _YF[tf]
    df = _yahoo_chart(symbol, interval, rng)
    if tf == "4h":
        df = resample_4h(df, symbol)
    return df


def resample_4h(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """จัดแท่ง 4H ให้ตรง TradingView: futures เริ่ม 18:00 NY · Spot FX 17:00 NY · อื่นๆ ตาม UTC"""
    if symbol.endswith("=F"):
        tz, offset = "America/New_York", "2h"
    elif symbol.endswith("=X"):
        tz, offset = "America/New_York", "1h"
    else:
        tz, offset = "UTC", "0h"
    out = df.tz_convert(tz).resample("4h", offset=offset).agg(_AGG).dropna(subset=["close"])
    return out.tz_convert("UTC")


def binance_ohlc(symbol: str, tf: str, limit: int = 600) -> pd.DataFrame:
    raw = _get("https://api.binance.com/api/v3/klines", {"symbol": symbol, "interval": tf, "limit": limit})
    df = pd.DataFrame(raw, columns=["t", "open", "high", "low", "close", "volume", "ct", "qv", "n", "taker_buy", "tbq", "x"])
    df.index = pd.to_datetime(df["t"], unit="ms", utc=True)
    return df[["open", "high", "low", "close", "volume", "taker_buy"]].astype(float)


def ohlc(asset: dict, tf: str) -> pd.DataFrame:
    if asset["source"] == "binance":
        try:
            return binance_ohlc(asset["binance"], tf)
        except Exception:  # noqa: BLE001  ถ้า Binance ใช้ไม่ได้ (บล็อกภูมิภาค) ใช้ Yahoo แทน
            pass
    return yf_ohlc(asset["yf"], tf)


# ---------------------------------------------------------------- Macro (รายวัน)
MACRO_SYMBOLS = {"DXY": "DX-Y.NYB", "US10Y": "^TNX", "NASDAQ": "^IXIC", "SPX": "^GSPC", "VIX": "^VIX"}


def macro() -> pd.DataFrame:
    cols = {}
    for name, sym in MACRO_SYMBOLS.items():
        try:
            d = _yahoo_chart(sym, "1d", "6mo")
            cols[name] = d["close"].set_axis(d.index.normalize())
        except Exception:  # noqa: BLE001
            continue
    if not cols:
        raise RuntimeError("ดึงข้อมูลมหภาคไม่ได้")
    return pd.DataFrame(cols).sort_index().ffill()


# ---------------------------------------------------------------- ดอกเบี้ย (ฟรี ไม่ต้องใช้คีย์)
def _treasury(kind: str, year: int) -> pd.DataFrame:
    url = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
           f"daily-treasury-rates.csv/{year}/all?type={kind}&field_tdr_date_value={year}&page&_format=csv")
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y")
    return df.set_index("Date")


def _ecb(key: str, start: str) -> pd.Series:
    r = requests.get(f"https://data-api.ecb.europa.eu/service/data/{key}", params={"format": "csvdata", "startPeriod": start},
                     headers=HEADERS, timeout=25)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    return pd.Series(df["OBS_VALUE"].values, index=pd.to_datetime(df["TIME_PERIOD"])).astype(float)


def rates() -> pd.DataFrame:
    """US 2Y/10Y + Real 10Y (US Treasury) · EU 2Y/10Y (ECB AAA yield curve)"""
    y = pd.Timestamp.now().year
    nom = pd.concat([_treasury("daily_treasury_yield_curve", yy) for yy in (y - 1, y)]).sort_index()
    real = pd.concat([_treasury("daily_treasury_real_yield_curve", yy) for yy in (y - 1, y)]).sort_index()
    out = pd.DataFrame({"US2Y": nom["2 Yr"], "US10Y": nom["10 Yr"]})
    out["REAL10Y"] = real["10 YR"].reindex(out.index)
    start = (pd.Timestamp.now() - pd.Timedelta(days=400)).strftime("%Y-%m-%d")
    for col, key in (("EU2Y", "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y"), ("EU10Y", "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y")):
        try:
            out = out.join(_ecb(key, start).rename(col), how="outer")
        except requests.RequestException:
            out[col] = float("nan")
    return out.sort_index().ffill()


# ---------------------------------------------------------------- CFTC COT (รายสัปดาห์)
def cot(code: str, weeks: int = 78, kind: str = "legacy") -> pd.DataFrame:
    url = ("https://publicreporting.cftc.gov/resource/72hh-3qpy.json" if kind == "disagg"
           else "https://publicreporting.cftc.gov/resource/6dca-aqww.json")
    rows = _get(url, {"cftc_contract_market_code": code, "$order": "report_date_as_yyyy_mm_dd DESC", "$limit": weeks})
    df = pd.DataFrame(rows)
    lc, sc = (("m_money_positions_long_all", "m_money_positions_short_all") if kind == "disagg"
              else ("noncomm_positions_long_all", "noncomm_positions_short_all"))
    out = pd.DataFrame({"date": pd.to_datetime(df["report_date_as_yyyy_mm_dd"]), "long": df[lc].astype(float),
                        "short": df[sc].astype(float), "oi": df["open_interest_all"].astype(float)}).sort_values("date").set_index("date")
    out["net"] = out["long"] - out["short"]
    out.attrs["group"] = "Managed money" if kind == "disagg" else "non-commercial"
    return out


# ---------------------------------------------------------------- BTC derivatives / sentiment
def btc_derivatives(symbol: str = "BTCUSDT", period: str = "4h") -> dict:
    base = "https://fapi.binance.com"
    prem = _get(f"{base}/fapi/v1/premiumIndex", {"symbol": symbol})
    oi = _get(f"{base}/futures/data/openInterestHist", {"symbol": symbol, "period": period, "limit": 30})
    ls = _get(f"{base}/futures/data/globalLongShortAccountRatio", {"symbol": symbol, "period": period, "limit": 1})
    return {"funding": float(prem["lastFundingRate"]), "oi": [float(x["sumOpenInterest"]) for x in oi],
            "ls_ratio": float(ls[-1]["longShortRatio"]) if ls else None}


def fear_greed() -> int:
    return int(_get("https://api.alternative.me/fng/", {"limit": 1})["data"][0]["value"])

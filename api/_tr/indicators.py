"""อินดิเคเตอร์พื้นฐาน (เขียนเองด้วย pandas ไม่ต้องพึ่ง TA-Lib)"""
import numpy as np
import pandas as pd


def clip(x, lo=-100.0, hi=100.0) -> float:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return 0.0
    return float(max(lo, min(hi, x)))


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def macd(s: pd.Series):
    m = ema(s, 12) - ema(s, 26)
    sig = ema(m, 9)
    return m, sig, m - sig


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    tr = pd.concat([df.high - df.low,
                    (df.high - df.close.shift()).abs(),
                    (df.low - df.close.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def cmf(df: pd.DataFrame, n: int = 20) -> pd.Series:
    rng = (df.high - df.low).replace(0, np.nan)
    mfm = ((df.close - df.low) - (df.high - df.close)) / rng
    return (mfm * df.volume).rolling(n).sum() / df.volume.rolling(n).sum()


def obv(df: pd.DataFrame) -> pd.Series:
    return (np.sign(df.close.diff()).fillna(0) * df.volume).cumsum()


def swings(df: pd.DataFrame, k: int = 3):
    """Fractal swing high/low (ยืนยันแล้ว k แท่งทั้งสองข้าง จึงไม่ repaint)"""
    w = 2 * k + 1
    hi = df.high[df.high == df.high.rolling(w, center=True).max()]
    lo = df.low[df.low == df.low.rolling(w, center=True).min()]
    return hi, lo

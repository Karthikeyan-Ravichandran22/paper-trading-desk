"""Technical indicators matching TradingView / Pine Script ta.* semantics where possible."""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length).mean()


def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()


def macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    line = fast_ema - slow_ema
    sig = ema(line, signal)
    hist = line - sig
    return line, sig, hist


def cci(close: pd.Series, length: int = 14) -> pd.Series:
    # Pine ta.cci(close, len) uses close as source for typical price approximation
    tp = close
    sma_tp = sma(tp, length)
    mad = tp.rolling(length).apply(lambda x: np.mean(np.abs(x - np.mean(x))), raw=True)
    return (tp - sma_tp) / (0.015 * mad.replace(0, np.nan))


def stoch(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    length: int = 14,
) -> pd.Series:
    lowest = low.rolling(length).min()
    highest = high.rolling(length).max()
    return 100 * (close - lowest) / (highest - lowest).replace(0, np.nan)


def dmi(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    di_len: int = 14,
    adx_len: int = 14,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    up = high.diff()
    down = -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = atr(high, low, close, di_len) * di_len  # rough; use TR smoothed
    prev_close = close.shift(1)
    tr_raw = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    atr_s = tr_raw.ewm(alpha=1 / di_len, min_periods=di_len, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=high.index).ewm(
        alpha=1 / di_len, min_periods=di_len, adjust=False
    ).mean() / atr_s.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=high.index).ewm(
        alpha=1 / di_len, min_periods=di_len, adjust=False
    ).mean() / atr_s.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / adx_len, min_periods=adx_len, adjust=False).mean()
    return plus_di, minus_di, adx


def supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    factor: float = 3.0,
    atr_len: int = 10,
) -> tuple[pd.Series, pd.Series]:
    """Returns (st_line, direction) where direction < 0 is bullish (Pine convention)."""
    atr_v = atr(high, low, close, atr_len)
    hl2 = (high + low) / 2
    upper = hl2 + factor * atr_v
    lower = hl2 - factor * atr_v

    st = pd.Series(index=close.index, dtype=float)
    direction = pd.Series(index=close.index, dtype=float)
    prev_st = np.nan
    prev_dir = 1.0
    prev_upper = np.nan
    prev_lower = np.nan

    for i in range(len(close)):
        if np.isnan(atr_v.iloc[i]):
            st.iloc[i] = np.nan
            direction.iloc[i] = np.nan
            continue

        curr_upper = upper.iloc[i]
        curr_lower = lower.iloc[i]

        if not np.isnan(prev_lower):
            curr_lower = max(curr_lower, prev_lower) if close.iloc[i - 1] > prev_lower else curr_lower
        if not np.isnan(prev_upper):
            curr_upper = min(curr_upper, prev_upper) if close.iloc[i - 1] < prev_upper else curr_upper

        if np.isnan(prev_st):
            curr_dir = 1.0
            curr_st = curr_upper
        elif prev_dir == -1.0:  # was bullish (below)
            if close.iloc[i] < curr_lower:
                curr_dir = 1.0
                curr_st = curr_upper
            else:
                curr_dir = -1.0
                curr_st = curr_lower
        else:
            if close.iloc[i] > curr_upper:
                curr_dir = -1.0
                curr_st = curr_lower
            else:
                curr_dir = 1.0
                curr_st = curr_upper

        st.iloc[i] = curr_st
        direction.iloc[i] = curr_dir
        prev_st = curr_st
        prev_dir = curr_dir
        prev_upper = curr_upper
        prev_lower = curr_lower

    return st, direction


def highest(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length).max()


def lowest(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length).min()


def crossover(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a > b) & (a.shift(1) <= b.shift(1))


def crossunder(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a < b) & (a.shift(1) >= b.shift(1))

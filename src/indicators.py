from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    out = out.where(loss > 0, 100.0)
    out = out.mask(gain <= 0, 0.0)
    out = out.mask((gain <= 0) & (loss <= 0), 50.0)
    return out


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["Close"].shift(1)
    tr = pd.concat(
        [
            (df["High"] - df["Low"]).abs(),
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def macd_hist(series: pd.Series) -> pd.Series:
    line = ema(series, 12) - ema(series, 26)
    return line - ema(line, 9)


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    up = df["High"].diff()
    down = -df["Low"].diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = atr(df, period)
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean() / tr
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean() / tr
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100
    return dx.ewm(alpha=1 / period, adjust=False).mean()


def bollinger(series: pd.Series, window: int = 20, num_std: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = sma(series, window)
    std = series.rolling(window).std()
    return mid + num_std * std, mid, mid - num_std * std


def vwap(df: pd.DataFrame) -> pd.Series:
    typical = (df["High"] + df["Low"] + df["Close"]) / 3.0
    vol = df["Volume"].replace(0, np.nan)
    return (typical * vol).cumsum() / vol.cumsum()


def _ny_index(df: pd.DataFrame) -> pd.DatetimeIndex:
    idx = df.index
    if not isinstance(idx, pd.DatetimeIndex):
        idx = pd.to_datetime(idx)
    if getattr(idx, "tz", None) is not None:
        return idx.tz_convert("America/New_York")
    return idx.tz_localize("America/New_York", ambiguous="infer", nonexistent="shift_forward")


def session_vwap(df: pd.DataFrame) -> pd.Series:
    if df is None or df.empty:
        return pd.Series(dtype=float)
    work = df.copy()
    work.index = _ny_index(work)
    parts = []
    for _, chunk in work.groupby(work.index.date, sort=False):
        parts.append(vwap(chunk))
    return pd.concat(parts)


def last_session(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    work = df.copy()
    work.index = _ny_index(work)
    last = work.index[-1].date()
    return work[work.index.date == last]


def swing_points(df: pd.DataFrame, lookback: int = 3) -> tuple[float | None, float | None]:
    if df is None or len(df) < lookback * 2 + 3:
        return None, None
    highs = df["High"].values
    lows = df["Low"].values
    last_high = None
    last_low = None
    for i in range(lookback, len(df) - lookback):
        window_h = highs[i - lookback : i + lookback + 1]
        window_l = lows[i - lookback : i + lookback + 1]
        if highs[i] == window_h.max():
            last_high = float(highs[i])
        if lows[i] == window_l.min():
            last_low = float(lows[i])
    return last_high, last_low


def opening_range(intra: pd.DataFrame, minutes: int = 30) -> tuple[float | None, float | None, str | None]:
    day = last_session(intra)
    if day.empty:
        return None, None, None
    cash = day[day.index.strftime("%H:%M") >= "09:30"]
    base = cash if not cash.empty else day
    start = base.index[0]
    end = start + pd.Timedelta(minutes=minutes)
    window = base[(base.index >= start) & (base.index < end)]
    if window.empty:
        window = base.iloc[:2]
    if window.empty:
        return None, None, None
    return float(window["High"].max()), float(window["Low"].min()), str(base.index[-1].date())


def overnight_gap(daily: pd.DataFrame, intra: pd.DataFrame) -> float:
    if daily is None or len(daily) < 2:
        return 0.0
    prior_close = float(daily["Close"].iloc[-2]) if len(daily) >= 2 else float(daily["Close"].iloc[-1])
    day = last_session(intra) if intra is not None and not intra.empty else pd.DataFrame()
    if day.empty:
        last_open = float(daily["Open"].iloc[-1])
    else:
        cash = day[day.index.strftime("%H:%M") >= "09:30"]
        last_open = float((cash if not cash.empty else day)["Open"].iloc[0])
    if prior_close <= 0:
        return 0.0
    return (last_open - prior_close) / prior_close


def intra_rvol(intra: pd.DataFrame, bars: int = 6) -> float:
    day = last_session(intra)
    if day is None or len(day) < bars + 2:
        return 1.0
    vol = day["Volume"].fillna(0)
    recent = float(vol.iloc[-bars:].mean())
    base = float(vol.iloc[:-bars].median()) if len(vol) > bars else float(vol.median())
    if base <= 0:
        return 1.0
    return recent / base


def intra_bias(intra: pd.DataFrame) -> str:
    day = last_session(intra)
    if day is None or len(day) < 8:
        return "FLAT"
    e9 = float(ema(day["Close"], 9).iloc[-1])
    e21 = float(ema(day["Close"], 21).iloc[-1]) if len(day) >= 21 else float(ema(day["Close"], 8).iloc[-1])
    if e9 > e21 * 1.001:
        return "LONG"
    if e9 < e21 * 0.999:
        return "SHORT"
    return "FLAT"

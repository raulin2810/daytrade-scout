from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import numpy as np
import pandas as pd


Side = Literal["LONG", "SHORT", "SKIP"]


@dataclass
class Idea:
    symbol: str
    name: str
    side: Side
    score: float
    price: float
    currency: str
    entry: float
    stop: float
    target: float
    atr: float
    risk_per_share: float
    shares: int
    position_value: float
    risk_amount: float
    reward_risk: float
    reasons: list[str]
    change_pct: float
    rsi: float
    volume_ratio: float
    news_score: float
    headlines: list[str]


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def macd_hist(series: pd.Series) -> pd.Series:
    macd_line = ema(series, 12) - ema(series, 26)
    signal = ema(macd_line, 9)
    return macd_line - signal


def analyze(
    df: pd.DataFrame,
    quote_price: float,
    news_score: float,
    atr_stop_mult: float = 1.5,
    reward_risk: float = 2.0,
) -> dict:
    if df is None or len(df) < 30:
        return {"side": "SKIP", "score": 0.0, "reasons": ["Zu wenig Kursdaten"], "rsi": 50.0, "atr": 0.0}

    close = df["Close"]
    last = float(close.iloc[-1])
    price = quote_price or last
    ema9 = float(ema(close, 9).iloc[-1])
    ema21 = float(ema(close, 21).iloc[-1])
    rsi_val = float(rsi(close).iloc[-1])
    hist = macd_hist(close)
    macd_now = float(hist.iloc[-1])
    macd_prev = float(hist.iloc[-2]) if len(hist) > 1 else 0.0
    atr_val = float(atr(df).iloc[-1])
    vol = df["Volume"].fillna(0)
    vol_ratio = float(vol.iloc[-5:].mean() / max(vol.iloc[-20:].mean(), 1))

    reasons: list[str] = []
    long_score = 0.0
    short_score = 0.0

    if ema9 > ema21:
        long_score += 18
        reasons.append("EMA9 über EMA21 (Aufwärtstrend kurzfristig)")
    else:
        short_score += 18
        reasons.append("EMA9 unter EMA21 (Abwärtstrend kurzfristig)")

    if price > ema21:
        long_score += 10
    else:
        short_score += 10

    if 45 <= rsi_val <= 68:
        long_score += 16
        reasons.append(f"RSI {rsi_val:.0f} – nicht überkauft, Raum nach oben")
    elif 32 <= rsi_val <= 55:
        short_score += 16
        reasons.append(f"RSI {rsi_val:.0f} – nicht überverkauft, Raum nach unten")
    elif rsi_val > 75:
        short_score += 8
        reasons.append(f"RSI {rsi_val:.0f} überkauft")
    elif rsi_val < 25:
        long_score += 8
        reasons.append(f"RSI {rsi_val:.0f} überverkauft")

    if macd_now > 0 and macd_now > macd_prev:
        long_score += 14
        reasons.append("MACD-Histogramm steigt im positiven Bereich")
    elif macd_now < 0 and macd_now < macd_prev:
        short_score += 14
        reasons.append("MACD-Histogramm fällt im negativen Bereich")

    if vol_ratio >= 1.3:
        long_score += 10
        short_score += 10
        reasons.append(f"Volumen erhöht ({vol_ratio:.1f}× Durchschnitt)")

    if news_score > 0.15:
        long_score += 12
        reasons.append("Nachrichten eher positiv")
    elif news_score < -0.15:
        short_score += 12
        reasons.append("Nachrichten eher negativ")

    ret_3 = float(close.iloc[-1] / close.iloc[-4] - 1) if len(close) >= 4 else 0.0
    if ret_3 > 0.02:
        long_score += 8
    elif ret_3 < -0.02:
        short_score += 8

    if long_score >= short_score and long_score >= 40:
        side: Side = "LONG"
        score = long_score
    elif short_score > long_score and short_score >= 40:
        side = "SHORT"
        score = short_score
    else:
        side = "SKIP"
        score = max(long_score, short_score)
        reasons.append("Kein klares Setup – besser abwarten")

    if atr_val <= 0:
        atr_val = price * 0.015

    if side == "LONG":
        entry = price
        stop = entry - atr_stop_mult * atr_val
        target = entry + reward_risk * (entry - stop)
    elif side == "SHORT":
        entry = price
        stop = entry + atr_stop_mult * atr_val
        target = entry - reward_risk * (stop - entry)
    else:
        entry = price
        stop = price - atr_stop_mult * atr_val
        target = price + reward_risk * atr_stop_mult * atr_val

    return {
        "side": side,
        "score": round(score, 1),
        "reasons": reasons[:6],
        "rsi": rsi_val,
        "atr": atr_val,
        "entry": entry,
        "stop": stop,
        "target": target,
        "volume_ratio": vol_ratio,
    }


def size_position(
    entry: float,
    stop: float,
    capital: float,
    risk_pct: float,
) -> tuple[int, float, float]:
    risk_per_share = abs(entry - stop)
    risk_amount = capital * (risk_pct / 100.0)
    if risk_per_share <= 0 or entry <= 0:
        return 0, 0.0, risk_amount
    shares = int(risk_amount // risk_per_share)
    position_value = shares * entry
    if position_value > capital:
        shares = int(capital // entry)
        position_value = shares * entry
    return shares, position_value, risk_amount

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd
import yfinance as yf


@dataclass
class Quote:
    symbol: str
    name: str
    price: float
    currency: str
    change_pct: float
    volume: float
    avg_volume: float
    market_cap: Optional[float]


def fetch_history(symbol: str, period: str = "60d", interval: str = "1d") -> pd.DataFrame:
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval, auto_adjust=True)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.rename(columns=str.title)
    df = df.dropna(subset=["Close"])
    return df


def fetch_intraday(symbol: str, period: str = "5d", interval: str = "15m") -> pd.DataFrame:
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval, auto_adjust=True)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.rename(columns=str.title)
    return df.dropna(subset=["Close"])


def fetch_quote(symbol: str) -> Optional[Quote]:
    ticker = yf.Ticker(symbol)
    info = {}
    try:
        info = ticker.fast_info or {}
    except Exception:
        info = {}

    price = _safe_float(info.get("last_price") or info.get("lastPrice"))
    if price is None:
        hist = fetch_history(symbol, period="5d", interval="1d")
        if hist.empty:
            return None
        price = float(hist["Close"].iloc[-1])

    prev = _safe_float(info.get("previous_close") or info.get("previousClose"))
    change_pct = 0.0
    if prev and prev > 0:
        change_pct = (price - prev) / prev * 100.0
    else:
        hist = fetch_history(symbol, period="5d", interval="1d")
        if len(hist) >= 2:
            prev = float(hist["Close"].iloc[-2])
            if prev:
                change_pct = (price - prev) / prev * 100.0

    name = symbol
    currency = str(info.get("currency") or "USD")
    volume = _safe_float(info.get("last_volume") or info.get("lastVolume")) or 0.0
    avg_volume = _safe_float(info.get("three_month_average_volume")) or volume
    market_cap = _safe_float(info.get("market_cap") or info.get("marketCap"))

    try:
        long_name = ticker.info.get("shortName") or ticker.info.get("longName")
        if long_name:
            name = long_name
    except Exception:
        pass

    return Quote(
        symbol=symbol,
        name=name,
        price=float(price),
        currency=currency,
        change_pct=float(change_pct),
        volume=float(volume),
        avg_volume=float(avg_volume or 0),
        market_cap=market_cap,
    )


def _safe_float(value) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import yfinance as yf


def _norm_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = [
            str(c[0]).title() if isinstance(c, tuple) else str(c).title()
            for c in df.columns
        ]
    else:
        df = df.rename(columns=str.title)
    needed = {"Open", "High", "Low", "Close"}
    if not needed.issubset(set(df.columns)):
        return pd.DataFrame()
    if "Volume" not in df.columns:
        df["Volume"] = 0.0
    return df.dropna(subset=["Close"])


def download_batch(symbols: list[str], period: str, interval: str) -> dict[str, pd.DataFrame]:
    symbols = [s for s in symbols if s]
    if not symbols:
        return {}
    raw = yf.download(
        tickers=" ".join(symbols),
        period=period,
        interval=interval,
        group_by="ticker",
        auto_adjust=True,
        threads=True,
        progress=False,
    )
    out: dict[str, pd.DataFrame] = {}
    if raw is None or raw.empty:
        return out
    if len(symbols) == 1:
        out[symbols[0]] = _norm_ohlcv(raw)
        return out
    if isinstance(raw.columns, pd.MultiIndex):
        for sym in symbols:
            if sym in raw.columns.get_level_values(0):
                out[sym] = _norm_ohlcv(raw[sym])
            elif sym in raw.columns.get_level_values(1):
                out[sym] = _norm_ohlcv(raw.xs(sym, axis=1, level=1))
    else:
        out[symbols[0]] = _norm_ohlcv(raw)
    return out


@dataclass
class Snapshot:
    symbol: str
    name: str
    price: float
    currency: str
    change_pct: float
    avg_volume: float
    market_cap: Optional[float]
    short_ratio: Optional[float]
    earnings_ts: Optional[int]
    week52_high: Optional[float]
    week52_low: Optional[float]
    sector: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def earnings_soon(self) -> bool:
        if not self.earnings_ts:
            return False
        now = datetime.now(timezone.utc).timestamp()
        return 0 <= self.earnings_ts - now <= 5 * 24 * 3600


def snapshots(symbols: list[str]) -> dict[str, Snapshot]:
    result: dict[str, Snapshot] = {}
    for symbol in symbols:
        ticker = yf.Ticker(symbol)
        info: dict = {}
        try:
            info = dict(ticker.fast_info or {})
        except Exception:
            info = {}
        slow: dict = {}
        try:
            slow = ticker.info or {}
        except Exception:
            slow = {}

        price = _f(
            info.get("last_price")
            or info.get("lastPrice")
            or slow.get("currentPrice")
            or slow.get("regularMarketPrice")
        )
        prev = _f(
            info.get("previous_close")
            or info.get("previousClose")
            or slow.get("previousClose")
            or slow.get("regularMarketPreviousClose")
        )
        if price is None:
            continue
        change = ((price - prev) / prev * 100.0) if prev else 0.0
        name = slow.get("shortName") or slow.get("longName") or symbol
        result[symbol] = Snapshot(
            symbol=symbol,
            name=str(name),
            price=float(price),
            currency=str(info.get("currency") or slow.get("currency") or "USD"),
            change_pct=float(change),
            avg_volume=float(
                _f(
                    info.get("three_month_average_volume")
                    or slow.get("averageDailyVolume10Day")
                    or slow.get("averageVolume")
                )
                or 0
            ),
            market_cap=_f(info.get("market_cap") or slow.get("marketCap")),
            short_ratio=_f(slow.get("shortRatio")),
            earnings_ts=_i(slow.get("earningsTimestamp") or slow.get("earningsTimestampStart")),
            week52_high=_f(slow.get("fiftyTwoWeekHigh") or info.get("year_high")),
            week52_low=_f(slow.get("fiftyTwoWeekLow") or info.get("year_low")),
            sector=str(slow.get("sector") or ""),
        )
    return result


def _f(value) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _i(value) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None

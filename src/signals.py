from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

import pandas as pd

from src.data import Snapshot
from src.indicators import (
    adx,
    atr,
    bollinger,
    ema,
    macd_hist,
    opening_range,
    rsi,
    session_vwap,
    swing_points,
)
from src.market import Regime


Side = Literal["LONG", "SHORT", "SKIP"]
Setup = Literal["ORB", "VWAP_RECLAIM", "PULLBACK", "BREAKOUT", "FADE", "WAIT", "NONE"]
Grade = Literal["A", "B", "C", "F"]


@dataclass
class Idea:
    symbol: str
    name: str
    side: Side
    setup: Setup
    grade: Grade
    score: float
    confluence: int
    price: float
    currency: str
    entry: float
    stop: float
    target1: float
    target2: float
    invalidation: str
    playbook: str
    atr: float
    atr_pct: float
    risk_per_share: float
    shares: int
    position_value: float
    risk_amount: float
    reward_risk: float
    reasons: list[str]
    warnings: list[str]
    change_pct: float
    rsi: float
    adx: float
    volume_ratio: float
    news_score: float
    headlines: list[str]
    vwap: Optional[float]
    or_high: Optional[float]
    or_low: Optional[float]
    swing_high: Optional[float]
    swing_low: Optional[float]
    rel_spy: float
    earnings_soon: bool
    extras: dict = field(default_factory=dict)


def size_position(entry: float, stop: float, capital: float, risk_pct: float) -> tuple[int, float, float]:
    risk_per_share = abs(entry - stop)
    risk_amount = capital * (risk_pct / 100.0)
    if risk_per_share <= 0 or entry <= 0:
        return 0, 0.0, risk_amount
    shares = int(risk_amount // risk_per_share)
    position_value = shares * entry
    if position_value > capital * 0.35:
        shares = int((capital * 0.35) // entry)
        position_value = shares * entry
    return max(shares, 0), position_value, risk_amount


def _rel_strength(asset: pd.DataFrame, bench: pd.DataFrame, lookback: int = 5) -> float:
    if asset is None or bench is None or len(asset) < lookback + 1 or len(bench) < lookback + 1:
        return 0.0
    a = float(asset["Close"].iloc[-1] / asset["Close"].iloc[-lookback] - 1)
    b = float(bench["Close"].iloc[-1] / bench["Close"].iloc[-lookback] - 1)
    return a - b


def analyze_symbol(
    symbol: str,
    snap: Snapshot,
    daily: pd.DataFrame,
    hourly: pd.DataFrame,
    intra: pd.DataFrame,
    spy_daily: pd.DataFrame,
    regime: Regime,
    news_score: float,
    headlines: list[str],
    cfg: dict,
) -> dict:
    warnings: list[str] = []
    reasons: list[str] = []
    if daily is None or len(daily) < 40:
        return _empty("Zu wenig Tagesdaten")

    price = snap.price or float(daily["Close"].iloc[-1])
    daily_atr = float(atr(daily).iloc[-1])
    atr_pct = daily_atr / price * 100 if price else 0
    daily_rsi = float(rsi(daily["Close"]).iloc[-1])
    daily_adx = float(adx(daily).iloc[-1]) if len(daily) >= 30 else 15.0
    ema9_d = float(ema(daily["Close"], 9).iloc[-1])
    ema21_d = float(ema(daily["Close"], 21).iloc[-1])
    ema50_d = float(ema(daily["Close"], 50).iloc[-1]) if len(daily) >= 50 else ema21_d
    hist_d = macd_hist(daily["Close"])
    macd_now = float(hist_d.iloc[-1])
    macd_prev = float(hist_d.iloc[-2])
    vol = daily["Volume"].fillna(0)
    vol_ratio = float(vol.iloc[-5:].mean() / max(float(vol.iloc[-20:].mean()), 1))
    upper, mid, lower = bollinger(daily["Close"])
    bb_pos = 0.5
    if float(upper.iloc[-1] - lower.iloc[-1]) != 0:
        bb_pos = float((price - lower.iloc[-1]) / (upper.iloc[-1] - lower.iloc[-1]))

    rel = _rel_strength(daily, spy_daily)
    swing_h, swing_l = swing_points(daily if hourly is None or hourly.empty else hourly)
    or_high, or_low, or_day = opening_range(intra) if intra is not None and not intra.empty else (None, None, None)
    last_vwap = None
    if intra is not None and not intra.empty:
        vw = session_vwap(intra)
        if not vw.empty:
            last_vwap = float(vw.dropna().iloc[-1])

    long_pts = 0.0
    short_pts = 0.0
    conf_long = 0
    conf_short = 0

    if ema9_d > ema21_d > ema50_d:
        long_pts += 18
        conf_long += 1
        reasons.append("Tagestrend aufwärts (EMA9>21>50)")
    elif ema9_d < ema21_d < ema50_d:
        short_pts += 18
        conf_short += 1
        reasons.append("Tagestrend abwärts (EMA9<21<50)")
    elif ema9_d > ema21_d:
        long_pts += 8
        reasons.append("Kurzfristiger Tagesbias long")
    else:
        short_pts += 8
        reasons.append("Kurzfristiger Tagesbias short")

    if 48 <= daily_rsi <= 68:
        long_pts += 12
        conf_long += 1
        reasons.append(f"RSI {daily_rsi:.0f} im Long-Arbeitsbereich")
    elif 32 <= daily_rsi <= 52:
        short_pts += 12
        conf_short += 1
        reasons.append(f"RSI {daily_rsi:.0f} im Short-Arbeitsbereich")
    elif daily_rsi > 78:
        short_pts += 6
        warnings.append("Tages-RSI überkauft – Long nur auf Rücksetzer")
    elif daily_rsi < 22:
        long_pts += 6
        warnings.append("Tages-RSI überverkauft – Short nur auf Gegenbounce")

    if macd_now > 0 and macd_now > macd_prev:
        long_pts += 10
        conf_long += 1
        reasons.append("MACD-Histogramm steigt")
    elif macd_now < 0 and macd_now < macd_prev:
        short_pts += 10
        conf_short += 1
        reasons.append("MACD-Histogramm fällt")

    if daily_adx >= 22:
        if ema9_d > ema21_d:
            long_pts += 8
            conf_long += 1
        else:
            short_pts += 8
            conf_short += 1
        reasons.append(f"ADX {daily_adx:.0f} – Trend hat Substanz")
    else:
        warnings.append(f"ADX {daily_adx:.0f} – eher Range, Fehlausbrüche möglich")

    if vol_ratio >= 1.25:
        long_pts += 6
        short_pts += 6
        reasons.append(f"Volumen {vol_ratio:.1f}× – Interesse da")

    if rel > 0.015:
        long_pts += 10
        conf_long += 1
        reasons.append(f"Stärker als SPY über 5 Tage ({rel*100:+.1f}%)")
    elif rel < -0.015:
        short_pts += 10
        conf_short += 1
        reasons.append(f"Schwächer als SPY über 5 Tage ({rel*100:+.1f}%)")

    if hourly is not None and len(hourly) >= 30:
        h_ema9 = float(ema(hourly["Close"], 9).iloc[-1])
        h_ema21 = float(ema(hourly["Close"], 21).iloc[-1])
        if h_ema9 > h_ema21:
            long_pts += 10
            conf_long += 1
            reasons.append("1h-Trend bestätigt Long")
        else:
            short_pts += 10
            conf_short += 1
            reasons.append("1h-Trend bestätigt Short")

    setup: Setup = "NONE"
    if last_vwap:
        if price >= last_vwap:
            long_pts += 8
            reasons.append(f"Kurs über Session-VWAP ({last_vwap:.2f})")
        else:
            short_pts += 8
            reasons.append(f"Kurs unter Session-VWAP ({last_vwap:.2f})")

    if or_high and or_low:
        if price > or_high:
            long_pts += 8
            conf_long += 1
            setup = "ORB"
            reasons.append(f"Über Opening-Range-High {or_high:.2f}")
        elif price < or_low:
            short_pts += 8
            conf_short += 1
            setup = "ORB"
            reasons.append(f"Unter Opening-Range-Low {or_low:.2f}")

    if news_score > 0.18:
        long_pts += 8
        reasons.append("Schlagzeilen eher positiv")
    elif news_score < -0.18:
        short_pts += 8
        reasons.append("Schlagzeilen eher negativ")

    if regime.bias == "BULL":
        long_pts += 8
        short_pts -= 10
    elif regime.bias == "BEAR":
        short_pts += 8
        long_pts -= 10
    if regime.vix >= 28:
        long_pts -= 6
        short_pts += 2
        warnings.append("Hoher VIX – Größe halbieren")

    if snap.earnings_soon:
        warnings.append("Zahlen innerhalb von 5 Tagen – Gap-Risiko, Daytrade nur mit hartem Stop")
        long_pts -= 8
        short_pts -= 8

    if snap.week52_high and price / snap.week52_high > 0.97:
        reasons.append("Nahe 52-Wochen-Hoch – Breakout oder Fakeout")
    if snap.short_ratio and snap.short_ratio >= 4:
        reasons.append(f"Short Ratio {snap.short_ratio:.1f} – Squeeze möglich, kein Muss")

    min_price = float(cfg.get("min_price", 8))
    max_atr_pct = float(cfg.get("max_atr_pct", 8))
    min_conf = int(cfg.get("min_confluence", 3))
    if snap.price < min_price:
        return _empty("Preis zu niedrig / unruhig")
    if atr_pct > max_atr_pct:
        warnings.append(f"ATR {atr_pct:.1f}% extrem – ungeeignet für enge Daytrade-Stops")
        long_pts -= 12
        short_pts -= 12

    if long_pts >= short_pts and long_pts >= 42 and conf_long >= min_conf and regime.long_ok:
        side: Side = "LONG"
        score = long_pts
        confluence = conf_long
    elif short_pts > long_pts and short_pts >= 42 and conf_short >= min_conf and regime.short_ok:
        side = "SHORT"
        score = short_pts
        confluence = conf_short
    else:
        side = "SKIP"
        score = max(long_pts, short_pts)
        confluence = max(conf_long, conf_short)
        reasons.append("Confluence zu dünn oder gegen das Marktumfeld")

    atr_mult = float(cfg.get("atr_stop_mult", 1.2))
    swing_buf = float(cfg.get("swing_buffer_atr", 0.15))
    rr1 = float(cfg.get("reward_risk_t1", 1.5))
    rr2 = float(cfg.get("reward_risk_t2", 2.5))
    atr_stop = atr_mult * daily_atr
    entry = price
    if side == "LONG":
        structural = (swing_l - swing_buf * daily_atr) if swing_l else None
        stop = entry - atr_stop
        if structural and structural < entry:
            if entry - structural >= 0.4 * daily_atr:
                stop = max(stop, structural) if (entry - structural) < atr_stop * 1.35 else structural
                stop = min(stop, entry - 0.4 * daily_atr)
        if last_vwap and price > last_vwap * 1.008 and setup != "ORB":
            setup = "WAIT"
            entry = last_vwap
            stop = min(stop, entry - 0.7 * daily_atr)
            reasons.append("Preis schon gestreckt – Plan: Rücksetzer an VWAP abwarten")
        elif last_vwap and abs(price - last_vwap) / price < 0.004:
            setup = "VWAP_RECLAIM"
        elif setup == "NONE":
            setup = "PULLBACK" if price < ema9_d * 1.01 else "BREAKOUT"
        risk = entry - stop
        t1 = entry + rr1 * risk
        t2 = entry + rr2 * risk
        if swing_h and swing_h > entry:
            t1 = min(t1, swing_h)
        invalidation = f"15m-Schluss unter {stop:.2f} oder zurück unter VWAP nach Break"
        playbook = (
            f"Long nur wenn die nächste 15m-Kerze über {entry:.2f} hält. "
            f"Stop {stop:.2f}. Erstes Ziel {t1:.2f}, Rest {t2:.2f} oder vor US-Schluss raus. "
            "Kein Nachkaufen unter dem Stop."
        )
    elif side == "SHORT":
        structural = (swing_h + swing_buf * daily_atr) if swing_h else None
        stop = entry + atr_stop
        if structural and structural > entry:
            if structural - entry >= 0.4 * daily_atr:
                stop = min(stop, structural) if (structural - entry) < atr_stop * 1.35 else structural
                stop = max(stop, entry + 0.4 * daily_atr)
        if last_vwap and price < last_vwap * 0.992 and setup != "ORB":
            setup = "WAIT"
            entry = last_vwap
            stop = max(stop, entry + 0.7 * daily_atr)
            reasons.append("Preis schon gestreckt nach unten – Plan: Rücksetzer an VWAP shorten")
        elif setup == "NONE":
            setup = "PULLBACK"
        risk = stop - entry
        t1 = entry - rr1 * risk
        t2 = entry - rr2 * risk
        if swing_l and swing_l < entry:
            t1 = max(t1, swing_l)
        invalidation = f"15m-Schluss über {stop:.2f} oder VWAP-Reclaim gegen die Position"
        playbook = (
            f"Short nur wenn 15m unter {entry:.2f} bleibt. "
            f"Stop {stop:.2f}. Ziel 1 {t1:.2f}, Ziel 2 {t2:.2f}. "
            "Shorts sind bei manchen Brokern teurer."
        )
    else:
        stop = price - atr_stop
        t1 = price + rr1 * atr_stop
        t2 = price + rr2 * atr_stop
        setup = "NONE"
        invalidation = "Kein Trade"
        playbook = "Heute stehen lassen. Kein Setup erzwingen."

    if confluence >= 5 and side != "SKIP" and not snap.earnings_soon and regime.vix < 26:
        grade: Grade = "A"
    elif confluence >= 4 and side != "SKIP":
        grade = "B"
    elif side != "SKIP":
        grade = "C"
    else:
        grade = "F"

    return {
        "side": side,
        "setup": setup,
        "grade": grade,
        "score": round(float(score), 1),
        "confluence": int(confluence),
        "entry": float(entry),
        "stop": float(stop),
        "target1": float(t1),
        "target2": float(t2),
        "invalidation": invalidation,
        "playbook": playbook,
        "atr": daily_atr,
        "atr_pct": atr_pct,
        "reasons": reasons[:8],
        "warnings": warnings,
        "rsi": daily_rsi,
        "adx": daily_adx,
        "volume_ratio": vol_ratio,
        "vwap": last_vwap,
        "or_high": or_high,
        "or_low": or_low,
        "swing_high": swing_h,
        "swing_low": swing_l,
        "rel_spy": rel,
        "bb_pos": bb_pos,
        "or_day": or_day,
    }


def _empty(msg: str) -> dict:
    return {
        "side": "SKIP",
        "setup": "NONE",
        "grade": "F",
        "score": 0.0,
        "confluence": 0,
        "entry": 0.0,
        "stop": 0.0,
        "target1": 0.0,
        "target2": 0.0,
        "invalidation": msg,
        "playbook": msg,
        "atr": 0.0,
        "atr_pct": 0.0,
        "reasons": [msg],
        "warnings": [],
        "rsi": 50.0,
        "adx": 0.0,
        "volume_ratio": 1.0,
        "vwap": None,
        "or_high": None,
        "or_low": None,
        "swing_high": None,
        "swing_low": None,
        "rel_spy": 0.0,
        "bb_pos": 0.5,
        "or_day": None,
    }

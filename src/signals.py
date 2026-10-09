from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from src.data import Snapshot
from src.indicators import (
    adx,
    atr,
    ema,
    intra_bias,
    intra_rvol,
    macd_hist,
    opening_range,
    overnight_gap,
    rsi,
    session_vwap,
    swing_points,
)
from src.market import Regime


@dataclass
class Idea:
    symbol: str
    name: str
    side: str
    setup: str
    grade: str
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
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    change_pct: float = 0.0
    rsi: float = 50.0
    adx: float = 15.0
    volume_ratio: float = 1.0
    news_score: float = 0.0
    headlines: list[str] = field(default_factory=list)
    vwap: Optional[float] = None
    or_high: Optional[float] = None
    or_low: Optional[float] = None
    swing_high: Optional[float] = None
    swing_low: Optional[float] = None
    rel_spy: float = 0.0
    earnings_soon: bool = False
    quality: float = 0.0
    gap_pct: float = 0.0
    rvol: float = 1.0
    affordability: str = ""
    extras: dict = field(default_factory=dict)


def size_position(
    capital: float,
    risk_pct: float,
    risk_per_share: float,
    entry: float,
    max_pos_pct: float = 0.35,
    risk_cfg: Optional[dict] = None,
) -> tuple[int, float, float]:
    risk_cfg = risk_cfg or {}
    if risk_per_share <= 0 or entry <= 0 or capital <= 0:
        return 0, 0.0, 0.0
    risk_budget = capital * (risk_pct / 100.0)
    shares_risk = int(risk_budget // risk_per_share)
    max_shares_cap = int((capital * max_pos_pct) // entry)
    shares = max(0, min(shares_risk, max_shares_cap))
    mode = str(risk_cfg.get("size_mode", "risk"))
    if mode == "deploy_cash":
        deploy = float(risk_cfg.get("portfolio_deploy_pct", 0.97))
        max_ideas = max(1, int(risk_cfg.get("max_ideas", 5)))
        per_idea = capital * deploy / max_ideas
        shares_deploy = int(per_idea // entry)
        shares = max(shares, shares_deploy)
        shares = min(shares, max_shares_cap) if max_shares_cap > 0 else shares
    pos_val = shares * entry
    risk_amt = shares * risk_per_share
    return shares, pos_val, risk_amt


def analyze_symbol(
    symbol: str,
    snap: Snapshot,
    daily: pd.DataFrame,
    hourly: Optional[pd.DataFrame],
    intra: Optional[pd.DataFrame],
    spy_daily: Optional[pd.DataFrame],
    regime: Regime,
    news_score: float,
    headlines: list[str],
    cfg: dict,
    iwm_daily: Optional[pd.DataFrame] = None,
) -> dict:
    reasons: list[str] = []
    warnings: list[str] = []
    confluence = 0
    score = 50.0

    zock = bool(cfg.get("_zock", False))
    min_price = float(cfg.get("min_price", 3.0))
    max_price = float(cfg.get("max_price", 500.0))
    max_atr_pct = float(cfg.get("max_atr_pct", 9.0))
    min_atr_pct = float(cfg.get("min_atr_pct", 0.0))
    atr_mult = float(cfg.get("atr_stop_mult", 1.25))
    rr1 = float(cfg.get("reward_risk_t1", 1.5))
    rr2 = float(cfg.get("reward_risk_t2", 2.5))
    min_conf = int(cfg.get("min_confluence", 3))
    gap_soft = float(cfg.get("max_gap_pct_soft", 3.0))
    gap_hard = float(cfg.get("max_gap_pct_hard", 6.0))
    min_rvol = float(cfg.get("min_rvol", 0.0))

    price = float(snap.price)
    if price < min_price or price > max_price:
        return _skip(symbol, snap, "Preisfilter", f"Preis {price:.2f} außerhalb {min_price}-{max_price}")

    if daily is None or len(daily) < 30:
        return _skip(symbol, snap, "Daten", "Zu wenig Tagesdaten")

    close = daily["Close"]
    atr_s = atr(daily)
    atr_v = float(atr_s.iloc[-1])
    atr_pct = atr_v / price * 100.0 if price else 0.0
    if zock:
        if atr_pct < min_atr_pct:
            return _skip(symbol, snap, "Zock", f"ATR {atr_pct:.1f}% zu niedrig für Zock-Modus (min {min_atr_pct})")
        if atr_pct > max_atr_pct:
            warnings.append(f"ATR {atr_pct:.1f}% extrem – Zock")
        score += min(25.0, atr_pct)
    elif atr_pct > max_atr_pct:
        warnings.append(f"ATR {atr_pct:.1f}% sehr hoch")
        score -= 8

    rsi_v = float(rsi(close).iloc[-1])
    adx_v = float(adx(daily).iloc[-1]) if len(daily) >= 30 else 15.0
    macd_v = float(macd_hist(close).iloc[-1])
    ema9 = float(ema(close, 9).iloc[-1])
    ema21 = float(ema(close, 21).iloc[-1])
    vol = daily["Volume"].fillna(0)
    vol_ratio = float(vol.iloc[-1] / vol.iloc[-20:].mean()) if len(vol) >= 20 and vol.iloc[-20:].mean() > 0 else 1.0

    gap = overnight_gap(daily, intra if intra is not None else pd.DataFrame())
    gap_pct = gap * 100.0
    if abs(gap_pct) >= gap_hard:
        return _skip(symbol, snap, "Gap", f"Gap {gap_pct:.1f}% zu groß")
    if abs(gap_pct) >= gap_soft:
        warnings.append(f"Gap {gap_pct:.1f}%")
        score -= 5

    or_h, or_l, or_day = opening_range(intra if intra is not None else pd.DataFrame())
    rvol = intra_rvol(intra if intra is not None else pd.DataFrame())
    if zock and rvol < min_rvol:
        return _skip(symbol, snap, "Zock", f"RVOL {rvol:.1f} < {min_rvol}")
    bias15 = intra_bias(intra if intra is not None else pd.DataFrame())
    vwap_s = session_vwap(intra) if intra is not None and not intra.empty else pd.Series(dtype=float)
    vwap_v = float(vwap_s.iloc[-1]) if len(vwap_s) else None
    sh, sl = swing_points(daily)

    rel_spy = 0.0
    if spy_daily is not None and len(daily) >= 5 and spy_daily is not None and len(spy_daily) >= 5:
        r_s = close.pct_change(5).iloc[-1]
        r_p = spy_daily["Close"].pct_change(5).iloc[-1]
        if pd.notna(r_s) and pd.notna(r_p):
            rel_spy = float(r_s - r_p) * 100.0

    rel_iwm = 0.0
    if iwm_daily is not None and len(iwm_daily) >= 5 and len(daily) >= 5:
        r_s = close.pct_change(5).iloc[-1]
        r_i = iwm_daily["Close"].pct_change(5).iloc[-1]
        if pd.notna(r_s) and pd.notna(r_i):
            rel_iwm = float(r_s - r_i) * 100.0

    long_ok = regime.long_ok
    side = "SKIP"
    setup = "kein Setup"

    bullish = 0
    if ema9 > ema21:
        bullish += 1
        reasons.append("EMA9 > EMA21")
        confluence += 1
    if macd_v > 0:
        bullish += 1
        reasons.append("MACD-Hist positiv")
        confluence += 1
    if 40 <= rsi_v <= 68:
        bullish += 1
        reasons.append(f"RSI {rsi_v:.0f} ok")
        confluence += 1
    if adx_v >= 18:
        bullish += 1
        reasons.append(f"ADX {adx_v:.0f}")
        confluence += 1
    if vol_ratio >= 1.2:
        bullish += 1
        reasons.append(f"Volumen x{vol_ratio:.1f}")
        confluence += 1
    if vwap_v and price >= vwap_v:
        bullish += 1
        reasons.append("über VWAP")
        confluence += 1
    if bias15 == "LONG":
        bullish += 1
        reasons.append("15m Bias long")
        confluence += 1
    if rvol >= 1.3:
        bullish += 1
        reasons.append(f"RVOL {rvol:.1f}")
        confluence += 1
    if rel_spy > 0.5:
        bullish += 1
        reasons.append(f"Rel vs SPY +{rel_spy:.1f}%")
        confluence += 1
    if news_score > 0.15:
        bullish += 1
        reasons.append("News eher positiv")
        confluence += 1

    if snap.earnings_soon:
        warnings.append("Earnings-Fenster")
        score -= 12
        confluence = max(0, confluence - 1)

    if not long_ok:
        warnings.append("Marktbias nicht long-freundlich")
        score -= 10

    if bullish >= min_conf and long_ok:
        side = "LONG"
        setup = "ZOCK Runner" if zock else "Momentum/ORB long"
        score = 50 + bullish * 5 + news_score * 10
        if zock:
            score += min(20.0, atr_pct * 0.5)
            reasons.append(f"Zock-Vol ATR {atr_pct:.1f}%")
        if or_h and price >= or_h * 0.998:
            setup = "ORB Break long" if not zock else "ZOCK ORB"
            reasons.append("nahe/über Opening Range High")
            confluence += 1
    else:
        return _skip(
            symbol, snap, setup, f"Confluence {confluence}/{min_conf} oder Bias",
            rsi_v=rsi_v, adx_v=adx_v, atr_v=atr_v, atr_pct=atr_pct, vol_ratio=vol_ratio,
            gap_pct=gap_pct, rvol=rvol, vwap_v=vwap_v, or_h=or_h, or_l=or_l, sh=sh, sl=sl,
            rel_spy=rel_spy, news_score=news_score, headlines=headlines, reasons=reasons, warnings=warnings,
        )

    entry = price
    stop = entry - atr_mult * atr_v
    if sl and sl < entry:
        stop = min(stop, sl - 0.05 * atr_v)
    risk = entry - stop
    if risk <= 0:
        return _skip(symbol, snap, "Stop", "Stop ungültig")
    t1 = entry + rr1 * risk
    t2 = entry + rr2 * risk
    if sh and sh > entry:
        t1 = min(t1, sh)

    if confluence >= 6:
        grade = "A"
    elif confluence >= 4:
        grade = "B"
    elif confluence >= min_conf:
        grade = "C"
    else:
        grade = "F"

    quality = min(100.0, max(0.0, score + confluence * 3))
    playbook = (
        f"Long bei {entry:.2f}, Stop {stop:.2f}, T1 {t1:.2f}, T2 {t2:.2f}. "
        f"Nur handeln wenn 15m Bias nicht SHORT und Volumen trägt."
    )
    invalidation = f"Schluss unter {stop:.2f} oder OR-Low" if or_l else f"Schluss unter {stop:.2f}"

    return {
        "side": side, "setup": setup, "grade": grade, "score": float(score),
        "confluence": int(confluence), "entry": float(entry), "stop": float(stop),
        "target1": float(t1), "target2": float(t2), "invalidation": invalidation,
        "playbook": playbook, "atr": float(atr_v), "atr_pct": float(atr_pct),
        "rsi": float(rsi_v), "adx": float(adx_v), "volume_ratio": float(vol_ratio),
        "reasons": reasons, "warnings": warnings, "vwap": vwap_v,
        "or_high": or_h, "or_low": or_l, "or_day": or_day,
        "swing_high": sh, "swing_low": sl, "rel_spy": float(rel_spy),
        "rel_iwm": float(rel_iwm), "quality": float(quality),
        "gap_pct": float(gap_pct), "rvol": float(rvol), "bias_15": bias15,
    }


def _skip(symbol: str, snap: Snapshot, setup: str, reason: str, **kw) -> dict:
    return {
        "side": "SKIP", "setup": setup, "grade": "F", "score": 0.0, "confluence": 0,
        "entry": float(snap.price), "stop": float(snap.price),
        "target1": float(snap.price), "target2": float(snap.price),
        "invalidation": reason, "playbook": reason,
        "atr": float(kw.get("atr_v") or 0), "atr_pct": float(kw.get("atr_pct") or 0),
        "rsi": float(kw.get("rsi_v") or 50), "adx": float(kw.get("adx_v") or 15),
        "volume_ratio": float(kw.get("vol_ratio") or 1),
        "reasons": list(kw.get("reasons") or [reason]),
        "warnings": list(kw.get("warnings") or []),
        "vwap": kw.get("vwap_v"), "or_high": kw.get("or_h"), "or_low": kw.get("or_l"),
        "or_day": None, "swing_high": kw.get("sh"), "swing_low": kw.get("sl"),
        "rel_spy": float(kw.get("rel_spy") or 0), "rel_iwm": 0.0, "quality": 0.0,
        "gap_pct": float(kw.get("gap_pct") or 0), "rvol": float(kw.get("rvol") or 1),
        "bias_15": "FLAT",
    }

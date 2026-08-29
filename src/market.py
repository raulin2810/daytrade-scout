from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.indicators import adx, ema, rsi


@dataclass
class Regime:
    spy_price: float
    spy_change: float
    qqq_change: float
    iwm_change: float
    vix: float
    spy_above_ema20: bool
    spy_rsi: float
    spy_adx: float
    bias: str
    label: str
    notes: list[str]

    @property
    def long_ok(self) -> bool:
        return self.bias in {"BULL", "NEUTRAL"}

    @property
    def short_ok(self) -> bool:
        return self.bias in {"BEAR", "NEUTRAL"}


def _last_change(df: pd.DataFrame) -> tuple[float, float]:
    if df is None or df.empty:
        return 0.0, 0.0
    price = float(df["Close"].iloc[-1])
    if len(df) < 2:
        return price, 0.0
    prev = float(df["Close"].iloc[-2])
    chg = (price - prev) / prev * 100.0 if prev else 0.0
    return price, chg


def detect_regime(spy: pd.DataFrame, qqq: pd.DataFrame, iwm: pd.DataFrame, vix: pd.DataFrame) -> Regime:
    spy_px, spy_chg = _last_change(spy)
    _, qqq_chg = _last_change(qqq)
    _, iwm_chg = _last_change(iwm)
    vix_px, _ = _last_change(vix)
    notes: list[str] = []

    ema20 = float(ema(spy["Close"], 20).iloc[-1]) if spy is not None and len(spy) >= 20 else spy_px
    above = spy_px >= ema20 if ema20 else True
    spy_rsi = float(rsi(spy["Close"]).iloc[-1]) if spy is not None and len(spy) >= 20 else 50.0
    spy_adx = float(adx(spy).iloc[-1]) if spy is not None and len(spy) >= 30 else 15.0

    if vix_px >= 28:
        notes.append(f"VIX {vix_px:.1f}: hohes Stress-Regime, Stops weiter, weniger Größe")
    elif vix_px <= 14:
        notes.append(f"VIX {vix_px:.1f}: ruhiges Regime, Breakouts können länger laufen")

    if above:
        notes.append("SPY über EMA20 – Marktbias eher long")
    else:
        notes.append("SPY unter EMA20 – Longs nur mit Extra-Confluence")

    if spy_adx >= 25:
        notes.append(f"SPY-ADX {spy_adx:.0f}: Trendmarkt")
    else:
        notes.append(f"SPY-ADX {spy_adx:.0f}: eher Range, Breakouts öfter Fehlausbrüche")

    if above and vix_px < 24 and spy_rsi < 75:
        bias = "BULL"
        label = "Risiko-an (bullisch)"
    elif (not above) and vix_px >= 20:
        bias = "BEAR"
        label = "Risiko-aus (bärisch)"
    else:
        bias = "NEUTRAL"
        label = "Gemischt / selektiv"

    return Regime(
        spy_price=spy_px,
        spy_change=spy_chg,
        qqq_change=qqq_chg,
        iwm_change=iwm_chg,
        vix=vix_px,
        spy_above_ema20=above,
        spy_rsi=spy_rsi,
        spy_adx=spy_adx,
        bias=bias,
        label=label,
        notes=notes,
    )

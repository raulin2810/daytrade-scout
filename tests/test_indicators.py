from __future__ import annotations

import pandas as pd

from src.indicators import atr, ema, rsi
from src.signals import size_position


def test_ema_constant():
    s = pd.Series([10.0] * 20)
    assert abs(float(ema(s, 9).iloc[-1]) - 10.0) < 1e-9


def test_rsi_bounds():
    up = pd.Series([float(i) for i in range(1, 40)])
    down = pd.Series([float(i) for i in range(40, 1, -1)])
    assert float(rsi(up).iloc[-1]) > 70
    assert float(rsi(down).iloc[-1]) < 30


def test_atr_positive():
    df = pd.DataFrame(
        {
            "High": [11, 12, 13, 14, 15, 16, 17, 18],
            "Low": [9, 10, 11, 12, 13, 14, 15, 16],
            "Close": [10, 11, 12, 13, 14, 15, 16, 17],
        }
    )
    assert float(atr(df).iloc[-1]) > 0


def test_size_caps_heat():
    shares, notional, risk = size_position(100, 98, 10_000, 0.5)
    assert risk == 50
    assert shares == 25
    assert notional == 2500

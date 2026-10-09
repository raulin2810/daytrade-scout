"""Minimal Scalable CLI helper."""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any


@dataclass
class ScalableResult:
    ok: bool
    data: Any
    raw: str
    error: str = ""


def sc_available() -> bool:
    return shutil.which("sc") is not None


def _run(args: list[str], timeout: int = 45) -> ScalableResult:
    if not sc_available():
        return ScalableResult(False, None, "", "sc not found")
    try:
        p = subprocess.run(["sc", *args], capture_output=True, text=True, timeout=timeout)
        raw = (p.stdout or "") + (p.stderr or "")
        data = None
        try:
            data = json.loads(p.stdout) if p.stdout.strip().startswith("{") else p.stdout
        except Exception:
            data = p.stdout
        return ScalableResult(p.returncode == 0, data, raw, "" if p.returncode == 0 else raw)
    except Exception as e:
        return ScalableResult(False, None, "", str(e))


def broker_overview() -> Any:
    r = _run(["broker", "overview", "--json"])
    return r.data if r.ok else {"error": r.error}


def broker_watchlist() -> Any:
    r = _run(["broker", "watchlist", "--json"])
    return r.data if r.ok else {"error": r.error}


def trade_buy_preview(isin: str, amount: float) -> Any:
    r = _run(["broker", "trade", "buy", "--isin", isin, "--amount", str(amount), "--order-type", "market", "--json"])
    return r.data if r.ok else {"error": r.error or r.raw}

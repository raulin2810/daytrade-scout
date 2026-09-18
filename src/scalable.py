"""Wrapper um die offizielle Scalable CLI (`sc`).

Phase 1 = Preview (automatisch aus Idee möglich).
Phase 2 = Confirm nur nach explizitem User-Klick (oder Terminal).
"""
from __future__ import annotations

import json
import re
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
        return ScalableResult(
            ok=False,
            data=None,
            raw="",
            error=(
                "`sc` nicht gefunden. Installiere mit:\n"
                "brew tap ScalableCapital/tap && brew install scalable-cli\n"
                "Dann: sc login"
            ),
        )
    try:
        proc = subprocess.run(
            ["sc", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ScalableResult(ok=False, data=None, raw="", error="Timeout bei sc-Aufruf")
    except FileNotFoundError:
        return ScalableResult(ok=False, data=None, raw="", error="`sc` nicht im PATH")

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if proc.returncode != 0:
        msg = stderr or stdout or f"Exit-Code {proc.returncode}"
        return ScalableResult(ok=False, data=None, raw=stdout or stderr, error=msg)

    if "--json" in args and stdout:
        try:
            return ScalableResult(ok=True, data=json.loads(stdout), raw=stdout)
        except json.JSONDecodeError:
            return ScalableResult(
                ok=False, data=None, raw=stdout, error="JSON-Parse-Fehler von sc"
            )
    return ScalableResult(ok=True, data=stdout, raw=stdout)


def whoami() -> ScalableResult:
    return _run(["whoami", "--json"])


def overview() -> ScalableResult:
    return _run(["broker", "overview", "--json"])


def holdings() -> ScalableResult:
    return _run(["broker", "holdings", "--json"])


def quote(isin: str) -> ScalableResult:
    isin = isin.strip().upper()
    if not isin:
        return ScalableResult(ok=False, data=None, raw="", error="ISIN fehlt")
    return _run(["broker", "quote", "--isin", isin, "--json"])


def search(query: str) -> ScalableResult:
    q = query.strip()
    if not q:
        return ScalableResult(ok=False, data=None, raw="", error="Suchbegriff fehlt")
    return _run(["broker", "search", q, "--json"])


def transactions(page_size: int = 30) -> ScalableResult:
    return _run(["broker", "transactions", "--page-size", str(page_size), "--json"])


def overnight() -> ScalableResult:
    return _run(["overnight", "--json"])


def extract_cash(data: Any) -> float | None:
    """Versucht verfügbares Cash / Buying Power aus Overview-JSON zu lesen."""
    if data is None:
        return None
    keys = (
        "buyingPower",
        "buying_power",
        "availableCash",
        "available_cash",
        "cash",
        "cashBalance",
        "cash_balance",
        "withdrawableCash",
        "freeCash",
        "liquidity",
        "availableForTrading",
    )

    def walk(obj: Any) -> float | None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                kl = str(k).lower().replace("-", "_")
                for want in keys:
                    if kl == want.lower() or want.lower() in kl:
                        try:
                            if isinstance(v, dict) and "amount" in v:
                                return float(v["amount"])
                            if isinstance(v, dict) and "value" in v:
                                return float(v["value"])
                            return float(v)
                        except (TypeError, ValueError):
                            pass
                found = walk(v)
                if found is not None:
                    return found
        if isinstance(obj, list):
            for item in obj:
                found = walk(item)
                if found is not None:
                    return found
        return None

    return walk(data)


def get_available_cash() -> tuple[float | None, ScalableResult]:
    r = overview()
    if not r.ok:
        return None, r
    cash = extract_cash(r.data)
    return cash, r


def resolve_isin(symbol: str, isin_map: dict[str, str] | None = None) -> str | None:
    sym = symbol.strip().upper()
    if not sym:
        return None
    if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", sym):
        return sym
    mapping = {k.upper(): v.upper() for k, v in (isin_map or {}).items()}
    if sym in mapping:
        return mapping[sym]
    base = sym.split(".")[0]
    if base in mapping:
        return mapping[base]

    r = search(base if "." in sym else sym)
    if not r.ok or r.data is None:
        return None
    items: list[dict] = []
    if isinstance(r.data, list):
        items = [x for x in r.data if isinstance(x, dict)]
    elif isinstance(r.data, dict):
        for key in ("results", "items", "securities", "data"):
            if isinstance(r.data.get(key), list):
                items = [x for x in r.data[key] if isinstance(x, dict)]
                break
    for it in items:
        isin = it.get("isin") or it.get("ISIN") or it.get("instrumentIsin") or ""
        ticker = str(it.get("ticker") or it.get("symbol") or it.get("name") or "").upper()
        if isin and (base in ticker or sym in ticker or ticker in (base, sym)):
            return str(isin).upper()
    if items:
        isin = items[0].get("isin") or items[0].get("ISIN")
        if isin:
            return str(isin).upper()
    return None


def extract_confirmation_id(data: Any) -> str | None:
    if data is None:
        return None
    if isinstance(data, dict):
        for key in ("confirmation_id", "confirmationId", "confirm_id", "confirmId", "id"):
            val = data.get(key)
            if val and isinstance(val, (str, int)):
                s = str(val)
                if len(s) >= 6:
                    return s
        for v in data.values():
            found = extract_confirmation_id(v)
            if found:
                return found
    if isinstance(data, list):
        for item in data:
            found = extract_confirmation_id(item)
            if found:
                return found
    if isinstance(data, str):
        m = re.search(
            r"(?:confirmation[_-]?id|confirm)[\"'\s:=]+([A-Za-z0-9_-]{6,})",
            data,
            re.I,
        )
        if m:
            return m.group(1)
    return None


def build_confirm_command(
    side: str,
    isin: str,
    confirmation_id: str,
    *,
    amount: float | None = None,
    shares: float | None = None,
    order_type: str = "market",
) -> str:
    parts = [
        "sc",
        "broker",
        "trade",
        side.lower().strip(),
        "--isin",
        isin.upper(),
        "--order-type",
        order_type,
    ]
    if amount is not None:
        parts.extend(["--amount", str(amount)])
    elif shares is not None:
        shares_int = int(shares) if float(shares).is_integer() else shares
        parts.extend(["--shares", str(shares_int)])
    parts.extend(["--confirm", str(confirmation_id)])
    return " ".join(parts)


def trade_preview(
    side: str,
    isin: str,
    *,
    amount: float | None = None,
    shares: float | None = None,
    order_type: str = "market",
) -> ScalableResult:
    side = side.lower().strip()
    if side not in {"buy", "sell"}:
        return ScalableResult(ok=False, data=None, raw="", error="side muss buy oder sell sein")
    isin = isin.strip().upper()
    if not isin:
        return ScalableResult(ok=False, data=None, raw="", error="ISIN fehlt")

    args = ["broker", "trade", side, "--isin", isin, "--order-type", order_type, "--json"]
    if amount is not None and shares is not None:
        return ScalableResult(ok=False, data=None, raw="", error="Nur amount ODER shares")
    if amount is not None:
        args.extend(["--amount", str(amount)])
    elif shares is not None:
        sh = int(shares) if float(shares).is_integer() else shares
        args.extend(["--shares", str(sh)])
    else:
        return ScalableResult(ok=False, data=None, raw="", error="amount oder shares erforderlich")
    return _run(args, timeout=60)


def cash_aware_size(
    *,
    price: float,
    desired_shares: int,
    desired_amount: float | None,
    cash: float | None,
    buffer_pct: float = 0.90,
) -> tuple[int | None, float | None, str]:
    """Begrenzt Stück/Betrag auf verfügbares Cash."""
    if cash is None or cash <= 0:
        return desired_shares, desired_amount, "kein Cash-Abruf – Idee-Größe unverändert"
    usable = cash * buffer_pct
    if desired_amount is not None and desired_amount > 0:
        amt = min(desired_amount, usable)
        if amt < 1:
            return None, None, f"Cash zu niedrig ({cash:.0f})"
        return None, round(amt, 2), f"Cash {cash:.0f} → Betrag {amt:.0f} (Puffer {buffer_pct:.0%})"
    if price <= 0:
        return desired_shares, None, ""
    max_sh = int(usable // price)
    sh = min(max(1, desired_shares), max_sh) if max_sh >= 1 else 0
    if sh < 1:
        return 0, None, f"Cash {cash:.0f} reicht nicht für 1 Share à {price:.2f}"
    return sh, None, f"Cash {cash:.0f} → max {max_sh} Shares, gewählt {sh}"


def prepare_order_from_idea(
    *,
    symbol: str,
    side: str,
    shares: float,
    isin_map: dict[str, str] | None = None,
    order_type: str = "market",
    amount: float | None = None,
    price: float | None = None,
    use_cash_limit: bool = True,
    cash_buffer_pct: float = 0.90,
) -> tuple[ScalableResult, str | None, str | None, dict]:
    """Idee → ISIN → optional Cash-Limit → Phase-1 → Confirm-Meta."""
    meta: dict[str, Any] = {}
    isin = resolve_isin(symbol, isin_map)
    if not isin:
        return (
            ScalableResult(
                ok=False,
                data=None,
                raw="",
                error=f"Keine ISIN für {symbol}. In config.yaml isin_map ergänzen.",
            ),
            None,
            None,
            meta,
        )

    trade_side = "buy"
    if side.upper() in {"SHORT", "SELL", "VERKAUF"}:
        trade_side = "sell"
    elif side.upper() in {"LONG", "BUY", "KAUF"}:
        trade_side = "buy"

    cash = None
    if use_cash_limit and trade_side == "buy":
        cash, _ = get_available_cash()
        meta["cash"] = cash
        sh, amt, note = cash_aware_size(
            price=price or 0,
            desired_shares=int(round(shares)),
            desired_amount=amount,
            cash=cash,
            buffer_pct=cash_buffer_pct,
        )
        meta["cash_note"] = note
        if amount is not None:
            amount = amt
            shares = 0
        else:
            if sh is None or sh < 1:
                return (
                    ScalableResult(ok=False, data=None, raw="", error=note),
                    isin,
                    None,
                    meta,
                )
            shares = sh

    kwargs: dict[str, Any] = {"order_type": order_type}
    if amount is not None and amount > 0:
        kwargs["amount"] = amount
        meta["size_mode"] = "amount"
        meta["size_value"] = amount
    else:
        sh = max(1, int(round(shares)))
        kwargs["shares"] = sh
        meta["size_mode"] = "shares"
        meta["size_value"] = sh

    meta["side"] = trade_side
    meta["order_type"] = order_type

    result = trade_preview(trade_side, isin, **kwargs)
    if not result.ok:
        return result, isin, None, meta

    cid = extract_confirmation_id(result.data) or extract_confirmation_id(result.raw)
    meta["confirmation_id"] = cid
    cmd = None
    if cid:
        cmd = build_confirm_command(
            trade_side,
            isin,
            cid,
            amount=kwargs.get("amount"),
            shares=kwargs.get("shares"),
            order_type=order_type,
        )
    return result, isin, cmd, meta


def trade_confirm(
    side: str,
    isin: str,
    confirmation_id: str,
    *,
    amount: float | None = None,
    shares: float | None = None,
    order_type: str = "market",
    enabled: bool = False,
) -> ScalableResult:
    if not enabled:
        return ScalableResult(
            ok=False,
            data=None,
            raw="",
            error="Phase 2 nur nach explizitem Bestätigen in der App.",
        )
    side = side.lower().strip()
    isin = isin.strip().upper()
    cid = confirmation_id.strip()
    if not cid:
        return ScalableResult(ok=False, data=None, raw="", error="confirmation_id fehlt")

    args = [
        "broker",
        "trade",
        side,
        "--isin",
        isin,
        "--order-type",
        order_type,
        "--confirm",
        cid,
        "--json",
    ]
    if amount is not None:
        args.extend(["--amount", str(amount)])
    elif shares is not None:
        args.extend(["--shares", str(shares)])
    else:
        return ScalableResult(ok=False, data=None, raw="", error="amount oder shares erforderlich")
    return _run(args, timeout=60)

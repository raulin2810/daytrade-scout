"""Wrapper um die offizielle Scalable CLI (`sc`).

Voraussetzungen auf dem Mac:
  brew tap ScalableCapital/tap
  brew trust --formula ScalableCapital/tap/scalable-cli
  brew install scalable-cli
  # Im Browser: Profil → Security → Agentic Investing aktivieren
  sc login

Alle Schreibaktionen (Trade Phase-2) sind standardmäßig deaktiviert.
Die App bereitet nur Phase-1-Previews vor und zeigt den Confirm-Befehl.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any


class ScalableError(Exception):
    """Fehler bei Aufruf oder Parsing der Scalable CLI."""


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
    cmd = ["sc", *args]
    try:
        proc = subprocess.run(
            cmd,
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


def capabilities() -> ScalableResult:
    return _run(["capabilities", "--json"])


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


def resolve_isin(symbol: str, isin_map: dict[str, str] | None = None) -> str | None:
    """Ticker → ISIN. Zuerst config-Map, sonst sc search."""
    sym = symbol.strip().upper()
    if not sym:
        return None
    # Schon eine ISIN?
    if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", sym):
        return sym
    mapping = {k.upper(): v.upper() for k, v in (isin_map or {}).items()}
    if sym in mapping:
        return mapping[sym]
    # Yahoo-DE-Ticker: SAP.DE → SAP
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
        isin = (
            it.get("isin")
            or it.get("ISIN")
            or it.get("instrumentIsin")
            or ""
        )
        ticker = str(
            it.get("ticker") or it.get("symbol") or it.get("name") or ""
        ).upper()
        if isin and (base in ticker or sym in ticker or ticker in (base, sym)):
            return str(isin).upper()
    if items:
        isin = items[0].get("isin") or items[0].get("ISIN")
        if isin:
            return str(isin).upper()
    return None


def extract_confirmation_id(data: Any) -> str | None:
    """confirmation_id aus Preview-JSON ziehen."""
    if data is None:
        return None
    if isinstance(data, dict):
        for key in (
            "confirmation_id",
            "confirmationId",
            "confirm_id",
            "confirmId",
            "id",
        ):
            val = data.get(key)
            if val and isinstance(val, (str, int)):
                return str(val)
        # verschachtelt
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
            r"(?:confirmation[_-]?id|confirm)[\"'\s:=]+([A-Za-z0-9_-]+)",
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
    """Exakter Terminal-Befehl für Phase 2 (nur zum Kopieren)."""
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
        # Buy-side: ganze Shares
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
    """Phase 1: Order-Preview (keine Ausführung).

    Gibt confirmation_id zurück. Phase 2 nur manuell mit --confirm.
    """
    side = side.lower().strip()
    if side not in {"buy", "sell"}:
        return ScalableResult(ok=False, data=None, raw="", error="side muss buy oder sell sein")
    isin = isin.strip().upper()
    if not isin:
        return ScalableResult(ok=False, data=None, raw="", error="ISIN fehlt")

    args = ["broker", "trade", side, "--isin", isin, "--order-type", order_type, "--json"]
    if amount is not None and shares is not None:
        return ScalableResult(
            ok=False, data=None, raw="", error="Nur amount ODER shares angeben"
        )
    if amount is not None:
        args.extend(["--amount", str(amount)])
    elif shares is not None:
        # CLI akzeptiert buy-side ganze Shares
        sh = int(shares) if float(shares).is_integer() else shares
        args.extend(["--shares", str(sh)])
    else:
        return ScalableResult(
            ok=False, data=None, raw="", error="amount oder shares erforderlich"
        )

    return _run(args, timeout=60)


def prepare_order_from_idea(
    *,
    symbol: str,
    side: str,
    shares: float,
    isin_map: dict[str, str] | None = None,
    order_type: str = "market",
    amount: float | None = None,
) -> tuple[ScalableResult, str | None, str | None]:
    """Idee → ISIN auflösen → Phase-1-Preview → Confirm-Befehl.

    Returns: (result, isin, confirm_command)
    """
    isin = resolve_isin(symbol, isin_map)
    if not isin:
        return (
            ScalableResult(
                ok=False,
                data=None,
                raw="",
                error=f"Keine ISIN für {symbol}. In config.yaml unter isin_map ergänzen oder manuell suchen.",
            ),
            None,
            None,
        )

    trade_side = "buy" if side.upper() in {"LONG", "BUY", "KAUF"} else "sell"
    if side.upper() in {"SHORT", "SELL", "VERKAUF"}:
        trade_side = "sell"

    kwargs: dict[str, Any] = {"order_type": order_type}
    if amount is not None and amount > 0:
        kwargs["amount"] = amount
    else:
        # ganze Stück für buy
        sh = max(1, int(round(shares)))
        kwargs["shares"] = sh

    result = trade_preview(trade_side, isin, **kwargs)
    if not result.ok:
        return result, isin, None

    cid = extract_confirmation_id(result.data) or extract_confirmation_id(result.raw)
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
    return result, isin, cmd


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
    """Phase 2: Order absenden – nur wenn enabled=True (explizit).

    Standardmäßig blockiert, damit die App keine ungewollten Trades auslöst.
    """
    if not enabled:
        return ScalableResult(
            ok=False,
            data=None,
            raw="",
            error=(
                "Trade-Ausführung ist in der App standardmäßig deaktiviert. "
                "Nur Preview (Phase 1) erlaubt. Bestätigung manuell im Terminal: "
                "sc broker trade ... --confirm <ID>"
            ),
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
        return ScalableResult(
            ok=False, data=None, raw="", error="amount oder shares erforderlich"
        )

    return _run(args, timeout=60)

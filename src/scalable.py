"""Wrapper um die offizielle Scalable CLI (`sc`).

Voraussetzungen auf dem Mac:
  brew tap ScalableCapital/tap
  brew trust --formula ScalableCapital/tap/scalable-cli
  brew install scalable-cli
  # Im Browser: Profil → Security → Agentic Investing aktivieren
  sc login

Alle Schreibaktionen (Trade Phase-2) sind standardmäßig deaktiviert.
"""
from __future__ import annotations

import json
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
        args.extend(["--shares", str(shares)])
    else:
        return ScalableResult(
            ok=False, data=None, raw="", error="amount oder shares erforderlich"
        )

    return _run(args, timeout=60)


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

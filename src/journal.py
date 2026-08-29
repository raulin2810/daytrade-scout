from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


JOURNAL = Path(__file__).resolve().parents[1] / "data" / "journal.csv"
COLUMNS = [
    "zeit",
    "ticker",
    "seite",
    "setup",
    "grade",
    "einstieg",
    "stop",
    "ziel1",
    "stueck",
    "status",
    "exit",
    "pnl",
    "notiz",
]


def _ensure() -> None:
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    if not JOURNAL.exists():
        pd.DataFrame(columns=COLUMNS).to_csv(JOURNAL, index=False)


def load() -> pd.DataFrame:
    _ensure()
    df = pd.read_csv(JOURNAL)
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[COLUMNS]


def add_row(row: dict) -> pd.DataFrame:
    df = load()
    row = {
        "zeit": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "ticker": row.get("ticker", ""),
        "seite": row.get("seite", ""),
        "setup": row.get("setup", ""),
        "grade": row.get("grade", ""),
        "einstieg": row.get("einstieg", ""),
        "stop": row.get("stop", ""),
        "ziel1": row.get("ziel1", ""),
        "stueck": row.get("stueck", ""),
        "status": row.get("status", "offen"),
        "exit": row.get("exit", ""),
        "pnl": row.get("pnl", ""),
        "notiz": row.get("notiz", ""),
    }
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(JOURNAL, index=False)
    return df

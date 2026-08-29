from __future__ import annotations

from html import unescape
from typing import Iterable
import re

import feedparser
import yfinance as yf


POS = {
    "beat", "beats", "surge", "surges", "rally", "rallies", "record", "upgrade",
    "upgraded", "growth", "profit", "profits", "strong", "bullish", "soar",
    "soars", "outperform", "buyback", "raises", "raised", "optimistic",
    "breakout", "contract", "award", "approval", "approved", "partnership",
    "gewinn", "steigt", "steigen", "rekord", "stark", "positiv", "kaufen",
    "auftrag",
}
NEG = {
    "miss", "misses", "fall", "falls", "drop", "drops", "downgrade",
    "downgraded", "lawsuit", "probe", "weak", "bearish", "cut", "cuts",
    "warning", "layoff", "layoffs", "fraud", "recall", "ban", "crash",
    "sinks", "plunge", "plunges", "investigation", "delay", "delayed",
    "verlust", "fällt", "fallen", "schwach", "klage", "warnung", "negativ",
    "verkauf", "skandal", "rückruf",
}


def _clean(text: str) -> str:
    text = unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def yahoo_headlines(symbol: str, limit: int = 7) -> list[str]:
    headlines: list[str] = []
    try:
        news = yf.Ticker(symbol).news or []
        for item in news:
            content = item.get("content") if isinstance(item, dict) else None
            title = None
            if isinstance(item, dict):
                title = item.get("title")
            if not title and isinstance(content, dict):
                title = content.get("title")
            if title:
                headlines.append(_clean(str(title)))
            if len(headlines) >= limit:
                break
    except Exception:
        pass
    return headlines


def rss_headlines(query: str, limit: int = 6) -> list[str]:
    url = (
        "https://news.google.com/rss/search?"
        f"q={query.replace(' ', '+')}&hl=en-US&gl=US&ceid=US:en"
    )
    headlines: list[str] = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:limit]:
            title = _clean(getattr(entry, "title", ""))
            if title:
                headlines.append(title)
    except Exception:
        pass
    return headlines


def collect_headlines(symbol: str, name: str = "", limit: int = 7) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    queries = [f"{symbol} stock", f"{symbol} aktie"]
    if name and name.upper() != symbol.upper():
        queries.append(f"{name} stock OR aktie")
    bag = yahoo_headlines(symbol, limit)
    for q in queries:
        bag.extend(rss_headlines(q, limit))
    for title in bag:
        key = title.lower()
        if key in seen or len(title) < 12:
            continue
        seen.add(key)
        out.append(title)
        if len(out) >= limit:
            break
    return out


def sentiment_score(headlines: Iterable[str]) -> float:
    texts = [h.lower() for h in headlines if h]
    if not texts:
        return 0.0
    score = 0.0
    for text in texts:
        tokens = set(re.findall(r"[a-zäöüß]+", text))
        score += len(tokens & POS)
        score -= len(tokens & NEG)
        if "downgrade" in text or "profit warning" in text:
            score -= 2
        if "upgrade" in text or "beats" in text:
            score += 1.5
    return max(-1.0, min(1.0, score / max(len(texts) * 2.0, 1.0)))

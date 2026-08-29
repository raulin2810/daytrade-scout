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
    "gewinn", "steigt", "steigen", "rekord", "stark", "positiv", "kaufen",
}
NEG = {
    "miss", "misses", "fall", "falls", "drop", "drops", "downgrade",
    "downgraded", "lawsuit", "probe", "weak", "bearish", "cut", "cuts",
    "warning", "layoff", "layoffs", "fraud", "recall", "ban", "crash",
    "sinks", "plunge", "plunges", "verlust", "fällt", "fallen", "schwach",
    "klage", "warnung", "negativ", "verkauf",
}


def _clean(text: str) -> str:
    text = unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def yahoo_headlines(symbol: str, limit: int = 6) -> list[str]:
    headlines: list[str] = []
    try:
        news = yf.Ticker(symbol).news or []
        for item in news:
            title = item.get("title") or item.get("content", {}).get("title")
            if title:
                headlines.append(_clean(str(title)))
            if len(headlines) >= limit:
                break
    except Exception:
        pass
    return headlines


def google_news_headlines(symbol: str, limit: int = 6) -> list[str]:
    query = f"{symbol} stock OR aktie"
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


def collect_headlines(symbol: str, limit: int = 6) -> list[str]:
    seen = set()
    out: list[str] = []
    for title in yahoo_headlines(symbol, limit) + google_news_headlines(symbol, limit):
        key = title.lower()
        if key in seen:
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
    # Normierung grob auf [-1, 1]
    return max(-1.0, min(1.0, score / max(len(texts) * 2.0, 1.0)))

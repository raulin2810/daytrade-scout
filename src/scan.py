from __future__ import annotations

from src.data import Snapshot, download_batch, snapshots
from src.market import Regime, detect_regime
from src.news import collect_headlines, sentiment_score
from src.signals import Idea, analyze_symbol, size_position


def run_scan(
    symbols: list[str],
    capital: float,
    risk_pct: float,
    cfg: dict,
    include_news: bool = True,
) -> tuple[Regime, list[Idea]]:
    risk_cfg = dict(cfg.get("risk", {}) or {})
    zock_mode = bool(cfg.get("_zock_mode", False))
    if zock_mode:
        z = dict(cfg.get("zock", {}) or {})
        risk_cfg["_zock"] = True
        for k in ("min_price", "max_price", "min_avg_volume", "min_atr_pct", "max_atr_pct",
                  "min_confluence", "min_rvol", "max_gap_pct_hard", "atr_stop_mult",
                  "reward_risk_t1", "reward_risk_t2"):
            if k in z:
                risk_cfg[k] = z[k]
        risk_cfg["min_avg_volume"] = float(z.get("min_avg_volume", 150000))
        risk_cfg["min_avg_volume_mid"] = float(z.get("min_avg_volume", 150000))
    benches = cfg.get("benchmarks", {})
    spy_t = benches.get("spy", "SPY")
    qqq_t = benches.get("qqq", "QQQ")
    iwm_t = benches.get("iwm", "IWM")
    vix_t = benches.get("vix", "^VIX")

    uniq = list(dict.fromkeys(symbols + [spy_t, qqq_t, iwm_t]))
    daily_map = download_batch(uniq, period="8mo", interval="1d")
    hourly_map = download_batch(uniq, period="30d", interval="60m")
    intra_map = download_batch(uniq, period="7d", interval="15m")
    vix_map = download_batch([vix_t], period="8mo", interval="1d")

    regime = detect_regime(
        daily_map.get(spy_t),
        daily_map.get(qqq_t),
        daily_map.get(iwm_t),
        vix_map.get(vix_t),
    )

    snaps = snapshots(symbols)
    min_vol = float(risk_cfg.get("min_avg_volume", 800_000))
    min_vol_mid = float(risk_cfg.get("min_avg_volume_mid", 500_000))
    max_pos_pct = float(risk_cfg.get("max_position_pct", 0.25))
    prefer_under = float(risk_cfg.get("prefer_mid_cap_under", 80))

    prelim: list[tuple[str, Snapshot, dict]] = []
    for symbol in symbols:
        snap = snaps.get(symbol)
        daily = daily_map.get(symbol)
        if snap is None or daily is None or daily.empty:
            continue
        vol_floor = min_vol_mid if (snap.price and snap.price < prefer_under) else min_vol
        if symbol.endswith(".DE"):
            vol_floor = min(vol_floor, 200_000)
        if snap.avg_volume and snap.avg_volume < vol_floor:
            continue
        raw = analyze_symbol(
            symbol,
            snap,
            daily,
            hourly_map.get(symbol),
            intra_map.get(symbol),
            daily_map.get(spy_t),
            regime,
            news_score=0.0,
            headlines=[],
            cfg=risk_cfg,
            iwm_daily=daily_map.get(iwm_t),
        )
        prelim.append((symbol, snap, raw))

    prelim.sort(key=lambda x: (x[2].get("quality", 0), x[2]["score"]), reverse=True)
    news_limit = 10
    news_cache: dict[str, tuple[float, list[str]]] = {}
    if include_news:
        for symbol, snap, _ in prelim[:news_limit]:
            heads = collect_headlines(symbol, snap.name, limit=int(cfg.get("news", {}).get("max_headlines_per_symbol", 7)))
            news_cache[symbol] = (sentiment_score(heads), heads)

    ideas: list[Idea] = []
    for symbol, snap, raw in prelim:
        nscore, heads = news_cache.get(symbol, (0.0, []))
        if include_news and symbol in news_cache:
            raw = analyze_symbol(
                symbol,
                snap,
                daily_map.get(symbol),
                hourly_map.get(symbol),
                intra_map.get(symbol),
                daily_map.get(spy_t),
                regime,
                news_score=nscore,
                headlines=heads,
                cfg=risk_cfg,
                iwm_daily=daily_map.get(iwm_t),
            )
        if raw["side"] == "SKIP":
            ideas.append(
                Idea(
                    symbol=symbol,
                    name=snap.name,
                    side="SKIP",
                    setup=raw["setup"],
                    grade=raw["grade"],
                    score=raw["score"],
                    confluence=raw["confluence"],
                    price=snap.price,
                    currency=snap.currency,
                    entry=raw["entry"],
                    stop=raw["stop"],
                    target1=raw["target1"],
                    target2=raw["target2"],
                    invalidation=raw["invalidation"],
                    playbook=raw["playbook"],
                    atr=raw["atr"],
                    atr_pct=raw["atr_pct"],
                    risk_per_share=abs(raw["entry"] - raw["stop"]),
                    shares=0,
                    position_value=0.0,
                    risk_amount=0.0,
                    reward_risk=float(risk_cfg.get("reward_risk_t1", 1.5)),
                    reasons=raw["reasons"],
                    warnings=raw["warnings"],
                    change_pct=snap.change_pct,
                    rsi=raw["rsi"],
                    adx=raw["adx"],
                    volume_ratio=raw["volume_ratio"],
                    news_score=nscore,
                    headlines=heads,
                    vwap=raw["vwap"],
                    or_high=raw["or_high"],
                    or_low=raw["or_low"],
                    swing_high=raw["swing_high"],
                    swing_low=raw["swing_low"],
                    rel_spy=raw["rel_spy"],
                    earnings_soon=snap.earnings_soon,
                    quality=float(raw.get("quality", 0)),
                    gap_pct=float(raw.get("gap_pct", 0)),
                    rvol=float(raw.get("rvol", 1)),
                    affordability="n/a",
                    extras={"sector": snap.sector},
                )
            )
            continue

        shares, pos_val, risk_amt = size_position(
            capital,
            risk_pct,
            abs(raw["entry"] - raw["stop"]),
            raw["entry"],
            max_pos_pct=max_pos_pct,
            risk_cfg=risk_cfg,
        )
        if shares >= 5:
            afford = "gut handelbar"
        elif shares >= 1:
            afford = "knapp handelbar"
        else:
            afford = "Position 0 – Risiko/Preis unpassend"

        ideas.append(
            Idea(
                symbol=symbol,
                name=snap.name,
                side=raw["side"],
                setup=raw["setup"],
                grade=raw["grade"],
                score=raw["score"],
                confluence=raw["confluence"],
                price=snap.price,
                currency=snap.currency,
                entry=raw["entry"],
                stop=raw["stop"],
                target1=raw["target1"],
                target2=raw["target2"],
                invalidation=raw["invalidation"],
                playbook=raw["playbook"],
                atr=raw["atr"],
                atr_pct=raw["atr_pct"],
                risk_per_share=abs(raw["entry"] - raw["stop"]),
                shares=shares,
                position_value=pos_val,
                risk_amount=risk_amt,
                reward_risk=float(risk_cfg.get("reward_risk_t1", 1.5)),
                reasons=raw["reasons"],
                warnings=raw["warnings"],
                change_pct=snap.change_pct,
                rsi=raw["rsi"],
                adx=raw["adx"],
                volume_ratio=raw["volume_ratio"],
                news_score=nscore,
                headlines=heads,
                vwap=raw["vwap"],
                or_high=raw["or_high"],
                or_low=raw["or_low"],
                swing_high=raw["swing_high"],
                swing_low=raw["swing_low"],
                rel_spy=raw["rel_spy"],
                earnings_soon=snap.earnings_soon,
                quality=float(raw.get("quality", 0)),
                gap_pct=float(raw.get("gap_pct", 0)),
                rvol=float(raw.get("rvol", 1)),
                affordability=afford,
                extras={
                    "sector": snap.sector,
                    "or_day": raw.get("or_day"),
                    "short_ratio": snap.short_ratio,
                    "rel_iwm": raw.get("rel_iwm"),
                    "bias_15": raw.get("bias_15"),
                    "market_cap": snap.market_cap,
                },
            )
        )

    rank = {"A": 3, "B": 2, "C": 1, "F": 0}
    ideas.sort(
        key=lambda i: (
            i.side != "SKIP",
            rank.get(i.grade, 0),
            i.quality,
            i.score,
            i.shares > 0,
        ),
        reverse=True,
    )
    return regime, ideas

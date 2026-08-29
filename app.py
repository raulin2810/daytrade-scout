from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yaml

from src.data import fetch_history, fetch_intraday, fetch_quote
from src.news import collect_headlines, sentiment_score
from src.signals import Idea, analyze, size_position


ROOT = Path(__file__).resolve().parent
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


st.set_page_config(
    page_title="Daytrade Scout",
    page_icon="📈",
    layout="wide",
)


def load_css():
    st.markdown(
        """
        <style>
        .block-container {padding-top: 1.4rem; max-width: 1400px;}
        .disclaimer {
            background: #3b1d1d;
            border: 1px solid #8a3a3a;
            color: #ffd7d7;
            padding: 0.9rem 1.1rem;
            border-radius: 12px;
            margin-bottom: 1rem;
            font-size: 0.95rem;
        }
        .idea-card {
            background: #16181d;
            border: 1px solid #2b3038;
            border-radius: 16px;
            padding: 1rem 1.1rem;
            margin-bottom: 0.8rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def market_status() -> str:
    now = datetime.now(ZoneInfo("America/New_York"))
    weekday = now.weekday()
    minutes = now.hour * 60 + now.minute
    open_m, close_m = 9 * 60 + 30, 16 * 60
    if weekday >= 5:
        return "US-Markt geschlossen (Wochenende)"
    if open_m <= minutes < close_m:
        return f"US-Markt geöffnet · {now.strftime('%H:%M')} ET"
    return f"US-Markt geschlossen · {now.strftime('%H:%M')} ET"


@st.cache_data(ttl=180, show_spinner=False)
def scan_universe(
    symbols: tuple[str, ...],
    capital: float,
    risk_pct: float,
    atr_mult: float,
    rr: float,
    min_volume: float,
    max_ideas: int,
) -> list[Idea]:
    ideas: list[Idea] = []
    for symbol in symbols:
        quote = fetch_quote(symbol)
        if quote is None:
            continue
        if quote.avg_volume and quote.avg_volume < min_volume:
            continue
        daily = fetch_history(symbol, period="90d", interval="1d")
        headlines = collect_headlines(symbol, CONFIG["news"]["max_headlines_per_symbol"])
        nscore = sentiment_score(headlines)
        raw = analyze(daily, quote.price, nscore, atr_mult, rr)
        shares, pos_val, risk_amt = size_position(
            raw["entry"], raw["stop"], capital, risk_pct
        )
        idea = Idea(
            symbol=symbol,
            name=quote.name,
            side=raw["side"],
            score=raw["score"],
            price=quote.price,
            currency=quote.currency,
            entry=raw["entry"],
            stop=raw["stop"],
            target=raw["target"],
            atr=raw["atr"],
            risk_per_share=abs(raw["entry"] - raw["stop"]),
            shares=shares,
            position_value=pos_val,
            risk_amount=risk_amt,
            reward_risk=rr,
            reasons=raw["reasons"],
            change_pct=quote.change_pct,
            rsi=raw["rsi"],
            volume_ratio=raw.get("volume_ratio", 1.0),
            news_score=nscore,
            headlines=headlines,
        )
        ideas.append(idea)

    tradable = [i for i in ideas if i.side != "SKIP" and i.shares > 0]
    tradable.sort(key=lambda x: x.score, reverse=True)
    skipped = [i for i in ideas if i not in tradable]
    skipped.sort(key=lambda x: x.score, reverse=True)
    return tradable[:max_ideas] + skipped


def candle_chart(symbol: str) -> go.Figure:
    df = fetch_intraday(symbol)
    if df.empty:
        df = fetch_history(symbol, period="6mo", interval="1d")
    fig = go.Figure(
        data=[
            go.Candlestick(
                x=df.index,
                open=df["Open"],
                high=df["High"],
                low=df["Low"],
                close=df["Close"],
                name=symbol,
            )
        ]
    )
    fig.update_layout(
        height=360,
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        title=f"{symbol} – Intraday / zuletzt verfügbare Kerzen",
    )
    return fig


def money(value: float, currency: str = "USD") -> str:
    return f"{value:,.2f} {currency}"


def main():
    load_css()
    st.title("Daytrade Scout")
    st.caption("Lokale Recherche-App · Kurse + Nachrichten + technische Filter · keine Orderausführung")

    st.markdown(
        f"""
        <div class="disclaimer">
        <b>Kein Finanzrat, keine Kaufempfehlung.</b>
        Die App durchsucht <i>nicht</i> das ganze Internet und kann den Markt nicht vorhersagen.
        Sie holt öffentlich verfügbare Kurse (Yahoo Finance) und Schlagzeilen, rechnet einfache
        Indikatoren (EMA, RSI, MACD, ATR) und schlägt daraus <i>Ideen zum Selbstprüfen</i> vor.
        Daytrading kann das gesamte Kapital vernichten. Daten können verzögert oder falsch sein.
        Status: {market_status()}
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("Einstellungen")
        capital = st.number_input(
            "Handelskapital",
            min_value=500.0,
            value=float(CONFIG["risk"]["default_capital_eur"]),
            step=500.0,
            help="Nur zur Positionsgröße. Es wird nichts gekauft.",
        )
        risk_pct = st.slider(
            "Risiko pro Idee (%)",
            min_value=0.1,
            max_value=2.0,
            value=float(CONFIG["risk"]["default_risk_pct"]),
            step=0.1,
        )
        max_ideas = st.slider("Max. Ideen", 1, 10, int(CONFIG["risk"]["max_ideas"]))
        atr_mult = st.slider("Stop-Abstand (× ATR)", 1.0, 3.0, float(CONFIG["risk"]["atr_stop_mult"]), 0.1)
        rr = st.slider("Chance/Risiko-Ziel", 1.0, 3.0, float(CONFIG["risk"]["reward_risk"]), 0.1)
        extra = st.text_input("Zusätzliche Ticker (Komma)", placeholder="SAP.DE, BMW.DE")
        run = st.button("Heute scannen", type="primary", use_container_width=True)
        st.markdown("---")
        st.markdown(
            "Start auf dem Mac: `start.command` doppelklicken "
            "oder `./start.sh` im Terminal."
        )

    symbols = list(CONFIG["universe"])
    if extra.strip():
        symbols.extend([s.strip().upper() for s in extra.split(",") if s.strip()])
    symbols = tuple(dict.fromkeys(symbols))

    if not run and "ideas" not in st.session_state:
        st.info("Links Kapital setzen und **Heute scannen** klicken.")
        st.markdown(
            """
            ### Was die App wirklich macht
            1. Lädt Schlusskurse und Intraday-Kerzen der Watchlist.
            2. Liest Yahoo-News und Google-News-RSS (kein Crawling des gesamten Webs).
            3. Bewertet Trend, RSI, MACD, Volumen und Schlagzeilen-Wörter.
            4. Setzt Stop-Loss auf **1,5 × ATR** und Ziel auf **2R**, Positionsgröße nach deinem Risiko.

            ### Was sie nicht macht
            - Keine Broker-Anbindung, keine automatischen Orders
            - Keine Garantie, kein Edge, kein „das ganze Internet“
            - Keine Steuer-, Rechts- oder Anlageberatung
            """
        )
        return

    if run:
        with st.spinner("Kurse und Nachrichten werden geladen …"):
            st.session_state.ideas = scan_universe(
                symbols,
                capital,
                risk_pct,
                atr_mult,
                rr,
                float(CONFIG["risk"]["min_avg_volume"]),
                max_ideas,
            )
            st.session_state.scanned_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    ideas: list[Idea] = st.session_state.get("ideas", [])
    picks = [i for i in ideas if i.side != "SKIP"][:max_ideas]
    rest = [i for i in ideas if i not in picks]

    st.subheader(f"Ideen ({st.session_state.get('scanned_at', '')})")
    if not picks:
        st.warning("Heute keine Idee über dem Schwellenwert. Markt überspringen ist oft die bessere Entscheidung.")
    else:
        rows = []
        for i in picks:
            rows.append(
                {
                    "Ticker": i.symbol,
                    "Richtung": i.side,
                    "Score": i.score,
                    "Kurs": round(i.price, 2),
                    "Einstieg": round(i.entry, 2),
                    "Stop-Loss": round(i.stop, 2),
                    "Ziel": round(i.target, 2),
                    "Stück": i.shares,
                    "Risiko €/$": round(i.risk_amount, 2),
                    "RSI": round(i.rsi, 1),
                    "News": round(i.news_score, 2),
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if picks:
        tabs = st.tabs([f"{p.symbol} {p.side}" for p in picks])
        for tab, idea in zip(tabs, picks):
            with tab:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Kurs", money(idea.price, idea.currency), f"{idea.change_pct:+.2f}%")
                c2.metric("Stop-Loss", money(idea.stop, idea.currency))
                c3.metric("Take-Profit", money(idea.target, idea.currency))
                c4.metric("Stückzahl", f"{idea.shares}", f"Risiko ca. {idea.risk_amount:.0f}")
                st.write(
                    f"**{idea.name}** · Score {idea.score:.0f} · "
                    f"Abstand Stop {idea.risk_per_share:.2f} {idea.currency} · "
                    f"Positionsnotional {idea.position_value:,.0f} {idea.currency}"
                )
                st.write("**Warum (Heuristik, kein Orakel):**")
                for reason in idea.reasons:
                    st.write(f"- {reason}")
                if idea.headlines:
                    st.write("**Schlagzeilen (ungeprüft):**")
                    for h in idea.headlines:
                        st.write(f"- {h}")
                st.plotly_chart(candle_chart(idea.symbol), use_container_width=True)
                if idea.side == "LONG":
                    st.info(
                        f"Long-Idee: Kaufzone um {idea.entry:.2f}. "
                        f"Wenn der Kurs {idea.stop:.2f} unterschreitet → raus. "
                        f"Teilgewinn / Ausstieg bei {idea.target:.2f} oder vor US-Schluss, "
                        "falls du wirklich nur Intraday handelst."
                    )
                else:
                    st.info(
                        f"Short-Idee: Zone um {idea.entry:.2f}. "
                        f"Stop über {idea.stop:.2f}. Ziel {idea.target:.2f}. "
                        "Shorts sind auf manchen Brokern teurer und riskanter."
                    )

    if rest:
        with st.expander("Watchlist ohne klares Setup"):
            df = pd.DataFrame(
                [
                    {
                        "Ticker": i.symbol,
                        "Kurs": round(i.price, 2),
                        "Tag %": round(i.change_pct, 2),
                        "Score": i.score,
                        "RSI": round(i.rsi, 1),
                    }
                    for i in rest
                ]
            )
            st.dataframe(df, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yaml

from src.journal import add_row, load as load_journal
from src.scan import run_scan
from src.signals import Idea


ROOT = Path(__file__).resolve().parent
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


st.set_page_config(page_title="Daytrade Scout", page_icon="📈", layout="wide")


def market_clock() -> str:
    now = datetime.now(ZoneInfo("America/New_York"))
    minutes = now.hour * 60 + now.minute
    if now.weekday() >= 5:
        return f"Wochenende · {now.strftime('%a %H:%M')} ET – Ideen sind ein Plan für die nächste Session"
    if 9 * 60 + 30 <= minutes < 16 * 60:
        return f"US-RTH offen · {now.strftime('%H:%M')} ET"
    if 4 * 60 <= minutes < 9 * 60 + 30:
        return f"Pre-Market · {now.strftime('%H:%M')} ET"
    return f"US-Markt zu · {now.strftime('%H:%M')} ET"


def idea_chart(idea: Idea) -> go.Figure:
    import yfinance as yf

    df = yf.Ticker(idea.symbol).history(period="7d", interval="15m", auto_adjust=True)
    if df is None or df.empty:
        df = yf.Ticker(idea.symbol).history(period="6mo", interval="1d", auto_adjust=True)
    df = df.rename(columns=str.title)
    fig = go.Figure(
        data=[
            go.Candlestick(
                x=df.index,
                open=df["Open"],
                high=df["High"],
                low=df["Low"],
                close=df["Close"],
                name=idea.symbol,
            )
        ]
    )
    levels = [
        (idea.entry, "Entry", "#3dd68c"),
        (idea.stop, "Stop", "#ff6b6b"),
        (idea.target1, "T1", "#f0c14b"),
        (idea.target2, "T2", "#9b8cff"),
    ]
    if idea.vwap:
        levels.append((idea.vwap, "VWAP", "#5ec8ff"))
    if idea.or_high:
        levels.append((idea.or_high, "OR High", "#888"))
    if idea.or_low:
        levels.append((idea.or_low, "OR Low", "#888"))
    for y, name, color in levels:
        fig.add_hline(
            y=y, line_color=color, line_dash="dot", annotation_text=name, annotation_position="right"
        )
    fig.update_layout(
        height=380,
        margin=dict(l=8, r=8, t=36, b=8),
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        title=f"{idea.symbol} 15m mit Entry / Stop / Ziele / VWAP",
    )
    return fig


def main() -> None:
    st.markdown(
        """
        <style>
        .block-container {padding-top: 1.2rem; max-width: 1500px;}
        .disclaimer {background:#3b1d1d;border:1px solid #8a3a3a;color:#ffd7d7;
                     padding:0.85rem 1.05rem;border-radius:12px;margin-bottom:0.9rem;}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title("Daytrade Scout")
    st.caption("Multi-Timeframe · VWAP/Opening-Range · Marktregime · Journal · keine Orders")
    st.markdown(
        f"""
        <div class="disclaimer">
        <b>Kein Finanzrat.</b> Präziser heißt hier: mehr Filter und klarere Invalidierung –
        nicht „besserer Hellseher“. Es wird nicht das ganze Internet gecrawlt.
        Stop-Loss schützt nicht vor Gaps. Status: {market_clock()}
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("Setup")
        capital = st.number_input(
            "Kapital", min_value=500.0, value=float(CONFIG["risk"]["default_capital"]), step=500.0
        )
        risk_pct = st.slider("Risiko je Idee %", 0.1, 2.0, float(CONFIG["risk"]["default_risk_pct"]), 0.1)
        max_ideas = st.slider("Max. Ideen", 1, 8, int(CONFIG["risk"]["max_ideas"]))
        use_de = st.checkbox("Deutsche Titel zusätzlich", value=False)
        extra = st.text_input("Extra-Ticker", placeholder="AMD, RHM.DE")
        only_ab = st.checkbox("Nur Note A/B", value=True)
        with_news = st.checkbox("News für Top-Titel laden", value=True)
        run = st.button("Scan starten", type="primary", use_container_width=True)
        st.caption("Erster Scan dauert 20–60 Sekunden (Batch-Kurse + News).")

    symbols = list(CONFIG["universe"])
    if use_de:
        symbols.extend(CONFIG.get("de_universe", []))
    if extra.strip():
        symbols.extend([s.strip().upper() for s in extra.split(",") if s.strip()])
    symbols = list(dict.fromkeys(symbols))

    tabs = st.tabs(["Scan", "Journal", "Methode"])

    with tabs[2]:
        st.markdown(
            """
            ### Wie die Bewertung jetzt läuft
            1. **Marktregime** aus SPY, QQQ, IWM, VIX (Trend, ADX, Volatilität).
            2. **Drei Zeitrahmen**: Tag, 1h, 15m.
            3. **Confluence**: EMA-Stack, RSI-Arbeitsbereich, MACD, ADX, Relativstärke vs. SPY,
               1h-Bestätigung, VWAP, Opening Range, Volumen, News-Wörter.
            4. **Stop** aus ATR *und* letztem Swing.
            5. **Zwei Ziele** (1,5R / 2,5R), T1 wird am nächsten Widerstand gekappt.
            6. **WAIT-Setup**: Kurs schon weggelaufen → VWAP abwarten statt hinterherlaufen.
            7. Zahlen in 5 Tagen und VIX ≥ 28 werden bestraft.

            Note **A** = mindestens 5 Confluence-Punkte, kein Earnings-Fenster, VIX nicht extrem.
            Unter 3 Punkten gibt es keine Idee.
            """
        )

    with tabs[1]:
        st.subheader("Paper-Journal")
        journal = load_journal()
        st.dataframe(journal, use_container_width=True, hide_index=True)
        if not journal.empty:
            st.download_button("Journal als CSV", journal.to_csv(index=False), "journal.csv", "text/csv")

    with tabs[0]:
        if not run and "ideas" not in st.session_state:
            st.info("Links **Scan starten**. Am Wochenende ist das ein Plan für Montag, kein Live-Intraday.")
            return
        if run:
            with st.spinner("Kurse, VIX, 15m-Struktur und News …"):
                regime, ideas = run_scan(symbols, capital, risk_pct, CONFIG, include_news=with_news)
                st.session_state.regime = regime
                st.session_state.ideas = ideas
                st.session_state.when = datetime.now().strftime("%Y-%m-%d %H:%M")

        regime = st.session_state["regime"]
        ideas: list[Idea] = st.session_state["ideas"]
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("SPY", f"{regime.spy_change:+.2f}%")
        c2.metric("QQQ", f"{regime.qqq_change:+.2f}%")
        c3.metric("IWM", f"{regime.iwm_change:+.2f}%")
        c4.metric("VIX", f"{regime.vix:.1f}")
        c5.metric("Regime", regime.label)
        st.caption(" · ".join(regime.notes))

        picks = [i for i in ideas if i.side != "SKIP" and i.shares > 0]
        if only_ab:
            picks = [i for i in picks if i.grade in {"A", "B"}]
        picks = picks[:max_ideas]
        rest = [i for i in ideas if i not in picks]

        st.subheader(f"Ideen · {st.session_state.get('when', '')}")
        if not picks:
            st.warning("Kein Setup mit genug Confluence. Das ist oft die richtige Antwort.")
        else:
            table = pd.DataFrame(
                [
                    {
                        "Note": i.grade,
                        "Ticker": i.symbol,
                        "Seite": i.side,
                        "Setup": i.setup,
                        "Conf.": i.confluence,
                        "Kurs": round(i.price, 2),
                        "Entry": round(i.entry, 2),
                        "Stop": round(i.stop, 2),
                        "T1": round(i.target1, 2),
                        "T2": round(i.target2, 2),
                        "Stück": i.shares,
                        "RSI": round(i.rsi, 0),
                        "ADX": round(i.adx, 0),
                        "vs SPY 5d": round(i.rel_spy * 100, 2),
                        "News": round(i.news_score, 2),
                    }
                    for i in picks
                ]
            )
            st.dataframe(table, use_container_width=True, hide_index=True)
            st.download_button(
                "Ideen exportieren",
                table.to_csv(index=False),
                f"ideen_{datetime.now().strftime('%Y%m%d')}.csv",
                "text/csv",
            )

            view = st.tabs([f"{p.grade} {p.symbol} {p.side}" for p in picks])
            for tab, idea in zip(view, picks):
                with tab:
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Entry", f"{idea.entry:.2f} {idea.currency}")
                    m2.metric("Stop", f"{idea.stop:.2f}")
                    m3.metric("T1 / T2", f"{idea.target1:.2f} / {idea.target2:.2f}")
                    m4.metric("Stück", f"{idea.shares}", f"Risiko {idea.risk_amount:.0f}")
                    st.write(
                        f"**{idea.name}** · Setup `{idea.setup}` · Score {idea.score:.0f} · "
                        f"ATR {idea.atr:.2f} ({idea.atr_pct:.1f}%) · "
                        f"Notional {idea.position_value:,.0f} {idea.currency}"
                    )
                    if idea.earnings_soon:
                        st.error("Earnings-Fenster: Gap kann durch jeden Stop laufen.")
                    for w in idea.warnings:
                        st.warning(w)
                    st.write("**Confluence**")
                    for r in idea.reasons:
                        st.write(f"- {r}")
                    st.info(idea.playbook)
                    st.caption(f"Invalidierung: {idea.invalidation}")
                    if idea.headlines:
                        st.write("**Schlagzeilen**")
                        for h in idea.headlines:
                            st.write(f"- {h}")
                    st.plotly_chart(idea_chart(idea), use_container_width=True)
                    if st.button(f"In Journal legen · {idea.symbol}", key=f"j_{idea.symbol}"):
                        add_row(
                            {
                                "ticker": idea.symbol,
                                "seite": idea.side,
                                "setup": idea.setup,
                                "grade": idea.grade,
                                "einstieg": round(idea.entry, 2),
                                "stop": round(idea.stop, 2),
                                "ziel1": round(idea.target1, 2),
                                "stueck": idea.shares,
                                "status": "plan",
                                "notiz": idea.setup,
                            }
                        )
                        st.success("Gespeichert unter Journal.")

        if rest:
            with st.expander("Rest der Watchlist"):
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Ticker": i.symbol,
                                "Note": i.grade,
                                "Seite": i.side,
                                "Score": i.score,
                                "Conf.": i.confluence,
                                "RSI": round(i.rsi, 0),
                                "%": round(i.change_pct, 2),
                            }
                            for i in rest
                        ]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )


if __name__ == "__main__":
    main()

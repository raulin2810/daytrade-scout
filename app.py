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
from src import scalable as sc

ROOT = Path(__file__).resolve().parent
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
ISIN_MAP = {str(k).upper(): str(v).upper() for k, v in (CONFIG.get("isin_map") or {}).items()}

st.set_page_config(page_title="Daytrade Scout", page_icon="📈", layout="wide")


def market_clock() -> str:
    now = datetime.now(ZoneInfo("America/New_York"))
    minutes = now.hour * 60 + now.minute
    if now.weekday() >= 5:
        return f"Wochenende · {now.strftime('%a %H:%M')} ET"
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
    fig = go.Figure(data=[go.Candlestick(x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"], name=idea.symbol)])
    for y, name, color in [(idea.entry, "Entry", "#3dd68c"), (idea.stop, "Stop", "#ff6b6b"), (idea.target1, "T1", "#f0c14b"), (idea.target2, "T2", "#9b8cff")]:
        fig.add_hline(y=y, line_color=color, line_dash="dot", annotation_text=name, annotation_position="right")
    if idea.vwap:
        fig.add_hline(y=idea.vwap, line_color="#5ec8ff", line_dash="dot", annotation_text="VWAP")
    fig.update_layout(height=380, margin=dict(l=8, r=8, t=36, b=8), xaxis_rangeslider_visible=False, template="plotly_dark", title=f"{idea.symbol} 15m")
    return fig


def _json_table(data):
    if data is None:
        return None
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return pd.DataFrame(data)
    if isinstance(data, dict):
        for key in ("holdings", "items", "transactions", "results", "positions"):
            if key in data and isinstance(data[key], list):
                return pd.DataFrame(data[key])
        return pd.DataFrame([data])
    return None


def render_scalable_tab():
    st.subheader("Scalable")
    if not sc.sc_available():
        st.warning("`sc` CLI fehlt. Install: brew install scalable-cli · dann sc login")
        return
    c1, c2 = st.columns(2)
    if c1.button("Übersicht laden"):
        st.session_state["sc_overview"] = sc.broker_overview()
    if c2.button("Watchlist laden"):
        st.session_state["sc_wl"] = sc.broker_watchlist()
    if "sc_overview" in st.session_state:
        st.json(st.session_state["sc_overview"])
    if "sc_wl" in st.session_state:
        df = _json_table(st.session_state["sc_wl"])
        if df is not None:
            st.dataframe(df, use_container_width=True)


def render_order_prepare_block(idea: Idea):
    allow = bool((CONFIG.get("scalable") or {}).get("allow_trade_execution", False))
    isin = ISIN_MAP.get(idea.symbol.upper()) or ISIN_MAP.get(idea.symbol)
    st.markdown("**Scalable Order**")
    if not isin:
        st.caption(f"Keine ISIN für {idea.symbol} in config.yaml")
        return
    st.caption(f"ISIN {isin}")
    if not sc.sc_available():
        st.caption("`sc` nicht gefunden – nur manuell in der App handeln")
        return
    if not allow:
        st.caption("Execution in config deaktiviert")
        return
    amount = max(10.0, float(idea.position_value or 0))
    if st.button(f"Preview Kauf {idea.symbol}", key=f"prev_{idea.symbol}"):
        try:
            preview = sc.trade_buy_preview(isin=isin, amount=amount)
            st.session_state[f"prev_{idea.symbol}"] = preview
            st.json(preview)
        except Exception as e:
            st.error(str(e))
    if st.session_state.get(f"prev_{idea.symbol}"):
        conf = st.checkbox(f"Ich bestätige die Order {idea.symbol}", key=f"cf_{idea.symbol}")
        if conf and st.button(f"Order senden {idea.symbol}", key=f"go_{idea.symbol}"):
            st.warning("Bitte Order im Terminal mit sc bestätigen (Two-Step). Preview siehe oben.")


def main():
    st.title("Daytrade Scout")
    st.caption("Favoriten · Quality-Score · optional Zock-Modus · Scalable")
    st.warning(f"Kein Finanzrat. Status: {market_clock()}")
    with st.sidebar:
        capital = st.number_input("Kapital", min_value=500.0, value=float(CONFIG["risk"]["default_capital"]), step=500.0)
        risk_pct = st.slider("Risiko %", 0.1, 2.0, float(CONFIG["risk"]["default_risk_pct"]), 0.1)
        max_ideas = st.slider("Max. Ideen", 1, 8, int(CONFIG["risk"]["max_ideas"]))
        use_de = st.checkbox("DE-Titel", value=False)
        use_big = st.checkbox("Big Caps zusaetzlich", value=False)
        extra = st.text_input("Extra-Ticker", placeholder="SOFI, HOOD")
        only_ab = st.checkbox("Nur A/B", value=True)
        only_afford = st.checkbox("Nur >=5 Stueck", value=False)
        with_news = st.checkbox("News", value=True)
        zock = st.checkbox("Zock-Modus (hohe Vola / Pennys, max 5% Kapital)", value=False)
        if zock:
            st.sidebar.warning("Nur Spaß/Spekulation – Totalverlust möglich. Max ~5% vom Kapital.")
        run = st.button("Scan starten", type="primary", use_container_width=True)
        st.caption("`sc` OK" if sc.sc_available() else "`sc` fehlt")

    symbols = list(CONFIG["universe"])
    if use_big:
        symbols.extend(CONFIG.get("big_universe", []))
    if use_de:
        symbols.extend(CONFIG.get("de_universe", []))
    if extra.strip():
        symbols.extend([s.strip().upper() for s in extra.split(",") if s.strip()])
    symbols = list(dict.fromkeys(symbols))

    tabs = st.tabs(["Scan", "Journal", "Scalable", "Methode"])
    with tabs[3]:
        st.markdown("""
### Filter (keine Prognose-Garantie)
- Regime SPY/QQQ/IWM/VIX
- Confluence, VWAP, ORB, RVOL
- **Zock-Modus**: nur hohe ATR/RVOL, max 5% Kapital – Spekulation
""")
    with tabs[1]:
        st.dataframe(load_journal(), use_container_width=True, hide_index=True)
    with tabs[2]:
        render_scalable_tab()

    with tabs[0]:
        if run:
            with st.spinner("Scan…"):
                scan_cfg = dict(CONFIG)
                scan_capital = capital
                if zock:
                    z = dict(CONFIG.get("zock") or {})
                    pct = float(z.get("max_budget_pct", 0.05))
                    scan_capital = max(50.0, capital * pct)
                    scan_cfg["_zock_mode"] = True
                    if "max_ideas" in z:
                        scan_cfg["risk"] = dict(scan_cfg.get("risk") or {})
                        scan_cfg["risk"]["max_ideas"] = int(z["max_ideas"])
                regime, ideas = run_scan(symbols, scan_capital, risk_pct, scan_cfg, include_news=with_news)
                if zock:
                    st.info(
                        f"Zock-Modus aktiv · Scan-Kapital ≈ {scan_capital:.0f} "
                        f"({float((CONFIG.get('zock') or {}).get('max_budget_pct', 0.05))*100:.0f}% von {capital:.0f})"
                    )
                st.session_state["ideas"] = ideas
                st.session_state["regime"] = regime
                st.session_state["when"] = datetime.now().strftime("%Y-%m-%d %H:%M")

        regime = st.session_state.get("regime")
        ideas = st.session_state.get("ideas") or []
        if regime:
            st.write(
                f"**Markt:** {regime.label} · SPY {regime.spy_change:+.2f}% · "
                f"QQQ {regime.qqq_change:+.2f}% · IWM {regime.iwm_change:+.2f}% · VIX {regime.vix:.1f}"
            )
            for n in regime.notes:
                st.caption(n)

        if ideas:
            picks = [i for i in ideas if i.side != "SKIP"]
            if only_ab:
                picks = [i for i in picks if i.grade in ("A", "B")]
            if only_afford:
                picks = [i for i in picks if i.shares >= 5]
            picks = picks[: max_ideas]
            rest = [i for i in ideas if i not in picks]
            st.subheader(f"Ideen · {st.session_state.get('when', '')}")
            if not picks:
                st.warning("Kein Setup mit genug Confluence.")
            else:
                table = pd.DataFrame([{
                    "Note": i.grade, "Q": round(getattr(i, "quality", 0), 0), "Ticker": i.symbol,
                    "Seite": i.side, "Setup": i.setup, "Conf.": i.confluence, "Kurs": round(i.price, 2),
                    "Entry": round(i.entry, 2), "Stop": round(i.stop, 2), "T1": round(i.target1, 2),
                    "T2": round(i.target2, 2), "Stueck": i.shares, "Handel": getattr(i, "affordability", ""),
                    "Gap%": round(getattr(i, "gap_pct", 0), 1), "RVOL": round(getattr(i, "rvol", 1), 1),
                    "RSI": round(i.rsi, 0), "ADX": round(i.adx, 0),
                } for i in picks])
                st.dataframe(table, use_container_width=True, hide_index=True)
                for idea in picks:
                    with st.expander(f"{idea.grade} {idea.symbol} {idea.side} · Q{getattr(idea, 'quality', 0):.0f}"):
                        m1, m2, m3, m4 = st.columns(4)
                        m1.metric("Entry", f"{idea.entry:.2f}")
                        m2.metric("Stop", f"{idea.stop:.2f}")
                        m3.metric("T1/T2", f"{idea.target1:.2f}/{idea.target2:.2f}")
                        m4.metric("Stueck", f"{idea.shares}")
                        st.write(f"**{idea.name}** · {idea.setup} · Score {idea.score:.0f} · {getattr(idea, 'affordability', '')}")
                        for w in idea.warnings:
                            st.warning(w)
                        for r in idea.reasons:
                            st.write(f"- {r}")
                        st.info(idea.playbook)
                        try:
                            st.plotly_chart(idea_chart(idea), use_container_width=True)
                        except Exception:
                            pass
                        if st.button(f"Journal · {idea.symbol}", key=f"j_{idea.symbol}"):
                            add_row({"ticker": idea.symbol, "seite": idea.side, "setup": idea.setup, "grade": idea.grade, "einstieg": round(idea.entry, 2), "stop": round(idea.stop, 2), "ziel1": round(idea.target1, 2), "stueck": idea.shares, "status": "plan", "notiz": idea.setup})
                            st.success("Gespeichert")
                        render_order_prepare_block(idea)
            if rest:
                with st.expander("Rest"):
                    st.dataframe(pd.DataFrame([{"Ticker": i.symbol, "Note": i.grade, "Score": i.score, "Conf.": i.confluence, "Setup": i.setup} for i in rest]), use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()

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
        try:
            return pd.DataFrame([data])
        except Exception:
            return None
    return None


def _show_prepared_order(key: str) -> None:
    prep = st.session_state.get(key)
    if not prep:
        return
    result, isin, cmd, symbol = prep["result"], prep.get("isin"), prep.get("cmd"), prep.get("symbol", "")
    meta = prep.get("meta") or {}
    if not result.ok:
        st.error(result.error or "Preview fehlgeschlagen")
        if result.raw:
            st.code(result.raw)
        return
    st.success(f"Order vorbereitet: {symbol}" + (f" ({isin})" if isin else ""))
    if meta.get("cash_note"):
        st.caption(meta["cash_note"])
    if meta.get("cash") is not None:
        st.caption(f"Scalable Cash ~ {meta['cash']:.2f}")
    table = _json_table(result.data)
    if table is not None and not table.empty:
        st.dataframe(table, use_container_width=True, hide_index=True)
    else:
        st.json(result.data if result.data is not None else result.raw)
    cid = meta.get("confirmation_id")
    if cmd:
        st.markdown("**Option A – Terminal:**")
        st.code(cmd, language="bash")
    allow = bool((CONFIG.get("scalable") or {}).get("allow_trade_execution", False))
    if allow and isin and cid:
        st.markdown("**Option B – App bestaetigen (Phase 2):**")
        ok = st.checkbox("Kosten/Warnungen geprueft – Order jetzt senden", key=f"ack_{symbol}_{cid}")
        if st.button("Order jetzt bestaetigen und senden", type="primary", key=f"go_{symbol}_{cid}"):
            if not ok:
                st.error("Bitte Checkbox setzen.")
            else:
                conf = sc.trade_confirm(
                    meta.get("side", "buy"), isin, cid,
                    amount=meta.get("size_value") if meta.get("size_mode") == "amount" else None,
                    shares=meta.get("size_value") if meta.get("size_mode") == "shares" else None,
                    order_type=meta.get("order_type", "market"), enabled=True,
                )
                if conf.ok:
                    st.success("Order gesendet.")
                    st.json(conf.data if conf.data is not None else conf.raw)
                    add_row({"ticker": symbol, "seite": meta.get("side", ""), "setup": "scalable", "grade": "", "einstieg": "", "stop": "", "ziel1": "", "stueck": meta.get("size_value", ""), "status": "submitted", "notiz": f"confirm {cid}"})
                else:
                    st.error(conf.error or "Confirm fehlgeschlagen")
    elif not cid:
        st.warning("Keine confirmation_id – Terminal nutzen.")


def render_order_prepare_block(idea: Idea) -> None:
    st.markdown("---")
    st.markdown("**Scalable: Order vorbereiten**")
    if not sc.sc_available():
        st.caption("`sc` fehlt – Tab Scalable.")
        return
    isin_hint = sc.resolve_isin(idea.symbol, ISIN_MAP)
    st.caption(f"ISIN: `{isin_hint}`" if isin_hint else "ISIN unbekannt – config.yaml ergaenzen")
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        size_mode = st.selectbox("Groesse", ["shares", "amount"], key=f"sz_{idea.symbol}")
    with c2:
        default_shares = max(1, int(round(idea.shares))) if idea.shares else 1
        default_amount = float(round(idea.position_value, 0)) if idea.position_value else 100.0
        size_val = st.number_input("Wert", min_value=1.0, value=float(default_shares if size_mode == "shares" else default_amount), step=1.0, key=f"sv_{idea.symbol}")
    with c3:
        order_type = st.selectbox("Order-Typ", ["market", "limit", "stop"], key=f"ot_{idea.symbol}")
    if st.button("Order vorbereiten (Preview)", type="primary", key=f"prep_{idea.symbol}"):
        with st.spinner("Preview …"):
            amount = size_val if size_mode == "amount" else None
            shares = size_val if size_mode == "shares" else float(default_shares)
            buf = float((CONFIG.get("scalable") or {}).get("cash_buffer_pct", 0.90))
            result, isin, cmd, meta = sc.prepare_order_from_idea(
                symbol=idea.symbol, side=idea.side, shares=shares, amount=amount,
                isin_map=ISIN_MAP, order_type=order_type, price=idea.price,
                use_cash_limit=True, cash_buffer_pct=buf,
            )
            st.session_state[f"prep_result_{idea.symbol}"] = {"result": result, "isin": isin, "cmd": cmd, "symbol": idea.symbol, "side": idea.side, "meta": meta}
    _show_prepared_order(f"prep_result_{idea.symbol}")


def render_scalable_tab() -> None:
    st.subheader("Scalable Broker")
    if not sc.sc_available():
        st.error("`sc` nicht gefunden. brew install scalable-cli && sc login")
        return
    cols = st.columns(5)
    if cols[0].button("Whoami"):
        st.session_state["sc_last"] = sc.whoami()
    if cols[1].button("Overview"):
        st.session_state["sc_last"] = sc.overview()
    if cols[2].button("Holdings"):
        st.session_state["sc_last"] = sc.holdings()
    if cols[3].button("Transactions"):
        st.session_state["sc_last"] = sc.transactions()
    if cols[4].button("Overnight"):
        st.session_state["sc_last"] = sc.overnight()
    cash, _ = sc.get_available_cash()
    if cash is not None:
        st.metric("Cash (geschaetzt)", f"{cash:,.2f}")
    last = st.session_state.get("sc_last")
    if last is None:
        return
    if not last.ok:
        st.error(last.error)
        return
    st.success("OK")
    table = _json_table(last.data)
    if table is not None and not table.empty:
        st.dataframe(table, use_container_width=True, hide_index=True)
    else:
        st.json(last.data if last.data is not None else last.raw)


def main() -> None:
    st.title("Daytrade Scout")
    st.caption("Mid-Caps · ~4k EUR · Quality-Score · Cash-aware Scalable Orders")
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
- MTF + VWAP/ORB + RVOL + Gap-Filter
- Relativstaerke vs SPY **und IWM** (Mid-Caps)
- Quality-Score 0–100 neben Note A/B/C
- Position max. 25% Kapital; Cash-Check vor Order
""")
    with tabs[2]:
        render_scalable_tab()
    with tabs[1]:
        journal = load_journal()
        st.dataframe(journal, use_container_width=True, hide_index=True)
        if not journal.empty:
            st.download_button("CSV", journal.to_csv(index=False), "journal.csv", "text/csv")
    with tabs[0]:
        if not run and "ideas" not in st.session_state:
            st.info("Links **Scan starten**.")
            return
        if run:
            with st.spinner("Scan …"):
                regime, ideas = run_scan(symbols, capital, risk_pct, CONFIG, include_news=with_news)
                st.session_state.regime = regime
                st.session_state.ideas = ideas
                st.session_state.when = datetime.now().strftime("%Y-%m-%d %H:%M")
        regime = st.session_state["regime"]
        ideas = st.session_state["ideas"]
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("SPY", f"{regime.spy_change:+.2f}%")
        c2.metric("QQQ", f"{regime.qqq_change:+.2f}%")
        c3.metric("IWM", f"{regime.iwm_change:+.2f}%")
        c4.metric("VIX", f"{regime.vix:.1f}")
        c5.metric("Regime", regime.label)
        picks = [i for i in ideas if i.side != "SKIP" and i.shares > 0]
        if only_ab:
            picks = [i for i in picks if i.grade in {"A", "B"}]
        if only_afford:
            picks = [i for i in picks if i.shares >= 5]
        picks = picks[:max_ideas]
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
                    st.plotly_chart(idea_chart(idea), use_container_width=True)
                    if st.button(f"Journal · {idea.symbol}", key=f"j_{idea.symbol}"):
                        add_row({"ticker": idea.symbol, "seite": idea.side, "setup": idea.setup, "grade": idea.grade, "einstieg": round(idea.entry, 2), "stop": round(idea.stop, 2), "ziel1": round(idea.target1, 2), "stueck": idea.shares, "status": "plan", "notiz": idea.setup})
                        st.success("Gespeichert")
                    render_order_prepare_block(idea)
        if rest:
            with st.expander("Rest"):
                st.dataframe(pd.DataFrame([{"Ticker": i.symbol, "Note": i.grade, "Score": i.score, "Conf.": i.confluence} for i in rest]), use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()

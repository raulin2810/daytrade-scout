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
ISIN_MAP: dict[str, str] = {
    str(k).upper(): str(v).upper() for k, v in (CONFIG.get("isin_map") or {}).items()
}


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


def _json_table(data: object) -> pd.DataFrame | None:
    if data is None:
        return None
    if isinstance(data, list):
        if not data:
            return pd.DataFrame()
        if isinstance(data[0], dict):
            return pd.DataFrame(data)
        return pd.DataFrame({"value": data})
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
    result: sc.ScalableResult = prep["result"]
    isin = prep.get("isin")
    cmd = prep.get("cmd")
    symbol = prep.get("symbol", "")

    if not result.ok:
        st.error(result.error or "Preview fehlgeschlagen")
        if result.raw:
            with st.expander("Rohausgabe"):
                st.code(result.raw)
        return

    st.success(f"Order vorbereitet für {symbol}" + (f" ({isin})" if isin else ""))
    st.caption("Phase 1 erledigt – noch keine Ausführung. Prüfe Kosten/Warnungen unten.")

    if cmd:
        st.markdown("**Zum Bestätigen im Terminal kopieren und ausführen:**")
        st.code(cmd, language="bash")
        st.warning(
            "Nur ausführen, wenn du die Order wirklich platzieren willst. "
            "Die confirmation_id ist zeitlich begrenzt."
        )
    else:
        st.warning(
            "Preview OK, aber keine confirmation_id gefunden. "
            "JSON prüfen und manuell mit --confirm fortsetzen."
        )

    table = _json_table(result.data)
    if table is not None and not table.empty:
        st.dataframe(table, use_container_width=True, hide_index=True)
    else:
        st.json(result.data if result.data is not None else result.raw)


def render_order_prepare_block(idea: Idea) -> None:
    """Aus Scan-Idee: Scalable-Order vorbereiten (nur Preview)."""
    st.markdown("---")
    st.markdown("**Scalable: Order vorbereiten**")
    if not sc.sc_available():
        st.caption("`sc` nicht installiert – siehe Tab Scalable.")
        return

    isin_hint = sc.resolve_isin(idea.symbol, ISIN_MAP)
    if isin_hint:
        st.caption(f"ISIN: `{isin_hint}`")
    else:
        st.caption("ISIN unbekannt – wird per `sc search` versucht oder in config.yaml ergänzen.")

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        size_mode = st.selectbox(
            "Größe",
            ["shares", "amount"],
            key=f"sz_{idea.symbol}",
            help="shares = Stückzahl aus Idee; amount = Euro-Betrag",
        )
    with c2:
        default_shares = max(1, int(round(idea.shares))) if idea.shares else 1
        default_amount = float(round(idea.position_value, 0)) if idea.position_value else 100.0
        if size_mode == "shares":
            size_val = st.number_input(
                "Stück",
                min_value=1.0,
                value=float(default_shares),
                step=1.0,
                key=f"sv_{idea.symbol}",
            )
        else:
            size_val = st.number_input(
                "Betrag €",
                min_value=1.0,
                value=default_amount,
                step=10.0,
                key=f"sv_{idea.symbol}",
            )
    with c3:
        order_type = st.selectbox(
            "Order-Typ",
            ["market", "limit", "stop"],
            key=f"ot_{idea.symbol}",
        )

    btn_key = f"prep_{idea.symbol}"
    if st.button("Order vorbereiten (Preview)", type="primary", key=btn_key):
        with st.spinner(f"Scalable Preview für {idea.symbol} …"):
            amount = size_val if size_mode == "amount" else None
            shares = size_val if size_mode == "shares" else float(default_shares)
            result, isin, cmd = sc.prepare_order_from_idea(
                symbol=idea.symbol,
                side=idea.side,
                shares=shares,
                amount=amount,
                isin_map=ISIN_MAP,
                order_type=order_type,
            )
            st.session_state[f"prep_result_{idea.symbol}"] = {
                "result": result,
                "isin": isin,
                "cmd": cmd,
                "symbol": idea.symbol,
                "side": idea.side,
            }

    _show_prepared_order(f"prep_result_{idea.symbol}")


def render_scalable_tab() -> None:
    st.subheader("Scalable Broker (CLI)")
    st.caption(
        "Liest Portfolio & Kurse über die offizielle `sc`-CLI. "
        "Trades: nur Preview (Phase 1). Ausführung bleibt manuell im Terminal."
    )

    if not sc.sc_available():
        st.error(
            "`sc` ist nicht installiert oder nicht im PATH.\n\n"
            "Auf dem Mac:\n"
            "```\n"
            "brew tap ScalableCapital/tap\n"
            "brew trust --formula ScalableCapital/tap/scalable-cli\n"
            "brew install scalable-cli\n"
            "sc login\n"
            "```\n"
            "Agentic Investing im Scalable-Web unter Profil → Security aktivieren."
        )
        return

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("Whoami", use_container_width=True):
            st.session_state["sc_last"] = sc.whoami()
    with col_b:
        if st.button("Overview", use_container_width=True):
            st.session_state["sc_last"] = sc.overview()
    with col_c:
        if st.button("Holdings", use_container_width=True):
            st.session_state["sc_last"] = sc.holdings()

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Transactions", use_container_width=True):
            st.session_state["sc_last"] = sc.transactions()
    with c2:
        if st.button("Overnight", use_container_width=True):
            st.session_state["sc_last"] = sc.overnight()

    st.divider()
    st.markdown("**Quote / Suche**")
    qcol1, qcol2 = st.columns([2, 1])
    with qcol1:
        isin_in = st.text_input("ISIN für Quote", placeholder="US0378331005")
    with qcol2:
        if st.button("Quote laden", use_container_width=True) and isin_in.strip():
            st.session_state["sc_last"] = sc.quote(isin_in)

    search_q = st.text_input("Suche (Name/Ticker)", placeholder="apple")
    if st.button("Suchen") and search_q.strip():
        st.session_state["sc_last"] = sc.search(search_q)

    st.divider()
    st.markdown("**Trade-Preview manuell (Phase 1)**")
    st.info(
        "Oder direkt aus dem Scan-Tab bei einer Idee: **Order vorbereiten**. "
        "Phase 2 immer selbst im Terminal bestätigen."
    )
    t1, t2, t3, t4 = st.columns(4)
    with t1:
        side = st.selectbox("Seite", ["buy", "sell"], key="man_side")
    with t2:
        trade_isin = st.text_input("ISIN", key="trade_isin", placeholder="US0378331005")
    with t3:
        size_mode = st.selectbox("Größe", ["amount", "shares"], key="man_size")
    with t4:
        size_val = st.number_input("Wert", min_value=1.0, value=100.0, step=1.0, key="man_val")

    if st.button("Preview erzeugen", type="primary", key="man_preview"):
        kwargs = {"amount": size_val} if size_mode == "amount" else {"shares": size_val}
        result = sc.trade_preview(side, trade_isin, **kwargs)
        cid = sc.extract_confirmation_id(result.data) if result.ok else None
        cmd = None
        if result.ok and cid:
            cmd = sc.build_confirm_command(
                side,
                trade_isin,
                cid,
                amount=kwargs.get("amount"),
                shares=kwargs.get("shares"),
            )
        st.session_state["sc_last"] = result
        st.session_state["sc_confirm_cmd"] = cmd

    last: sc.ScalableResult | None = st.session_state.get("sc_last")
    if last is None:
        st.caption("Noch kein Abruf – Buttons oben nutzen.")
        return

    if not last.ok:
        st.error(last.error or "Unbekannter Fehler")
        if last.raw:
            with st.expander("Rohausgabe"):
                st.code(last.raw)
        return

    st.success("OK")
    cmd = st.session_state.get("sc_confirm_cmd")
    if cmd:
        st.markdown("**Zum Bestätigen im Terminal:**")
        st.code(cmd, language="bash")

    table = _json_table(last.data)
    if table is not None and not table.empty:
        st.dataframe(table, use_container_width=True, hide_index=True)
    else:
        st.json(last.data if last.data is not None else last.raw)


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
    st.caption(
        "Multi-Timeframe · VWAP/Opening-Range · Marktregime · Journal · Scalable Order-Preview"
    )
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

        st.divider()
        st.caption("Scalable CLI")
        if sc.sc_available():
            st.success("`sc` gefunden")
        else:
            st.warning("`sc` fehlt – siehe Tab Scalable")

    symbols = list(CONFIG["universe"])
    if use_de:
        symbols.extend(CONFIG.get("de_universe", []))
    if extra.strip():
        symbols.extend([s.strip().upper() for s in extra.split(",") if s.strip()])
    symbols = list(dict.fromkeys(symbols))

    tabs = st.tabs(["Scan", "Journal", "Scalable", "Methode"])

    with tabs[3]:
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

            ### Scalable Order-Flow
            1. Scan → Idee öffnen → **Order vorbereiten (Preview)**
            2. App holt Phase-1 bei Scalable (Kosten, Warnungen, confirmation_id)
            3. Du kopierst den angezeigten `sc … --confirm <ID>` Befehl ins Terminal
            4. Erst dann wird die Order wirklich platziert
            """
        )

    with tabs[2]:
        render_scalable_tab()

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

                    bj1, bj2 = st.columns(2)
                    with bj1:
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

                    render_order_prepare_block(idea)

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

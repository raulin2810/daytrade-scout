# Daytrade Scout

Lokale Mac-App: Watchlist scannen (Mid-Caps + selektive Large), Ideen mit
Entry/Stop/Zielen, Qualitäts-Score, Paper-Journal und **Scalable Order-Preview**.

**Keine Finanzberatung.** Confluence und Quality-Score sind Filter – keine
Gewinn-Garantie. Daytrading kann Kapital vernichten.

Repo: https://github.com/raulin2810/daytrade-scout

## Für ~4 000 € Konto

- Standard-Kapital: **4000**
- Universum: **Mid-Caps** (SOFI, HOOD, RIVN, PLTR, …) statt nur Big Caps
- Max. **25 %** Kapital pro Position
- Cash-Check über Scalable vor Order-Preview
- Big Caps optional per Checkbox

## Qualität der Setups (ehrlich)

Die App „sagt nicht die Zukunft voraus“. Sie filtert strenger:

- Multi-Timeframe + VWAP/ORB
- Relativstärke vs **SPY und IWM** (Mid-Cap-Momentum)
- Overnight-Gap-Filter
- Intraday-RVOL + 15m-Bias
- Earnings-Fenster abstrafen
- **Quality-Score** (0–100) neben Note A/B/C

Mehr Filter ≠ höhere Trefferquote garantiert – aber weniger Müll-Setups.

## Start

```bash
cd daytrade-scout
git pull
chmod +x start.sh start.command
./start.sh
```

Browser: http://localhost:8501

## Scalable

```bash
brew tap ScalableCapital/tap
brew install scalable-cli
# Web: Profil → Security → Agentic Investing
sc login
```

1. Scan → Idee → **Order vorbereiten** (Cash-limitiert)
2. Preview prüfen
3. Checkbox + **Order bestätigen** (Phase 2) **oder** Terminal-Befehl kopieren

## Grenzen

Yahoo kann verzögert sein. Stops schützen nicht vor Gaps. Siehe DISCLAIMER.md.

# Daytrade Scout

Lokale Mac-App: Watchlist scannen, Marktumfeld lesen, drei Zeitrahmen
prüfen, daraus **Ideen zum Selbstprüfen** bauen – mit Entry, Stop, zwei
Zielen, Stückzahl und Paper-Journal.

**Keine Finanzberatung.** Präziser = mehr Filter und klarere Invalidierung,
nicht hellsehen. Niemand durchsucht „das ganze Internet“ und sagt dir
zuverlässig, was du heute kaufen sollst.

Repo: https://github.com/raulin2810/daytrade-scout

## Neu in dieser Version

- Marktregime aus **SPY / QQQ / IWM / VIX**
- Multi-Timeframe: Tag + 1h + 15m
- **VWAP**, Opening Range, Swings
- Relativstärke gegen SPY
- Earnings-Warnung (5 Tage)
- Note A/B/C statt jeder Idee
- WAIT-Setup: nicht hinterherlaufen
- Stop aus ATR **und** Struktur
- Zwei Ziele (1,5R / 2,5R)
- Batch-Download (schneller)
- Optionale DE-Watchlist
- Paper-Journal + CSV-Export
- Chart mit Entry/Stop/VWAP/OR
- **Scalable CLI**: Portfolio, Holdings, Quotes, Trade-Preview (Phase 1)

## Start auf dem Mac

```bash
git clone https://github.com/raulin2810/daytrade-scout.git
cd daytrade-scout
chmod +x start.command start.sh
./start.sh
```

Oder `start.command` im Finder doppelklicken. Browser: http://localhost:8501

Falls das Repo schon existiert:

```bash
cd daytrade-scout
git pull
./start.sh
```

```bash
xattr -d com.apple.quarantine start.command start.sh
```

Python 3 wird gebraucht. Erster Start installiert die Pakete.

## Scalable Broker anbinden (optional)

1. CLI installieren:

```bash
brew tap ScalableCapital/tap
brew trust --formula ScalableCapital/tap/scalable-cli
brew install scalable-cli
```

2. Im **Browser** (Scalable Web): Profil → Security → **Agentic Investing** aktivieren.

3. Einloggen:

```bash
sc login
sc whoami
```

4. App starten → Tab **Scalable**.

Dort kannst du Overview, Holdings, Transactions, Overnight, Quote und Suche abrufen.
**Trade-Preview (Phase 1)** erzeugt nur die Bestätigungs-ID – echte Orders (Phase 2)
bleiben absichtlich deaktiviert. Ausführung manuell im Terminal:

```bash
sc broker trade buy --isin US0378331005 --amount 100 --order-type market --confirm <ID>
```

Fork der CLI (falls du sie lokal anpassen willst):
https://github.com/raulin2810/scalable-cli

## Nutzung

1. Kapital und Risiko einstellen (Standard 0,5 %).
2. Optional deutsche Titel aktivieren.
3. **Scan starten**.
4. Nur A/B ansehen, Playbook lesen, Invalidierung setzen.
5. Idee ins Journal legen, wenn du sie wirklich handelst (Paper zählt).
6. Optional: Tab **Scalable** für dein echtes Broker-Konto.

Am Wochenende ist der Scan ein **Plan für die nächste US-Session**,
kein Live-Daytrade.

## Grenzen

Yahoo-Daten können verzögert sein. Stops schützen nicht vor Gaps.
Daytrading kann das Kapital vernichten. Siehe [DISCLAIMER.md](DISCLAIMER.md).
Scalable-Orders erfordern immer deine explizite Bestätigung (Two-Step).

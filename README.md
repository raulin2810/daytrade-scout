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
- **Scalable CLI**: Portfolio, Holdings, Quotes
- **Order vorbereiten** aus Scan-Idee (Phase 1) → du bestätigst nur im Terminal

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

## Scalable: Idee → Order vorbereiten → selbst bestätigen

### 1. CLI installieren & einloggen

```bash
brew tap ScalableCapital/tap
brew trust --formula ScalableCapital/tap/scalable-cli
brew install scalable-cli
```

Im **Browser**: Profil → Security → **Agentic Investing** aktivieren, dann:

```bash
sc login
sc whoami
```

### 2. In der App

1. **Scan starten**
2. Idee öffnen (z. B. Note A)
3. Unten: **Order vorbereiten (Preview)**
4. App löst ISIN auf, ruft Scalable Phase 1 auf und zeigt den fertigen Befehl:

```bash
sc broker trade buy --isin US0378331005 --order-type market --shares 2 --confirm <ID>
```

5. Befehl **kopieren und im Terminal ausführen** – erst dann wird die Order platziert.

Die App führt **keine** Phase-2-Orders aus. confirmation_id ist zeitlich begrenzt.

ISINs stehen in `config.yaml` unter `isin_map` (bei Bedarf ergänzen).

Fork der CLI: https://github.com/raulin2810/scalable-cli

## Nutzung

1. Kapital und Risiko einstellen (Standard 0,5 %).
2. Optional deutsche Titel aktivieren.
3. **Scan starten**.
4. Nur A/B ansehen, Playbook lesen, Invalidierung setzen.
5. Idee ins Journal legen und/oder Order vorbereiten.
6. Optional: Tab **Scalable** für Portfolio & manuelle Previews.

Am Wochenende ist der Scan ein **Plan für die nächste US-Session**,
kein Live-Daytrade.

## Grenzen

Yahoo-Daten können verzögert sein. Stops schützen nicht vor Gaps.
Daytrading kann das Kapital vernichten. Siehe [DISCLAIMER.md](DISCLAIMER.md).
Scalable-Orders erfordern immer deine explizite Bestätigung (Two-Step).

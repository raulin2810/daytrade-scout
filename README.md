# Daytrade Scout

Lokale App für den Mac: Watchlist scannen, Schlagzeilen holen, technische
Filter rechnen, daraus **Ideen zum Selbstprüfen** machen – inklusive
Beispiel für Einstieg, Stop-Loss, Ziel und Stückzahl.

**Das ist keine Finanzberatung und kein fertiger Gelddruckautomat.**
Niemand kann „das ganze Internet“ in Echtzeit auswerten und daraus
zuverlässig sagen, welche Aktie du heute kaufen und wann du verkaufen
sollst. Wer das verspricht, lügt. Diese App macht das bewusst nicht.

Repo: https://github.com/raulin2810/daytrade-scout

## Was du bekommst

- Ein-Klick-Start auf dem Mac (`start.command`)
- Watchlist liquider US-Titel (in `config.yaml` änderbar, auch `SAP.DE` usw.)
- Kurse über Yahoo Finance (`yfinance`)
- Schlagzeilen über Yahoo News + Google News RSS
- Score aus EMA, RSI, MACD, Volumen, einfacher Nachrichten-Wortliste
- Stop = aktueller Kurs ± 1,5 × ATR (einstellbar)
- Ziel = 2R (einstellbar)
- Positionsgröße aus deinem Kapital und Risiko pro Idee (Standard 0,5 %)
- Candlestick-Chart je Idee
- Läuft nur lokal, keine Broker-Anbindung, keine automatischen Orders

## Was du nicht bekommst

- Keine Garantie, keinen nachweisbaren Edge
- Kein Crawling „des ganzen Internets“
- Keine Live-Millisekunden-Daten wie bei einem Profi-Terminal
- Keine Steuer- oder Rechtsberatung

Daytrading ist hochspekulativ. Ein Stop-Loss schützt nicht vor Gaps
(Kurslücken über Nacht oder nach Zahlen).

## Mac: so startest du

1. [Python 3](https://www.python.org/downloads/) installieren, falls nicht vorhanden.
   Im Terminal prüfen: `python3 --version`
2. Repo holen:

```bash
git clone https://github.com/raulin2810/daytrade-scout.git
cd daytrade-scout
chmod +x start.command start.sh
```

3. `start.command` im Finder doppelklicken
   **oder** im Terminal:

```bash
./start.sh
```

4. Browser öffnet (oder du gehst auf) http://localhost:8501
5. Kapital eintragen → **Heute scannen**

Beim ersten Start legt das Skript ein virtuelles Environment an und
installiert die Pakete aus `requirements.txt`. Das dauert eine Minute.

### Falls macOS „unbekanntes Skript“ blockiert

```bash
xattr -d com.apple.quarantine start.command start.sh
chmod +x start.command start.sh
```

## Täglich nutzen

Es gibt keinen Server in der Cloud. „Täglich“ heißt: du startest die App
morgens (am besten vor oder kurz nach US-Open, 15:30 Uhr MESZ / 9:30 ET)
und klickst auf Scannen.

Wenn du eine Erinnerung willst, reicht ein Kalendereintrag oder
`launchd` – die App selbst führt keine Trades aus.

## Watchlist anpassen

Datei `config.yaml` öffnen und Ticker ergänzen. Yahoo-Syntax:

- USA: `AAPL`, `NVDA`
- Deutschland: `SAP.DE`, `VOW3.DE`
- ETF: `SPY`, `QQQ`

## Limits der Datenquelle

`yfinance` nutzt inoffizielle Yahoo-Schnittstellen. Die können
raten-limitieren oder zeitweise leer antworten. Für echtes Live-Trading
brauchst du einen Broker mit eigener Marktdaten-API.

## Haftungsausschluss

Siehe [DISCLAIMER.md](DISCLAIMER.md). Nutzung auf eigenes Risiko.
MIT-Lizenz, siehe [LICENSE](LICENSE).

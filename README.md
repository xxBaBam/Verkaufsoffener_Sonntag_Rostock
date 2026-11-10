# Verkaufsoffene Sonntage Rostock

Ein Kalender-Abo (ICS) mit allen angekündigten verkaufsoffenen Sonntagen in Rostock – mit Uhrzeit und Anlass.
Aktualisiert sich täglich von selbst.

**Seite zum Abonnieren (iPhone, Android, PC):** https://xxbabam.github.io/Verkaufsoffener_Sonntag_Rostock/

Abo-Adresse: `https://xxbabam.github.io/Verkaufsoffener_Sonntag_Rostock/sonntage.ics`

## Wie es funktioniert

- Die Hansestadt Rostock veröffentlicht keine maschinenlesbare Terminliste. Deshalb werden täglich mehrere
  Termin-Portale abgefragt: verkaufsoffener-sonntag.nrw, sonntagsoffen.de, verkaufsoffener-sonntag.com,
  offline-einkaufen.com, opensunday.de und kaufsonntag.de.
- **Abgleich:** Ein Termin gilt als bestätigt, wenn ihn mindestens zwei Portale nennen. Nennt ihn nur eines, steht er
  mit „(unbestätigt)“ im Kalender. Uhrzeit = häufigste Angabe, abweichende Angaben stehen in der Beschreibung.
  Den Anlass (z. B. „Ostermarkt“, „Weihnachtsmarkt – 1. Advent“) liefert das Portal mit den besten Angaben.
- Nachbarorte (z. B. Bentwisch) und die saisonale Sonntagsöffnung nach Bäderregelung (Warnemünde, Markgrafenheide)
  werden herausgefiltert.
- Alle Termine werden in `daten/sonntage.json` gesammelt. **Vergangene Termine werden nie gelöscht.** Ein künftiger
  Termin wird nur entfernt, wenn ihn keine Quelle mehr nennt (und mindestens zwei Quellen erreichbar waren).
- Einmal im Monat ändert sich `daten/letzte-pruefung.txt`, damit GitHub den Zeitplan nicht nach 60 Tagen ohne
  Aktivität abschaltet.
- Ist keine oder nur eine Quelle erreichbar, bleibt der alte Kalender erhalten und der Workflow schlägt fehl
  (GitHub schickt eine E-Mail).

## Kosten

Keine: Für öffentliche Repos sind GitHub Actions (Standard-Runner) und GitHub Pages kostenlos und zählen nicht gegen
das Freikontingent.

`debug/`, `scripts/explore.py` und der Workflow „Erkundung (manuell)“ dienen nur der Fehlersuche bzw. zum Prüfen
neuer Quellen.

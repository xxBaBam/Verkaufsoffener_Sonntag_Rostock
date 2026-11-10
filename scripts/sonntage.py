"""Kalender "Verkaufsoffene Sonntage Rostock" (ICS-Abo).

Die Hansestadt Rostock veroeffentlicht keine maschinenlesbare Terminliste. Deshalb werden mehrere Termin-Portale
abgefragt und gegeneinander abgeglichen:
- ein Termin gilt als bestaetigt, wenn ihn mindestens zwei Portale nennen;
  nennt ihn nur eines, steht er mit dem Hinweis "nur eine Quelle" im Kalender;
- Uhrzeit = haeufigste Angabe, abweichende Angaben stehen in der Beschreibung;
- Nachbarorte (z. B. Bentwisch) und die saisonale Sonntagsoeffnung nach Baederregelung werden herausgefiltert.

Alle Termine werden in daten/sonntage.json gesammelt; vergangene werden nie geloescht. Ein kuenftiger Termin wird nur
entfernt, wenn ihn keine Quelle mehr nennt und mindestens zwei Quellen erfolgreich abgerufen wurden.
Ausgabe: docs/sonntage.ics und docs/index.html. Nur Python-Standardbibliothek.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "daten"
OUT = ROOT / "docs"
FILE = DATA / "sonntage.json"
KEEPALIVE_FILE = DATA / "letzte-pruefung.txt"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
TZ = ZoneInfo("Europe/Berlin")
MONATE = {m: i for i, m in enumerate(["januar", "februar", "märz", "april", "mai", "juni", "juli", "august",
                                      "september", "oktober", "november", "dezember"], 1)}
NACHBARORTE = re.compile(r"Bentwisch|Sievershagen|Lambrechtshagen|Roggentin|Kritzmow|Broderstorf|Bäder|saisonal", re.I)

SOURCES = {
    "verkaufsoffener-sonntag.nrw": "https://www.verkaufsoffener-sonntag.nrw/mecklenburg-vorpommern/rostock/",
    "sonntagsoffen.de": "https://www.sonntagsoffen.de/rostock/",
    "verkaufsoffener-sonntag.com": "https://www.verkaufsoffener-sonntag.com/in/rostock/",
    "offline-einkaufen.com": "https://www.offline-einkaufen.com/mv/verkaufsoffener-sonntag-rostock.html",
    "opensunday.de": "https://www.opensunday.de/verkaufsoffene-sonntage/mecklenburg-vorpommern/rostock",
    "kaufsonntag.de": "https://www.kaufsonntag.de/mecklenburg-vorpommern/rostock/",
}


class FetchError(Exception):
    pass


def http_get(url: str) -> str:
    last = None
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "de"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            if isinstance(e, urllib.error.HTTPError) and e.code == 404:
                break
    raise FetchError(f"{url}: {last}")


def text(h: str) -> str:
    h = re.sub(r"<script(?![^>]*ld\+json).*?</script>|<style.*?</style>", " ", h, flags=re.S)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", h)).replace("\u00a0", " ").replace("\u00ad", "").split())


def ldjson_events(h: str) -> list[dict]:
    out = []
    for raw in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', h, re.S):
        try:
            d = json.loads(raw)
        except ValueError:
            continue
        for e in d if isinstance(d, list) else [d]:
            if isinstance(e, dict) and e.get("@type") == "Event" and e.get("startDate"):
                out.append(e)
    return out


def _date(s: str) -> dt.date | None:
    s = s.strip().lower()
    if m := re.fullmatch(r"(\d{1,2})\.\s?(\d{1,2})\.\s?(20\d{2})", s):
        return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    if m := re.fullmatch(r"(\d{1,2})\.\s?([a-zä]+)\s(20\d{2})", s):
        if m.group(2) in MONATE:
            return dt.date(int(m.group(3)), MONATE[m.group(2)], int(m.group(1)))
    return None


def _time(s: str) -> str:
    h, m = re.split(r"[:.]", s)
    return f"{int(h):02d}:{m}"


DATE = r"(\d{1,2}\.\s?\d{1,2}\.\s?20\d{2}|\d{1,2}\.\s?(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s20\d{2})"
TIME = r"(\d{1,2}[:.]\d{2})"


def hit(d: dt.date | None, von: str | None, bis: str | None, anlass: str = "") -> dict | None:
    if not d or d.weekday() != 6:  # nur Sonntage
        return None
    return {"datum": d.isoformat(), "von": _time(von) if von else None, "bis": _time(bis) if bis else None,
            "anlass": " ".join(anlass.split()).strip(" -–,.")}


# ------------------------------------------------------------------ Parser je Quelle

def p_nrw(h: str) -> list[dict]:
    out = []
    for e in ldjson_events(h):
        d = dt.date.fromisoformat(e["startDate"][:10])
        anlass = (e.get("description") or "").split(" - ", 1)[1] if " - " in (e.get("description") or "") else ""
        out.append(hit(d, e["startDate"][11:16] or None, (e.get("endDate") or "")[11:16] or None, anlass))
    return out


def p_sonntagsoffen(h: str) -> list[dict]:
    # Die Zeitangabe "+0000" auf der Seite ist falsch gesetzt; gemeint ist Ortszeit.
    return [hit(dt.date.fromisoformat(e["startDate"][:10]), e["startDate"][11:16] or None,
                (e.get("endDate") or "")[11:16] or None) for e in ldjson_events(h)]


def p_vsc(h: str) -> list[dict]:
    t = text(h)
    return [hit(_date(d), a, b, anl) for d, anl, a, b in
            re.findall(r"Verkaufsoffener Sonntag in Rostock am " + DATE + r"\s+(.{0,120}?),?\s+von " + TIME + r" bis " + TIME, t)]


def p_offline(h: str) -> list[dict]:
    t = text(h)
    out = [hit(_date(d), a, b, anl) for d, anl, a, b in
           re.findall(r"findet am " + DATE + r"\s*\(([^)]*)\)\s*statt\..{0,80}?von " + TIME + r" bis " + TIME, t)]
    return out


def p_opensunday(h: str) -> list[dict]:
    t = text(h)
    return [hit(_date(d), a, b, anl) for d, a, b, anl in
            re.findall(DATE + r" Rostock " + TIME + r"\s*[–-]\s*" + TIME + r" Uhr\s+(.{0,80}?)\s+Mecklenburg-Vorpommern", t)]


def p_kaufsonntag(h: str) -> list[dict]:
    t = text(h)
    out = []
    for d, a, b, rest in re.findall(r"Datum " + DATE + r" Uhrzeit " + TIME + r" bis " + TIME + r" Uhr Anlass (.{0,160}?) Mehr Infos", t):
        if NACHBARORTE.search(rest):
            continue
        anlass = re.sub(r"\s*Ort .*$", "", rest)
        out.append(hit(_date(d), a, b, "" if anlass.lower().startswith("rostock") else anlass))
    return out


PARSERS = {"verkaufsoffener-sonntag.nrw": p_nrw, "sonntagsoffen.de": p_sonntagsoffen,
           "verkaufsoffener-sonntag.com": p_vsc, "offline-einkaufen.com": p_offline,
           "opensunday.de": p_opensunday, "kaufsonntag.de": p_kaufsonntag}


# ------------------------------------------------------------------ Abgleich

def collect() -> tuple[dict, int]:
    found: dict[str, list[tuple[str, dict]]] = {}
    ok = 0
    for name, url in SOURCES.items():
        try:
            hits = [x for x in PARSERS[name](http_get(url)) if x]
        except FetchError as e:
            print(f"::warning::{name} nicht abrufbar: {e}")
            continue
        ok += 1
        print(f"{name}: {sorted({x['datum'] for x in hits})}")
        for x in hits:
            if not any(src == name for src, _ in found.get(x["datum"], [])):
                found.setdefault(x["datum"], []).append((name, x))
    result = {}
    for datum, lst in found.items():
        times = Counter((x["von"], x["bis"]) for _, x in lst if x["von"] and x["bis"])
        (von, bis), _ = times.most_common(1)[0] if times else ((None, None), 0)
        andere = sorted({f"{a}–{b}" for (a, b) in times if (a, b) != (von, bis)})
        # Anlass: nach Qualitaet der Quelle (Reihenfolge in SOURCES), allgemeine Floskeln ueberspringen
        rang = list(SOURCES)
        anlaesse = [x["anlass"] for src, x in sorted(lst, key=lambda sx: rang.index(sx[0]))
                    if x["anlass"] and not re.match(r"(?i)verkaufsoffen|sonntags", x["anlass"])]
        anlass = anlaesse[0] if anlaesse else ""
        result[datum] = {"von": von, "bis": bis, "andere_zeiten": andere, "anlass": anlass,
                         "quellen": sorted(src for src, _ in lst)}
    return result, ok


def merge(old: dict, new: dict, ok: int, today: dt.date) -> tuple[dict, list[str]]:
    notes, merged = [], {}
    for d, e in old.items():
        if d in new:
            continue
        if dt.date.fromisoformat(d) >= today and ok >= 2:
            notes.append(f"entfernt (von keiner Quelle mehr genannt): {d}")
            continue
        merged[d] = e  # Vergangenheit wird nie geloescht
    for d, e in new.items():
        if d not in old:
            notes.append(f"neu: {d} {e['anlass']} ({len(e['quellen'])} Quellen)")
        elif old[d] != e:
            # Quellen fuer vergangene Termine verschwinden oft – dann alte (vollstaendigere) Angaben behalten
            if dt.date.fromisoformat(d) < today and len(e["quellen"]) < len(old[d]["quellen"]):
                e = old[d]
            else:
                notes.append(f"geaendert: {d}")
        merged[d] = e
    return dict(sorted(merged.items())), notes


# ------------------------------------------------------------------ Ausgabe

def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def fold(line: str) -> str:
    out, b = [], line.encode("utf-8")
    while len(b) > 74:
        cut = 74
        while (b[cut] & 0xC0) == 0x80:
            cut -= 1
        out.append(b[:cut].decode())
        b = b[cut:]
    out.append(b.decode())
    return "\r\n ".join(out)


def title(e: dict) -> str:
    t = "🛍️ Verkaufsoffener Sonntag Rostock"
    if e["anlass"]:
        t += f" – {e['anlass']}"
    if len(e["quellen"]) < 2:
        t += " (unbestätigt)"
    return t


def description(e: dict) -> str:
    lines = []
    if e["von"]:
        lines.append(f"Geöffnet: {e['von']}–{e['bis']} Uhr (teilnehmende Geschäfte, v. a. Innenstadt)")
    if e["andere_zeiten"]:
        lines.append("Abweichende Angaben: " + ", ".join(e["andere_zeiten"]) + " Uhr (z. B. einzelne Center)")
    if e["anlass"]:
        lines.append(f"Anlass: {e['anlass']}")
    lines += ["", "Die Teilnahme ist freiwillig – nicht alle Geschäfte haben geöffnet."]
    if len(e["quellen"]) < 2:
        lines.append("Achtung: Dieser Termin wird nur von einer Quelle genannt.")
    lines += ["", "Quellen: " + ", ".join(e["quellen"]), "Angaben ohne Gewähr."]
    return "\n".join(lines)


def render_ics(events: dict) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//verkaufsoffener-sonntag-rostock//DE", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", "X-WR-CALNAME:Verkaufsoffene Sonntage Rostock", "X-WR-TIMEZONE:Europe/Berlin",
             "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H"]
    for d, e in events.items():
        day = dt.date.fromisoformat(d)
        lines += ["BEGIN:VEVENT", f"UID:{day:%Y%m%d}@verkaufsoffener-sonntag-rostock", "DTSTAMP:20260101T000000Z"]
        if e["von"] and e["bis"]:
            s = dt.datetime.combine(day, dt.time.fromisoformat(e["von"]), TZ).astimezone(dt.timezone.utc)
            en = dt.datetime.combine(day, dt.time.fromisoformat(e["bis"]), TZ).astimezone(dt.timezone.utc)
            lines += [f"DTSTART:{s:%Y%m%dT%H%M%SZ}", f"DTEND:{en:%Y%m%dT%H%M%SZ}"]
        else:
            lines += [f"DTSTART;VALUE=DATE:{day:%Y%m%d}", f"DTEND;VALUE=DATE:{day + dt.timedelta(days=1):%Y%m%d}"]
        lines += [f"SUMMARY:{esc(title(e))}", "LOCATION:Rostock\\, Innenstadt", f"DESCRIPTION:{esc(description(e))}",
                  "TRANSP:TRANSPARENT", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(x) for x in lines) + "\r\n"


PAGE = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Verkaufsoffene Sonntage Rostock</title>
<style>
  :root {{ --bg:#fff; --fg:#1d1d1f; --muted:#666; --box:#f3f4f6; --line:#e3e5e8; --btn:#7a3fb0; --g:#1a73e8; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg:#111; --fg:#eee; --muted:#aaa; --box:#222; --line:#333; --btn:#9a62d1; --g:#4c8df6; }} }}
  body {{ background:var(--bg); color:var(--fg); font:17px/1.5 system-ui,-apple-system,sans-serif; max-width:40rem; margin:1.5rem auto; padding:0 16px; }}
  h1 {{ font-size:1.6rem; margin-bottom:.25rem; }}
  .btn {{ display:block; text-align:center; text-decoration:none; color:#fff; background:var(--btn); padding:1rem; border-radius:12px; font-weight:600; margin:.75rem 0; }}
  .btn.g {{ background:var(--g); }}
  .box {{ background:var(--box); padding:.75rem 1rem; border-radius:12px; margin:1rem 0; }}
  code {{ word-break:break-all; font-size:.9rem; }}
  small, .muted {{ color:var(--muted); }}
  .list {{ list-style:none; padding:0; }}
  .list li {{ border-bottom:1px solid var(--line); padding:.6rem 0; }}
  .list .top {{ font-weight:600; }}
  .list .sub {{ font-size:.9rem; color:var(--muted); }}
</style>
</head>
<body>
<h1>Verkaufsoffene Sonntage in Rostock</h1>
<p>Alle angekündigten Shopping-Sonntage in Rostock als Kalender – mit Uhrzeit und Anlass. Die Termine werden täglich
aus mehreren Termin-Portalen abgeglichen; neue Termine kommen von selbst dazu.</p>

<h2>Abonnieren</h2>
<a class="btn" id="ios" href="sonntage.ics">iPhone / iPad / Mac: Abonnieren</a>
<a class="btn g" id="google" href="https://calendar.google.com/">Android / Google Kalender: Abonnieren</a>
<div class="box">
<small><strong>iPhone:</strong> „Abonnieren“ → „Hinzufügen“. Für iPhone <em>und</em> iPad: Kalender-App → „Kalender“ → „Kalender hinzufügen“ → „Kalenderabo hinzufügen“ → Adresse unten eingeben → bei „Account“ iCloud wählen.<br>
<strong>Google:</strong> Knopf antippen und „Hinzufügen“. Öffnet sich nur die App: im Chrome-Menü „Desktopwebsite“ einschalten oder am PC über calendar.google.com → „Weitere Kalender“ → „+“ → „Per URL“.</small>
</div>
<p>Abo-Adresse:</p>
<div class="box"><code id="url"></code></div>

<h2>Die nächsten Termine</h2>
<ul class="list">
{rows}
</ul>
<div class="box"><small><strong>Warnemünde und Markgrafenheide:</strong> Dort dürfen Geschäfte nach der Bäderregelung
in der Saison ohnehin sonntags öffnen – diese allgemeine Sonntagsöffnung ist hier nicht einzeln eingetragen.</small></div>
<p><small>Angaben ohne Gewähr. Die Teilnahme ist für Geschäfte freiwillig. Quellen: {quellen}.</small></p>
<script>
  var url = location.href.replace(/[?#].*$/, "").replace(/[^/]*$/, "") + "sonntage.ics";
  var webcal = url.replace(/^https?:/, "webcal:");
  document.getElementById("url").textContent = url;
  document.getElementById("ios").href = webcal;
  document.getElementById("google").href = "https://calendar.google.com/calendar/render?cid=" + encodeURIComponent(webcal);
</script>
</body>
</html>
"""
WD = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def render_page(events: dict, today: dt.date) -> str:
    rows = []
    for d, e in events.items():
        day = dt.date.fromisoformat(d)
        if day < today:
            continue
        zeit = f"{e['von']}–{e['bis']} Uhr" if e["von"] else "Uhrzeit noch offen"
        bestaetigt = f"{len(e['quellen'])} Quellen" if len(e["quellen"]) > 1 else "nur 1 Quelle (unbestätigt)"
        rows.append(f'<li><div class="top">{WD[day.weekday()]} {day:%d.%m.%Y}'
                    f'{" – " + html.escape(e["anlass"]) if e["anlass"] else ""}</div>'
                    f'<div class="sub">{zeit} · {bestaetigt}</div></li>')
    if not rows:
        rows.append('<li class="muted">Derzeit sind keine weiteren Termine angekündigt. '
                    'Neue Termine erscheinen automatisch, sobald sie veröffentlicht werden.</li>')
    return PAGE.format(rows="\n".join(rows), quellen=", ".join(SOURCES))


def main() -> int:
    today = dt.date.fromisoformat(os.environ["TODAY"]) if os.environ.get("TODAY") else dt.datetime.now(TZ).date()
    old = json.loads(FILE.read_text(encoding="utf-8")) if FILE.exists() else {}
    new, ok = collect()
    if ok == 0 or (not new and not old):
        print("::error::Keine Quelle lieferte Termine – bisheriger Kalender bleibt erhalten")
        return 1
    events, notes = merge(old, new, ok, today)
    for n in notes:
        print(n)
    print(f"{ok}/{len(SOURCES)} Quellen abgerufen, {len(events)} Termine im Kalender")
    DATA.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    FILE.write_text(json.dumps(events, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    KEEPALIVE_FILE.write_text(f"{today:%Y-%m}\n", encoding="utf-8")  # monatlicher Commit gegen Abschalten
    (OUT / "sonntage.ics").write_text(render_ics(events), encoding="utf-8", newline="")
    (OUT / "index.html").write_text(render_page(events, today), encoding="utf-8")
    if ok < 2:
        print(f"::warning::Nur {ok} Quelle(n) erreichbar – Abgleich eingeschränkt")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

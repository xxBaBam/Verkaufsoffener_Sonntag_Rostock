"""Erkundung: Quellen fuer verkaufsoffene Sonntage in Rostock. Ergebnisse -> debug/"""
import json, re, urllib.parse, urllib.request, urllib.error, gzip
from pathlib import Path
OUT = Path("debug"); OUT.mkdir(exist_ok=True)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
rep = []
def log(m): print(m); rep.append(str(m))
def get(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "de"})
        with urllib.request.urlopen(req, timeout=40) as r:
            b = r.read()
            if b[:2] == b"\x1f\x8b": b = gzip.decompress(b)
            return r.status, b.decode("utf-8", "replace"), r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, "", url
    except Exception as e:
        return None, str(e)[:120], url
def text(h): return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script(?![^>]*ld\+json).*?</script>|<style.*?</style>", " ", h, flags=re.S)))
SRC = {
  "opensunday": "https://www.opensunday.de/verkaufsoffene-sonntage/mecklenburg-vorpommern/rostock",
  "sonntagsoffen": "https://www.sonntagsoffen.de/rostock/",
  "offline-einkaufen": "https://www.offline-einkaufen.com/mv/verkaufsoffener-sonntag-rostock.html",
  "kaufsonntag": "https://www.kaufsonntag.de/mecklenburg-vorpommern/rostock/",
  "verkaufsoffene-sonntage": "https://www.verkaufsoffene-sonntage.de/rostock.html",
  "vos-nrw": "https://www.verkaufsoffener-sonntag.nrw/mecklenburg-vorpommern/rostock/",
  "verkaufsoffener-sonntag-com": "https://www.verkaufsoffener-sonntag.com/mecklenburg-vorpommern/rostock/",
  "rostock-suche": "https://www.rostock.de/suche.html?q=verkaufsoffen",
  "rathaus-suche": "https://rathaus.rostock.de/de/suche?q=verkaufsoffener+Sonntag",
  "rostock-einkaufen": "https://www.rostock.de/erleben/einkaufen.html",
}
for name, url in SRC.items():
    st, h, final = get(url)
    t = text(h)
    lds = re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', h, re.S)
    events = [l for l in lds if '"Event"' in l or "Event" in l]
    dates = re.findall(r"\b(?:\d{1,2}\.\s?\d{1,2}\.\s?20\d{2}|\d{1,2}\.\s(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s20\d{2})\b", t)
    log(f"\n##### {name} {st} {len(h)}B final={final}\n  LD+JSON: {len(lds)} (Event: {len(events)}) | Datumsangaben: {len(dates)} {dates[:25]}")
    for e in events[:3]: log("  EVENT: " + re.sub(r"\s+", " ", e)[:700])
    for w in ["Uhr", "Advent", "Innenstadt", "Warnemünde", "Ostern", "Herbst"]:
        for m in list(re.finditer(w, t))[:2]: log(f"  [{w}] …{t[max(0,m.start()-150):m.start()+120]}…")
    if st == 200: (OUT / f"{name}.html").write_text(h, encoding="utf-8")
    ics = [l for l in re.findall(r'href="([^"]+)"', h) if re.search(r"\.ics|ical|webcal", l, re.I)]
    if ics: log(f"  ICS-LINKS: {ics[:5]}")
(OUT / "report.txt").write_text("\n".join(rep), encoding="utf-8")

import re, pathlib

p = pathlib.Path(r"C:\Users\Coord Planeación\.gemini\antigravity\scratch\quantbet\scratch")
# Let's check probe_nba_match logic on a cached or live NBA match page
import urllib.request
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
url = "https://apuestas.wplay.co/es/e/34102609/Milwaukee-Bucks-%40-Miami-Heat"
req = urllib.request.Request(url, headers={"User-Agent": UA})
with urllib.request.urlopen(req, timeout=12) as r:
    html = r.read().decode("utf-8", "replace")

for kw in ("Puntos totales de jugador", "Total asistencias del jugador", "Total rebotes por jugador", "Total de Puntos"):
    idx = html.find(kw)
    if idx != -1:
        print("====", kw)
        print(html[idx-100:idx+2500])

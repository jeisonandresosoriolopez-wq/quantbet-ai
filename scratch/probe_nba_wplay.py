import urllib.request, re

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
url = "https://apuestas.wplay.co/es/s/BASK/Baloncesto"
req = urllib.request.Request(url, headers={"User-Agent": UA})
try:
    with urllib.request.urlopen(req, timeout=12) as r:
        html = r.read().decode("utf-8", "replace")
    print("Wplay Baloncesto len:", len(html))
    links = sorted(set(re.findall(r'href="(/es/t/\d+/[^"]+|/es/e/\d+/[^"]+)"', html)))
    for l in links:
        if "nba" in l.lower() or "baloncesto" in l.lower():
            print("NBA link:", l)
    for m in re.finditer(r'href="(/es/e/(\d+)/[^"]+)"[^>]*>([^<]+)<', html):
        print("BASK EV:", m.group(1), m.group(3).strip())
except Exception as e:
    print("ERR:", e)

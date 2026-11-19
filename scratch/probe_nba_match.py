import urllib.request, re

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
url = "https://apuestas.wplay.co/es/e/34102609/Milwaukee-Bucks-%40-Miami-Heat"
req = urllib.request.Request(url, headers={"User-Agent": UA})
try:
    with urllib.request.urlopen(req, timeout=12) as r:
        html = r.read().decode("utf-8", "replace")
    print("NBA match HTML len:", len(html))
    headers = re.findall(r'<span[^>]*class="[^"]*mkt-name[^"]*"[^>]*>([^<]+)</span>|<h4[^>]*>([^<]+)</h4>', html)
    for h1, h2 in headers[:30]:
        t = (h1 or h2).strip()
        if t:
            print("NBA MKT:", t)
except Exception as e:
    print("ERR:", e)

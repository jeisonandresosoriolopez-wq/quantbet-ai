import urllib.request, re

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
url = "https://apuestas.wplay.co/es/t/19172/NBA"
req = urllib.request.Request(url, headers={"User-Agent": UA})
with urllib.request.urlopen(req, timeout=12) as r:
    html = r.read().decode("utf-8", "replace")

p = html.find("34102597")
if p != -1:
    print(html[max(0, p-600):p+300])

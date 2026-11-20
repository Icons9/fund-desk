"""Pre-push checks for Fund Desk data. Exit code 1 on any failure."""
import json, glob, subprocess, sys, re
bad = []
for f in glob.glob("learn/data/*.json") + glob.glob("data/root/*.json"):
    try: json.load(open(f))
    except Exception as e: bad.append(f"{f}: {e}")
n = json.load(open("learn/data/news.json"))
if not all(s.get("items") for s in n["sources"]): bad.append("news.json: a source has no items")
d = json.load(open("learn/data/deals.json"))["companies"]
if len(d) < 2500: bad.append(f"deals.json shrank to {len(d)} companies")
for c in d:
    if not c.get("n") or c.get("sig") not in list("ABCD") or not c.get("sec"): bad.append(f"deals row malformed: {c.get('n')}"); break
src = json.load(open("data/root/SRC.json"))
if len(src) < 5 or not all(s.get("items") for s in src): bad.append("data/root/SRC.json: sources or items missing")
for page in ("index.html", "learn/index.html"):
    html = open(page).read()
    js = max(re.findall(r"<script>([\s\S]*?)</script>", html), key=len)
    open("/tmp/_fd_check.js", "w").write(js)
    r = subprocess.run(["node", "--check", "/tmp/_fd_check.js"], capture_output=True, text=True)
    if r.returncode: bad.append(f"{page}: script syntax error: {r.stderr[:200]}")
print("\n".join(bad) if bad else "all checks passed")
sys.exit(1 if bad else 0)

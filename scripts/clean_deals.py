"""Normalise learn/data/deals.json: investor aliases, round dates, ids. Safe to run repeatedly."""
import json, re, sys
P = sys.argv[1] if len(sys.argv) > 1 else "learn/data/deals.json"
ALIAS = {
    "european innovation council": "EIC", "eic accelerator": "EIC", "eic": "EIC",
    "european innovation council fund": "EIC Fund", "eic fund": "EIC Fund",
    "y combinator": "Y Combinator", "yc": "Y Combinator", "y combinator (yc)": "Y Combinator",
    "european investment bank": "EIB", "eib": "EIB",
    "bpifrance": "Bpifrance", "bpi france": "Bpifrance",
    "high-tech gründerfonds": "HTGF", "high-tech grunderfonds": "HTGF", "htgf": "HTGF",
    "andreessen horowitz": "a16z", "a16z": "a16z",
    "nato diana": "NATO DIANA", "nato innovation fund": "NATO Innovation Fund",
    "innovate uk": "Innovate UK", "sequoia capital": "Sequoia", "sequoia": "Sequoia",
    "general catalyst": "General Catalyst", "lux capital": "Lux Capital",
    "israel innovation authority": "Israel Innovation Authority",
}
DROP = {"business angels", "angels", "angel investors", "undisclosed", "undisclosed investors", "others", "existing investors"}
def norm_inv(x):
    x = re.sub(r"\s+", " ", re.sub(r"\((?:lead|led|co-lead)[^)]*\)", "", x, flags=re.I)).strip(" .")
    k = x.lower()
    if k in DROP or len(k) < 2: return None
    return ALIAS.get(k, x)
d = json.load(open(P)); cs = d["companies"]
for c in cs:
    seen, inv = set(), []
    for i in c.get("inv", []):
        n = norm_inv(i)
        if n and n.lower() not in seen: seen.add(n.lower()); inv.append(n)
    c["inv"] = inv
    rd = str(c.get("rd", "") or "")
    m = re.search(r"(20\d\d|19\d\d)(?:-(\d\d))?", rd)
    c["rd"] = (m.group(1) + ("-" + m.group(2) if m.group(2) else "")) if m else ""
    for f in ("ra", "tr"):
        m = re.match(r"~?\s*([\d.]+)", str(c.get(f, "") or "")); c[f] = m.group(1) if m else ""
for i, c in enumerate(cs): c["id"] = i
json.dump(d, open(P, "w"), ensure_ascii=False, separators=(",", ":"))
print(len(cs), "companies cleaned")

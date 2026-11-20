"""Merge new research rows (DEALS_SPEC.md JSONL format) into learn/data/deals.json.

usage: python3 scripts/deals_add.py new_rows.jsonl [more.jsonl ...]
- New company (by name+sector) -> appended, ck "Not checked".
- Known company with a newer last_round_date -> round fields, signal and evidence updated.
- Rows whose signal is "X - Exclude" (acquired, listed, defunct, over ~$10bn) remove the company.
Prints a one-line summary per file. Run scripts/clean_deals.py afterwards.
"""
import json, re, sys
P = "learn/data/deals.json"
EU = {"Austria","Belgium","Bulgaria","Croatia","Cyprus","Czechia","Denmark","Estonia","Finland","France","Germany","Greece","Hungary","Ireland","Italy","Latvia","Lithuania","Luxembourg","Malta","Netherlands","Poland","Portugal","Romania","Slovakia","Slovenia","Spain","Sweden"}
WEU = {"Switzerland","Norway","Iceland","Monaco","Liechtenstein"}
ASIA = {"India","China","Japan","South Korea","Singapore","Taiwan","Hong Kong","Vietnam","Indonesia","Thailand","Malaysia","Philippines","Bangladesh","Pakistan","Sri Lanka"}
OCEANIA = {"Australia","New Zealand"}
AFRICA = {"Nigeria","Kenya","South Africa","Egypt","Ghana","Rwanda","Ethiopia","Tunisia","Morocco","Cameroon","Zimbabwe","Senegal","Uganda","Tanzania","Ivory Coast","Algeria"}
MIDEAST = {"Israel","UAE","Saudi Arabia","Qatar","Oman","Bahrain","Kuwait","Jordan","Lebanon","Turkey","Iraq"}
EM = {"China","India","South Korea","Taiwan","Indonesia","Thailand","Malaysia","Philippines","Vietnam","Brazil","Mexico","Chile","Colombia","Peru","Argentina","Saudi Arabia","UAE","Qatar","Kuwait","Egypt","South Africa","Turkey","Poland","Hungary","Greece","Czechia","Kazakhstan","Uzbekistan","Nigeria","Kenya","Morocco","Ecuador","Oman","Bahrain","Jordan","Pakistan","Bangladesh","Ghana","Rwanda","Ethiopia","Tunisia","Cameroon","Zimbabwe","Uruguay"}
FIX = {"Czech Republic":"Czechia","UK":"United Kingdom","USA":"United States","US":"United States","Korea":"South Korea","United Arab Emirates":"UAE"}
SEC = {"Healthcare":"health","Deeptech":"deeptech","AI":"ai","Aerospace":"aero","Maritime":"maritime","Defence":"defence","Defense":"defence"}
def regions(c):
    r = []
    if c in EU: r.append("eu")
    elif c == "United Kingdom": r.append("uk")
    elif c in WEU: r.append("weu")
    if c in ("United States","Canada"): r.append("usa")
    if c in ASIA: r += ["asia","apac"]
    if c in OCEANIA: r.append("apac")
    if c in AFRICA: r.append("africa")
    if c in MIDEAST: r.append("mideast")
    if c in EM and "em" not in r: r.append("em")
    return r
num = lambda x: (re.match(r"~?\s*([\d.]+)", str(x or "")) or [None, ""])[1]
key = lambda n, s: (re.sub(r"[^a-z0-9]", "", re.sub(r"\(.*?\)", "", n.lower())), s)
d = json.load(open(P)); cs = d["companies"]
idx = {key(c["n"], c["sec"]): c for c in cs}
for f in sys.argv[1:]:
    add = upd = rm = 0
    for line in open(f):
        line = line.strip()
        if not line: continue
        r = json.loads(line)
        sec = SEC.get(r.get("sector", ""))
        if not sec or not r.get("company"): continue
        k = key(r["company"], sec)
        sig = (r.get("signal") or "C")[:1].upper()
        if sig == "X":
            if k in idx: cs.remove(idx.pop(k)); rm += 1
            continue
        if sig not in "ABCD": sig = "C"
        ctry = FIX.get(r.get("country", ""), r.get("country", ""))
        row = {"n": r["company"], "c": ctry, "s": r.get("subsector", ""), "ni": r.get("niche", ""), "st": r.get("stage", "") or "Unknown",
               "sig": sig, "rt": r.get("last_round_type", ""), "ra": num(r.get("last_round_amount_eur")), "rd": r.get("last_round_date", ""),
               "tr": num(r.get("total_raised_eur_m")), "inv": [x.strip() for x in re.split(r"[,;]", r.get("key_investors", "") or "") if len(x.strip()) > 1],
               "ev": r.get("signal_evidence", ""), "ck": r.get("checked", "Not checked"), "ceo": r.get("ceo_or_founder", ""), "web": r.get("website", ""),
               "city": r.get("city", ""), "src": r.get("source_url", ""), "sec": sec, "reg": regions(ctry), "pl": r.get("product_launch", "") or ""}
        if k in idx:
            o = idx[k]
            newer = (row["rd"] or "") > (o.get("rd") or "")
            if newer or r.get("force_update"):
                for fld in ("rt", "ra", "rd", "sig", "ev", "src", "st", "ck"): o[fld] = row[fld] or o.get(fld, "")
                o["inv"] = list(dict.fromkeys(o.get("inv", []) + row["inv"]))
                upd += 1
            for fld, v in row.items():
                if not o.get(fld) and v: o[fld] = v
        else:
            cs.append(row); idx[k] = row; add += 1
    print(f"{f}: +{add} new, {upd} updated, {rm} removed")
for i, c in enumerate(cs): c["id"] = i
json.dump(d, open(P, "w"), ensure_ascii=False, separators=(",", ":"))
print("total", len(cs))

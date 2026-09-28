"""Extended portal features: family offices, signals, manager check, founder mode (find VCs),
outreach exports (HubSpot CSV, email drafts) and an MCP endpoint so Claude can query the portal."""
import csv
import io
import json
import math
import os
import re
import statistics

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response

THEME_WORDS = {
    "deep tech": ["deep", "frontier", "quantum", "robot", "hardware", "space", "semiconductor", "photonic", "fusion",
                  "autonom", "materials", "compute", "artificial intel", "defen", "industrial tech", "dual-use", "dual use"],
    "climate/energy transition": ["climate", "energy", "carbon", "sustain", "clean", "green", "decarbon", "transition", "renewable", "hydrogen"],
    "life sciences/health": ["bio", "life sci", "health", "thera", "medic", "pharma", "genom", "care"],
    "software/IT": ["software", "saas", "cloud", "digital", "data", "cyber", "enterprise"],
    "fintech": ["fintech", "financial tech", "payments", "insur"],
    "consumer": ["consumer", "brand", "retail", "food"],
    "industrials": ["industrial", "manufactur", "logistic", "mobility", "supply"],
    "impact": ["impact", "inclusive", "gender", "social", "agri", "access"],
}
FO_REGIONS = {
    "India": ["India", "Middle East", "Asia"], "Asia": ["Asia", "India"], "China": ["Asia"], "Japan": ["Asia"],
    "Middle East": ["Middle East", "India"], "Europe": ["Europe", "UK"], "UK": ["UK", "Europe"],
    "North America": ["North America"], "Global": ["Europe", "UK", "North America", "Asia", "Middle East", "India"],
    "Emerging markets": ["Middle East", "India", "Asia"], "Africa": ["Middle East", "Europe", "UK"], "Latin America": ["North America", "Europe"],
}
EUROPE = {"France", "Germany", "Luxembourg", "Ireland", "United Kingdom", "Switzerland", "Netherlands", "Sweden", "Denmark",
          "Finland", "Norway", "Spain", "Italy", "Belgium", "Austria", "Monaco", "Jersey", "Guernsey", "Portugal", "Estonia", "Poland"}
ASIA = {"Singapore", "Hong Kong", "Japan", "China", "India", "Korea, Republic of", "Taiwan", "Indonesia", "Vietnam", "Mauritius"}
BIG4 = ("pricewaterhouse", "pwc", "deloitte", "ernst", "kpmg")


def _themes_in(text, want):
    t = " " + (text or "").lower() + " "
    return [th for th in want if any(w in t for w in THEME_WORDS.get(th, []))]


def register(app, g):
    con, rows, one, paged, match = g["con"], g["rows"], g["one"], g["paged"], g["match"]
    PRIVATE = g["PRIVATE"]

    # ---------------- family offices ----------------
    @app.get("/api/family_offices")
    def family_offices(q: str = "", region: str = "", style: str = "", has_funds: int = 0, page: int = 0):
        where, p = ["1=1"], []
        if q:
            where.append("(name ILIKE ? OR principal ILIKE ? OR sectors ILIKE ? OR fund_commitments ILIKE ? OR city ILIKE ?)"); p += [f"%{q}%"] * 5
        if region:
            where.append("region = ?"); p.append(region)
        if style:
            where.append("style ILIKE ?"); p.append(f"%{style}%")
        if has_funds:
            where.append("fund_commitments IS NOT NULL")
        sql = f"""SELECT name, principal, country, city, fo_type, style, fund_commitments, sectors, stages, typical_cheque,
                  notable_directs, website, general_contact, sources, region FROM family_offices WHERE {' AND '.join(where)}"""
        res = paged(sql, p, "(fund_commitments IS NULL), name", page)
        res["available"] = "family_offices" in PRIVATE
        return res

    @app.get("/api/match_fo")
    def match_fo(strategy: str = "Venture", geography: str = "Europe", themes: str = ""):
        want = [t.strip() for t in themes.split(";") if t.strip() and t.strip() != "generalist"]
        regions = FO_REGIONS.get(geography, [geography])
        fos = rows("SELECT * FROM family_offices")
        out = []
        for f in fos:
            if f["region"] not in regions:
                continue
            geo_w = 1.0 if f["region"] == regions[0] else 0.5
            style = (f["style"] or "").lower()
            style_w = 1.4 if "fund" in style else 1.1 if "both" in style else 0.7
            funds = f["fund_commitments"] or ""
            text = " ".join(filter(None, [f["sectors"], funds, f["notable_directs"], f["notes"]]))
            hits = _themes_in(text, want) if want else []
            theme_w = 1 + 0.5 * len(hits) if want else 1.0
            vc_signal = 1.2 if re.search(r"venture|vc|seed|startup|early", text.lower()) and strategy in ("Venture", "Growth") else 1.0
            score = geo_w * style_w * theme_w * vc_signal * (1.8 if funds else 1.0)
            reasons = []
            if funds:
                reasons.append("LP in: " + funds[:160])
            if hits:
                reasons.append("themes: " + ", ".join(hits))
            if "fund" in style or "both" in style:
                reasons.append("invests through funds")
            out.append({**f, "score": round(score, 2), "reasons": reasons})
        out.sort(key=lambda x: x["score"], reverse=True)
        out = out[:60]
        top = out[0]["score"] if out else 1
        for o in out:
            o["match"] = round(100 * o["score"] / top)
        return {"available": "family_offices" in PRIVATE, "family_offices": out}

    # ---------------- signals: who is allocating now ----------------
    @app.get("/api/signals")
    def signals(days: int = 365):
        recent = rows(f"""SELECT lp, lp_type, fund_name, coalesce(manager_std, manager) manager, strategy, themes, geography,
                          date_committed, round(amount_usd_m,1) amount_usd_m, source_url
                          FROM cmx WHERE date_committed >= current_date - INTERVAL {int(days)} DAY
                          ORDER BY date_committed DESC LIMIT 200""")
        active = rows(f"""SELECT lp, any_value(lp_type) lp_type, count(*) n, round(sum(amount_usd_m)) usd_m,
                          string_agg(DISTINCT strategy, ', ') strategies, max(date_committed) latest
                          FROM cmx WHERE date_committed >= current_date - INTERVAL {int(days)} DAY OR vintage >= year(current_date) - 1
                          GROUP BY lp ORDER BY n DESC LIMIT 25""")
        themes = rows(f"""SELECT t.theme, count(*) n, round(sum(amount_usd_m)) usd_m FROM
                          (SELECT unnest(string_split(themes, ';')) theme, amount_usd_m FROM cmx
                           WHERE vintage >= year(current_date) - 1 AND themes IS NOT NULL) t
                          GROUP BY 1 ORDER BY n DESC""")
        new_funds = rows("""SELECT fund_id, fund_name, fund_type, domicile_country, round(gross_assets_usd/1e6,1) gav_musd,
                            beneficial_owners, adviser_name, adviser_crd, first_reported FROM funds
                            WHERE first_reported >= DATE '2024-01-01' AND fund_type IN ('Venture Capital Fund','Private Equity Fund')
                            AND coalesce(is_fund_of_funds,'N') <> 'Y'
                            ORDER BY gross_assets_usd DESC NULLS LAST LIMIT 50""")
        return {"recent_commitments": recent, "active_lps": active, "themes_recent": themes, "new_funds": new_funds}

    # ---------------- manager check (GP due diligence) ----------------
    @app.get("/api/manager_check/{crd}")
    def manager_check(crd: str):
        m = one("SELECT * FROM advisers WHERE crd = ?", [crd])
        if not m:
            raise HTTPException(404)
        funds = rows("""SELECT fund_id, fund_name, fund_type, domicile_country, gross_assets_usd, min_investment_usd, beneficial_owners,
                        pct_owned_by_manager, pct_owned_by_fund_of_funds, pct_owned_non_us, is_master, is_feeder, auditor,
                        administrator, custodian, prime_broker, placement_agent, uses_placement_agent, exemption_3c7, first_reported
                        FROM funds WHERE adviser_crd = ? ORDER BY first_reported""", [crd])
        c = one("SELECT * FROM adviser_contacts WHERE crd = ?", [crd]) or {}
        lp = rows("""SELECT c.lp, c.fund_name, c.vintage, round(c.amount_usd_m,1) amount_usd_m, c.net_irr, c.multiple, c.source_url
                     FROM commitments c JOIN funds f ON f.fund_id = c.adv_fund_id WHERE f.adviser_crd = ?
                     ORDER BY c.vintage DESC NULLS LAST""", [crd])

        def vals(k):
            return [f[k] for f in funds if f[k] is not None]

        def med(k):
            v = vals(k)
            return round(statistics.median(v), 1) if v else None

        def providers(k):
            cnt = {}
            for f in funds:
                for x in (f[k] or "").split("; "):
                    if x:
                        cnt[x] = cnt.get(x, 0) + 1
            return sorted(cnt.items(), key=lambda kv: -kv[1])[:6]

        auditors = providers("auditor")
        gav = sum(vals("gross_assets_usd")) if funds else 0
        main = [f for f in funds if f["fund_type"] in ("Venture Capital Fund", "Private Equity Fund") and not f["is_feeder"] == "Y"]
        flags, positives = [], []
        if m["adviser_type"] == "ERA":
            flags.append("Exempt reporting adviser: files a reduced Form ADV and is not fully SEC-registered.")
        unaudited = [f for f in funds if not f["auditor"]]
        if unaudited:
            flags.append(f"{len(unaudited)} of {len(funds)} funds name no auditor.")
        if auditors and any(a[0].lower().startswith(BIG4) or any(b in a[0].lower() for b in BIG4) for a in auditors):
            positives.append("Big Four auditor on at least one fund.")
        high_own = [f for f in funds if (f["pct_owned_by_manager"] or 0) >= 50]
        if high_own:
            flags.append(f"{len(high_own)} funds are majority-owned by the manager or related persons (captive or family capital).")
        med_fof = med("pct_owned_by_fund_of_funds")
        if med_fof and med_fof >= 20:
            positives.append(f"Institutional LP base: median {med_fof:.0f}% of fund equity held by funds of funds.")
        if len(main) <= 1:
            flags.append("One main fund on record: an emerging or first-time manager.")
        if any(f["placement_agent"] for f in funds):
            positives.append("Uses a placement agent: " + ", ".join(sorted({f['placement_agent'] for f in funds if f['placement_agent']}))[:120])
        if not any(f["administrator"] for f in funds):
            flags.append("No third-party administrator reported.")
        if lp:
            positives.append(f"{len({x['lp'] for x in lp})} tracked public LPs back its funds.")
        years = sorted({(f["first_reported"] or "")[:4] for f in funds if f["first_reported"]})
        return {
            "manager": m, "contact": c, "funds": funds, "lp_backers": lp,
            "summary": {
                "n_funds": len(funds), "gross_assets_usd": gav, "first_on_record": years[0] if years else None,
                "latest_fund_filed": years[-1] if years else None,
                "fund_types": sorted({f["fund_type"] for f in funds if f["fund_type"]}),
                "domiciles": sorted({f["domicile_country"] for f in funds if f["domicile_country"]}),
                "median_investors": med("beneficial_owners"), "median_pct_fof": med_fof,
                "median_pct_non_us": med("pct_owned_non_us"), "median_pct_manager": med("pct_owned_by_manager"),
                "median_min_investment": med("min_investment_usd"),
            },
            "providers": {"auditor": auditors, "administrator": providers("administrator"), "custodian": providers("custodian"),
                          "placement_agent": providers("placement_agent")},
            "flags": flags, "positives": positives,
            "sec_profile": f"https://adviserinfo.sec.gov/firm/summary/{crd}",
        }

    # ---------------- founder mode: find VCs ----------------
    STAGE_BAND = {"Pre-seed / seed": (5, 150), "Series A": (75, 600), "Series B+": (300, 2500), "Growth": (1000, 50000)}

    @app.get("/api/find_vcs")
    def find_vcs(stage: str = "Series A", geography: str = "North America", themes: str = ""):
        want = [t.strip() for t in themes.split(";") if t.strip() and t.strip() != "generalist"]
        lo, hi = STAGE_BAND.get(stage, (75, 600))
        mgrs = rows("""SELECT f.adviser_crd crd, any_value(f.adviser_name) AS "name", any_value(f.adviser_country) AS country,
                        count(*) n_funds, max(f.first_reported) newest, median(f.gross_assets_usd)/1e6 median_fund_musd,
                        sum(f.gross_assets_usd)/1e6 total_musd, string_agg(DISTINCT f.domicile_country, '; ') domiciles,
                        string_agg(f.fund_name, ' | ') fund_names, arg_max(f.fund_name, f.first_reported) latest_fund,
                        count(*) FILTER (WHERE f.india_link) n_india, count(*) FILTER (WHERE f.domicile_country IN ('Singapore','Hong Kong','China','Japan','India','Mauritius','Korea, Republic of','Taiwan','Indonesia','Vietnam')) n_asia
                        FROM funds f WHERE f.fund_type = 'Venture Capital Fund' AND coalesce(f.is_fund_of_funds,'N') <> 'Y'
                        AND coalesce(f.is_feeder,'N') <> 'Y' GROUP BY f.adviser_crd HAVING median(f.gross_assets_usd) > 0""")
        cls = {r["crd"]: r["t"] for r in rows("""SELECT f.adviser_crd crd, string_agg(k.themes, ';') t FROM commitments c
                 JOIN funds f ON f.fund_id = c.adv_fund_id JOIN fund_class k USING (name_key) GROUP BY 1""")}
        contacts = {r["crd"]: r for r in rows("SELECT crd, phone, websites FROM adviser_contacts")}
        out = []
        for mg in mgrs:
            size = mg["median_fund_musd"] or 0
            if size < 3 or (mg["n_funds"] > 150 and size < 20):
                continue  # SPV platforms and single-deal vehicles, not VC firms
            mid = math.sqrt(lo * hi)
            size_w = math.exp(-((math.log(max(size, 1)) - math.log(mid)) ** 2) / (2 * (math.log(hi / lo) / 2) ** 2))
            yr = int((mg["newest"] or "1900")[:4])
            rec = 1.5 if yr >= 2023 else 1.2 if yr >= 2021 else 0.5
            doms = set((mg["domiciles"] or "").split("; "))
            country = mg["country"] or ""
            names = (mg["fund_names"] or "").lower()
            if geography == "North America":
                geo = 1.3 if country == "United States" else 0.6
            elif geography in ("Europe", "UK"):
                geo = 1.6 if country in EUROPE else 1.1 if doms & EUROPE else 0.4
            elif geography == "India":
                share = (mg["n_india"] or 0) / mg["n_funds"]
                geo = 2.0 if country == "India" or share >= 0.3 else 0.05
            elif geography in ("Asia", "China", "Japan"):
                share = (mg["n_asia"] or 0) / mg["n_funds"]
                geo = 1.8 if country in ASIA or share >= 0.3 else 0.1
            else:
                geo = 1.0
            hits = _themes_in(names + " " + (cls.get(mg["crd"]) or ""), want) if want else []
            theme = (1 + 0.6 * len(hits)) if want else 1.0
            if want and not hits:
                theme = 0.6
            score = size_w * rec * geo * theme * (1 + math.log10(mg["n_funds"]))
            if score <= 0.02:
                continue
            ct = contacts.get(mg["crd"], {})
            out.append({**{k: mg[k] for k in ("crd", "name", "country", "n_funds", "newest", "domiciles", "latest_fund")},
                        "median_fund_musd": round(size, 1), "total_musd": round(mg["total_musd"] or 0),
                        "themes_hit": hits, "score": round(score, 3), "phone": ct.get("phone"), "websites": ct.get("websites")})
        out.sort(key=lambda x: x["score"], reverse=True)
        out = out[:80]
        top = out[0]["score"] if out else 1
        for o in out:
            o["match"] = round(100 * o["score"] / top)
        return {"vcs": out, "note": "Ranked from SEC Form ADV venture funds: fund size fit for the stage, how recently the manager filed a new fund, geography and theme words in fund names or in the LP-commitment classification."}

    # ---------------- outreach: email drafts and HubSpot export ----------------
    def _channel(t):
        t = (t or "").strip()
        if not t or t.lower().startswith(("no ", "none", "not ")) or not re.search(r"@|http|portal|form|submit|inbox", t.lower()):
            return None
        return t

    def _vt(e):
        return f"{e['fund_name']} ({e['vintage']})" if e.get("vintage") else e["fund_name"]

    def _draft(lp, fund_name, strategy, geography, themes, size, contact=None):
        ex = [e for e in lp.get("examples", []) if e.get("fund_name")][:3]
        cited = ", ".join(_vt(e) for e in ex)
        channel = _channel(lp.get("how_to_apply"))
        who = (contact or {}).get("contact_name") or ""
        first = who.split()[0] if who else ""
        greet = f"Dear {first}," if first else "Dear " + (lp["lp"] + " team,")
        theme_txt = ", ".join(t for t in themes.split(";") if t and t != "generalist") or "our sectors"
        size_txt = f" targeting ${size:,.0f}m" if size else ""
        subject = f"{fund_name or '[Fund name]'}: {strategy.lower()} fund, {geography}{size_txt}"
        body = f"""{greet}

We are raising {fund_name or '[Fund name]'}, a {strategy.lower()} fund{size_txt} investing in {theme_txt} across {geography}.

{('Your commitments to ' + cited + ' are close to what we do, which is why we are writing to you. ') if cited else ''}We would value 30 minutes to take you through the strategy, the team's record and the pipeline, and to understand how you look at funds of our size{' and at emerging managers' if lp.get('emerging_programme') else ''}.

{('We have also submitted through your published channel (' + channel + '). ') if channel else ''}Our deck and a short track-record summary are attached.

Kind regards,
[Name]
[Fund name] | [phone]"""
        return subject, body

    def _match_args(req):
        q = req.query_params
        return dict(strategy=q.get("strategy", "Venture"), geography=q.get("geography", "Europe"), themes=q.get("themes", ""),
                    stage=q.get("stage", ""), fund_size_m=float(q.get("fund_size_m") or 0), emerging=int(q.get("emerging") or 0))

    @app.get("/api/draft_email")
    def draft_email(request: Request, lp: str, fund_name: str = ""):
        a = _match_args(request)
        r = match(**a)
        d = next((x for x in r["public_lps"] if x["lp"] == lp), None)
        if not d:
            raise HTTPException(404, "LP not in this match")
        c = next((x for x in d.get("contacts", []) if x.get("contact_name")), None)
        subject, body = _draft(d, fund_name, a["strategy"], a["geography"], a["themes"], a["fund_size_m"], c)
        return {"to": c, "subject": subject, "body": body}

    @app.get("/api/export/hubspot.csv")
    def export_hubspot(request: Request, lps: str = "", fund_name: str = ""):
        """HubSpot import file (one row per contact; companies created from Company name / domain)."""
        a = _match_args(request)
        r = match(**a)
        chosen = {x for x in lps.split("||") if x} if lps else None
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Company name", "Company domain name", "First Name", "Last Name", "Job Title", "Email", "Phone Number",
                    "Country/Region", "Lifecycle Stage", "Lead Status", "LP type", "Match score", "Typical ticket (USD m)",
                    "Comparable funds", "How to apply", "Source", "Email subject", "Email draft"])
        for d in r["public_lps"]:
            if chosen is not None and d["lp"] not in chosen:
                continue
            comps = "; ".join(_vt(e) for e in d["examples"][:4])
            contacts = [c for c in d.get("contacts", [])] or [{}]
            for c in contacts:
                name = (c.get("contact_name") or "").split()
                subj, body = _draft(d, fund_name, a["strategy"], a["geography"], a["themes"], a["fund_size_m"], c if name else None)
                w.writerow([d["lp"], "", name[0] if name else "", " ".join(name[1:]) if len(name) > 1 else "",
                            c.get("title") or c.get("team") or "", c.get("email") or "", c.get("phone") or "", d["country"],
                            "lead", "NEW", d["lp_type"], d["match"], d["median_ticket_usd_m"] or "", comps,
                            d.get("how_to_apply") or "", c.get("source_url") or "", subj, body])
        for f in r["fof_allocators"]:
            if chosen is not None and f["name"] not in chosen:
                continue
            dom = (f.get("websites") or "").split("; ")[0].replace("http://", "").replace("https://", "").strip("/") if f.get("websites") else ""
            w.writerow([f["name"], dom, "", "", "", "", f.get("phone") or "", f["country"], "lead", "NEW",
                        "Fund-of-funds manager", f["match"], "", f["largest_vehicle"], "", f"https://adviserinfo.sec.gov/firm/summary/{f['crd']}", "", ""])
        name = f"hubspot-import-{a['strategy']}-{a['geography']}.csv".replace(" ", "-").replace("/", "-")
        return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.get("/api/meta")
    def meta():
        return {"private_data": sorted(PRIVATE.keys()), "mcp_enabled": bool(os.environ.get("PORTAL_MCP_TOKEN"))}

    # ---------------- MCP endpoint (Claude connector) ----------------
    TOOLS = [
        {"name": "find_lps", "description": "Rank LPs for a fund being raised. Returns public LPs with comparable commitments, typical ticket and contacts where available, plus fund-of-funds allocators.",
         "inputSchema": {"type": "object", "properties": {
             "strategy": {"type": "string", "description": "Venture, Growth, Buyout, Secondaries, Fund of funds, Co-investment, Private credit, Distressed/special situations, Infrastructure, Real estate, Real assets/natural resources"},
             "geography": {"type": "string", "description": "North America, Europe, UK, Asia, India, China, Japan, Middle East, Africa, Latin America, Emerging markets, Global"},
             "themes": {"type": "string", "description": "semicolon-separated: deep tech; climate/energy transition; life sciences/health; software/IT; fintech; consumer; industrials; impact"},
             "stage": {"type": "string"}, "fund_size_m": {"type": "number"}, "emerging": {"type": "boolean"}}, "required": ["strategy", "geography"]}},
        {"name": "search_funds", "description": "Search 116k private funds from SEC Form ADV by name, manager or GP entity.",
         "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}, "fund_type": {"type": "string"}, "domicile": {"type": "string"}}, "required": ["q"]}},
        {"name": "manager_check", "description": "Due-diligence summary of a fund manager (by name): funds, sizes, investor base, service providers, LP backers, flags.",
         "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
        {"name": "lp_commitments", "description": "Commitments made by an LP (partial name ok), optionally filtered by fund text and vintage.",
         "inputSchema": {"type": "object", "properties": {"lp": {"type": "string"}, "q": {"type": "string"}, "vintage_from": {"type": "integer"}}, "required": ["lp"]}},
        {"name": "family_offices", "description": "Family offices by region / keyword, with known fund commitments and sectors.",
         "inputSchema": {"type": "object", "properties": {"region": {"type": "string"}, "q": {"type": "string"}, "has_funds": {"type": "boolean"}}}},
        {"name": "find_vcs", "description": "Founder mode: rank venture managers for a startup by stage, geography and themes.",
         "inputSchema": {"type": "object", "properties": {"stage": {"type": "string", "description": "Pre-seed / seed, Series A, Series B+, Growth"},
                                                          "geography": {"type": "string"}, "themes": {"type": "string"}}, "required": ["stage", "geography"]}},
    ]

    def _slim_match(r):
        return {"public_lps": [{k: d[k] for k in ("lp", "lp_type", "country", "match", "n_similar", "median_ticket_usd_m", "flags", "how_to_apply")}
                               | {"comparables": [_vt(e) for e in d["examples"][:4]],
                                  "contacts": [{k: c[k] for k in ("contact_name", "title", "email", "phone") if c.get(k)} for c in d.get("contacts", [])[:4]]}
                               for d in r["public_lps"][:25]],
                "fof_allocators": [{k: f.get(k) for k in ("name", "country", "match", "n_vehicles", "n_vc", "n_pe", "gav_bn", "phone", "websites")} for f in r["fof_allocators"][:15]]}

    def _call(name, a):
        if name == "find_lps":
            return _slim_match(match(a.get("strategy", "Venture"), a.get("geography", "Europe"), a.get("themes", ""), a.get("stage", ""),
                                     float(a.get("fund_size_m") or 0), int(bool(a.get("emerging")))))
        if name == "search_funds":
            p = [f"%{a['q']}%"] * 2
            extra_w = ""
            if a.get("fund_type"):
                extra_w += " AND fund_type = ?"; p.append(a["fund_type"])
            if a.get("domicile"):
                extra_w += " AND domicile_country = ?"; p.append(a["domicile"])
            return rows(f"""SELECT fund_name, fund_type, domicile_country, round(gross_assets_usd/1e6,1) gav_musd, beneficial_owners,
                            pct_owned_by_fund_of_funds, pct_owned_non_us, adviser_name, auditor, administrator, first_reported
                            FROM funds WHERE (fund_name ILIKE ? OR adviser_name ILIKE ?){extra_w} ORDER BY gross_assets_usd DESC NULLS LAST LIMIT 25""", p)
        if name == "manager_check":
            mm = one("SELECT crd FROM advisers WHERE adviser_name ILIKE ? ORDER BY active_fund_gav DESC NULLS LAST LIMIT 1", [f"%{a['name']}%"])
            if not mm:
                return {"error": "manager not found"}
            r = manager_check(mm["crd"])
            r["funds"] = [{k: f[k] for k in ("fund_name", "fund_type", "gross_assets_usd", "beneficial_owners", "first_reported")} for f in r["funds"][:30]]
            return r
        if name == "lp_commitments":
            p = [f"%{a['lp']}%"]
            w = "lp ILIKE ?"
            if a.get("q"):
                w += " AND fund_name ILIKE ?"; p.append(f"%{a['q']}%")
            if a.get("vintage_from"):
                w += " AND vintage >= ?"; p.append(int(a["vintage_from"]))
            return rows(f"""SELECT lp, fund_name, manager_std manager, strategy, themes, geography, vintage, round(amount_usd_m,1) amount_usd_m,
                            net_irr, source_url FROM cmx WHERE {w} ORDER BY vintage DESC NULLS LAST LIMIT 60""", p)
        if name == "family_offices":
            return family_offices(q=a.get("q", ""), region=a.get("region", ""), has_funds=int(bool(a.get("has_funds"))))["rows"]
        if name == "find_vcs":
            return find_vcs(a.get("stage", "Series A"), a.get("geography", "North America"), a.get("themes", ""))["vcs"][:30]
        raise ValueError("unknown tool")

    @app.post("/mcp")
    async def mcp(request: Request):
        token = os.environ.get("PORTAL_MCP_TOKEN")
        if not token:
            return JSONResponse({"error": "MCP disabled: set PORTAL_MCP_TOKEN"}, status_code=403)
        auth = request.headers.get("authorization", "")
        given = auth[7:] if auth.lower().startswith("bearer ") else request.query_params.get("token", "")
        import hmac as _h
        if not _h.compare_digest(given, token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        msg = await request.json()

        def reply(mid, result=None, error=None):
            out = {"jsonrpc": "2.0", "id": mid}
            out["error" if error else "result"] = error or result
            return out

        def handle(m):
            method, mid = m.get("method"), m.get("id")
            if method == "initialize":
                return reply(mid, {"protocolVersion": m.get("params", {}).get("protocolVersion", "2025-06-18"),
                                   "capabilities": {"tools": {}}, "serverInfo": {"name": "lp-portal", "version": "1.0"}})
            if method in ("notifications/initialized",) or mid is None:
                return None
            if method == "ping":
                return reply(mid, {})
            if method == "tools/list":
                return reply(mid, {"tools": TOOLS})
            if method == "tools/call":
                p = m.get("params", {})
                try:
                    res = _call(p.get("name"), p.get("arguments") or {})
                    return reply(mid, {"content": [{"type": "text", "text": json.dumps(res, default=str)[:180000]}]})
                except Exception as e:  # noqa: BLE001
                    return reply(mid, {"content": [{"type": "text", "text": f"error: {e}"}], "isError": True})
            return reply(mid, error={"code": -32601, "message": "method not found"})

        if isinstance(msg, list):
            res = [r for r in (handle(x) for x in msg) if r]
            return JSONResponse(res) if res else Response(status_code=202)
        r = handle(msg)
        return JSONResponse(r) if r else Response(status_code=202)

    @app.get("/mcp")
    def mcp_get():
        return Response(status_code=405)

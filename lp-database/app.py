"""LP portal: a small password-protected web app over the LP / private fund database.

Data lives in data/*.parquet (exported from db/lp.duckdb by scripts/export_portal_data.py).
Run locally:  PORTAL_PASSWORD=secret uvicorn app:app --reload
"""
import hashlib
import math
import hmac
import os
import time
from pathlib import Path

import duckdb
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

BASE = Path(__file__).parent
DATA = BASE / "data"
USER = os.environ.get("PORTAL_USER", "icons")
PASSWORD = os.environ.get("PORTAL_PASSWORD", "")
SECRET = (os.environ.get("PORTAL_SECRET") or PASSWORD or "dev").encode()
COOKIE = "lp_portal"
SESSION_DAYS = 14

con = duckdb.connect()
for t in ("funds", "advisers", "lps"):
    con.execute(f"CREATE VIEW {t} AS SELECT * FROM read_parquet('{DATA / (t + '.parquet')}')")
# monthly updates (appended by the scheduled refresh) extend commitments and their classification
UPD = DATA / "commitments_updates.csv"
if UPD.exists():
    con.execute(f"""CREATE VIEW commitments_upd AS SELECT lp, lp_country, lp_type, asset_class, fund_name, manager,
        TRY_CAST(vintage AS INT) vintage, TRY_CAST(date_committed AS DATE) date_committed, TRY_CAST(amount_usd_m AS DOUBLE) amount_usd_m,
        NULL::DOUBLE contributed_usd_m, NULL::DOUBLE distributed_usd_m, NULL::VARCHAR net_irr, NULL::VARCHAR multiple, themes theme,
        notes, TRY_CAST(date_committed AS DATE) as_of, source_url, NULL::VARCHAR adv_fund_id,
        'upd:' || lower(regexp_replace(fund_name, '[^A-Za-z0-9]+', ' ', 'g')) name_key, strategy, stage, themes, geography
        FROM read_csv('{UPD}', header=true, all_varchar=true, delim=',', quote='"', escape='"')""")
    con.execute(f"""CREATE VIEW commitments AS SELECT * FROM read_parquet('{DATA / 'commitments.parquet'}')
        UNION ALL BY NAME SELECT * EXCLUDE (strategy, stage, themes, geography) FROM commitments_upd""")
    con.execute(f"""CREATE VIEW fund_class AS SELECT * FROM read_parquet('{DATA / 'fund_class.parquet'}')
        UNION ALL BY NAME SELECT DISTINCT ON (name_key) name_key, strategy, stage, themes, geography, manager manager_std FROM commitments_upd""")
else:
    for t in ("commitments", "fund_class"):
        con.execute(f"CREATE VIEW {t} AS SELECT * FROM read_parquet('{DATA / (t + '.parquet')}')")
# private data (contacts, family offices): only present when the repo is private / files are provided
PRIVATE = {}
for t in ("lp_contacts", "adviser_contacts", "family_offices"):
    for folder in (BASE / "private", DATA):
        f = folder / (t + ".parquet")
        if f.exists():
            con.execute(f"CREATE VIEW {t} AS SELECT * FROM read_parquet('{f}')")
            PRIVATE[t] = True
            break
if "lp_contacts" not in PRIVATE:
    con.execute('CREATE VIEW lp_contacts AS SELECT NULL::VARCHAR AS "db_lp", NULL::VARCHAR AS "institution", NULL::VARCHAR AS "team", NULL::VARCHAR AS "contact_name", NULL::VARCHAR AS "title", NULL::VARCHAR AS "email", NULL::VARCHAR AS "phone", NULL::VARCHAR AS "address", NULL::VARCHAR AS "how_to_apply", NULL::VARCHAR AS "source_url", NULL::VARCHAR AS "notes" WHERE false')
if "adviser_contacts" not in PRIVATE:
    con.execute('CREATE VIEW adviser_contacts AS SELECT NULL::VARCHAR AS "crd", NULL::VARCHAR AS "street", NULL::VARCHAR AS "city", NULL::VARCHAR AS "state", NULL::VARCHAR AS "country", NULL::VARCHAR AS "postal", NULL::VARCHAR AS "phone", NULL::VARCHAR AS "websites", NULL::VARCHAR AS "cco_name", NULL::VARCHAR AS "regulatory_contact" WHERE false')
if "family_offices" not in PRIVATE:
    con.execute('CREATE VIEW family_offices AS SELECT NULL::VARCHAR AS "name", NULL::VARCHAR AS "principal", NULL::VARCHAR AS "country", NULL::VARCHAR AS "city", NULL::VARCHAR AS "website", NULL::VARCHAR AS "fo_type", NULL::VARCHAR AS "style", NULL::VARCHAR AS "fund_commitments", NULL::VARCHAR AS "sectors", NULL::VARCHAR AS "stages", NULL::VARCHAR AS "typical_cheque", NULL::VARCHAR AS "notable_directs", NULL::VARCHAR AS "general_contact", NULL::VARCHAR AS "sources", NULL::VARCHAR AS "notes", NULL::VARCHAR AS "region" WHERE false')
# commitments with strategy / stage / themes / geography attached
con.execute("""CREATE VIEW cmx AS SELECT c.*, k.strategy, k.stage, k.themes, k.geography, coalesce(nullif(k.manager_std,''), c.manager) manager_std
               FROM commitments c LEFT JOIN fund_class k USING (name_key)""")
# fund-of-funds managers from Form ADV: allocators to other funds
con.execute("""CREATE VIEW fof_managers AS
  SELECT f.adviser_crd crd, any_value(a.adviser_name) AS "name", any_value(a.city) AS city, any_value(a.country) AS country,
         count(*) n_vehicles, sum(f.gross_assets_usd) gav,
         count(*) FILTER (WHERE f.fund_type='Venture Capital Fund') n_vc,
         count(*) FILTER (WHERE f.fund_type='Private Equity Fund') n_pe,
         count(*) FILTER (WHERE f.fund_type='Real Estate Fund') n_re,
         count(*) FILTER (WHERE f.fund_type NOT IN ('Venture Capital Fund','Private Equity Fund','Real Estate Fund')) n_other,
         string_agg(DISTINCT f.domicile_country, '; ') domiciles,
         max(f.first_reported) newest_vehicle,
         arg_max(f.fund_name, f.gross_assets_usd) largest_vehicle
  FROM funds f JOIN advisers a ON a.crd = f.adviser_crd
  WHERE f.is_fund_of_funds = 'Y' GROUP BY f.adviser_crd""")

app = FastAPI(title="LP Portal", docs_url=None, redoc_url=None)


# ---------- auth ----------
def _sign(value: str) -> str:
    return hmac.new(SECRET, value.encode(), hashlib.sha256).hexdigest()


def _make_token(user: str) -> str:
    exp = str(int(time.time()) + SESSION_DAYS * 86400)
    return f"{user}|{exp}|{_sign(user + '|' + exp)}"


def _valid(token: str | None) -> bool:
    if not PASSWORD:
        # no password configured: open only when running locally, locked when hosted
        return os.environ.get("RENDER") is None
    if not token:
        return False
    try:
        user, exp, sig = token.split("|")
    except ValueError:
        return False
    return hmac.compare_digest(sig, _sign(user + "|" + exp)) and int(exp) > time.time()


@app.middleware("http")
async def auth(request: Request, call_next):
    path = request.url.path
    if path in ("/login", "/healthz") or path.startswith("/static/login") or path.startswith("/mcp"):
        return await call_next(request)
    if not _valid(request.cookies.get(COOKIE)):
        if path.startswith("/api/"):
            return JSONResponse({"error": "not signed in"}, status_code=401)
        return RedirectResponse("/login")
    return await call_next(request)


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/login", response_class=HTMLResponse)
def login_page(error: int = 0):
    html = (BASE / "static" / "login.html").read_text()
    return html.replace("{{error}}", "Wrong user name or password." if error else "")


@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    ok = bool(PASSWORD) and hmac.compare_digest(username.strip(), USER) and hmac.compare_digest(password, PASSWORD)
    if not ok:
        time.sleep(1)
        return RedirectResponse("/login?error=1", status_code=303)
    r = RedirectResponse("/", status_code=303)
    r.set_cookie(COOKIE, _make_token(username), max_age=SESSION_DAYS * 86400, httponly=True,
                 secure=os.environ.get("RENDER") is not None, samesite="lax")
    return r


@app.get("/logout")
def logout():
    r = RedirectResponse("/login", status_code=303)
    r.delete_cookie(COOKIE)
    return r


@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(BASE / "static" / "index.html")


# ---------- helpers ----------
def rows(sql: str, params: list | None = None):
    cur = con.cursor()
    res = cur.execute(sql, params or [])
    cols = [d[0] for d in res.description]
    out = []
    for r in res.fetchall():
        out.append({c: (v.isoformat() if hasattr(v, "isoformat") else v) for c, v in zip(cols, r)})
    return out


def one(sql: str, params: list | None = None):
    r = rows(sql, params)
    return r[0] if r else None


PAGE = 50


def paged(base_sql: str, params: list, order: str, page: int):
    total = one(f"SELECT count(*) AS n FROM ({base_sql})", params)["n"]
    data = rows(f"{base_sql} ORDER BY {order} LIMIT {PAGE} OFFSET {max(page, 0) * PAGE}", params)
    return {"total": total, "page": page, "page_size": PAGE, "rows": data}


def safe_order(sort: str, allowed: dict, default: str) -> str:
    return allowed.get(sort, default)


# ---------- API ----------
@app.get("/api/stats")
def stats():
    return {
        "funds": one("""SELECT count(*) n, round(sum(gross_assets_usd)/1e12, 2) gav_tn,
                        count(*) FILTER (WHERE fund_type='Venture Capital Fund') vc,
                        count(*) FILTER (WHERE fund_type='Private Equity Fund') pe,
                        count(*) FILTER (WHERE is_fund_of_funds='Y') fof,
                        count(*) FILTER (WHERE india_link) india,
                        count(*) FILTER (WHERE deeptech_kw AND fund_type IN ('Venture Capital Fund','Private Equity Fund')) deeptech
                        FROM funds"""),
        "managers": one("SELECT count(*) n FROM advisers"),
        "commitments": one("SELECT count(*) n, count(DISTINCT lp) lps, round(sum(amount_usd_m)/1e3) usd_bn FROM commitments"),
        "by_type": rows("""SELECT fund_type, count(*) n, round(sum(gross_assets_usd)/1e9) gav_bn,
                           round(median(beneficial_owners)) median_investors,
                           round(avg(pct_owned_by_fund_of_funds),1) avg_pct_fof, round(avg(pct_owned_non_us),1) avg_pct_non_us
                           FROM funds GROUP BY 1 ORDER BY gav_bn DESC"""),
        "by_domicile": rows("SELECT domicile_country, count(*) n FROM funds GROUP BY 1 ORDER BY n DESC LIMIT 12"),
        "recent_commitments": rows("""SELECT lp, fund_name, coalesce(manager,'') manager, asset_class, vintage, date_committed,
                                      round(amount_usd_m,1) amount_usd_m FROM commitments
                                      WHERE date_committed IS NOT NULL ORDER BY date_committed DESC LIMIT 15"""),
    }


@app.get("/api/facets")
def facets():
    return {
        "fund_types": [r["fund_type"] for r in rows("SELECT DISTINCT fund_type FROM funds WHERE fund_type IS NOT NULL ORDER BY 1")],
        "domiciles": [r["d"] for r in rows("SELECT domicile_country d, count(*) n FROM funds WHERE d IS NOT NULL GROUP BY 1 ORDER BY n DESC")],
        "lps": [r["lp"] for r in rows("SELECT lp FROM lps ORDER BY lp")],
        "asset_classes": [r["a"] for r in rows("SELECT DISTINCT asset_class a FROM commitments WHERE a IS NOT NULL ORDER BY 1")],
    }


@app.get("/api/funds")
def funds(q: str = "", fund_type: str = "", domicile: str = "", flag: str = "", min_gav: float = 0,
          min_fof: float = 0, min_non_us: float = 0, sort: str = "gav", page: int = 0):
    where, p = ["1=1"], []
    if q:
        where.append("(fund_name ILIKE ? OR adviser_name ILIKE ? OR gp_entities ILIKE ?)")
        p += [f"%{q}%"] * 3
    if fund_type:
        where.append("fund_type = ?"); p.append(fund_type)
    if domicile:
        where.append("domicile_country = ?"); p.append(domicile)
    if flag == "deeptech":
        where.append("deeptech_kw")
    elif flag == "india":
        where.append("india_link")
    elif flag == "near_home":
        where.append("near_home")
    elif flag == "fof":
        where.append("is_fund_of_funds = 'Y'")
    if min_gav:
        where.append("gross_assets_usd >= ?"); p.append(min_gav * 1e6)
    if min_fof:
        where.append("pct_owned_by_fund_of_funds >= ?"); p.append(min_fof)
    if min_non_us:
        where.append("pct_owned_non_us >= ?"); p.append(min_non_us)
    sql = f"""SELECT fund_id, fund_name, fund_type, domicile_country, round(gross_assets_usd/1e6,1) gav_musd,
              beneficial_owners, pct_owned_by_fund_of_funds, pct_owned_non_us, adviser_name, adviser_country,
              first_reported, last_reported FROM funds WHERE {' AND '.join(where)}"""
    order = safe_order(sort, {"gav": "gav_musd DESC NULLS LAST", "name": "fund_name", "investors": "beneficial_owners DESC NULLS LAST",
                              "fof": "pct_owned_by_fund_of_funds DESC NULLS LAST", "nonus": "pct_owned_non_us DESC NULLS LAST",
                              "newest": "first_reported DESC NULLS LAST"}, "gav_musd DESC NULLS LAST")
    return paged(sql, p, order, page)


@app.get("/api/fund/{fund_id}")
def fund(fund_id: str):
    f = one("SELECT * FROM funds WHERE fund_id = ?", [fund_id])
    if not f:
        raise HTTPException(404)
    f["commitments"] = rows("""SELECT lp, asset_class, vintage, round(amount_usd_m,1) amount_usd_m, net_irr, multiple, as_of, source_url
                               FROM commitments WHERE adv_fund_id = ? ORDER BY lp""", [fund_id])
    f["siblings"] = rows("""SELECT fund_id, fund_name, fund_type, round(gross_assets_usd/1e6,1) gav_musd, first_reported
                            FROM funds WHERE adviser_crd = ? AND fund_id <> ? ORDER BY gross_assets_usd DESC NULLS LAST LIMIT 25""",
                         [f["adviser_crd"], fund_id])
    return f


@app.get("/api/managers")
def managers(q: str = "", country: str = "", sort: str = "gav", page: int = 0):
    where, p = ["1=1"], []
    if q:
        where.append("(adviser_name ILIKE ? OR adviser_legal_name ILIKE ?)"); p += [f"%{q}%"] * 2
    if country:
        where.append("country = ?"); p.append(country)
    sql = f"""SELECT crd, adviser_name, adviser_type, city, country, round(regulatory_aum/1e6) aum_musd,
              n_active_funds, round(active_fund_gav/1e6) fund_gav_musd, fund_types, fund_domiciles
              FROM advisers WHERE {' AND '.join(where)}"""
    order = safe_order(sort, {"gav": "fund_gav_musd DESC NULLS LAST", "funds": "n_active_funds DESC", "name": "adviser_name"},
                       "fund_gav_musd DESC NULLS LAST")
    return paged(sql, p, order, page)


@app.get("/api/manager/{crd}")
def manager(crd: str):
    m = one("SELECT * FROM advisers WHERE crd = ?", [crd])
    if not m:
        raise HTTPException(404)
    m["funds"] = rows("""SELECT fund_id, fund_name, fund_type, domicile_country, round(gross_assets_usd/1e6,1) gav_musd,
                         beneficial_owners, pct_owned_by_fund_of_funds, pct_owned_non_us, first_reported
                         FROM funds WHERE adviser_crd = ? ORDER BY gross_assets_usd DESC NULLS LAST""", [crd])
    m["lp_commitments"] = rows("""SELECT c.lp, c.fund_name, c.vintage, round(c.amount_usd_m,1) amount_usd_m
                                  FROM commitments c JOIN funds f ON f.fund_id = c.adv_fund_id
                                  WHERE f.adviser_crd = ? ORDER BY c.vintage DESC NULLS LAST""", [crd])
    return m


@app.get("/api/lps")
def lps():
    return rows("""SELECT l.*, (SELECT string_agg(DISTINCT asset_class, ', ') FROM commitments c WHERE c.lp = l.lp) asset_classes
                   FROM lps l ORDER BY total_usd_m DESC NULLS LAST""")


@app.get("/api/commitments")
def commitments(q: str = "", lp: str = "", asset_class: str = "", vintage_from: int = 0, sort: str = "recent", page: int = 0):
    where, p = ["1=1"], []
    if q:
        where.append("(fund_name ILIKE ? OR manager ILIKE ? OR theme ILIKE ? OR notes ILIKE ?)"); p += [f"%{q}%"] * 4
    if lp:
        where.append("lp = ?"); p.append(lp)
    if asset_class:
        where.append("asset_class = ?"); p.append(asset_class)
    if vintage_from:
        where.append("vintage >= ?"); p.append(vintage_from)
    sql = f"""SELECT lp, lp_type, asset_class, fund_name, manager, vintage, date_committed, round(amount_usd_m,1) amount_usd_m,
              round(contributed_usd_m,1) contributed_usd_m, net_irr, multiple, theme, notes, adv_fund_id, source_url
              FROM commitments WHERE {' AND '.join(where)}"""
    order = safe_order(sort, {"recent": "coalesce(date_committed, make_date(vintage,1,1)) DESC NULLS LAST",
                              "amount": "amount_usd_m DESC NULLS LAST", "fund": "fund_name"},
                       "coalesce(date_committed, make_date(vintage,1,1)) DESC NULLS LAST")
    return paged(sql, p, order, page)


# ---------- LP matching ("describe your fund, get ranked LPs") ----------
STRAT_SIM = {
    "Venture": {"Venture": 1, "Growth": .5, "Fund of funds": .2},
    "Growth": {"Growth": 1, "Venture": .6, "Buyout": .3},
    "Buyout": {"Buyout": 1, "Growth": .4, "Co-investment": .3},
    "Secondaries": {"Secondaries": 1, "Fund of funds": .5, "Co-investment": .3},
    "Fund of funds": {"Fund of funds": 1, "Secondaries": .5},
    "Co-investment": {"Co-investment": 1, "Buyout": .4, "Growth": .3},
    "Private credit": {"Private credit": 1, "Distressed/special situations": .5},
    "Distressed/special situations": {"Distressed/special situations": 1, "Private credit": .5},
    "Infrastructure": {"Infrastructure": 1, "Real assets/natural resources": .5},
    "Real estate": {"Real estate": 1},
    "Real assets/natural resources": {"Real assets/natural resources": 1, "Infrastructure": .5},
}
GEO_SIM = {
    "Europe": {"Europe": 1, "UK": .8, "Global": .6},
    "UK": {"UK": 1, "Europe": .8, "Global": .6},
    "North America": {"North America": 1, "Global": .6},
    "Asia": {"Asia": 1, "China": .7, "India": .7, "Japan": .7, "Emerging markets": .6, "Global": .6},
    "India": {"India": 1, "Asia": .7, "Emerging markets": .7, "Global": .5},
    "China": {"China": 1, "Asia": .7, "Emerging markets": .5, "Global": .5},
    "Japan": {"Japan": 1, "Asia": .7, "Global": .5},
    "Middle East": {"Middle East": 1, "Emerging markets": .7, "Global": .5},
    "Africa": {"Africa": 1, "Emerging markets": .7, "Global": .5},
    "Latin America": {"Latin America": 1, "Emerging markets": .7, "Global": .5},
    "Emerging markets": {"Emerging markets": 1, "Africa": .7, "Latin America": .7, "Asia": .7, "India": .7, "Middle East": .7, "Global": .5},
    "Global": {"Global": 1, "North America": .6, "Europe": .6, "UK": .5, "Asia": .5},
}
EUROPE = {"France", "Germany", "Luxembourg", "Ireland", "United Kingdom", "Switzerland", "Netherlands", "Sweden", "Denmark",
          "Finland", "Norway", "Spain", "Italy", "Belgium", "Austria", "Monaco", "Jersey", "Guernsey", "Portugal"}
ASIA = {"Singapore", "Hong Kong", "Japan", "China", "India", "Korea, Republic of", "Taiwan", "Australia"}


@app.get("/api/match_options")
def match_options():
    return {"strategies": list(STRAT_SIM.keys()), "geographies": list(GEO_SIM.keys()),
            "themes": ["deep tech", "climate/energy transition", "life sciences/health", "software/IT", "fintech",
                       "consumer", "industrials", "impact", "generalist"],
            "stages": ["Seed", "Early", "Multi-stage", "Late/growth", "Small", "Mid", "Large", "Mega"]}


@app.get("/api/match")
def match(strategy: str = "Venture", geography: str = "Europe", themes: str = "", stage: str = "",
          fund_size_m: float = 0, emerging: int = 0):
    want_themes = {t.strip() for t in themes.split(";") if t.strip()}
    ssim = STRAT_SIM.get(strategy, {strategy: 1})
    gsim = dict(GEO_SIM.get(geography, {geography: 1}))
    regional = geography not in ("North America", "Europe", "UK", "Global")
    if regional:
        gsim["Global"] = 0.1  # a global growth fund says little about appetite for India, Africa etc.
    recs = rows("""SELECT lp, lp_type, lp_country, fund_name, manager_std, strategy, stage, themes, geography, vintage,
                   date_committed, amount_usd_m, asset_class, notes, source_url FROM cmx""")
    by_lp = {}
    for r in recs:
        sw = ssim.get(r["strategy"], 0)
        gw = gsim.get(r["geography"], 0)
        if not sw or not gw:
            continue
        th = {t.strip() for t in (r["themes"] or "").split(";")}
        theme_bonus = min(1.0, 0.5 * len(want_themes & th)) if want_themes else 0
        if want_themes and not (want_themes & th) and "generalist" not in th:
            theme_bonus = -0.3
        v = r["vintage"] or 0
        rec = 1.5 if v >= 2022 else 1.0 if v >= 2018 else 0.4
        stage_bonus = 0.3 if stage and r["stage"] == stage else 0
        w = sw * gw * (1 + theme_bonus + stage_bonus) * rec
        if w <= 0:
            continue
        d = by_lp.setdefault(r["lp"], {"lp": r["lp"], "lp_type": r["lp_type"], "country": r["lp_country"], "score": 0,
                                       "n_similar": 0, "tickets": [], "examples": [], "emerging_programme": False})
        d["score"] += w
        d["n_similar"] += 1
        if gw >= 0.7:
            d["n_regional"] = d.get("n_regional", 0) + 1
        if r["amount_usd_m"]:
            d["tickets"].append(r["amount_usd_m"])
        d["examples"].append((w, v, r))
        if "emerging" in ((r["asset_class"] or "") + (r["notes"] or "")).lower():
            d["emerging_programme"] = True
    out = []
    for d in by_lp.values():
        d.setdefault("n_regional", 0)
        if regional and d["n_regional"] == 0:
            continue
        t = sorted(d.pop("tickets"))
        d["median_ticket_usd_m"] = round(t[len(t) // 2], 1) if t else None
        ex = sorted(d.pop("examples"), key=lambda x: (x[0] >= 0.5, x[1], x[0]), reverse=True)[:6]
        d["examples"] = [{"fund_name": e[2]["fund_name"], "manager": e[2]["manager_std"], "vintage": e[1],
                          "amount_usd_m": round(e[2]["amount_usd_m"], 1) if e[2]["amount_usd_m"] else None,
                          "themes": e[2]["themes"], "geography": e[2]["geography"], "source_url": e[2]["source_url"]} for e in ex]
        if emerging and d["emerging_programme"]:
            d["score"] *= 1.3
        flags = []
        if fund_size_m and d["median_ticket_usd_m"] and d["median_ticket_usd_m"] > 0.25 * fund_size_m:
            flags.append(f"typical ticket ${d['median_ticket_usd_m']:.0f}m is large for a ${fund_size_m:.0f}m fund")
        if d["emerging_programme"]:
            flags.append("has an emerging manager programme")
        d["flags"] = flags
        d["score"] = round(d["score"], 2)
        out.append(d)
    out.sort(key=lambda d: d["score"], reverse=True)
    for d in out:
        d["contacts"] = rows("""SELECT institution, team, contact_name, title, email, phone, how_to_apply, source_url FROM lp_contacts
                                WHERE db_lp = ? ORDER BY (contact_name IS NULL), (email IS NULL), contact_name""", [d["lp"]])
        d["how_to_apply"] = next((c["how_to_apply"] for c in d["contacts"] if c["how_to_apply"]), None)
    top = out[0]["score"] if out else 1
    for d in out:
        d["match"] = round(100 * d["score"] / top)

    # fund-of-funds allocators from Form ADV
    col = {"Venture": "n_vc + 0.02*n_pe", "Growth": "0.6*n_vc + 0.3*n_pe", "Buyout": "n_pe", "Co-investment": "n_pe",
           "Secondaries": "n_pe + 0.5*n_vc + 0.3*n_other", "Fund of funds": "n_pe + n_vc",
           "Real estate": "n_re", "Infrastructure": "n_other + 0.2*n_pe", "Private credit": "n_other + 0.2*n_pe",
           "Distressed/special situations": "n_other + 0.3*n_pe", "Real assets/natural resources": "n_other + 0.2*n_pe"}.get(strategy, "n_pe")
    fof = rows(f"""SELECT m.*, ({col}) AS rel, c.phone, c.websites, c.cco_name
                   FROM fof_managers m LEFT JOIN adviser_contacts c ON c.crd = m.crd WHERE ({col}) > 0""")
    for f in fof:
        geo = 1.0
        doms = set((f["domiciles"] or "").split("; "))
        if geography in ("Europe", "UK"):
            geo = 1.6 if f["country"] in EUROPE else 1.15 if doms & EUROPE else 1.0
        elif geography in ("Asia", "India", "China", "Japan", "Emerging markets"):
            geo = 2.0 if f["country"] in ASIA else 1.3 if doms & (ASIA | {"Mauritius"}) else 0.25
        elif geography == "North America" and f["country"] == "United States":
            geo = 1.3
        elif regional:
            geo = 0.25
        size = (f["gav"] or 0) / 1e9
        f["rel"] = float(f["rel"]); f["score"] = round((f["rel"] ** 0.5) * geo * (1 + math.log10(1 + size)), 2)
        f["gav_bn"] = round(size, 1)
    fof.sort(key=lambda f: f["score"], reverse=True)
    fof = fof[:60]
    top = fof[0]["score"] if fof else 1
    for f in fof:
        f["match"] = round(100 * f["score"] / top)
    return {"public_lps": out, "fof_allocators": fof, "regional": regional, "private_data": bool(PRIVATE),
            "note": "Public LPs are ranked by how many similar funds they backed (strategy, geography, themes, recency). "
                    "Fund-of-funds allocators come from SEC Form ADV and are ranked by how many relevant fund-of-funds vehicles they run and their size."}


@app.get("/api/overlap")
def overlap(min_lps: int = 2):
    return rows("""SELECT any_value(fund_name) fund_name, count(DISTINCT lp) n_lps, string_agg(DISTINCT lp, '; ') lps,
                   max(vintage) vintage, round(sum(amount_usd_m)) total_usd_m, any_value(adv_fund_id) adv_fund_id
                   FROM commitments GROUP BY name_key HAVING count(DISTINCT lp) >= ?
                   ORDER BY n_lps DESC, total_usd_m DESC NULLS LAST LIMIT 500""", [min_lps])


# ---------- extended features (family offices, signals, manager check, founder mode, exports, MCP) ----------
import extra  # noqa: E402
extra.register(app, globals())

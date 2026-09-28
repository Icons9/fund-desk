# LP Portal

Password-protected portal for fundraising research over public private-markets data.

- **Find LPs**: describe the fund you are raising (strategy, stage, geography, themes, size, first-time manager) and get ranked public LPs with comparable commitments, typical ticket and published contacts; matching family offices; and fund-of-funds allocators from SEC Form ADV. Shortlist LPs, draft emails that cite each LP's comparable funds, and export to a HubSpot import file.
- **Shortlist**: saved LPs with outreach status and notes (kept in the browser), exportable to HubSpot.
- **Family offices**: ~660 family offices across India, the Gulf, Singapore/Hong Kong, Europe and the US, with known fund commitments where public.
- **Signals**: most active LPs, recent dated commitments, themes in the latest vintages, new large funds, managers backed by several LPs.
- **Manager check**: due-diligence view of any SEC-reporting manager: funds, investor base, service providers, public LP backers, points to probe.
- **Find VCs** (founder mode): rank venture managers for a startup by round, geography and themes.
- **Funds / Managers / LPs / Commitments / Overview**: the underlying data: 116,604 private funds, 12,367 managers, 6,620 LP commitments from 86 LPs.
- **Claude connector**: `POST /mcp` (MCP over HTTP) with tools find_lps, search_funds, manager_check, lp_commitments, family_offices, find_vcs. Enabled when `PORTAL_MCP_TOKEN` is set; pass it as `Authorization: Bearer <token>` or `?token=<token>`.

Contacts and family offices live in `private/` (git-ignored) and are only served when those files are present, i.e. once the portal runs from a private repository.

`data/commitments_updates.csv` is appended monthly by a scheduled refresh (new commitments with strategy/themes/geography) and is merged into the commitments at start-up.

## Run locally

```
pip install -r requirements.txt
PORTAL_PASSWORD=choose-one uvicorn app:app --reload
```
Open http://localhost:8000 and sign in with user `icons` (or `PORTAL_USER`) and the password.

## Deploy on Render

1. In Render, New > Blueprint, pick this repo. `render.yaml` sets up the web service.
2. Set `PORTAL_PASSWORD` when prompted. `PORTAL_SECRET` is generated automatically.
3. The free plan sleeps after 15 minutes idle and takes ~30 seconds to wake; the $7/month Starter plan stays on.

## Updating the data

The files in `data/` are exported from `db/lp.duckdb` in the LP-Database folder. Re-export them, commit, and push; Render redeploys on each push.

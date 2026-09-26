# LP Portal

Password-protected web portal over the Icons & Company private fund and LP database.

- **Find LPs**: describe the fund you are raising (strategy, stage, geography, themes, size, first-time manager) and get ranked LPs: public LPs with a record of backing similar funds, with examples and typical ticket, plus fund-of-funds allocators from SEC Form ADV that run relevant vehicles.

- **Funds**: 116,604 private funds reported on SEC Form ADV Schedule D 7.B.1 (latest filings to Dec 2024): type, domicile, size, investor count, share held by funds of funds and non-US investors, GP entities, auditor, administrator, custodian, prime broker, placement agent.
- **Managers**: 12,367 advisers with active private funds.
- **LP commitments**: 4,349 LP-to-fund records from 19 LPs (CalPERS, CalSTRS, Washington SIB, Oregon PERF, NY Common, Florida SBA, EIB, EIF, and UK LGPS funds: Greater Manchester, Strathclyde, Lothian, West Yorkshire, Merseyside, Northern PE Pool, Nottinghamshire, Cambridgeshire, Cheshire, Suffolk, Lincolnshire). Each row links to its public source.

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

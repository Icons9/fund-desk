# Fund Desk daily update — runbook

Run once a day. Goal: every dataset on the desk is current, nothing breaks, and the live site and the claude.ai copy match. The live site is served behind a sign-in by the LP Portal web service on Render (service `srv-das40ou0tbcc73do402g`, workspace `tea-d9r0u2nqj5pc73ahpkeg`), which redeploys on pushes to `main`.

Research date = today. Work in the repo root. Never invent facts, figures, dates or URLs: every new or changed item needs a source you actually opened. If a step fails, skip it, keep the old data, and say so in the summary. Do not rewrite text that is still correct.

## 0. Setup
- `npm i --prefix /tmp acorn@8` (needed by `scripts/rootdata.mjs`).
- `node scripts/rootdata.mjs export` — pulls the root desk's inline data into `data/root/*.json`. Edit those JSON files, never the inline arrays in `index.html`.
- The web search budget is about 200 searches per run, shared by every agent you start. Split it roughly: news 50, deals 110, directories and legal 20, A-signal rechecks 20. Prefer list and roundup pages, then WebFetch them.

## 1. Headlines (daily)
Two stores, same seven sources and categories:
- `learn/data/news.json` — `{asof, sources:[{id,name,tag,url,items:[{t,u,d,r}]}]}`; `d` like "16 Nov 2026"; `r` is a short region/theme tag already used in the file.
- `data/root/SRC.json` — `[{name,tag,url,items:[{t,u,d,s}]}]`; `s` is a one-line summary in your own words (no copied sentences).
For each source, open its listing page (the `url` field) and take the newest real headlines. Keep 6–8 items per source, newest first; drop items older than 21 days. Headline text may be the publisher's title; summaries must be your own words. Set `news.json` `asof` to today ("21 November 2026") and `data/root/meta.json` `curated_at` to today ("21 Nov 2026").

## 2. Deals (daily)
Data: `learn/data/deals.json`. Spec for rows: `scripts/DEALS_SPEC.md` (same fields; sectors Healthcare, Deeptech, AI, Aerospace, Maritime, Defence; regions europe, usa, asia, em_africa).
a. New rounds: find funding rounds announced in the last 3 days across all six sectors and regions (Tech.eu funding database, Crunchbase News, TechCrunch, Sifted, Inc42/Entrackr, DealStreetAsia, Wamda/MAGNiTT, TechCabal, SpaceNews/Payload, Splash247, Breaking Defense, CTVC, Labiotech, Fierce Biotech). Write rows (signal C, or A if the round is still open) to `/tmp/deals_new.jsonl`.
b. Recheck "A - Actively raising" rows: pick the 10 A rows in deals.json with the oldest evidence and check whether the raise is still open. Write an update row with the corrected signal and `"force_update": true`, and `"checked": "Confirmed"` or `"Corrected"`. Rows for companies now acquired, listed, defunct or valued over ~$10bn get `"signal": "X - Exclude"` with the company name exactly as it appears in deals.json.
c. Product launches: for companies in deals.json, note any 2026 launch you come across in `product_launch`.
d. Merge: `python3 scripts/deals_add.py /tmp/deals_new.jsonl && python3 scripts/clean_deals.py learn/data/deals.json`.

## 3. Directories, people, M&A (check daily, change only on news)
- `learn/data/desk.json` (`global`, `india`, `fo`, `companies`, `navs`, `marketnews`) and `data/root/GLOBAL.json`, `INDIA.json`, `FO.json` (positional arrays — keep the same order of fields), `PEOPLE.json`, `MADEALS.json`, `MATRENDS.json`.
- Search for: new AUM figures from the listed managers (quarterly results), leadership changes at listed firms (PEOPLE), and major private-markets M&A announced in the last 3 days (MADEALS, newest first, keep 12). Update only what a source confirms. Keep the two directory stores consistent with each other.
- If anything in `desk.json` changed, set its `asof` to today.

## 4. Legal and compliance (check daily, change only on news)
- `learn/data/legal.json`. Check regulator news for the eight jurisdictions it covers (EU/ESMA AIFMD, UK FCA, Luxembourg CSSF, Ireland CBI, Monaco CCAF, India SEBI/IFSCA, US SEC, UAE/DIFC/ADGM). Change a rule, threshold or calendar entry only when an official source confirms it. Calendar entries whose date has passed: roll a recurring one to its next occurrence; leave one-offs.
- If anything changed, set `asof` to today and say what in the summary.

## 5. Write back, check, publish
1. `node scripts/rootdata.mjs import`
2. `python3 scripts/validate.py` — must print "all checks passed". If not, fix or revert the offending file (`git checkout -- <file>`).
3. Commit to `main` with a message listing what changed (counts: headlines refreshed, deals added/updated/removed, any directory or legal changes), then `git -c push.negotiate=true push origin HEAD:main`. Then check Render `list_deploys` for service `srv-das40ou0tbcc73do402g`: if no deploy for the new commit has started within two minutes, call `trigger_deploy` for it, and confirm it goes live. Never change the service's environment variables (they hold the user accounts).
4. claude.ai copy (artifact `fae8f453-ae9c-460b-b509-d3813234b466`, "Fund Desk"): if the artifact tools are available, `get_artifact` for its version, then `publish_files` in patch mode with every changed `learn/data/*.json` as `data/<name>.json`. Do not send its `index.html` unless `learn/index.html` changed; if it did, send `learn/index.html` with the `<meta name="fd-mode" content="learn">` line removed and the title set to `Fund Desk · Icons &amp; Company`.

## 6. Summary
End with a short plain summary: what was refreshed, numbers added/updated/removed per dataset, notable new deals (raising now), anything that failed or was skipped and why.

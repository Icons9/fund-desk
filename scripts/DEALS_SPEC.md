# Research spec v2: companies seeking or likely to seek funding, by sector and region

Research date: 20 November 2026. You cover ONE sector and ONE region, named in your task.

## Sector definitions (stay inside yours; skip companies that belong to another)
- Deeptech: quantum, semiconductors and photonics, advanced materials, robotics and automation hardware, energy and climate hardware (batteries, hydrogen, fusion, carbon capture, grid), industrial and synthetic biology outside human health, advanced manufacturing. Not AI software, not space or aviation, not defence, not maritime, not healthcare.
- AI: companies whose core product is AI: foundation and vertical models, AI agents and applications, AI infrastructure and tooling (MLOps, inference, data, AI chips counted here only if the company sells primarily to AI workloads), AI safety and evaluation. Not general SaaS that merely adds AI features.
- Aerospace: aviation (eVTOL, electric and hydrogen aircraft, drones for civil use, airline and airport tech, sustainable aviation fuel) and space (launch, satellites, earth observation, in-orbit services, space data).
- Maritime: shipping and port technology, ship decarbonisation and alternative fuels, vessel design and autonomy, maritime logistics and chartering software, ocean data, offshore and blue-economy tech, maritime insurance and finance tech.
- Defence: defence and dual-use technology, security, autonomy and drones for defence, C4ISR, electronic warfare, space defence, cyber for defence and critical infrastructure, simulation and training.

## Region definitions
- europe: EU-27, UK, Switzerland, Norway, Iceland
- usa: United States (and Canada if clearly in scope; note it)
- asia: India, China, Japan, South Korea, Singapore, Southeast Asia, Taiwan, Hong Kong, Australia, New Zealand
- em_africa: Middle East and Gulf, Israel, Turkey, Latin America, Africa, Central Asia

## Output
Write your own helper script in your own folder /home/claude/work/<your-file-stem>/ and never use or overwrite shared paths such as /home/claude/scripts. Append one JSON object per company, one per line, to the JSONL file named in your task (Python json.dumps(..., ensure_ascii=False), append mode, write in batches as you go). Fields (use "" when unknown, never invent):

- company, website, country (English name), city
- sector: exactly your sector name ("Deeptech", "AI", "Aerospace", "Maritime", "Defence")
- subsector: a short category inside the sector (e.g. "Quantum", "Batteries", "Launch", "eVTOL", "Port tech", "Counter-drone", "AI agents")
- niche: short phrase on what they make
- founded: year
- stage: "Pre-seed", "Seed", "Series A", "Series B", "Series C+", "Growth", "Grant-funded only", "Unknown"
- last_round_type, last_round_amount_eur (number in EUR millions; convert approximately and say so in notes), last_round_date (YYYY-MM or YYYY), total_raised_eur_m, key_investors (comma-separated)
- signal: one of
  - "A - Actively raising": open round, live crowdfunding or deal-platform campaign, public statement or credible press that they are raising now
  - "B - Due to raise": last priced round 18+ months ago (seed 12+ months), stated plan to raise in 2026/2027, bridge or convertible recently, OR a significant product launch in the last ~6 months with no round since (say so in evidence)
  - "C - Recently funded": closed a round since about Nov 2025
  - "D - Non-dilutive / grant": grants or government contracts only (EIC, SBIR/STTR, DARPA/AFWERX, ESA BIC, national programmes) with little or no equity found
- signal_evidence: one short sentence in your own words
- product_launch: if the company launched or announced a significant new product in 2026, a short phrase with month, e.g. "2026-09: launched X200 battery module"; else ""
- ceo_or_founder, employees (approx range), source_url (best URL backing the funding info), notes

## Rules
- Aim for 60–120 distinct companies for your sector and region. Every row needs a real source. Do not fabricate companies, amounts or dates; leave unknowns blank.
- Prefer 2025–2026 information. Exclude acquired, publicly listed (except clearly raising micro-caps, noted) and defunct companies, and household-name late-stage giants valued over about $10bn unless clearly raising.
- Use many query angles: sector + region/country + "raises"/"seed"/"Series A"/"funding round" + 2026; funding trackers and roundups (Tech.eu, Sifted, TechCrunch, Crunchbase News, Inc42, Entrackr, DealStreetAsia, e27, Wamda, MAGNiTT, Disrupt Africa, TechCabal, LAVCA, Contxto, SpaceNews, Payload, Breaking Defense, Defense One, Splash247, TradeWinds, Maritime Executive, The Robot Report, Quantum Insider, Canary Media, CTVC), accelerator cohorts (Y Combinator, Techstars, ESA BIC, NATO DIANA, AFWERX, PortXL, Plug and Play), government grant lists (EIC, SBIR, DIANA), and local-language press where useful.
- The web search budget is shared and limited. Prefer roundup and list pages that name many companies at once, then WebFetch them. Don't spend searches confirming single facts.
- Work only with WebSearch and WebFetch. Don't ask questions; make sensible calls.
- Finish with: rows written, file path, and 3–5 lines on coverage gaps.

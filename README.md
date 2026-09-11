# mpua-lead-engine

Backend + database foundation (stage 1). No parsers, UI, Telegram, Google Maps
integration, or enrichment logic exist yet — this stage only provides the
FastAPI app skeleton, SQLAlchemy models, and Alembic migrations.

## Stack

- Python 3.11
- FastAPI + uvicorn
- SQLAlchemy 2.x
- Alembic
- PyMySQL (MySQL/MariaDB driver)
- Pydantic / pydantic-settings
- pytest / pytest-asyncio

## Project layout

```
app/
  api/        FastAPI routers (health check, etc.)
  core/       settings/config
  models/     SQLAlchemy ORM models
  schemas/    Pydantic response/request schemas
  services/   business logic (empty in this stage)
  main.py     FastAPI app entrypoint
db/
  base.py     SQLAlchemy declarative Base
  session.py  engine + session factory
migrations/   Alembic environment and versions
tests/        pytest suite
```

## Windows + XAMPP setup

### 1. Enable MySQL in XAMPP

Open **XAMPP Control Panel** and click **Start** next to the **MySQL**
module. Wait until the status turns green and a PID/port (3306) appears.

### 2. Create the database

Open a terminal and run (adjust the path to your XAMPP install if different):

```bash
"C:\xampp\mysql\bin\mysql.exe" -u root -e "CREATE DATABASE mpua_lead_engine CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

If you plan to run the test suite against a real database (recommended, see
below), also create a separate test database:

```bash
"C:\xampp\mysql\bin\mysql.exe" -u root -e "CREATE DATABASE mpua_lead_engine_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

Alternatively use phpMyAdmin (`http://localhost/phpmyadmin`) to create the
databases through the UI.

### 3. Create your `.env` file

Copy the example file and adjust credentials if your XAMPP MySQL root user
has a password (by default it does not):

```bash
copy .env.example .env
```

`.env` content:

```
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=mpua_lead_engine
DB_USER=root
DB_PASSWORD=

TEST_DB_HOST=127.0.0.1
TEST_DB_PORT=3306
TEST_DB_NAME=mpua_lead_engine_test
TEST_DB_USER=root
TEST_DB_PASSWORD=
```

Never commit `.env` — only `.env.example` is tracked.

### 4. Install Python dependencies

Create a virtual environment and install the project (including dev/test
dependencies):

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

### 5. Run Alembic migrations

With the virtual environment active and `.env` configured:

```bash
alembic upgrade head
```

This creates all tables (`jobs`, `sources`, `raw_records`, `companies`,
`company_phones`, `company_emails`, `company_websites`, `addresses`,
`social_links`) in the `mpua_lead_engine` database.

If you created a separate test database, apply the same migration there too
(PowerShell):

```powershell
$env:DB_NAME="mpua_lead_engine_test"; alembic upgrade head
```

### 6. Run the FastAPI app

```bash
uvicorn app.main:app --reload
```

Then check `http://127.0.0.1:8000/health` — it should return
`{"status": "ok"}`.

### 7. Run the tests

```bash
pytest
```

The test suite (`tests/`) connects to the database configured by
`TEST_DB_*` variables in `.env` and exercises the ORM models inside rolled-back
transactions, so no test data is left behind. Tests intentionally run against
real MySQL/MariaDB (not SQLite) so ORM behavior matches production.

## Data model overview

- **Job** — a lead-generation job/run (status, query, target count, requested
  fields). Has many `Source` and `RawRecord`.
- **Source** — a place data was collected from (Google Maps, website,
  directory, manual entry, ...), optionally tied to a `Job`.
- **RawRecord** — raw scraped payload (JSON) tied to a `Job`/`Source`, pending
  further processing.
- **Company** — the canonical deduplicated business entity. Has many
  `CompanyPhone`, `CompanyEmail`, `CompanyWebsite`, `Address`, `SocialLink`.
- **CompanyPhone / CompanyEmail / CompanyWebsite / Address / SocialLink** —
  contact/attribute records for a company, each optionally linked back to the
  `Source` it was observed from.

### Cascade behavior

- Deleting a `Job` cascades to its `Source` and `RawRecord` rows.
- Deleting a `Company` cascades to all of its phones, emails, websites,
  addresses, and social links.
- Deleting a `Source` does **not** delete the `Company` or its contact data —
  the `source_id` foreign key on contact tables uses `ON DELETE SET NULL`, so
  the contact record survives with its provenance link cleared.

## Not included in this stage

Parsers (Google Maps, Google Search, websites), enrichment, deduplication
logic, Telegram bot, UI/dashboard. These belong to later stages.

## OpenStreetMap discovery source (MLE-003)

`sources/osm/` implements `OpenStreetMapAdapter`, the first real discovery
source, on top of the public Overpass API.

**Public Overpass endpoint = development / validation source.** Do not run
production or high-volume traffic against `https://overpass-api.de` — this
adapter caps its own concurrency at 1 in-flight request and does at most 2
retries with backoff. For real production use, point `OVERPASS_API_URL` (see
`.env.example`) at a self-hosted Overpass instance or a local OSM extract.

### Attribution / licensing

```
Contains information from OpenStreetMap,
which is made available under the Open Database License (ODbL).
```

Any downstream export or publication built from OSM-derived data must carry
this attribution and comply with ODbL share-alike requirements. This project
does not implement a license-compliance engine — that is a separate concern
from data collection.

### Supported presets (v0.1)

Only presets backed by an established, documented OSM tag are implemented;
nothing is guessed:

| preset key   | OSM tag               | notes |
|--------------|------------------------|-------|
| `dentist`    | `amenity=dentist`      | standard OSM tag for dental clinics |
| `car_repair` | `shop=car_repair`      | standard tag for garages/STO |
| `car_parts`  | `shop=car_parts`       | standard tag for auto parts stores |
| `hvac`       | *(unsupported)*        | no single reliable canonical OSM tag |
| `construction` | *(unsupported)*      | no single reliable canonical OSM tag |

### Geography

`region` is treated as a city name. For the 5 MLE-003 benchmark cities
(Dnipro, Kyiv, Lviv, Odesa, Vinnytsia), the adapter queries by a static
bounding-box fixture (`sources/osm/cities.py`) — `area["name"=...]`
resolution proved unreliable against the public Overpass instance during
development. Any other city falls back to Overpass area-name resolution,
which may legitimately return 0 results if the area can't be resolved (not
an error).

## Normalization layer (MLE-004)

`processing/normalization/` turns a `RawCandidate` into a `NormalizedCandidate`
(pure Pydantic transport model, not persisted): deterministic, network-free,
DB-free text/phone/email/website/address normalization used later for
dedup/matching. It does **not** create a `Company` — that decision belongs to
a future dedup/matching stage.

- `phone.py` — via `phonenumbers`, default region `UA`, E.164 output;
  unparseable/invalid numbers become `phone_normalized=None` (never guessed).
- `email.py` — trim + lowercase + basic syntax check; no SMTP/DNS/MX lookup.
- `website.py` — canonical absolute URL + stable domain (no `www.`, IDNA-safe,
  no fragment); no HTTP requests, no alive/dead check.
- `company_name.py` — `canonical_name` is trim-only; `normalized_name` is
  lowercased, Unicode-normalized, with Ukrainian legal-entity prefixes
  (ТОВ/ФОП/ПП/ПРАТ/ПАТ/АТ/ДП/КП) stripped as whole tokens only.
- `address.py` — plain text cleanup (trim/lowercase/collapse spaces); no
  geocoding, no street-name correction.

Run `pytest` (normalization tests are included in the default run) and the
real-data benchmark:

```bash
python scripts/benchmark_normalization.py
```

## Identity resolution & deduplication (MLE-005)

`processing/identity/` decides whether a `NormalizedCandidate` is a **new**
Company, **matches** an existing one (auto-merge), or needs human **review**
(never auto-merged). Only deterministic, exact-value signals are used — no
fuzzy/AI/embedding matching.

Pipeline after MLE-005:

```
RawCandidate -> Normalization -> NormalizedCandidate
             -> Identity Resolution -> Company -> Contacts / Sources
```

### Scoring policy (see `processing/identity/signals.py`)

| signal | weight | notes |
|---|---|---|
| same `Source.source_type` + `external_id` | 100 | idempotency: reprocessing the same raw record never creates a duplicate Company |
| same normalized phone | 100 | |
| same website domain | 100 | domain must not be in the shared-domain denylist |
| same exact email address | 90 | the *domain* of a free/consumer email provider is never used as a signal — only the exact address |
| same normalized_name + normalized_address (both exact) | 90 | |
| same normalized_name + normalized_city (both exact) | 70 | intentionally capped below MATCH — many businesses share a generic name in one city |

Decision thresholds: **score >= 90 -> MATCH** (auto-merge), **60-89 -> REVIEW**
(never persisted as a Company), **< 60 -> NEW**.

Shared domains (never a company-identity signal): `facebook.com`,
`instagram.com`, `linkedin.com`, `youtube.com`, `tiktok.com`, `t.me`,
`telegram.me`, `prom.ua`, `olx.ua`, `google.com`.

Free email domains (exact address can still match; the domain alone never
does): `gmail.com`, `ukr.net`, `i.ua`, `meta.ua`, `outlook.com`,
`hotmail.com`, `yahoo.com`.

**Principle:** a false positive (merging two different real companies) is
worse than a false negative (a missed duplicate, left as REVIEW/NEW).
Auto-merge only fires on strong, deterministic signals.

### Provenance & idempotency

A `company_sources` association table (`company_id`, `source_id`, unique
pair) records every `Source` that confirmed a Company — deleting a `Source`
never deletes a `Company`. `CompanyPhone`/`CompanyEmail`/`CompanyWebsite`
each carry a `UNIQUE(company_id, <value>)` constraint (MySQL allows multiple
`NULL`s in a unique index, so unset values never collide) so reprocessing
the same candidate never duplicates a contact row.

### Running the identity resolution benchmarks

```bash
# Real-data idempotency check: OSM dentist/Dnipro/limit=50, run twice
python scripts/benchmark_osm_identity.py

# Synthetic 100-candidate duplicate benchmark (precision/recall) — part of
# the normal pytest run:
pytest tests/test_identity_synthetic_benchmark.py -v -s
```

## End-to-end job orchestrator (MLE-008)

`app/services/job_orchestrator.py` is the single entrypoint that replaces
running OSM/Tavily/normalization/identity/enrichment by hand. One `Job`
(a specification: preset, regions, which sources, limits, whether to
enrich) can be `run_job()`'d any number of times; each execution is a
`JobRun` with its own `JobStageRun` history:

```
CREATED
  -> DISCOVERY_OSM -> DISCOVERY_WEB_SEARCH
  -> NORMALIZATION -> IDENTITY_RESOLUTION
  -> WEBSITE_ENRICHMENT
  -> FINALIZING
  -> COMPLETED / FAILED / CANCELLED
```

- **Soft failure**: one discovery source being unavailable (OSM timeout,
  missing `TAVILY_API_KEY`, an unsupported OSM preset like `hvac`) marks
  that stage `skipped`/`failed` with a reason, adds a warning, and the
  Job still completes on whatever source(s) worked.
- **Fatal failure**: an exception in normalization, identity resolution,
  or website enrichment marks the Job `FAILED` with `error` set.
- **Cancellation**: `Job.status` is checked before each stage; a
  cancelled Job stops before starting the next stage.
- Each stage commits its own persisted state (discovery, identity, and
  enrichment already commit internally) — a website timeout never rolls
  back discovery.
- A Company matched by both OSM and Tavily is enriched exactly once (the
  enrichment batch is built from a `set` of company ids).
- `JobRun.metrics` / each `JobStageRun.metrics` are persisted as JSON —
  see `job_orchestrator.py` for the exact shape (raw_candidates,
  unique_companies, new/matched/review, coverage percentages, per-source
  metrics, cost, runtime).

### CLI

```bash
python scripts/run_job.py --preset dentist --region Kyiv \
    --osm-limit 100 --tavily-limit 20 --enrich

python scripts/run_job.py --preset hvac --region Kyiv --region Lviv \
    --no-osm --tavily-limit 20 --enrich
```

### API (blocking execution — see Technical debt below)

```
POST /jobs                  create a Job specification
POST /jobs/{id}/run         run it end to end (blocking, returns final metrics)
GET  /jobs/{id}             fetch a Job
GET  /jobs/{id}/runs        list its JobRuns
GET  /job-runs/{id}         fetch one JobRun
```

## Second discovery source: Tavily Web Search (MLE-007)

`sources/tavily_search/` implements `TavilySearchAdapter`, a second,
independent `SourceAdapter` (`source_type=web_search`) on top of the
[Tavily Search API](https://tavily.com/) — **Basic Search only** (no
generated answer, no advanced search, no raw content, no crawl/extract).
It is used solely to discover official company websites, never as a
source of rating/reviews.

```
Tavily -> RawCandidate -> Normalization -> Identity Resolution -> Company -> Website Enrichment
```

### Why Tavily instead of Brave

Brave Search API was evaluated first but its developer dashboard returned
HTTP 403 for the operator, so it was dropped as a project dependency
before any code was committed. Tavily has a working free tier (1000
credits/month, Basic Search = 1 credit) and is used instead.

### Config

```env
TAVILY_API_KEY=
TAVILY_API_URL=https://api.tavily.com/search
TAVILY_SEARCH_DEPTH=basic
TAVILY_MAX_RESULTS=20
TAVILY_TIMEOUT=20
TAVILY_MAX_REQUESTS_PER_JOB=20
TAVILY_COST_PER_CREDIT_USD=0.008
```

`TAVILY_MAX_REQUESTS_PER_JOB` is a hard budget guard — once reached, the
client raises `TavilySearchBudgetExceeded` and the adapter stops, returning
whatever candidates it already collected instead of continuing to spend
credits.

### Query presets

Same philosophy as the OSM preset registry (`sources/tavily_search/
query_builder.py`) — 2 query variants per preset, `dentist` / `car_repair`
/ `car_parts` / `hvac`. Unlike OSM, `hvac` works well here since it's plain
text search rather than an OSM tag lookup.

### Filtering (`sources/tavily_search/filters.py`)

Reuses the MLE-005 shared-domain denylist (facebook.com, instagram.com,
linkedin.com, youtube.com, tiktok.com, t.me, prom.ua, olx.ua, google.com)
plus wikipedia.org/search-engine domains, a small known-directory list,
file extensions (.pdf/.doc/...), search-result-page URLs, and a listicle/
news/blog title-denyword heuristic (топ, кращі, рейтинг, список, каталог,
огляд, новини, article, blog). Within one search run, results are
deduplicated by normalized domain before filtering. This is a heuristic,
not a classifier — false negatives (an unfiltered directory slipping
through) are documented debt, not a crash risk.

### Snippet policy

Tavily's `content` (snippet) can be stale and is preserved **only** inside
`RawCandidate.raw_payload` for provenance — `RawCandidate.description` is
always left `None` for Tavily results, so a snippet never gets written
into `Company.description` automatically.

### Cost tracking

Every `TavilySearchAdapter.search()` call exposes `last_api_requests`,
`last_credits_used`, `last_estimated_cost_usd`, `last_results_received`,
and `last_unique_domains` for reporting (adapter instance attributes —
the `SourceAdapter` contract itself is unchanged).

### Running the benchmarks

```bash
# Real API integration test (skipped, not failed, without TAVILY_API_KEY)
pytest -m tavily_integration tests/test_tavily_search_integration.py -v -s

# Manual relevance QA sample (20 candidates, title + website)
python scripts/manual_qa_tavily.py

# Combined OSM + Tavily benchmark: baseline -> merge -> enrich -> cost KPIs
python scripts/benchmark_combined_osm_tavily.py
```

## Website enrichment (MLE-006)

`enrichment/website/` crawls a Company's own website (when it has one) to
find additional phones/emails/socials and merges them into the *existing*
Company — it never creates or merges Companies, and never reruns identity
resolution.

```
Company -> website -> homepage + up to 4 discovered contact/about pages
        -> extract phone/email/social (tel:/mailto:/JSON-LD/microdata/visible text)
        -> normalize (reuses MLE-004) -> idempotent CompanyPhone/CompanyEmail/SocialLink
```

### Config

```env
WEBSITE_TIMEOUT=15
WEBSITE_MAX_PAGES=5
WEBSITE_MAX_CONCURRENCY=5
WEBSITE_USER_AGENT=MPUA-Lead-Engine/0.1
WEBSITE_MAX_RESPONSE_BYTES=5000000
```

### Crawl scope

- Same-domain only (`www.` stripped for comparison); external links are
  extracted (socials) but never followed.
- Homepage + up to `WEBSITE_MAX_PAGES - 1` links whose href/text match a
  contact/about keyword list (EN + UA: contact(s), kontakt(y), контакт(и),
  зв'язок, about(-us), про нас, pro-nas), contact-priority first.
  `/login`, `/signin`, `/cart`, `/checkout`, `/search`, `/wp-admin`,
  `/admin` paths are skipped. The `visited` set uses a normalized URL
  (fragment + `utm_*`/`fbclid`/`gclid` stripped) so crawl loops can't occur.
- A Company's own website is never picked from the shared-domain denylist
  (facebook.com, instagram.com, t.me, prom.ua, olx.ua, ...) reused from
  MLE-005 — those are never treated as "the company's website".
- Retry policy: timeout/network error -> up to 2 retries; HTTP 429 -> 1
  retry with backoff; HTTP 5xx -> 1 retry; HTTP 404/other 4xx -> no retry.
- Only `text/html`/`application/xhtml+xml` responses are parsed; binary
  content is ignored. Response bodies are capped at
  `WEBSITE_MAX_RESPONSE_BYTES` (truncated, not crashed).
- No JS rendering (no Playwright), no `robots.txt` fetching — the crawl is
  bounded by the page limit + same-domain + skip-path rules instead
  (documented debt, see below).

### Running the benchmark

```bash
python scripts/benchmark_website_enrichment.py
```

### Running the integration tests / benchmark

```bash
# Real Overpass request + end-to-end MySQL persistence (excluded from the
# default `pytest` run, see pyproject.toml addopts)
pytest -m integration tests/test_osm_integration.py -v

# Manual 3-scenario coverage benchmark (dentist/Dnipro, car_repair/Kyiv,
# car_parts/Lviv), prints returned/with_name/with_phone/with_website/with_email/runtime
python scripts/benchmark_osm_adapter.py
```

## Technical debt (as of MLE-008)

- `POST /jobs/{id}/run` executes the whole pipeline **synchronously**
  (blocking the request) — there is no queue or background worker yet.
  Fine for local/internal use; a real async execution model (Celery/RQ/
  similar) is a future stage, not introduced here to keep scope tight.
- No resume-from-stage: `JobRun`/`JobStageRun` are structured so this
  could be added later, but a failed/cancelled run must currently be
  re-run from the start (a new `JobRun`).
- No scheduler — a `Job` is only ever triggered manually via the CLI or
  `POST /jobs/{id}/run`.
- No XLSX/CSV export (planned for `MLE-009`).
- `http_requests` in `JobRun.metrics` is an approximation (OSM: one
  Overpass call assumed per region; Tavily: actual tracked API requests;
  website enrichment: `pages_requested`) rather than a byte-for-byte
  request log.

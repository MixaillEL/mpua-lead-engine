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

### Running the integration tests / benchmark

```bash
# Real Overpass request + end-to-end MySQL persistence (excluded from the
# default `pytest` run, see pyproject.toml addopts)
pytest -m integration tests/test_osm_integration.py -v

# Manual 3-scenario coverage benchmark (dentist/Dnipro, car_repair/Kyiv,
# car_parts/Lviv), prints returned/with_name/with_phone/with_website/with_email/runtime
python scripts/benchmark_osm_adapter.py
```

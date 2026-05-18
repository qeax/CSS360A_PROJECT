# CSS360 Car Flip

Stack: FastAPI backend, static frontend (Nginx), MariaDB in Docker, Traefik TLS in production.

## Backend layout

- [backend/app/main.py](backend/app/main.py) — FastAPI app and routers
- [backend/app/config.py](backend/app/config.py) — environment and database URL
- [backend/app/db.py](backend/app/db.py) — SQLAlchemy engine and sessions
- [backend/app/models/car.py](backend/app/models/car.py) — `cars` table (includes fields reserved for future eBay sync)
- [backend/app/repositories/cars.py](backend/app/repositories/cars.py) — DB queries and filter helpers
- [backend/app/api/routes/](backend/app/api/routes/) — HTTP routes (`/cars`, `/health`, `/auth/*` Microsoft Entra OAuth)
- [backend/app/services/flip.py](backend/app/services/flip.py) — ROI / net profit
- [backend/app/integrations/ebay/](backend/app/integrations/ebay/) — placeholder for eBay client
- [backend/app/demo_seed.py](backend/app/demo_seed.py) — deterministic demo inventory generator (DB insert and/or in-memory views)
- [backend/app/seed.py](backend/app/seed.py) — optional DB seed (explicit write of generated demo when enabled)
- [backend/app/purge_demo.py](backend/app/purge_demo.py) — delete demo rows (`source=demo`) when switching to real data

## Database

- Docker Compose service `db` stores data in the named volume `mariadb_data` (persists across container restarts).
- The backend reads connection settings from environment variables (typically a `.env` file on the server that is **not** committed to git).

## Configuration and secrets (production)

All deployment environment variables are supplied through **GitHub Actions secrets** (same pattern as database credentials). The deploy workflow writes a runtime `.env` on the VPS before `docker compose up`.

Configure these repository secrets for CD:

| Secret | Purpose |
|--------|---------|
| `SSH_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY` | SSH access to the server |
| `APP_ENV` | e.g. `production` |
| `DB_HOST` | e.g. `db` (Compose service name) |
| `DB_PORT` | e.g. `3306` |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `MYSQL_ROOT_PASSWORD` | MariaDB and app DB user |
| `SEED_ON_START` | `true` or `false` — run [backend/app/seed.py](backend/app/seed.py) on container start when the `cars` table is empty (usually a no-op unless you enable DB writes below) |
| `PURGE_DEMO_ON_START` | Optional `true` — before seed, run [backend/app/purge_demo.py](backend/app/purge_demo.py) once to delete rows with `source=demo` (child tables cascade) |
| `AZURE_AD_TENANT_ID` | Microsoft Entra ID directory (tenant) ID |
| `AZURE_AD_CLIENT_ID` | App registration application (client) ID |
| `AZURE_AD_CLIENT_SECRET` | App registration client secret (backend only) |
| `AZURE_AD_REDIRECT_URI` | Must match Entra Web redirect URI exactly (e.g. `https://<your-domain>/api/auth/callback`) |
| `AUTH_SESSION_SECRET` | Random secret used to sign browser session cookies |
| `ALLOWED_EMAIL_DOMAIN` | Optional; if set (e.g. `uw.edu`), only emails ending with `@` that domain may sign in |
| `APP_PUBLIC_HOST` | Public hostname for Traefik routing (no scheme), e.g. `app.example.com` |
| `CORS_ORIGINS` | Required in production: comma-separated browser origins (e.g. `https://app.example.com`) |

Future variables (for example eBay API keys) follow the same rule: add a GitHub secret, pass it into the workflow `env` block, append a line to the `cat > .env <<EOF` script, and list the name in `envs` for `appleboy/ssh-action`.

Local development: keep a private `.env` on your machine (ignored by git); do not commit credentials.

**Quick start without Entra ID:** see [LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md). Copy [.env.example](.env.example) to `.env`, set `DEV_AUTH_BYPASS=true`, use [docker-compose.override.example.yml](docker-compose.override.example.yml), and run `docker compose up --build`. Teammates without production secrets can sign in locally via the dev bypass (never enabled in production).

**Docker on Windows/mac:** copy [docker-compose.override.example.yml](docker-compose.override.example.yml) to `docker-compose.override.yml` (gitignored) to publish ports `8080` / `8000` for the static site and API. Production on Ubuntu should **not** use that file—only [docker-compose.yml](docker-compose.yml) and Traefik.

### Public repository safety rules

- Never commit real credentials, private keys, callback secrets, or production hostnames that are not already public.
- Keep all secret values only in GitHub Actions Secrets and server runtime `.env`.
- Use placeholders (`<your-domain>`, `<secret>`, `<tenant-id>`) in documentation examples.
- Rotate `AZURE_AD_CLIENT_SECRET` and `AUTH_SESSION_SECRET` immediately if a leak is suspected.
- Restrict `CORS_ORIGINS` to trusted app origins only (avoid wildcard origins in production).
- Ensure `AZURE_AD_REDIRECT_URI` in GitHub Secrets exactly matches the Entra App Registration value.

## Migrations and seed

The backend container runs `alembic upgrade head` on startup ([backend/entrypoint.sh](backend/entrypoint.sh)), including migration `005_vehicle_title_on_cars` which adds nullable `vehicle_title` on `cars`.

### Demo catalog without filling MySQL

When the `cars` table has **no rows**, `GET /api/cars` and `GET /api/cars/meta` use the same **deterministic in-memory** demo catalog as the generator (~100 vehicles by default). Nothing is inserted; the database stays empty for future real imports.

- **`DEMO_IN_MEMORY_WHEN_EMPTY`** — default `true`. Set to `false` if you want an empty API when there are no DB rows.
- **`DEMO_SEED_COUNT`** — how many in-memory (or DB) demo vehicles (default `100`, max `500`).

### Optional: write demo rows into the database

`python -m app.seed` (or `SEED_ON_START=true` on container start) only **writes** to MySQL when **`SEED_WRITE_DEMO_TO_DB=1`** — insert generated demo cars + satellites (same data shape as in-memory). Otherwise the seed script prints a short message and exits without inserts.

Manual run (same rules as on start):

```bash
docker compose exec backend python -m app.seed
```

To remove persisted demo rows (`source=demo`) on each deploy before the rest of startup, set **`PURGE_DEMO_ON_START=true`** (Compose / `.env` / GitHub secret `PURGE_DEMO_ON_START`). The entrypoint runs `python -m app.purge_demo` before `app.seed`. You can also run purge manually:

```bash
docker compose exec backend python -m app.purge_demo --dry-run
docker compose exec backend python -m app.purge_demo
```

### Removing mock / demo data later

When you start loading real data, remove demo rows as in the purge commands in the previous subsection.

This deletes only rows where **`source=demo`**. It does not touch rows you inserted with another `source`.

If you seeded before the `demo` marker existed and old rows still have `source=manual`, either update them in SQL (for example set `source='demo'` on rows you know are mock) or delete them selectively; do not run a blind delete on all `manual` rows if you already have real manual entries.

Local Alembic (from `backend/` with the same env as the app):

```bash
cd backend
alembic upgrade head
```

## Frontend

Static files live under [frontend/](frontend/). Global styles load from [frontend/styles.css](frontend/styles.css), which pulls in partials under [frontend/css/](frontend/css/).

### `GET /api/cars`

Returns JSON **`{ "items": [...], "total": <number> }`**. Filters apply to the **full** result set; the backend sorts, then returns a page.

| Query | Notes |
|--------|--------|
| `limit` | Page size (default **30**, max **50**) |
| `offset` | Starting index (default **0**) |
| `sort_by` | e.g. `roi`, `net_profit`, `price` |
| `sort_order` | `asc` or `desc` (default `desc`) |
| `makes` | Repeatable; OR match on brand (case-insensitive). Legacy single `make` is still accepted. |
| `min_mileage` / `max_mileage` | Optional mileage bounds (cars with null mileage are excluded when these filters are set). |
| `vehicle_titles` | Repeatable; OR match on `vehicle_title` (case-insensitive). |
| `q` | Soft match on brand, model, location, aspects, etc. (substring, any token, or fuzzy brand+model). |
| `radius_mi` | Optional; with `anchor_lat` / `anchor_lng`, filters by distance (**miles**). `radius_km` is still accepted for compatibility. |

The dashboard appends pages with **Load more** (same filters and sort, larger `offset`).

`GET /api/cars/meta` exposes slider bounds, **mileage** bounds, **makes**, **vehicle_titles**, and location options for the filter UI.

Vendor icons used in the UI also live under [frontend/icons/](frontend/icons/) (MIT-licensed Heroicons-derived paths; each file cites the source).

## CI, lint, tests, and security

GitHub Actions [.github/workflows/ci.yml](.github/workflows/ci.yml) on every **push** and **pull request** to `main`:

- **Ruff** — lint and format check  
- **pip-audit** — known vulnerabilities in locked dependency names from `requirements.txt` + `requirements-dev.txt`  
- **Bandit** — security-oriented static analysis on `app/`  
- **pytest** — tests against **MariaDB 10.11**

[Dependabot](.github/dependabot.yml) opens weekly PRs for **pip** (`backend/`), **GitHub Actions**, and the **backend Docker** image.

Local (from `backend/`):

```bash
cd backend
python -m pip install -r requirements.txt -r requirements-dev.txt
ruff check .
ruff format --check .
pip-audit -r requirements.txt -r requirements-dev.txt
bandit -r app -ll
pytest
```

Optional git hooks — uses [.pre-commit-config.yaml](.pre-commit-config.yaml) (Ruff with auto-fix, Ruff format, Bandit, pip-audit).

### Setting up pre-commit (one-time per clone)

From the **repository root** (not `backend/`):

```bash
python -m pip install pre-commit
pre-commit install
```

That installs a **git `pre-commit` hook**. On every `git commit`, hooks run on staged files; Ruff may **edit** files in place, then you **stage again** and commit if something changed:

```bash
git add -u
git commit -m "your message"
```

First-time or “fix the whole tree” pass (optional):

```bash
pre-commit run --all-files
```

Then review diffs, `git add`, and commit.

**Note:** Hooks run only on **your machine** after `pre-commit install`. They do not change what other contributors do unless everyone installs them. CI on GitHub remains the shared gate.

## Development Standards (v1.0)
- **Branching:** Do not push directly to `main`. Create a feature branch first.
- **Code Reviews:** Every Pull Request (PR) requires at least one approval from a teammate.
- **Testing:** CI runs Ruff, pip-audit, Bandit, and pytest; keep them green before merging.
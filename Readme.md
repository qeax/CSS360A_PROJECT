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
- [backend/seeds/cars_seed.json](backend/seeds/cars_seed.json) — optional demo seed data (not loaded from Python code)
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
| `SEED_ON_START` | `true` or `false` — run [backend/app/seed.py](backend/app/seed.py) on container start when the `cars` table is empty |
| `AZURE_AD_TENANT_ID` | Microsoft Entra ID directory (tenant) ID |
| `AZURE_AD_CLIENT_ID` | App registration application (client) ID |
| `AZURE_AD_CLIENT_SECRET` | App registration client secret (backend only) |
| `AZURE_AD_REDIRECT_URI` | Must match Entra Web redirect URI exactly (e.g. `https://<your-domain>/api/auth/callback`) |
| `AUTH_SESSION_SECRET` | Random secret used to sign browser session cookies |
| `ALLOWED_EMAIL_DOMAIN` | Optional; if set (e.g. `uw.edu`), only emails ending with `@` that domain may sign in |
| `CORS_ORIGINS` | Optional comma-separated allowed browser origins; if unset in production, set it to your public app origin (for example `https://<your-domain>`) |

Future variables (for example eBay API keys) follow the same rule: add a GitHub secret, pass it into the workflow `env` block, append a line to the `cat > .env <<EOF` script, and list the name in `envs` for `appleboy/ssh-action`.

Local development: keep a private `.env` on your machine (ignored by git); do not commit credentials.

### Public repository safety rules

- Never commit real credentials, private keys, callback secrets, or production hostnames that are not already public.
- Keep all secret values only in GitHub Actions Secrets and server runtime `.env`.
- Use placeholders (`<your-domain>`, `<secret>`, `<tenant-id>`) in documentation examples.
- Rotate `AZURE_AD_CLIENT_SECRET` and `AUTH_SESSION_SECRET` immediately if a leak is suspected.
- Restrict `CORS_ORIGINS` to trusted app origins only (avoid wildcard origins in production).
- Ensure `AZURE_AD_REDIRECT_URI` in GitHub Secrets exactly matches the Entra App Registration value.

## Migrations and seed

The backend container runs `alembic upgrade head` on startup ([backend/entrypoint.sh](backend/entrypoint.sh)).

- Create or upgrade schema: happens automatically on deploy.
- Fill demo rows once: set secret `SEED_ON_START` to `true` for the first deploy, then set it back to `false`, or run manually on the server:

```bash
docker compose exec backend python -m app.seed
```

The seed only inserts when the `cars` table is empty.

Demo rows are stored with **`source=demo`** (see [backend/seeds/cars_seed.json](backend/seeds/cars_seed.json)). Real data should use another value (for example `ebay`, `import`, or `manual` for hand-entered listings).

### Removing mock / demo data later

When you start loading real data, remove demo rows once:

```bash
docker compose exec backend python -m app.purge_demo --dry-run
docker compose exec backend python -m app.purge_demo
```

This deletes only rows where **`source=demo`**. It does not touch rows you inserted with another `source`.

If you seeded before the `demo` marker existed and old rows still have `source=manual`, either update them in SQL (for example set `source='demo'` on rows you know are mock) or delete them selectively; do not run a blind delete on all `manual` rows if you already have real manual entries.

Local Alembic (from `backend/` with the same env as the app):

```bash
cd backend
alembic upgrade head
```

## Frontend

Static files live under [frontend/](frontend/). Global styles load from [frontend/styles.css](frontend/styles.css), which pulls in partials under [frontend/css/](frontend/css/).

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
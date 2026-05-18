# Local development (no Entra ID secrets)

This guide is for anyone cloning the **public** repository who does **not** have access to the course/production `.env` or Microsoft Entra app registration.

## What you get locally

- Static UI at **http://localhost:8080**
- API at **http://localhost:8080/api/...** (proxied by nginx) or **http://localhost:8000** (backend directly)
- **Demo inventory** when the `cars` table is empty (in-memory catalog, no eBay/Entra required)
- **Dev auth bypass** — sign in without Microsoft when `DEV_AUTH_BYPASS=true` (disabled automatically in production)

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/macOS) or Docker Engine + Compose (Linux)
- Git

## 1. Clone and configure

```bash
git clone <repository-url>
cd <repo-directory>
```

Create a local env file from the template (passwords are placeholders — set your own):

```bash
cp .env.example .env
```

Ensure these lines are present (they are in `.env.example` by default):

```env
APP_ENV=development
DEV_AUTH_BYPASS=true
DEV_AUTH_EMAIL=dev@localhost
```

You do **not** need `AZURE_AD_*` or `AUTH_SESSION_SECRET` for local bypass.

## 2. Docker network and ports

Create the external network once (same name as production Compose):

```bash
docker network create proxy_network
```

Enable local port publishing (gitignored):

```bash
cp docker-compose.override.example.yml docker-compose.override.yml
```

| URL | Purpose |
|-----|---------|
| http://localhost:8080 | Frontend + `/api` proxy |
| http://localhost:8000 | Backend (optional, Swagger at `/docs`) |

## 3. Start the stack

```bash
docker compose up --build
```

Wait until `db` is healthy and `backend` has finished Alembic migrations.

## 4. Sign in (dev bypass)

1. Open **http://localhost:8080/login.html**
2. Click **Sign in with Microsoft** — with bypass enabled this hits `/api/auth/login`, creates a local dev user, and redirects to the inventory (no Microsoft prompt).
3. Alternatively open **http://localhost:8080/index.html** directly; the app calls `/api/auth/me` and should treat you as signed in.

The top bar shows `dev@localhost` (or your `DEV_AUTH_EMAIL`).

**Log out** uses `/api/auth/logout` as usual.

## 5. Verify

- http://localhost:8080/api/health — should return OK
- Inventory list loads; search bar and sidebar filters work (click **Apply** after changing filters)
- http://localhost:8000/docs — OpenAPI UI (development only)

## Demo data

By default, with an **empty** `cars` table, the API serves an in-memory demo catalog (~100 vehicles). No seed step is required.

To persist demo rows in MariaDB (optional):

```env
SEED_ON_START=true
SEED_WRITE_DEMO_TO_DB=1
```

Then restart: `docker compose up --build`.

## Running without Docker (advanced)

From `backend/` with a venv:

```bash
pip install -r requirements.txt
set APP_ENV=development
set DEV_AUTH_BYPASS=true
# Omit DB_* to use SQLite file cars_dev.db, or point DB_* at a local MariaDB
uvicorn app.main:app --reload --port 8000
```

Serve `frontend/` with any static server on port 8080 and ensure API calls go to the backend (Compose/nginx is simpler).

## Security notes

| Rule | Why |
|------|-----|
| `DEV_AUTH_BYPASS` only works when `APP_ENV` is **not** `production` | Prevents accidental open API in prod |
| Never set `DEV_AUTH_BYPASS=true` on the public server | Anyone could use the app without SSO |
| Do not commit `.env` | Keeps passwords local |

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `network proxy_network not found` | Run `docker network create proxy_network` |
| Login redirects to Microsoft then fails | Confirm `DEV_AUTH_BYPASS=true` in `.env` and restart `docker compose up` |
| `authentication_is_not_configured` on login | Bypass is off and Azure vars are missing — enable bypass or add Entra settings |
| Empty inventory | Check browser network tab for `401` on `/api/cars`; confirm bypass / session cookie |
| Port already in use | Change ports in `docker-compose.override.yml` |

## Real Microsoft sign-in (optional)

If you have your own Entra app registration:

1. Set `DEV_AUTH_BYPASS=false`
2. Fill `AZURE_AD_TENANT_ID`, `AZURE_AD_CLIENT_ID`, `AZURE_AD_CLIENT_SECRET`, `AUTH_SESSION_SECRET`
3. Set `AZURE_AD_REDIRECT_URI=http://localhost:8080/api/auth/callback` and add the same URI in Entra **Authentication** → Redirect URIs

Production deployment uses GitHub Actions secrets and **must not** use dev bypass.

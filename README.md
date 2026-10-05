# Zynox

Modern, minimal management panel for V2Ray/Xray-based proxy services.

> **Zynox** is a production-ready administration panel for managing Xray-core
> services, configurations, users, and servers — with a Telegram management bot
> and Telegram Mini App built in.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Quick Start (Docker)](#quick-start-docker)
- [Local Development](#local-development)
  - [Backend](#backend)
  - [Frontend](#frontend)
  - [Telegram Bot](#telegram-bot)
  - [Telegram Mini App](#telegram-mini-app)
- [Environment Variables](#environment-variables)
- [Database Setup](#database-setup)
- [Testing](#testing)
- [Security](#security)
- [Deployment](#deployment)
  - [Railway](#railway)
  - [Other Platforms](#other-platforms)
- [Troubleshooting](#troubleshooting)
- [Project Structure](#project-structure)

---

## Overview

Zynox provides a single pane of glass for proxy infrastructure:

- **Services** — manage Xray-core service instances (start/stop/restart, health, logs)
- **Configurations** — generate, validate, edit, duplicate, export VLESS/VMess/Trojan
  configurations across TCP, WebSocket, and xHTTP transports
- **Users & Roles** — RBAC with `admin`, `operator`, and `viewer` roles
- **Servers** — track backend servers and resource utilization (CPU / RAM / disk / network)
- **Telegram** — a management bot plus a Telegram Mini App, both gated by server-side
  Telegram authentication and backend RBAC
- **Audit Logs** — every privileged action is recorded

The UI is a dark, desktop-first dashboard built with React + TypeScript + Tailwind CSS.

### Branding

The application name is configurable through `APP_NAME` (default: `Zynox`). The value
flows to the browser title, login page, dashboard, Telegram Mini App title, and the
Telegram bot.

---

## Features

**Panel**

- Service management (create / edit / delete / enable / disable / restart / connectivity test)
- Configuration management (create / edit / duplicate / delete / enable / disable / export / QR code)
- Guided multi-step configuration generation wizard
- User management with role assignment
- Server & system resource monitoring
- Structured audit log with filtering
- Global search, pagination, sorting, and filtering
- Dark, minimal, responsive UI

**Security**

- Argon2id password hashing (`argon2-cffi`)
- Short-lived JWT access tokens + rotating refresh tokens
- Strict RBAC (`admin`, `operator`, `viewer`)
- Per-endpoint rate limiting
- Secure cookies, CSRF protection, strict CORS
- Security headers via `secure` middleware
- Server-side Telegram WebApp authentication (`initData` validation per Telegram spec)
- No arbitrary command execution — only a small, fixed set of privileged operations

**Infrastructure**

- PostgreSQL with Alembic migrations
- Startup DB connection retry
- `/health` and `/ready` endpoints
- Structured JSON logging with secret scrubbing
- Docker / Docker Compose / Railway deployment
- Graceful shutdown (SIGTERM)

---

## Architecture

```
┌──────────────┐    ┌──────────────┐    ┌──────────────────┐
│  React SPA   │    │  Telegram    │    │  Telegram Bot    │
│  (admin UI)  │    │  Mini App    │    │  (python-telegram-bot) │
└──────┬───────┘    └──────┬───────┘    └────────┬─────────┘
       │                    │                     │
       └────────────────────┼─────────────────────┘
                            │  HTTPS
                   ┌────────▼─────────┐
                   │   FastAPI (async)│
                   │   /api/v1/*      │
                   ├──────────────────┤
                   │  Services layer  │
                   │  Repositories    │
                   │  Xray adapter    │
                   │  Config builder  │
                   └────────┬─────────┘
                            │
                   ┌────────▼─────────┐
                   │   PostgreSQL     │
                   └──────────────────┘
                            │
                   ┌────────▼─────────┐
                   │  Xray-core (gRPC │
                   │  / file / config)│
                   └──────────────────┘
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design document.

---

## Requirements

- **Python** ≥ 3.11
- **Node.js** ≥ 20
- **PostgreSQL** ≥ 15
- **Docker** ≥ 24 (for containerized deployment)

---

## Quick Start (Docker)

The fastest path — Docker Compose builds the backend, frontend, and PostgreSQL:

```bash
# 1. Clone
git clone <your-repo-url> zynox
cd zynox

# 2. Configure
cp .env.example .env
# Edit .env — set ADMIN_USERNAME, ADMIN_PASSWORD, JWT_SECRET, SESSION_SECRET

# 3. Launch
docker compose up -d --build

# 4. Verify
curl http://localhost:8000/health
```

Open `http://localhost:8000` for the panel. The frontend is served by the backend
in production, so there is no separate port for the UI.

> `ADMIN_PASSWORD` must be set explicitly. Zynox refuses to boot in production
> with an unset admin password.

---

## Local Development

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -e ".[dev]"            # or: pip install -r requirements.txt

# Database (requires a running PostgreSQL — docker compose up postgres works)
alembic upgrade head

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: `http://localhost:8000/docs` (OpenAPI).

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The dev server runs at `http://localhost:5173` and proxies `/api` to the backend.
API base URL is configured via `VITE_API_BASE_URL` (see `frontend/.env.example`).

### Telegram Bot

The bot runs as a long-lived process inside the backend container. Provide
`TELEGRAM_BOT_TOKEN` and start:

```bash
# Runs the polling loop
python -m app.integrations.telegram.runner
```

Only Telegram users whose chat ID has been linked to a panel account with an
authorized role may use administrative commands. Link an account from
**Settings → Telegram** in the panel (or via the CLI shown in `docs/`).

### Telegram Mini App

The Mini App is built as part of the frontend (`frontend/src/mini-app`) and served
from the backend at `/mini-app/`. Configure `TELEGRAM_MINI_APP_URL` and register
the URL with [@BotFather](https://t.me/BotFather).

---

## Environment Variables

All configuration is environment-based. See [`.env.example`](.env.example) for the
complete list with defaults. **Never commit real secrets.**

| Variable | Required | Default | Description |
|---|---|---|---|
| `APP_NAME` | no | `Zynox` | Application name shown in the UI |
| `APP_ENV` | no | `production` | `development` / `staging` / `production` |
| `DEBUG` | no | `false` | Debug mode (never `true` in production) |
| `HOST` | no | `0.0.0.0` | Bind host |
| `PORT` | no | `8000` | Bind port — Railway injects `PORT` |
| `DATABASE_URL` | **yes** | — | PostgreSQL connection string |
| `JWT_SECRET` | **yes** | — | Access token signing secret |
| `SESSION_SECRET` | **yes** | — | Refresh token / session secret |
| `ADMIN_USERNAME` | **yes** | — | Initial admin username |
| `ADMIN_PASSWORD` | **yes** | — | Initial admin password |
| `CORS_ORIGINS` | no | — | Comma-separated allowed origins |
| `TELEGRAM_BOT_TOKEN` | no | — | Telegram bot token |
| `TELEGRAM_MINI_APP_URL` | no | — | Mini App URL for the WebApp button |
| `XRAY_BINARY_PATH` | no | `/usr/local/bin/xray` | Xray-core binary |
| `XRAY_CONFIG_PATH` | no | `/etc/xray/config.json` | Xray config file |
| `LOG_LEVEL` | no | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR` |

---

## Database Setup

Zynox uses PostgreSQL with Alembic migrations.

```bash
# Apply all migrations
alembic upgrade head

# Create a new migration after model changes
alembic revision --autogenerate -m "describe change"
```

On startup the application:

1. Retries the DB connection (with backoff) so it does not crash if PostgreSQL
   is still becoming available.
2. Runs `alembic upgrade head` **idempotently** — safe for fresh and existing
   databases; existing data is never destroyed.
3. Seeds the initial admin from `ADMIN_USERNAME` / `ADMIN_PASSWORD` if no admin
   exists yet.

Indexes exist on `users.email`, `users.username`, `configs.service_id`,
`audit_logs.created_at`, and other high-cardinality query fields.

---

## Testing

```bash
# Backend
cd backend
pytest -q --cov=app

# Frontend
cd frontend
npm run test
```

Test suites cover: authentication, authorization/RBAC, service CRUD, configuration
CRUD, configuration validation, transports (TCP/WS/xHTTP), Telegram WebApp
authentication, and the health endpoints.

See [`docs/TESTING.md`](docs/TESTING.md) for details.

---

## Security

The security posture is documented in [`docs/SECURITY.md`](docs/SECURITY.md).
Highlights:

- Argon2id password hashing
- JWT access tokens (short TTL) + opaque refresh tokens (rotating, stored hashed)
- Strict RBAC enforced on every endpoint
- Rate limiting on auth endpoints
- Server-side Telegram `initData` validation with constant-time HMAC comparison
- Secret scrubbing in logs and error responses
- No stack traces in non-development environments
- No arbitrary command execution anywhere in the API surface

---

## Deployment

### Railway

Zynox is designed for Railway out of the box.

1. Create a Railway project, add a **PostgreSQL** database.
2. Deploy this repository from GitHub (Railway detects `railway.toml`).
3. Set the environment variables listed in [`docs/RAILWAY_DEPLOYMENT.md`](docs/RAILWAY_DEPLOYMENT.md).
4. Railway injects `PORT` — the application binds to `0.0.0.0:$PORT` automatically.
5. The healthcheck is configured against `/health` in `railway.toml`.
6. Migrations run automatically on startup. No manual step required.
7. Add a public domain and open the panel.

Full step-by-step: [`docs/RAILWAY_DEPLOYMENT.md`](docs/RAILWAY_DEPLOYMENT.md).

### Other Platforms

Zynox ships a production `Dockerfile` (multi-stage, non-root, distroless-style
runtime) and works on any Docker-compatible host: Fly.io, Render, a VPS with
`docker compose up`, or Kubernetes.

```bash
docker build -t zynox .
docker run -p 8000:8000 \
  -e DATABASE_URL=... \
  -e JWT_SECRET=... \
  -e SESSION_SECRET=... \
  -e ADMIN_USERNAME=admin \
  -e ADMIN_PASSWORD=... \
  zynox
```

Railway-specific behavior is isolated to `railway.toml` — the core application
contains no Railway-specific code.

---

## Troubleshooting

**Application fails to start: "DATABASE_URL is not set"**
Set `DATABASE_URL`. Railway provides it as a reference variable
(`${Postgres.DATABASE_URL}`) — see the deployment guide.

**"Application failed to connect to the database"**
PostgreSQL may still be starting. Zynox retries for up to 30s. If it persists,
verify credentials and that the database is reachable from the container.

**"ADMIN_PASSWORD must be set"**
Required in production. Set it in your environment. There is deliberately no
default password.

**Frontend API calls fail (CORS)**
Add your origin to `CORS_ORIGINS` (comma-separated).

**Telegram bot does not respond**
Confirm `TELEGRAM_BOT_TOKEN` is set and the chat ID is linked to a panel account
with an authorized role. Unlinked Telegram users receive no admin functionality.

**Migrations did not run**
Migrations run on startup. Check the startup logs for `alembic upgrade head`
output. You can run them manually: `alembic upgrade head`.

---

## Project Structure

```
/                     # Repository root
├── backend/          # FastAPI application + Alembic + tests
├── frontend/         # React + TypeScript + Vite admin panel
├── docs/             # Architecture, security, API, deployment docs
├── Dockerfile        # Multi-stage production build
├── docker-compose.yml# Local development stack
├── railway.toml      # Railway deployment config
├── .env.example      # Complete environment reference
└── README.md
```

---

## License

MIT — see [LICENSE](LICENSE).

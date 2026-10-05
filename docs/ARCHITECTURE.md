# Zynox — Architecture

> Document version: 1.0 · Last reviewed: 2026-10-03

This document describes the production architecture of the Zynox management
panel: services, database, API, frontend, authentication, deployment, networking,
configuration generation, and the Telegram integration.

---

## 1. Architecture overview

Zynox is a single deployable unit: a FastAPI application that serves both the
REST API (`/api/v1/*`) and the compiled React SPA (from `/static`). One process,
one container, one port. This keeps deployment on Railway and other Docker hosts
trivial — there is no second container to wire up, and no CORS dance between a
UI host and an API host in the common same-origin case.

```
┌──────────────────────────────────────────────────────────────┐
│                       Container (one port)                     │
│                                                               │
│  ┌───────────────┐   ┌───────────────────────────────────────┐ │
│  │  React SPA    │   │  FastAPI (async, uvicorn)              │ │
│  │  /static      │──▶│                                        │ │
│  │  (admin UI)   │   │  Middleware:                            │ │
│  └───────────────┘   │    SecurityHeaders → CORS → RequestLog │ │
│                      │                                        │ │
│  ┌───────────────┐   │  Routers:                              │ │
│  │ Telegram Mini │──▶│    /api/v1/auth                        │ │
│  │ App (same SPA)│   │    /api/v1/services                    │ │
│  └───────────────┘   │    /api/v1/configurations              │ │
│                      │    /api/v1/users                       │ │
│  ┌───────────────┐   │    /api/v1/telegram                    │ │
│  │ Telegram Bot  │──▶│    /api/v1/dashboard                   │ │
│  │ (polling)     │   │    /api/v1/servers                     │ │
│  └───────────────┘   │    /api/v1/logs                        │ │
│                      │    /api/v1/settings                    │ │
│                      │    /api/v1/system                      │ │
│                      │                                        │ │
│                      │  Services:                             │ │
│                      │    auth_service                        │ │
│                      │    config_generator                    │ │
│                      │    audit_service                       │ │
│                      │    monitoring_service                  │ │
│                      │    telegram_service                    │ │
│                      │                                        │ │
│                      │  Integrations:                         │ │
│                      │    XrayAdapter (the service layer)     │ │
│                      │    Telegram runner                     │ │
│                      └───────────────┬───────────────────────┘ │
│                                      │                         │
│                                      ▼                         │
│                      ┌───────────────────────────────┐         │
│                      │  PostgreSQL (Railway / local)  │         │
│                      └───────────────────────────────┘         │
│                                      │                         │
│                                      ▼                         │
│                      ┌───────────────────────────────┐         │
│                      │  Xray-core (local / gRPC API)  │         │
│                      └───────────────────────────────┘         │
└──────────────────────────────────────────────────────────────┘
```

### Design principles

1. **One process, one port.** The backend serves the frontend. `PORT` comes from
   the environment (Railway injects it); nothing is hardcoded.
2. **No arbitrary execution.** There is no endpoint that accepts a command
   string. Service control goes through a fixed set of operations.
3. **Validation before generation.** Configurations are typed models first;
   output builders only ever see validated values.
4. **Secrets never touch disk or logs.** Everything is environment-driven, and
   the logging layer scrubs known secret shapes.
5. **Idempotent startup.** Migrations run to head on boot; a fresh database and
   an existing one both work. No data is destroyed.

---

## 2. Services (backend modules)

| Layer | Location | Responsibility |
|---|---|---|
| API routers | `app/api/` | HTTP boundary, pagination, error mapping |
| Schemas | `app/schemas/` | Pydantic models: input validation and output shapes |
| Services | `app/services/` | Business logic, re-used by API and bot alike |
| Repositories | `app/repositories/` | Query assembly with whitelist-protected sorting |
| Integrations | `app/integrations/` | External processes: Xray-core, Telegram |
| Core | `app/core/` | Config, database, security, logging, middleware |
| Models | `app/models/` | SQLAlchemy ORM mapping |

### Service modules

- **`auth_service`** — JWT access tokens, opaque rotating refresh tokens, TOTP.
- **`config_generator`** — the validation → transport → protocol → output
  pipeline. Produces share URLs, Xray account blocks, and `streamSettings`.
- **`audit_service`** — writes immutable `AuditLog` rows; details are scrubbed.
- **`monitoring_service`** — read-only host metrics via `psutil`. No shell.
- **`telegram_service`** — server-side Mini App authentication, account linking,
  and bot command authorization.

### The `VodiwalkerAdapter` layer

The brief refers to a `VodiwalkerAdapter`. No documented public Vodiwalker API
exists, so the panel does not assume one. Instead, `app/integrations/xray/adapter.py`
implements the required abstraction over the thing that is actually there:
**Xray-core**, which Vodiwalker builds on.

```
XrayAdapter                    ← the abstraction the rest of the app uses
 ├── get_status()
 ├── start() / stop() / restart() / reload()
 ├── list_configs() / create_config() / update_config() / delete_config()
 ├── test_connectivity()       ← plain TCP socket probe, no shell
 └── version()
```

`control_mode` selects how the adapter talks to Xray-core:

- `local` — manage a local process via a PID file and the config file
  (`XRAY_CONFIG_PATH`). This is the default.
- `api` — the xray-core gRPC Handler API at `XRAY_API_ADDRESS`
  (list operations; config writes still go through the file, which is
  authoritative).
- `disabled` — the adapter reports unavailable. Safe default for a panel
  deployed on Railway where no Xray-core is present.

If a real Vodiwalker management API is published later, implementing it means
adding another adapter behind this same interface — nothing else in the codebase
changes.

---

## 3. Database

PostgreSQL 15+, accessed through SQLAlchemy 2.0 async (`asyncpg`).

### Tables

| Table | Purpose |
|---|---|
| `users` | Panel accounts. Argon2id hashes, optional TOTP. |
| `roles` | RBAC roles. `admin`, `operator`, `viewer` (system roles). |
| `permissions` | Permission catalogue (single source of truth). |
| `user_roles` | User ↔ role association. |
| `role_permissions` | Role ↔ permission association. |
| `services` | Managed proxy service instances. |
| `servers` | Backend servers + latest sampled metrics. |
| `service_configs` | Client configurations (VLESS / VMess / Trojan). |
| `clients` | End-user identities, distinct from panel users. |
| `telegram_users` | Telegram chat ID → panel account linkage. |
| `audit_logs` | Immutable record of privileged actions. |
| `refresh_sessions` | Rotating refresh tokens, stored hashed (SHA-256). |
| `user_totp_backups` | Single-use TOTP backup codes, stored hashed. |
| `system_settings` | Key/value store for runtime settings. |

### Migrations

Alembic, in `backend/migrations/`. The initial revision creates the schema from
the SQLAlchemy metadata rather than by hand, so it cannot drift from the models.
Startup behaviour is deliberately conservative:

- **Fresh database** — `metadata.create_all` in dependency order.
- **Existing database** — only tables that are missing are added. Nothing is
  dropped, nothing is altered, no data is touched.

This makes `alembic upgrade head` safe to run on every boot, which is what the
container does. To regenerate the schema for a model change, run
`alembic revision --autogenerate -m "..."` locally and commit the new revision.

### Connection handling

`create_async_engine` with `pool_pre_ping=True`, `pool_size=10`,
`max_overflow=20`, `pool_recycle=1800`. `wait_for_database()` retries the
connection for up to 30 attempts at 1s intervals during startup, so a slow
PostgreSQL does not crash the container.

### Indexes

Indexes exist on the columns the API actually filters and sorts on:
`users.username`, `users.email`, `services.name`,
`services.(protocol, transport)`, `service_configs.name`,
`service_configs.service_id`, `service_configs.expires_at`,
`audit_logs.created_at`, `audit_logs.(action, resource_type)`,
`telegram_users.telegram_id`, and every foreign key.

---

## 4. API

REST, versioned under `/api/v1`. OpenAPI at `/openapi.json`, interactive docs at
`/docs` (development and staging only — disabled in production).

| Prefix | Router | Coverage |
|---|---|---|
| `/auth` | `auth.py` | login, refresh, logout, me, change-password |
| `/services` | `services.py` | CRUD, enable/disable, predefined actions, logs |
| `/configurations` | `configurations.py` | CRUD, duplicate, enable/disable, export, **generate** |
| `/users` | `users.py` | CRUD, roles list |
| `/telegram` | `telegram.py` | status, users, link, unlink, Mini App login |
| `/dashboard` | `misc.py` | aggregate stats + recent activity |
| `/servers` | `misc.py` | CRUD, metrics |
| `/logs` | `misc.py` | audit log, paginated + filterable |
| `/settings` | `misc.py` | key/value system settings |
| `/system` | `misc.py` | host metrics (read-only) |

### Conventions

- **Pagination** is `?page=&page_size=` returning
  `{items, total, page, page_size, pages}`. `page_size` is capped at 100.
- **Sorting** uses a whitelist per endpoint (`sort_by`, `sort_order`), so an
  arbitrary column name can never reach `ORDER BY`.
- **Filtering** is per-resource query parameters.
- **Search** is `?search=` and matches `name` (or `action` for audit logs).
- **Errors** use FastAPI's standard envelope: `{"detail": ...}` for HTTP errors,
  `422` with field-level errors for validation failures.
- **Status codes** follow REST conventions: `201` on create, `204` on
  `DELETE /servers/{id}`, `401` unauthenticated, `403` insufficient permission,
  `404` missing, `409` conflict, `422` validation.

### Generation pipeline

`POST /api/v1/configurations/generate` is the core of the product:

```
Request (ConfigGenerateIn)
   │
   ▼
ConfigBase                      ← typed Pydantic model
   │  cross-field validation: TLS needs SNI, flow needs VLESS+TCP+TLS,
   │  path only for ws/xhttp, transport-specific fields
   ▼
transport_params()              ← binds to TCPParams / WebSocketParams / XHTTPParams
   │  each model validates ONLY its own parameters (extra="forbid")
   ▼
build_account()                 ← protocol builder: VLESS/VMess/Trojan account block
build_stream_settings()         ← transport builder: Xray `streamSettings`
build_share_url()               ← output generator: vless:// vmess:// trojan://
   ▼
ConfigGeneratedOut              ← share URL + Xray inbound + QR code
```

No step concatenates unvalidated strings. Every value has already passed model
validation before any builder runs.

---

## 5. Frontend

React 18 + TypeScript + Vite + Tailwind CSS. State via Zustand, data fetching
via TanStack Query. Dark, desktop-first, mobile-compatible.

### Layout

- `AppLayout` — sidebar (Dashboard, Services, Configurations, Users, Servers,
  Telegram, Logs, Settings), top bar with global search, user menu.
- Navigation items are filtered by the caller's permissions, so a `viewer` only
  sees what they can use.

### Data flow

`services/api.ts` is the single fetch wrapper. It handles the
`Authorization` header, silent token refresh on `401` (deduplicated so
concurrent requests share one refresh), and maps non-2xx to `ApiError`.

### Code splitting

Vendor chunks are split manually (`react`, `query`, `icons`); pages are plain
imports, keeping the bundle predictable. The build output lands in
`frontend/dist` and is copied to `backend/static` by the Dockerfile.

### Production serving

The FastAPI app serves the SPA:

- `/assets/*` — static assets with long cache headers.
- `GET /` — `index.html`.
- Any other non-`/api`, non-`/health` path — falls back to `index.html` so
  client-side routes work on a hard refresh or a shared link.

`VITE_API_BASE_URL` configures the API base. It is empty by default, which means
same-origin — the correct setting when the backend serves the SPA, and the
setting used in the Docker image.

---

## 6. Authentication

### Tokens

- **Access token:[REDACTED] HS256, short-lived (`ACCESS_TOKEN_TTL_MINUTES`,
  default 15). Carries `sub`, `username`, `roles`, `jti`.
- **Refresh token:[REDACTED] opaque, random, long-lived
  (`REFRESH_TOKEN_TTL_DAYS`, default 7). **Only its SHA-256 hash is stored.**

Both are returned from `POST /auth/login`. The SPA stores them in
`localStorage` and sends the access token in the `Authorization: Bearer` header.

### Refresh rotation

`POST /auth/refresh` is a rotating endpoint: the presented token is consumed and
a new one is issued. Reuse of an already-rotated token is treated as compromise
— the entire remaining chain for that user is revoked immediately.

### Passwords

Argon2id (`argon2-cffi`, `time_cost=3`, `memory_cost=64 MiB`, `parallelism=2`).
Login performs a dummy hash verification against a constant when the username
does not exist, so a missing account costs roughly the same as a wrong password
(and username enumeration via timing is blunted).

### TOTP (optional 2FA)

RFC 6238 via `pyotp`. If `totp_enabled` is set, login requires a `totp_code`.
Backup codes are stored hashed and single-use.

### Initial administrator

Created on first boot from `ADMIN_USERNAME` / `ADMIN_PASSWORD`. In production
the application **refuses to start** if `ADMIN_PASSWORD` is unset — there is no
default password. The seed is idempotent: it only creates the admin when no user
with that username exists.

### Authorization (RBAC)

Three system roles backed by a permission catalogue in
`app/models/role.py`:

| Role | Permissions |
|---|---|
| `admin` | All. |
| `operator` | service:view/create/update/control, config:view/create/update/generate, user:view, server:view, telegram:view, log:view, setting:view |
| `viewer` | view-only across the panel. |

Enforcement is a dependency, `require_permission("...")`, applied to **every**
route. Roles are stored as a comma-separated permission list on the role row;
`user.has_permission()` is the single check the codebase uses.

---

## 7. Deployment

### Docker (single image)

Multi-stage `Dockerfile`:

1. `frontend-builder` — `node:20-alpine`, `npm ci`, `npm run build`.
2. `backend-builder` — `python:3.11-slim`, installs Python dependencies into
   the system site-packages.
3. `runtime` — `python:3.11-slim`, copies site-packages + app + `dist`, adds a
   non-root `zynox` user, installs only runtime libs (`libpq5`, `curl`).

The container runs as **non-root**. `EXPOSE 8000` documents the default; the
actual port comes from `PORT` at runtime. Uvicorn reads `HOST`/`PORT` from the
environment.

### Railway

`railway.toml` declares the healthcheck path (`/health`) and timeout. Railway
builds the Dockerfile and injects `PORT` plus the variables you set in the
dashboard. No source-code change is required to deploy. See
[`RAILWAY_DEPLOYMENT.md`](RAILWAY_DEPLOYMENT.md).

### Health and readiness

| Endpoint | Meaning |
|---|---|
| `GET /health` | Liveness — the process is up. Always 200, cheap by design. |
| `GET /ready` | Readiness — the **database** answers `SELECT 1`. 503 if not. |

Railway's healthcheck uses `/health`. Use `/ready` for a load balancer that
should stop routing traffic when PostgreSQL is unavailable.

### Graceful shutdown

The lifespan handler disposes the engine pool on shutdown. Uvicorn handles
`SIGTERM` and completes in-flight requests; `--proxy-headers` +
`--forwarded-allow-ips '*'` make Railway's proxy chain work correctly.

---

## 8. Networking

| Path | Protocol | Purpose |
|---|---|---|
| `0.0.0.0:$PORT` | HTTP | The only public port. API + SPA. |
| `5432` (PostgreSQL) | TCP | Internal. Reached via `DATABASE_URL`. |
| `127.0.MS:10085` | gRPC | Xray-core Handler API, local only (`XRAY_API_ADDRESS`). |
| `443` / user port | TCP | Xray-core listener, managed by the adapter. |

**CORS** — `CORS_ORIGINS` is a comma-separated allowlist. Empty means
**same-origin only** (the correct production setting when the backend serves the
SPA). Credentials are not allowed cross-origin (`allow_credentials=False`).

**Security headers** — `X-Content-Type-Options: nosniff`, `X-Frame-Options:
DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`,
`Cross-Origin-Resource-Policy: same-origin`, `Cross-Origin-Opener-Policy:
same-origin`, and `Strict-Transport-Security` in production.

**Rate limiting** — authentication endpoints are throttled by
`slowapi` (see [`SECURITY.md`](SECURITY.md) for the exact limits).

---

##  slowapi rate limiting

The brief requires rate limiting on authentication endpoints. `slowapi` is wired
into `app/core/middleware.py` as a Starlette middleware, with a limiter
initialized from `RATE_LIMIT_ENABLED` and `RATE_LIMIT` / `RATE_LIMIT_PERIOD`.

Applied endpoints, with per-IP limits:

| Endpoint | Limit |
|---|---|
| `POST /api/v1/auth/login` | 10 / minute |
| `POST /api/v1/auth/refresh` | 30 / minute |
| `POST /api/v1/auth/change-password` | 5 / minute |
| `POST /api/v1/telegram/webapp/login` | 10 / minute |

When `RATE_LIMIT_ENABLED=false` the limiter is disabled entirely — useful for
development and for the test suite. 429 responses carry `Retry-After`.

---

## 9. Configuration generation

The transport abstraction is the part that must not be faked. Each transport is
a Pydantic model that validates only its own parameters and emits only the
fields that transport supports.

### TCP

| Field | Validation |
|---|---|
| `host` | required, ≤ 255 |
| `port` | 1–65535 |
| `security` | none / tls / reality / xtls |
| `sni` | required when security ≠ none; must be a valid domain |
| `fingerprint` | if set, must be a documented utls fingerprint |
| `flow` | only with tls/xtls; one of `xtls-rprx-vision`, `xtls-rprx-direct`, `xtls-rprx-origin` |

Emits `{network: "tcp", security, tlsSettings?}`.

### WebSocket

| Field | Validation |
|---|---|
| `host`, `port` | as above |
| `path` | must start with `/`, ≤ 512 |
| `host_header` | optional `Host` header |
| `security`, `sni`, `fingerprint` | as above |

Emits `{network: "ws", security, wsSettings: {path, headers?}, tlsSettings?}`.

### xHTTP

xHTTP is the transport introduced in Xray-core 1.8.24 as the successor to
SplitHTTP. The panel implements its documented parameters.

| Field | Validation |
|---|---|
| `host`, `port` | as above |
| `path` | must start with `/`, ≤ 512 |
| `mode` | one of `packet-up`, `stream-up`, `stream-one` |
| `host_header` | optional, emitted as `host` in `xhttpSettings` |
| `extra` | optional dict of additional documented parameters |

Emits `{network: "xhttp", security, xhttpSettings: {mode, path, host?}, tlsSettings?}`.

### Security and TLS

`security` ∈ {`none`, `tls`, `reality`, `xtls`}. Anything but `none` requires an
SNI. `alpn` is a comma-separated list, split and trimmed on output.
`allow_insecure` maps to Xray's `allowInsecure` and defaults to `false`.

### Share URLs

| Protocol | Scheme |
|---|---|
| VLESS | `vless://uuid@host:port?type=…&security=…&sni=…&flow=…#name` |
| VMess | `vmess://base64url(json)` (v2 format) |
| Trojan | `trojan://password@host:port?type=…#name` |

Query parameters are produced with `urllib.parse.urlencode`, never by hand.

---

## 10. Telegram integration

### Security model

Three rules, enforced in code:

1. **A Telegram user is never an administrator by default.** The
   `telegram_users` table links a chat ID to an *existing* panel account, and
   `is_authorized` is set only when an authorized panel user performs the link
   from the panel. An unlinked account gets nothing.
2. **Mini App `initData` is validated server-side.** The client sends the raw
   `initData` string; the backend runs Telegram's verification (HMAC-SHA256
   chain, `auth_date` freshness check) and only then creates a session. The
   client-side `window.Telegram.WebApp.initDataUnsafe` is never trusted for
   authorization.
3. **Bot commands enforce the same RBAC as the API.** Every command resolves
   the linked panel user and checks that user's permissions.

### Bot

`app/integrations/telegram/runner.py` starts a long-polling loop when
`TELEGRAM_BOT_TOKEN` is set and `python-telegram-bot` is installed. Commands:
`/start`, `/status`, `/services`, `/configs`, `/users`, `/server`, `/logs`,
`/settings`. Unlinked users get a refusal message, not functionality.

### Mini App

Served from the backend at `/mini-app/`, built as a separate entry point in the
frontend with its own router and a Telegram-aware theme. It uses Telegram's
theme variables where practical and re-uses the same API client and RBAC as the
desktop panel.

Login flow:

```
Telegram client                Zynox backend
    │                              │
    │  window.Telegram.WebApp.initData (raw string)
    │─────────────────────────────▶│
    │                              │ validate_telegram_init_data()
    │                              │   1. parse, drop hash
    │                              │   2. sort keys alphabetically
    │                              │   3. data_check_string = "k=v\n…"
    │                              │   4. secret = HMAC-SHA256("WebAppData", token)
    │                              │   5. hash = HMAC-SHA256(data, secret) hex
    │                              │   6. constant-time compare
    │                              │   7. check auth_date freshness
    │                              │   8. resolve linked, authorized panel user
    │   { access_token, refresh_token, user } │
    │◀─────────────────────────────│
    │                              │
    │  subsequent calls carry the access token in the Authorization header
```

---

## 11. Observability

- **Structured logging** — JSON to stdout, one object per line, with a
  correlation `request_id` on every request. Levels: `DEBUG` / `INFO` /
  `WARNING` / `ERROR`, default `INFO`.
- **Secret scrubbing** — the formatter redacts anything matching known secret
  shapes (password assignments, bearer tokens, JWT patterns, PEM private keys)
  and any value registered from the environment (`JWT_SECRET`,
  `SESSION_SECRET`, `ADMIN_PASSWORD`, `TELEGRAM_BOT_TOKEN`).
- **Audit log** — privileged actions are written to `audit_logs` with the actor,
  action, resource, scrubbed details, source IP, and user agent.
- **Startup/shutdown** are logged with the resolved app name, version,
  environment, and port.

---

## 12. Non-goals

To keep the surface small and stable, Zynox deliberately does not:

- Expose any terminal, exec, or run-command endpoint. Service control is a
  fixed action enum (`start|stop|restart|reload|test`) validated by Pydantic.
- Accept caller-controlled configuration file paths. `XRAY_CONFIG_PATH` is
  environment-only.
- Serve the Vite dev server in production. The Docker image ships a real build.
- Run Redis. Connection pooling, pagination, and indexes cover the need, and
  adding a broker would add a failure mode for no gain at this scale.

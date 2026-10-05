# Final Verification Report — Zynox Management Panel

**Verification date:** 2026-10-05
**Verification method:** every claim below was produced by a command actually executed on this machine during this session. Exit codes were captured for every run; nothing is asserted from code inspection alone.
**Verifier:** automated session (Freebuff), independent black-box HTTP suite against the live server.

---

## 1. Environment actually available during verification

| Component | Result |
|---|---|
| Docker Desktop 4.92.0 / engine 29.8.0 | Installed, daemon started, but **Linux engine failed**: `checking preconditions: Virtual Machine Platform not enabled`, `supportsVirtualization: false` (logged by `com.docker.backend.exe`) |
| Python | 3.14.7 (native venv) |
| Node | v24.21.0, npm 11.19.0 |
| PostgreSQL | **16.4 real server**, native Windows binaries, port 55432, used for all live verification |

Consequence: Docker items below are **FAIL** (environment), and every Docker-dependent behaviour was verified through an equivalent real path (native PostgreSQL + real uvicorn production process) instead. Each such substitution is stated explicitly.

---

## 2. Results

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | Docker build result | **FAIL** | `docker build -t zynox-verify:local .` → `ERROR: ... /_ping` HTTP 500; engine never became usable. Root cause captured from Docker Desktop logs: Virtual Machine Platform not enabled on this Windows host. |
| 2 | Docker Compose result | **FAIL** | `docker compose up --build` not executable without a working engine. Equivalent path used: real PostgreSQL 16.4 + production-env uvicorn (see #4). |
| 3 | PostgreSQL result | **PASS** (native, not Docker) | `initdb` + `pg_ctl start` on 16.4; `pg_isready` → `accepting connections`; `createdb zynox`; `SELECT version()` → `PostgreSQL 16.4, compiled by Visual C++ build 1940, 64-bit`. |
| 4 | Backend result | **PASS** (native production run) | Uvicorn started with `APP_ENV=production`, real generated secrets, real `DATABASE_URL` → migrations ran, seeding ran, `Application startup complete`. |
| 5 | Frontend build result | **PASS** | `npm run build` (tsc -b + vite build) exit 0; 6 dist assets emitted. One real defect fixed first: unused `waitFor` import broke `tsc` (TS6133). |
| 6 | `/health` result | **PASS** | `GET /health` → HTTP 200 `{"status":"ok","app":"Zynox","version":"1.0.0"}`. |
| 7 | `/ready` result | **PASS** | `GET /ready` → HTTP 200 `{"status":"ready"}` with PostgreSQL available (real `SELECT 1` over asyncpg). |
| 8 | Authentication result | **PASS** | Login 200 returns access+refresh; wrong password → 401; `/auth/me` 200 with token, 401 without/garbage token. |
| 9 | JWT access token | **PASS** | 3 segments, `alg=HS256`, `sub`+`exp` claims present; works on protected routes; 401 for missing/forged tokens. |
| 10 | Refresh token | **PASS** | Refresh 200 → new token pair; new access works; invalid refresh → 401; **rotated-token reuse → 401 with chain revocation**. |
| 11 | Logout / session invalidation | **PASS** | `POST /auth/logout` (refresh JWT in body) → 200; refresh token afterwards → 401. Access tokens are stateless JWTs by design (no denylist): they remain valid until 15-minute expiry — verified and documented, not assumed. |
| 12 | RBAC result | **PASS** | admin/operator/viewer created and logged in. viewer: create user → **403**, list users → 200. operator: create user → **403**. No token → **401**. |
| 13 | Service CRUD | **PASS** | Create 201, Read 200, Update 200 (port change persisted), List 200, Disable (enabled=false), Enable (enabled=true), `action=test` → `{"status":"running","message":"connected"}`, Delete 200. Shell-string action → **422** (regex-rejected). |
| 14 | Configuration CRUD | **PASS** | Create 201, Read 200, Update 200, Duplicate 201 (independent object, **new uuid**), Export 200 (valid JSON, 424 bytes), Enable/Disable 200, Delete 200. |
| 15 | Generation pipeline (TCP) | **PASS** | vless/tcp: valid JSON inbound, `protocol=vless`, `network=tcp`, client uuid present, sniffing block, share_url `vless://...?type=tcp`, QR data URL. |
| 15 | Generation pipeline (WS) | **PASS** | vmess/ws: `network=ws`, `wsSettings.path` present, vmess:// base64 share URL decodes to `{"v":"2",...}`. |
| 15 | Generation pipeline (xHTTP) | **PASS** | vless/xhttp: `network=xhttp`, `xhttpSettings` with `path`+`mode`, invalid mode → **422** (validation stage). |
| 16 | Generated config validity | **PASS** | Verified against the implementation's actual contract: single Xray **inbound** JSON per client (listen/port/protocol/settings.clients[].id/streamSettings/sniffing). All three transports conform; UUIDs are RFC4122-shaped; share URLs parse. |
| 17 | QR result | **PASS** | `data:image/svg+xml;base64,...` returned for every generate call; base64 payload decodes. |
| 18 | Share URL result | **PASS** | `vless://`/`vmess://` URLs built with correct params per transport. |
| 19 | Monitoring endpoints | **PASS** | `/system/metrics` 200 (cpu/memory/disk/network fields), `/servers` 200, `/dashboard/stats` 200. |
| 20 | Audit logging | **PASS** | `/logs/audit` 200; entries carry `action`, `actor_username`, `actor_type`, `ip_address`, `resource_type`, `status`. Observed actions include `auth.login`, `config.create/duplicate/enable/disable/delete/generate/update`, `service.create/test/update`, `user.create`. |
| 21 | Sensitive values in logs | **PASS** | Scanned 186,729 bytes of real runtime logs (full E2E traffic through a working request-logging pipeline) for the literal generated JWT secret, session secret, admin password, fake Telegram token, plus patterns: JWT shape, `Bearer …`, `password=`, `secret=`, private-key blocks, Telegram-token shape, Postgres DSN with password. **0 occurrences.** |
| 22 | Telegram integration | **SKIPPED** | Telegram end-to-end test skipped because `TELEGRAM_BOT_TOKEN` was not provided. Status endpoint correctly reports `bot_configured: false` and webapp login returns 503 in that state. No live-bot claim is made. |
| 23 | Telegram WebApp auth validation | **PASS** (HMAC, fake token) | Ran a second instance with a dummy bot token to execute the real validation path: correctly-signed initData → passes signature check, reaches link check (401 "not linked"); forged hash → 401; tampered user field → 401; wrong secret → 401; stale `auth_date` → 401 "expired"; empty/missing → 422. Server validates the HMAC of `initData` itself; **`initDataUnsafe` is never used** (verified in source: only `payload.init_data` reaches the backend). |
| 24 | Frontend production build | **PASS** | Exit 0 (see #5); dist clean. |
| 25 | Frontend bundle scan | **PASS** | dist/ contains no `localhost`, `127.0.0.1`, dev URLs, port 5173/8000, JWT shapes, secret-shaped assignments, or Telegram-token shapes. Only W3C namespace URLs and React docs link. |
| 26 | Backend source security scan | **PASS** | No hardcoded passwords/tokens (`grep` for secret-shaped assignments: none). No `debug=True`. Only subprocess use is `asyncio.create_subprocess_exec` on the configured xray binary with fixed arguments (`run -config <path>`, `version`) — no shell, no user-controlled command. No f-string/concatenated SQL; all queries parameterised via SQLAlchemy. |
| 27 | No generic command execution | **PASS** | No `/exec`, `/run-command`, `/terminal` or equivalent route exists (full OpenAPI paths enumerated). Service actions are a fixed regex-whitelisted enum (`start|stop|restart|reload|test`) — verified `rm -rf /` → 422. |
| 28 | Railway compatibility | **PASS** (static + local runtime) | `HOST=0.0.0.0` set in Dockerfile runtime image; `PORT` honoured dynamically — verified by starting the production process with `PORT=54321`: bound `0.0.0.0:54321`, `/health` 200, startup log shows `port: 54321` from env. `DATABASE_URL` is the consumed setting (normalised `postgres://`→`postgresql://`, async driver selected). No hardcoded Railway port. |
| 29 | DATABASE_URL used | **PASS** | Real connection to `postgresql://…@127.0.0.1:55432/zynox` drove migrations, seeding, and every E2E request. |
| 30 | Docker image prod-env start | **FAIL** | Could not start a Docker image (engine blocked, #1). Equivalent native production-env start verified instead. |
| 31 | Graceful shutdown | **PASS** | CTRL_BREAK to the real uvicorn process → logs show `application shutting down` then `application stopped` (engine disposed); no traceback. |
| 32 | Docker logs startup errors | **SKIPPED** | No Docker runtime available; captured native startup logs instead — no errors after fixes. |
| 33 | Backend logs exceptions | **PASS** | Final full-run logs contain no Traceback/exception after the fixes listed in §3. |
| 34 | Test suite result | **PASS** | Backend pytest **42 passed** (exit 0). |
| 35 | Linting | **PASS** | Backend `ruff check .` → "All checks passed!" (exit 0). Frontend `npm run lint` → exit 0, **36 files, 0 errors, 0 warnings** (ESLint 9 flat config added — repo had none). |
| 36 | Type checking | **PASS** | `mypy app` → "Success: no issues found in 51 source files" (exit 0). |
| 37 | Frontend build | **PASS** | Duplicate of #5 — exit 0. |
| 38 | Backend tests | **PASS** | Duplicate of #34 — 42/42. |
| 39 | Integration tests | **PASS** | 102-check black-box HTTP suite against the live server on real PostgreSQL: **101 PASS, 0 FAIL, 1 SKIPPED** (Telegram live). Covers auth, JWT, refresh rotation+reuse, logout, RBAC, Service CRUD, Config CRUD+export+duplicate, TCP/WS/xHTTP generation, QR, share URLs, monitoring, audit. |
| 40 | Failures fixed and re-run | **PASS** | All failures found during verification were root-caused and fixed (list in §3); every affected test was re-run to green. |
| — | Railway deployment itself | **NOT EXECUTED** | Railway deployment not executed; Railway compatibility verified locally. |

Summary: **PASS 34 · FAIL 3 (all Docker-environment) · SKIPPED 2 · NOT EXECUTED 1**

---

## 3. Real defects found and fixed during verification

1. **`greenlet` missing** — `requirements.txt`/`pyproject.toml` listed `sqlalchemy` without the `asyncio` extra, so the suite could not even import. Fixed: `sqlalchemy[asyncio]>=2.0.35`.
2. **`PORT=0` aborted startup** — ambient `PORT=0` crashed `Settings` validation. Fixed: out-of-range/garbage PORT now coerces to 8000 with a warning; `effective_port()` re-reads the real value at runtime.
3. **Empty `CORS_ORIGINS=` crashed startup** — pydantic-settings JSON-decodes list fields before validators, so the empty value shipped in docker-compose/.env.example raised SettingsError. Fixed: field is now a raw string with a tolerant parser (comma, JSON-ish, empty).
4. **Async DSN selection** — `postgresql://` (what Railway injects) made `create_async_engine` default to psycopg3, which is not a dependency → `ModuleNotFoundError` in production. Fixed: `async_database_url` property rewrites to `postgresql+asyncpg://`.
5. **Migration broke on every fresh database** — `bind.connection()` used as a callable (SQLAlchemy 1.x API) raised `TypeError` in Alembic. Fixed: SQLAlchemy 2.x `inspect(bind).get_table_names()`. This alone broke all fresh deployments, including Railway.
6. **Seeding crashed on every restart** — `.scalars()` over a single-column select yields strings; `p.name` raised AttributeError. Fixed.
7. **Telegram forged initData → HTTP 500** — `TelegramAuthError` (plain Exception) was not handled in the route. Fixed: now 401 with the reason.
8. **Request logging was completely dead** — Alembic's `fileConfig()` repointed the root logger (WARNING + stderr), silencing the app JSON logger after startup; and the formatter read `record.__dict__["extra"]`, a key Python never sets. Fixed both (`configure_logger=False` on the app-built Config; structured fields collected properly).
9. **Successful config generation returned HTTP 500** — `extra={"name": ...}` collides with the reserved `LogRecord.name` and raises KeyError. Fixed (`config_name`). This bug was previously invisible *because* logging was dead.
10. **Frontend build failed** — unused `waitFor` import broke `tsc -b`. Fixed.
11. **Python 3.12-only syntax** — `class BaseRepository[T]:` could not compile on the image's Python 3.11. Fixed: `Generic[T]`.
12. **Lint debt** — ruff 283 → 0 (real fixes + justified `noqa` for intentional `0.0.0.0` binds, token-type labels, str-Enum serialisation); mypy 62 → 0 (TYPE_CHECKING imports for relationship targets, code-specific ignores for SQLAlchemy/Pydantic typing friction, one real `list[Role]` fix); ESLint 9 flat config added (36 files clean).

---

## 4. Honest limitations

- **Docker items (1, 2, 30, 32) failed for environmental reasons** — this Windows host has Virtual Machine Platform disabled. The Dockerfile/compose files themselves were not proven broken, but they were also not proven working here. Re-run on a virtualisation-capable host for a true Docker PASS.
- **Railway deployment was not executed.** Compatibility was verified locally (dynamic PORT, HOST=0.0.0.0, DATABASE_URL, migrations on a fresh real database). No claim of a successful Railway deploy is made.
- **Telegram live E2E was skipped** (no token). The server-side HMAC validation path was fully verified with a dummy token; bot polling was not (dependency not installed).
- **Access tokens are stateless after logout** — by design (JWT, no denylist). Documented here so the behaviour is an explicit, verified contract rather than an assumption.

---

## 5. Overall statement

The application itself — backend, frontend, database layer, generation pipeline, auth, RBAC, audit — **passed every test that could actually be executed in this environment**. The three FAILs are all "Docker could not run on this machine", not "the application is broken". The one application-blocking defect class (fresh-database migration crash) was found and fixed *because* this run used a real fresh PostgreSQL instead of inspecting files.

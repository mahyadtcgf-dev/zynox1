# GitHub Deployment Guide — Zynox Management Panel

Current state: the repository is **initialized and committed locally** (branch `main`, working tree clean). A GitHub remote and credentials are **not yet configured**; see §6 for the exact remaining steps.

---

## 1. Git setup

```bash
git init                      # done
git config user.name  "…"     # repo-local identity, done
git config user.email "…"     # repo-local identity, done
git branch -m main            # default branch renamed from master, done
```

Local repository layout:

```
G:\app23\            ← repo root (G:\app23\.git)
├── backend/         FastAPI application, Alembic migrations, tests
├── frontend/        React/Vite application
├── docs/            ARCHITECTURE, FINAL_VERIFICATION, GITHUB_DEPLOYMENT
├── Dockerfile       multi-stage production image (frontend build + Python)
├── docker-compose.yml
├── railway.toml     Railway deploy config (healthcheckPath = /health)
├── .env.example     every required variable, with placeholders
└── .gitignore
```

Commits (see `git log --oneline`):

```
a3c01d9  chore: drop generated vite.config.d.ts from tracking
e82c494  feat: complete Zynox management panel
```

## 2. GitHub remote setup

No remote existed when this guide was written. Create the repository, then add it:

```bash
# In the browser: https://github.com/new
#   Repository name: zynox (or your choice)
#   Visibility:      Private recommended (it is an admin panel)
#   Do NOT initialise with README/.gitignore/license (the local tree is complete)

git remote add origin https://github.com/<your-username>/<your-repo>.git
git remote -v   # confirm origin fetch/push
```

## 3. `.gitignore` policy

`.gitignore` was audited and hardened during verification:

- **Excluded:** `.env`, `.env.*` (except `!.env.example`), `*.pem`, `*.key`, `*.secret`, `*.p12/.pfx/.jks`, `secrets/`, `*credentials*.json`, `*token*.txt`
- **Python:** `__pycache__/`, `*.py[cod]`, `.venv/`, `venv/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.coverage`, `htmlcov/`, `*.egg-info/`
- **Node:** `node_modules/`, `frontend/dist/`, `*.tsbuildinfo`, `frontend/vite.config.d.ts` (tsc build artifact)
- **Tooling metadata:** `.freebuff/`
- **Runtime data:** `*.log`, `logs/`, `data/`, `uploads/`, `db.sqlite3`, `docker-data/`

Verified empirically: marker files dropped into `.env`, `.venv`, `node_modules`, `__pycache__`, `.pytest_cache`, `*.tsbuildinfo` were all ignored, while `.env.example` stayed tracked.

## 4. Secrets policy

1. **No real secret ever enters the tree.** Every runtime secret comes from the environment (`DATABASE_URL`, `JWT_SECRET`, `SESSION_SECRET`, `ADMIN_PASSWORD`, `TELEGRAM_BOT_TOKEN`).
2. The application **refuses to start** in production without the required secrets (enforced in `backend/app/core/config.py`), so a deploy without them fails loudly rather than silently running with defaults.
3. `.env.example` contains placeholders only (`change-me…`).
4. Every commit is scanned before pushing (script below). During this verification the scan covered 122 staged files → **0 hits**; the two candidate hits were confirmed false positives (a Telegram documentation-format dummy token used inside `tests/test_security.py` via monkeypatch, and docker-compose variable interpolation).
5. If a secret ever lands in history: remove it from the working tree **and** purge history (see §7), rotate the secret itself, then force-push.

Pre-push scan (needs any Python 3.11+):

```bash
git add -A
python scripts/secret_scan.py    # exits non-zero on any hit
```

## 5. Commit workflow

```bash
git status                 # only intended changes
git add <paths>            # add specific files, never blanket-add new trees
git diff --cached          # review what will be committed
python scripts/secret_scan.py
git commit -m "feat: …"    # imperative, one blank line, then the why
```

## 6. Push workflow (remaining steps)

The only missing piece is **authentication**. Current facts:

- `git remote -v` → empty (no origin)
- `gh` CLI → not installed
- SSH → `git@github.com: Permission denied (publickey)` (no key registered with GitHub)
- Windows credential manager → no GitHub entry

Pick one of the two options below; the first is simplest on Windows.

### Option A — Git Credential Manager (recommended)

1. Create the empty repo on https://github.com/new
2. Run:

   ```bash
   git remote add origin https://github.com/<your-username>/<your-repo>.git
   git push -u origin main
   ```

3. A Git Credential Manager window opens → **Sign in with browser** → authorise.
4. Verify:

   ```bash
   git status                  # clean, up to date with origin/main
   git log origin/main --oneline -3
   ```

The token is stored in Windows Credential Manager; later pushes need no interaction.

### Option B — SSH key

```bash
ssh-keygen -t ed25519 -C "your_email@example.com" -f ~/.ssh/id_ed25519 -N ""
```

Copy the contents of `~/.ssh/id_ed25519.pub`, paste into
https://github.com/settings/keys → **New SSH key**, then:

```bash
git remote add origin git@github.com:<your-username>/<your-repo>.git
git push -u origin main
ssh -T git@github.com   # should greet you by username
```

### Troubleshooting a failed push

| Symptom | Cause | Fix |
|---|---|---|
| `Authentication failed` | bad/expired token | re-authenticate via Credential Manager |
| `Permission denied (publickey)` | key not registered | add the public key on GitHub |
| `Repository not found` | wrong URL or no access | check `git remote -v`, repo visibility/collaborator |
| `non-fast-forward` / `fetch first` | remote has commits you lack | `git pull --rebase origin main` then push |
| `unrelated histories` | remote was initialised with files | `git pull origin main --allow-unrelated-histories`, resolve, push |
| `protected branch` / required checks | branch rules | open a PR instead, or relax the rule |
| `push declined due to … secrets` | GitHub push protection | remove the secret, purge history (§7), rotate it, push again |
| `file exceeds … limit` / LFS prompt | file >100 MB | use Git LFS or drop the file from the tree |

**Never** `git push --force` without explicit intent to rewrite remote history.

## 7. If a secret reaches Git history

```bash
# 1. Stop and identify where it is
git log --all --oneline -- path/to/file
git show <commit>:path/to/file | grep -n <secret>

# 2. Remove from the current tree, move to environment config,
#    add a placeholder to .env.example, commit.

# 3. Purge history (rewrites commits!), e.g. with git-filter-repo:
pip install git-filter-repo
git filter-repo --path path/to/file --invert-paths
#    or a text replacement across all history:
git filter-repo --replace-text <(echo 'SECRET==>*')

# 4. Rotate the exposed credential (GitHub, Telegram @BotFather, DB password…).
#    Purging history without rotating is NOT a fix.

# 5. Re-add the remote (filter-repo drops it) and push:
git remote add origin <url>
git push -u origin main --force   # only now, and only with the owner's consent
```

## 8. Railway deployment from GitHub

1. https://railway.app/new → **Deploy from GitHub repo** → select the repository.
2. Railway builds from the `Dockerfile` (railway.toml sets `healthcheckPath = "/health"`). No build config needed.
3. Add the **Postgres** plugin; it injects `DATABASE_URL`. Reference it in the app service if it isn't linked automatically.
4. Set the remaining variables on the app service: `JWT_SECRET`, `SESSION_SECRET`, `ADMIN_PASSWORD` (all required; the app refuses to boot without them), optional `TELEGRAM_BOT_TOKEN`, `TELEGRAM_MINI_APP_URL`, `CORS_ORIGINS`.
5. Generate a domain (Settings → Networking). Railway routes to the port the app listens on; the app honours the injected `PORT` and binds `0.0.0.0` (verified locally).
6. First deploy runs Alembic to head and seeds roles + the initial admin. Watch the deploy logs for `database migrations complete` / `database seeding complete`, then `/health` and `/ready` should return 200.

> Status reminder: Railway deployment itself was **not executed** during verification — only its prerequisites were verified locally.

# Windows Production Server + Mac Dev Workflow

**Date:** 2026-04-25
**Goal:** Windows desktop runs the scanner 24/7 as a headless production server. Mac laptop develops strategies against the remote DB and deploys via git.

---

## Architecture

```
┌─────────────────────────────────┐       ┌──────────────────────────┐
│   WINDOWS DESKTOP (24/7)        │       │   MAC LAPTOP (dev)       │
│                                 │       │                          │
│   Docker Desktop                │       │   Code editor            │
│   ├── db (Postgres)             │◄──────│   ├── develop strategies │
│   ├── scraper-watch             │  SSH  │   ├── query remote DB    │
│   ├── spread-hunter             │  via   │   └── git push           │
│   └── universe-scanner          │Tailscale                       │
│                                 │       │                          │
│   Git repo (auto-pull)          │       │   Git repo               │
│   Schwab tokens                 │       │   Termius (SSH client)   │
│   pg_data volume                │       │                          │
└─────────────────────────────────┘       └──────────────────────────┘

         │
         │ Discord webhooks
         ▼
    Discord (alerts)
```

**Data flow:**
1. Windows scraper pulls option chains from Schwab every 5 min -> Postgres
2. Windows spread-hunter + universe-scanner run on schedule -> Discord alerts
3. Mac connects to Windows Postgres over Tailscale (port 5433)
4. Mac develops algo modules, tests against live data, git push
5. Windows auto-pulls changes and restarts services

**Deployment workflow:**
```
Mac: edit code -> git push -> ...
Windows: cron/webhook detects push -> git pull -> docker compose restart <service>
```

---

## Hardware

**Windows Desktop** -- Ryzen 5 5600X, 16GB RAM, RTX 3060, 2.27TB storage, Windows 11 Pro
- More than enough for Postgres + 3 Python services (~2GB RAM total)
- 2.27TB can hold years of option data at ~140MB/day
- RTX 3060 unused for now (could run ML models later)

---

## Phase 1: Windows Desktop Setup (do this first)

### 1a. Install Prerequisites

1. **Docker Desktop** (WSL2 backend)
   - Download from docker.com, install with WSL2 option
   - Settings -> General -> "Start Docker Desktop when you log in" (check)
   - Settings -> Resources -> allocate 4GB RAM, 2 CPUs (plenty)
   - After install, open PowerShell: `docker --version` to confirm

2. **Git for Windows**
   - Download from git-scm.com
   - Default options are fine
   - Configure: `git config --global user.name "arivera"` and email

3. **Tailscale** (VPN -- zero-config networking)
   - Download from tailscale.com
   - Install and log in (Google/GitHub/Microsoft account)
   - This gives the desktop a stable IP like `100.x.x.x` reachable from anywhere
   - Do the same on the Mac (install Tailscale, same account)
   - Test: from Mac, `ping <windows-tailscale-ip>`

4. **OpenSSH Server** (built into Windows 11 Pro)
   - Settings -> System -> Optional features -> Add a feature -> "OpenSSH Server" -> Install
   - Or PowerShell (admin):
     ```powershell
     Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
     Start-Service sshd
     Set-Service -Name sshd -StartupType Automatic
     ```
   - Test from Mac: `ssh <windows-username>@<tailscale-ip>`
   - Set up SSH key auth so you don't need passwords:
     - On Mac: `ssh-copy-id <windows-username>@<tailscale-ip>`
     - Or manually: copy Mac's `~/.ssh/id_rsa.pub` to Windows `C:\Users\<you>\.ssh\authorized_keys`

5. **Termius** (optional, just a nice SSH client)
   - Download from termius.com on Mac
   - Add host: `<tailscale-ip>`, port 22, your Windows username + SSH key
   - Termius is just a convenience -- `ssh` from Mac terminal works fine too

### 1b. Clone the Project on Windows

```powershell
# Pick a working directory
cd C:\Users\<you>
mkdir projects
cd projects

# Clone (HTTPS or SSH, whichever you have set up)
git clone <repo-url> tos_options
cd tos_options
```

### 1c. Configure Schwab Auth on Windows

Schwab auth requires a browser redirect. Do this ONCE on the Windows desktop:

```powershell
cd C:\Users\<you>\projects\tos_options
docker compose run --rm -it cli auth --prompt
```

This will give you a URL -> open in Windows browser -> log in -> paste redirect URL back.

Token files will be in the Docker volume. They refresh automatically for 7 days.

**IMPORTANT:** Set a reminder to re-auth every 7 days (or automate it). If the desktop is headless, you may need to RDP/VNC in for the browser step. Alternatively, auth on Mac, then copy the token files to Windows.

### 1d. Create .env on Windows

Create `C:\Users\<you>\projects\tos_options\.env`:

```env
SCHWAB_TOKEN_DIR=C:\Users\<you>\.schwabdev
POSTGRES_PASSWORD=changeme
DISCORD_WEBHOOK_URL=<your-discord-webhook>
DISCORD_SPREAD_WEBHOOK=<your-spread-webhook>
```

### 1e. Transfer Existing DB Data (Recommended)

The Mac has ~2 weeks of SPY/QQQ/$SPX data. IV rank filter needs 20+ days to activate.

```bash
# ON MAC -- dump the database
cd ~/projects/tos_options
docker compose exec -T db pg_dump -U trader options > tos_dump.sql
scp tos_dump.sql <windows-user>@<tailscale-ip>:C:/Users/<you>/projects/tos_options/
```

```powershell
# ON WINDOWS -- start just the DB first
cd C:\Users\<you>\projects\tos_options
docker compose up -d db
# Wait for it to be healthy (about 10 seconds)
docker compose exec -T db psql -U trader -d options < tos_dump.sql
# Verify
docker compose exec -T db psql -U trader -d options -c "SELECT COUNT(*) FROM snapshots;"
```

### 1f. Start All Services

```powershell
docker compose up -d
# Verify all running
docker compose ps
# Check logs
docker compose logs -f --tail 20
```

---

## Phase 2: Mac Dev Environment Setup

### 2a. Connect to Remote Postgres

The Mac already has the code. Just change the DB URL to point at Windows:

```bash
# Add to Mac's .zshrc or just export per-session
export DATABASE_URL="postgresql://trader:changeme@<tailscale-ip>:5433/options"
```

Now all Mac scripts work against the live Windows DB:
```bash
# Run algo pipeline against live data
python3 scripts/run_pipeline.py

# Run backtests against live data
python3 scripts/backtest_signals.py --ticker SPY

# Run spread backtest
python3 scripts/backtest_spreads.py --months 3
```

**No need for Docker on Mac anymore for this project.** The Mac becomes a pure dev client.

**Mac requirements** (system Python is fine for most things):
```bash
pip3 install psycopg psycopg2-binary pyyaml
```

Or just `cd tos_options && pip3 install -r requirements.txt` for full compat.

### 2b. Dev Workflow

```
1. Mac: edit code (new strategy, filter, etc.)
2. Mac: test against remote DB
   DATABASE_URL="postgresql://trader:changeme@100.x.x.x:5433/options" python3 scripts/run_pipeline.py
3. Mac: git add + git commit + git push
4. Windows: pulls changes and restarts (see Phase 3)
```

---

## Phase 3: Auto-Deploy (Mac push -> Windows restart)

### Option A: Simple Scheduled Task (recommended to start)

On the Windows desktop, create a deploy script:

```powershell
# Save as: C:\Users\<you>\projects\tos_options\deploy.ps1
cd C:\Users\<you>\projects\tos_options
git fetch origin
$local = git rev-parse HEAD
$remote = git rev-parse origin/main
if ($local -ne $remote) {
    git pull origin main
    docker compose up -d --build
    Add-Content -Path "deploy.log" -Value "$(Get-Date): Deployed $remote"
}
```

Then in Windows Task Scheduler:
- Trigger: every 5 minutes
- Action: `powershell -File C:\Users\<you>\projects\tos_options\deploy.ps1`
- Run whether user is logged in or not (check)

### Option B: Git Hook (more advanced)

If you set up a bare git repo on Windows as a remote, you can use a post-receive hook to auto-deploy. More complex, but instant.

### Option C: GitHub Webhook (if repo is on GitHub)

Push to GitHub -> webhook hits Windows -> Windows pulls and restarts. Requires Windows to be reachable from the internet (Tailscale Funnel or port forwarding). More setup.

**Start with Option A.** It's dead simple and works.

---

## Phase 4: Codebase Cleanup (can do anytime)

### 4a. Delete Dead Scripts (7 files, ~1,000 lines)

```
scripts/debug_signals.py              -- signal filter debugging
scripts/debug_width.py                -- strike width debugging
scripts/test_algo_signals.py          -- algo pipeline testing
scripts/massive_backtest.py           -- S3 backtest runner
scripts/massive_calendar_analysis.py  -- calendar spread analysis
scripts/fetch_massive_historical.py   -- S3 historical fetch
```

### 4b. Delete Raw Data

```
options-backtest/raw/  -- 130+ CSV.gz files, already in parquet
```

### 4c. Archive s3_test/

Move useful docs to `docs/`, delete the rest:
- `s3_test/algo_analysis.md` -> `docs/algo_analysis.md`
- `s3_test/DATA_GUIDE.md` -> `docs/DATA_GUIDE.md`
- Delete `s3_test/` directory

### 4d. Parameterize docker-compose.yml

Replace all `/Users/arivera/.schwabdev` with `${SCHWAB_TOKEN_DIR:-~/.schwabdev}` so it works on both machines.

### 4e. Fix Dockerfile

Remove stale `VOLUME /app/data` (SQLite no longer used).

### 4f. Add healthchecks to all services

Prevent zombie containers (bug already happened once).

### 4g. Drop scanner-watch service

The live_scanner.py is a subset of spread_hunter.py. Remove it from Docker services. Keep the file as a standalone tool.

### 4h. Add .gitattributes

```
*.py text eol=lf
*.sh text eol=lf
*.yml text eol=lf
*.yaml text eol=lf
```

Prevents CRLF issues when editing on Windows and running in Docker (Linux containers).

---

## Phase 5: Ongoing Maintenance

### Token Refresh (every 7 days)

Schwab refresh tokens expire after 7 days. Options:
1. **Manual:** RDP into Windows or SSH in, run `docker compose run --rm -it cli auth --prompt`, open browser
2. **Auto-reminder:** Discord bot or calendar reminder every Monday
3. **SSH + port forward:** SSH into Windows with `-L 8080:localhost:8080`, run auth, open redirect URL on Mac browser (this actually works if schwabdev binds to localhost)

### DB Size Management

At ~140MB/day with 3 tickers, growing to ~400MB/day with 8+ individual stocks:
- 1 month = ~4-12 GB
- 1 year = ~50-150 GB

Your 2.27TB is fine for 1+ year. Add a retention policy later if needed:
```sql
-- Example: delete snapshots older than 90 days for individual stocks
DELETE FROM snapshots WHERE symbol NOT IN ('SPY','QQQ','$SPX')
  AND captured_at::timestamp < NOW() - INTERVAL '90 days';
```

### Monitoring

- **Discord alerts** -- already built in for spread-hunter and universe-scanner
- **status_check.py** -- run via SSH: `ssh windows "cd tos_options && python scripts/status_check.py --troubleshoot"`
- **Docker healthchecks** -- built into compose, auto-restart on failure
- **Windows Task Scheduler** -- can email you if Docker Desktop stops

---

## Summary: Execution Order

| Priority | Step | Where | Time |
|----------|------|-------|------|
| 1 | Install Docker Desktop + Git + Tailscale on Windows | Windows | 30 min |
| 2 | Enable OpenSSH Server on Windows | Windows | 5 min |
| 3 | SSH from Mac to Windows (test with Termius) | Mac | 10 min |
| 4 | Clone repo on Windows | Windows | 5 min |
| 5 | Schwab auth on Windows (browser) | Windows | 10 min |
| 6 | Dump DB from Mac, transfer to Windows | Mac + Windows | 15 min |
| 7 | docker compose up -d on Windows | Windows | 5 min |
| 8 | Verify services running + Discord alerts | Mac (SSH) | 10 min |
| 9 | Mac connects to remote DB via Tailscale | Mac | 5 min |
| 10 | Set up auto-deploy (deploy.ps1 + scheduled task) | Windows | 15 min |
| 11 | Codebase cleanup (delete dead scripts, fix paths) | Mac | 30 min |
| 12 | Shut down Docker on Mac | Mac | 1 min |

Total: ~2.5 hours, most of it install/click/wait.

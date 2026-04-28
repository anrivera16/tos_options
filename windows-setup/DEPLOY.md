# Auto-Deploy: Mac push → Windows desktop

## How it works

```
Mac:     git push origin main
                ↓
GitHub:  hosts main branch
                ↓
Windows: Task Scheduler runs deploy.ps1 every 2 min
         - git fetch origin main
         - if HEAD != origin/main:
             git pull --ff-only
             docker compose up -d --build
         - log result to deploy.log
```

Lock file prevents overlapping runs during long rebuilds.

## One-time Windows setup

### 1. Set token dir in .env

Edit `C:\Users\arivera\projects\tos_options\.env`:

```
SCHWAB_TOKEN_DIR=C:\Users\arivera\.schwabdev
POSTGRES_PASSWORD=<existing>
DISCORD_WEBHOOK_URL=<existing>
DISCORD_SPREAD_WEBHOOK=<existing>
```

`docker-compose.yml` reads this and falls back to the Mac path if unset.

### 2. Create the scheduled task

PowerShell (admin):

```powershell
$action  = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File C:\Users\arivera\projects\tos_options\windows-setup\deploy.ps1"

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 2)

$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERNAME" `
    -LogonType S4U `
    -RunLevel Highest

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

Register-ScheduledTask -TaskName "tos_options-deploy" `
    -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings
```

Verify in Task Scheduler GUI: task `tos_options-deploy` should show "Running" or "Ready" with next run in <2 min.

### 3. First run

```powershell
Start-ScheduledTask -TaskName "tos_options-deploy"
Get-Content C:\Users\arivera\projects\tos_options\deploy.log -Tail 5
```

## Daily use

```
Mac:                          # edit code
git commit -am "..." && git push origin main

# 0-2 min later, Windows pulls and rebuilds. Tail the log to confirm:
ssh windows "Get-Content projects/tos_options/deploy.log -Tail 5"
```

## Operations

| Task | Command |
|------|---------|
| View recent deploys | `Get-Content deploy.log -Tail 20` |
| Run deploy now | `Start-ScheduledTask -TaskName "tos_options-deploy"` |
| Pause auto-deploy | `Disable-ScheduledTask -TaskName "tos_options-deploy"` |
| Resume | `Enable-ScheduledTask -TaskName "tos_options-deploy"` |
| Remove | `Unregister-ScheduledTask -TaskName "tos_options-deploy"` |

## Notes

- `--build` is cheap when nothing in the Dockerfile or `requirements.txt` changes (Docker layer cache). Most deploys take <30 sec.
- `git pull --ff-only` refuses to merge — if Windows has local changes, deploy fails and logs the error. Fix by SSHing in and resetting (`git reset --hard origin/main`) only if you're sure.
- The lock file (`.deploy.lock`) is auto-cleaned. Stale locks >30 min old are removed on the next run.

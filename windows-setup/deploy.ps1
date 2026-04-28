# tos_options auto-deploy
# Polls origin/main, pulls + restarts containers when changes are detected.
# Designed to be run by Windows Task Scheduler every 1-5 minutes.
#
# Setup: see windows-setup/DEPLOY.md

$ErrorActionPreference = "Stop"

$RepoDir  = "C:\Users\arivera\projects\tos_options"
$LogFile  = Join-Path $RepoDir "deploy.log"
$LockFile = Join-Path $RepoDir ".deploy.lock"

function Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $msg"
    Add-Content -Path $LogFile -Value $line
}

# Prevent overlapping runs (a long rebuild shouldn't be re-entered)
if (Test-Path $LockFile) {
    $age = (Get-Date) - (Get-Item $LockFile).LastWriteTime
    if ($age.TotalMinutes -lt 30) {
        Log "skip: lock held ($([int]$age.TotalSeconds)s old)"
        exit 0
    }
    Log "warn: stale lock (>30 min), removing"
    Remove-Item $LockFile -Force
}
New-Item -Path $LockFile -ItemType File | Out-Null

try {
    Set-Location $RepoDir

    git fetch origin main 2>&1 | Out-Null
    $local  = (git rev-parse HEAD).Trim()
    $remote = (git rev-parse origin/main).Trim()

    if ($local -eq $remote) { exit 0 }

    Log "deploy: $($local.Substring(0,7)) -> $($remote.Substring(0,7))"

    git pull --ff-only origin main 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Log "ERROR: git pull failed (exit $LASTEXITCODE)"
        exit 1
    }

    docker compose up -d --build 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Log "ERROR: docker compose failed (exit $LASTEXITCODE)"
        exit 1
    }

    Log "ok: deployed $($remote.Substring(0,7))"
}
finally {
    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
}

# =============================================================================
# deploy.ps1 - Auto-deploy script for tos_options on Windows
# =============================================================================
# Place this at:  D:\trading\tos_options\deploy.ps1
# Schedule via Windows Task Scheduler to run every 5 minutes:
#   Action:  powershell -ExecutionPolicy Bypass -File D:\trading\tos_options\deploy.ps1
#   Check:   "Run whether user is logged in or not"
# =============================================================================

# ---- CONFIG ----
$ProjectDir = "D:\trading\tos_options"
$Branch     = "main"
# ----------------

Set-Location $ProjectDir

# Stop on errors so a failed git/docker call doesn't silently log "deployed"
$ErrorActionPreference = "Stop"

try {
    git fetch origin $Branch | Out-Null

    $local  = (git rev-parse HEAD).Trim()
    $remote = (git rev-parse "origin/$Branch").Trim()

    if ($local -ne $remote) {
        Add-Content -Path "deploy.log" -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss'): change detected $local -> $remote, deploying..."

        git pull origin $Branch
        docker compose up -d --build

        Add-Content -Path "deploy.log" -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss'): deployed $remote"
    }
    # else: no change, stay quiet to keep deploy.log readable
}
catch {
    Add-Content -Path "deploy.log" -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss'): ERROR - $($_.Exception.Message)"
    exit 1
}

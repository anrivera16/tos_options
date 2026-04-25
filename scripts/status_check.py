#!/usr/bin/env python3
"""
TOS Options System Status Check

Verifies Docker services, database health, data freshness, and auth status.
Run:  python scripts/status_check.py
      python scripts/status_check.py --troubleshoot
"""

import sys
import subprocess
import argparse
from datetime import datetime, timezone, timedelta

# Eastern time for market-hour checks
ET = timezone(timedelta(hours=-4))

ALL_SERVICES = ["scraper-watch", "scanner-watch", "db", "spread-hunter", "universe-scanner"]


def _cmd(args, timeout=15, check=False):
    """Run a subprocess, return (stdout, stderr, returncode)."""
    try:
        r = subprocess.run(args, capture_output=True, text=True,
                           timeout=timeout, check=check)
        return r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        return "", "timed out", -1
    except FileNotFoundError:
        return "", f"command not found: {args[0]}", -1


def _db_query(sql):
    """Run a SQL query via docker exec, return raw psql output."""
    out, err, rc = _cmd(
        ["docker", "compose", "exec", "-T", "db",
         "psql", "-U", "trader", "-d", "options",
         "-t", "-A", "-c", sql],
        timeout=10,
    )
    if rc != 0:
        return None
    return out.strip()


# ── Docker Services ───────────────────────────────────────────────

def check_docker_services():
    """Check which Docker Compose services are running."""
    out, _, rc = _cmd(["docker", "compose", "ps", "--format", "json"])
    if rc != 0:
        print("  Unable to query Docker (is Docker running?)")
        return False

    import json
    try:
        containers = json.loads(out)
    except json.JSONDecodeError:
        print("  Unable to parse Docker output")
        return False

    running = {}
    health_info = {}
    for c in containers:
        svc = c.get("Service", "")
        running[svc] = c.get("State", "") == "running"
        h = c.get("Health", "")
        if h:
            health_info[svc] = h

    print("  Docker Services:")
    all_ok = True
    for svc in ALL_SERVICES:
        ok = running.get(svc, False)
        icon = "OK" if ok else "DOWN"
        extra = f" ({health_info.get(svc, '')})" if svc in health_info else ""
        print(f"    {svc}: {icon}{extra}")
        if not ok:
            all_ok = False
    return all_ok


# ── Database Health ───────────────────────────────────────────────

def check_database():
    """Check DB connectivity, snapshot counts, freshness, and contract data."""
    print("  Database:")

    # 1. Total snapshots
    result = _db_query("SELECT COUNT(*) FROM snapshots;")
    if result is None:
        print("    Cannot connect to database")
        return False
    total_snaps = int(result) if result.isdigit() else 0
    print(f"    Total snapshots: {total_snaps:,}")
    if total_snaps == 0:
        print("    No data in database")
        return False

    # 2. Total contracts
    result = _db_query("SELECT COUNT(*) FROM option_contracts;")
    total_contracts = int(result) if result and result.isdigit() else 0
    print(f"    Total contracts: {total_contracts:,}")

    # 3. Latest snapshot timestamp
    latest = _db_query(
        "SELECT MAX(captured_at::text) FROM snapshots;"
    )
    print(f"    Latest snapshot: {latest or 'unknown'}")

    # 4. Snapshots today
    today_count = _db_query(
        "SELECT COUNT(*) FROM snapshots WHERE captured_at::timestamp >= CURRENT_DATE;"
    )
    today_count = int(today_count) if today_count and today_count.isdigit() else 0
    print(f"    Today's snapshots: {today_count:,}")

    # 5. Contracts today
    today_contracts = _db_query("""
        SELECT COUNT(*) FROM option_contracts oc
        JOIN snapshots s ON oc.snapshot_id = s.id
        WHERE s.captured_at::timestamp >= CURRENT_DATE;
    """)
    today_contracts = int(today_contracts) if today_contracts and today_contracts.isdigit() else 0
    print(f"    Today's contracts: {today_contracts:,}")

    # 6. Per-symbol breakdown today
    symbols = _db_query("""
        SELECT s.symbol, COUNT(DISTINCT s.id) as snaps
        FROM snapshots s
        WHERE s.captured_at::timestamp >= CURRENT_DATE
        GROUP BY s.symbol
        ORDER BY snaps DESC;
    """)
    if symbols:
        print("    Today by symbol:")
        for line in symbols.splitlines():
            if "|" in line:
                sym, cnt = line.split("|", 1)
                print(f"      {sym}: {cnt} snapshots")

    # 7. Freshness — snapshots in last 30 min
    recent = _db_query("""
        SELECT COUNT(*) FROM snapshots
        WHERE captured_at::timestamp >= NOW() - INTERVAL '30 minutes';
    """)
    recent = int(recent) if recent and recent.isdigit() else 0

    now_et = datetime.now(ET)
    is_market_hours = (
        now_et.weekday() < 5
        and now_et.hour >= 9
        and (now_et.hour < 16)
    )

    if recent > 0:
        print(f"    Freshness: {recent} snapshots in last 30 min")
        return True
    elif is_market_hours:
        print("    STALE: no new data in 30 min (market is open!)")
        return False
    else:
        print("    Freshness: no recent data (market closed, expected)")
        return True


# ── Authentication ────────────────────────────────────────────────

def check_auth():
    """Check auth by looking at token files and recent scraper behavior."""
    print("  Authentication:")

    # Check if token files exist inside the scraper container
    out, err, rc = _cmd(
        ["docker", "compose", "exec", "-T", "scraper-watch",
         "ls", "-la", "/root/.schwabdev/"],
        timeout=5,
    )
    if rc != 0:
        print("    Cannot reach scraper container")
        return False

    has_tokens = False
    token_age = None
    for line in out.splitlines():
        if ".json" in line or "token" in line.lower():
            has_tokens = True
            # Try to parse mtime from ls -la
            parts = line.split()
            if len(parts) >= 9:
                # ls -la format: perms, links, owner, group, size, month, day, time/year, name
                date_str = " ".join(parts[5:8])
                print(f"    Token file: {parts[-1]} ({date_str})")

    if not has_tokens:
        print("    No token files found")
        return False

    # Check recent scraper logs for auth errors
    out, _, _ = _cmd(
        ["docker", "compose", "logs", "--tail", "20", "scraper-watch"],
        timeout=5,
    )
    auth_errors = [
        "invalid_grant",
        "refresh token has expired",
        "unauthorized",
        "401",
        "authentication failed",
    ]
    for line in out.lower().splitlines():
        if any(e in line for e in auth_errors):
            print("    EXPIRED: auth errors found in recent logs")
            return False

    # If scraper has recent successful snapshots, auth is good
    if "snapshot" in out.lower():
        print("    OK (recent successful scrapes)")
        return True

    print("    Tokens present, no errors in logs")
    return True


# ── Recent Activity ───────────────────────────────────────────────

def check_recent_activity():
    """Tail recent logs from each service."""
    print("  Recent Activity:")

    services = ["scraper-watch", "scanner-watch", "spread-hunter"]
    any_active = False
    today = datetime.now(ET).strftime("%Y-%m-%d")

    for svc in services:
        out, _, _ = _cmd(
            ["docker", "compose", "logs", "--tail", "5", svc],
            timeout=5,
        )
        if not out.strip():
            print(f"    {svc}: no logs")
            continue

        found_today = False
        for line in out.splitlines():
            if today in line:
                found_today = True
                # Truncate long lines
                display = line.strip()[:120]
                print(f"    {display}")

        if not found_today:
            print(f"    {svc}: no activity today")
        else:
            any_active = True

    return any_active


# ── Troubleshooting ───────────────────────────────────────────────

def print_troubleshooting():
    print()
    print("  Troubleshooting:")
    print("  " + "=" * 48)
    print()
    print("  1. AUTH EXPIRED (most common, ~every 7 days):")
    print("     docker compose run --rm cli auth")
    print("     # open the URL in browser, login, get callback URL")
    print("     docker compose run --rm cli auth --prompt")
    print("     # paste the callback URL FAST (30s expiry)")
    print("     docker compose restart scraper-watch scanner-watch spread-hunter")
    print()
    print("  2. SERVICE NOT RUNNING:")
    print("     docker compose up -d        # start everything")
    print("     docker compose restart <svc> # restart one service")
    print()
    print("  3. WATCH LIVE LOGS:")
    print("     docker compose logs -f scraper-watch scanner-watch")
    print()
    print("  4. MARKET HOURS:")
    now_et = datetime.now(ET)
    print(f"     Current time: {now_et.strftime('%A %Y-%m-%d %I:%M %p ET')}")
    print("     Market: Mon-Fri 9:30 AM - 4:00 PM ET")
    print("     Scraper only runs during market hours.")
    print()
    print("  5. DATABASE:")
    print("     docker compose exec -T db psql -U trader -d options")
    print("     SELECT COUNT(*) FROM snapshots WHERE captured_at::timestamp >= CURRENT_DATE;")


# ── Main ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="TOS Options system status check"
    )
    parser.add_argument("--troubleshoot", action="store_true",
                        help="Always show troubleshooting guide")
    args = parser.parse_args()

    now_et = datetime.now(ET)
    print(f"TOS Options Status Check  ({now_et.strftime('%Y-%m-%d %I:%M %p ET')})")
    print("=" * 52)

    services_ok = check_docker_services()
    print()
    db_ok = check_database()
    print()
    auth_ok = check_auth()
    print()
    activity_ok = check_recent_activity()

    # Summary
    print()
    print("  Summary:")
    print(f"    Docker services: {'OK' if services_ok else 'ISSUES'}")
    print(f"    Database:        {'OK' if db_ok else 'ISSUES'}")
    print(f"    Authentication:  {'OK' if auth_ok else 'ISSUES'}")
    print(f"    Recent activity: {'OK' if activity_ok else 'STALE'}")

    all_ok = services_ok and db_ok and auth_ok and activity_ok

    if args.troubleshoot or not all_ok:
        print_troubleshooting()

    if all_ok:
        print("  All systems operational.")
        return 0
    else:
        print("  Issues detected -- see details above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

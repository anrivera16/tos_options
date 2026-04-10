#!/usr/bin/env python3
"""
Calendar Spread Analysis using Massive MCP Server v0.8+
Uses the new 4-tool architecture: search, docs, call_api, query_data
"""

import subprocess
import json
import os
import sys


def run_massive_analysis():
    env = os.environ.copy()
    env["MASSIVE_API_KEY"] = "eAOickvOvgp6jaSFQ9TNpiMdHqP6tVbt"

    proc = subprocess.Popen(
        ["/Users/arivera/.local/bin/mcp_massive"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    def send_request(req):
        proc.stdin.write(json.dumps(req) + "\n")
        proc.stdin.flush()
        return json.loads(proc.stdout.readline())

    # Initialize
    send_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "calendar-spread", "version": "1.0"},
            },
        }
    )

    print("=" * 70)
    print("MASSIVE MCP SERVER - CALENDAR SPREAD ANALYSIS")
    print("=" * 70)

    # Step 1: Fetch SPY options contracts reference
    print("\n[1] Fetching SPY options contract reference...")
    send_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "call_api",
                "arguments": {
                    "method": "GET",
                    "path": "/v3/reference/options/contracts",
                    "params": {"underlying_ticker": "SPY", "limit": 500},
                    "store_as": "contracts",
                },
            },
        }
    )

    # Step 2: Get all available expirations
    print("[2] Analyzing available expirations...")
    response = send_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "query_data",
                "arguments": {
                    "sql": """
                       SELECT 
                           expiration_date,
                           COUNT(*) as contract_count,
                           MIN(strike_price) as min_strike,
                           MAX(strike_price) as max_strike,
                           AVG(strike_price) as avg_strike
                       FROM contracts 
                       GROUP BY expiration_date 
                       ORDER BY expiration_date
                       LIMIT 10
                   """
                },
            },
        }
    )

    expirations = []
    for item in response.get("result", {}).get("content", []):
        if item.get("type") == "text":
            lines = item["text"].strip().split("\n")[1:]  # Skip header
            for line in lines:
                parts = line.split(",")
                if len(parts) >= 2:
                    expirations.append(
                        {
                            "date": parts[0],
                            "count": int(parts[1]),
                            "avg_strike": float(parts[4]),
                        }
                    )
            print(f"    Found {len(expirations)} expiration dates")

    # Step 3: Fetch SPY price
    print("[3] Fetching SPY price...")
    send_request(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "call_api",
                "arguments": {
                    "method": "GET",
                    "path": "/v2/aggs/ticker/SPY/prev",
                    "store_as": "spy_price",
                },
            },
        }
    )

    response = send_request(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "query_data",
                "arguments": {"sql": "SELECT c as price FROM spy_price LIMIT 1"},
            },
        }
    )

    spy_price = 676.01  # Default
    for item in response.get("result", {}).get("content", []):
        if item.get("type") == "text":
            try:
                spy_price = float(item["text"].strip().split("\n")[1])
                print(f"    SPY Price: ${spy_price:.2f}")
            except:
                pass

    # Step 4: Find ATM strikes for each expiration
    print("[4] Finding ATM options...")

    atm_data = []
    for exp in expirations[:5]:  # Analyze first 5 expirations
        response = send_request(
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {
                    "name": "query_data",
                    "arguments": {
                        "sql": f"""
                           SELECT 
                               strike_price,
                               ticker,
                               ABS(CAST(strike_price AS REAL) - {spy_price}) as dist
                           FROM contracts
                           WHERE expiration_date = '{exp["date"]}'
                             AND contract_type = 'call'
                           ORDER BY dist
                           LIMIT 1
                       """
                    },
                },
            }
        )

        for item in response.get("result", {}).get("content", []):
            if item.get("type") == "text":
                lines = item["text"].strip().split("\n")[1:]
                for line in lines:
                    parts = line.split(",")
                    if len(parts) >= 2:
                        atm_strike = float(parts[0])
                        ticker = parts[1]
                        atm_data.append(
                            {
                                "expiration": exp["date"],
                                "strike": atm_strike,
                                "ticker": ticker,
                                "spy_price": spy_price,
                            }
                        )

    # Step 5: Fetch snapshot data for IV
    print("[5] Fetching options snapshot with IV...")
    send_request(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "call_api",
                "arguments": {
                    "method": "GET",
                    "path": "/v3/snapshot/options/SPY",
                    "store_as": "snapshot",
                },
            },
        }
    )

    # Step 6: Analyze calendar spread opportunities
    print("\n" + "=" * 70)
    print("CALENDAR SPREAD ANALYSIS")
    print("=" * 70)

    if len(atm_data) >= 2:
        print(f"\n{'FRONT EXP':<12} {'BACK EXP':<12} {'STRIKE':>8} {'SETUP':<20}")
        print("-" * 70)

        for i, front in enumerate(atm_data):
            for back in atm_data[i + 1 :]:
                # Check if same strike
                if abs(front["strike"] - back["strike"]) < 5:
                    print(
                        f"{front['expiration']:<12} {back['expiration']:<12} "
                        f"{front['strike']:>8.2f} Calendar Spread (Same Strike)"
                    )
    else:
        print("\nInsufficient expiration data for calendar spread analysis.")
        print("Need at least 2 expiration dates with ATM options.")

    # Show summary
    print("\n" + "=" * 70)
    print("DATA SUMMARY")
    print("=" * 70)
    print(f"SPY Price: ${spy_price:.2f}")
    print(f"Expirations found: {len(expirations)}")
    print(f"ATM strikes mapped: {len(atm_data)}")

    if expirations:
        print("\nExpiration Dates:")
        for exp in expirations[:10]:
            print(
                f"  {exp['date']}: {exp['count']} contracts, avg strike ${exp['avg_strike']:.2f}"
            )

    proc.terminate()
    print("\n" + "=" * 70)
    print("Analysis complete!")
    print("=" * 70)


if __name__ == "__main__":
    run_massive_analysis()

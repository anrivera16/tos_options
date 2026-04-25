from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from discord.webhook import DiscordWebhookError, send_message, send_png
from gex import compute_exposure_report, compute_gex
from gex.chart import generate_chart
from gex.storage import (
    DEFAULT_DB_PATH,
    get_connection,
    init_db,
    insert_aggregate_rows,
    insert_option_contracts,
    insert_snapshot,
)
from schwab.api import (
    get_expirations,
    get_option_chain,
    get_option_chain_rows,
    get_quote,
)
from schwab.client import SchwabConfigError, build_authorize_url, create_client


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        args.func(args)
    except SchwabConfigError as exc:
        raise SystemExit(str(exc)) from exc
    except DiscordWebhookError as exc:
        raise SystemExit(str(exc)) from exc


def gexd_main() -> None:
    parser = argparse.ArgumentParser(
        prog="gexd",
        description="Render a GEX chart and upload the PNG to Discord",
    )
    parser.add_argument("symbol", nargs="?", default="SPY")
    parser.add_argument("max_levels", nargs="?", type=int, default=10)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--history-days", type=int, default=60)
    parser.add_argument("--interval-hours", type=int, default=1)
    parser.add_argument("--output")
    parser.add_argument("--extended-hours", action="store_true")

    args = parser.parse_args()
    symbol = args.symbol.upper()
    output = args.output or f"out/{symbol.lower()}_gex_price_overlay.png"

    command_args = argparse.Namespace(
        symbol=symbol,
        days=args.days,
        history_days=args.history_days,
        interval_hours=args.interval_hours,
        max_levels=args.max_levels,
        output=output,
        contract_type="ALL",
        option_range="OTM",
        strike_range=None,
        strategy="SINGLE",
        extended_hours=args.extended_hours,
    )

    try:
        run_gex_chart_discord(command_args)
    except SchwabConfigError as exc:
        raise SystemExit(str(exc)) from exc
    except DiscordWebhookError as exc:
        raise SystemExit(str(exc)) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Schwab data utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── Auth ──
    auth_parser = subparsers.add_parser("auth", help="Authentication commands")
    auth_parser.add_argument("--callback-url", help="OAuth callback URL to exchange")
    auth_parser.add_argument(
        "--prompt", action="store_true", help="Read callback URL from stdin"
    )
    auth_parser.set_defaults(func=run_auth)
    auth_subparsers = auth_parser.add_subparsers(dest="auth_command")

    auth_login_parser = auth_subparsers.add_parser(
        "login", help="Print auth URL or exchange callback URL"
    )
    auth_login_parser.add_argument(
        "--callback-url", help="OAuth callback URL to exchange"
    )
    auth_login_parser.add_argument(
        "--prompt", action="store_true", help="Read callback URL from stdin"
    )
    auth_login_parser.set_defaults(func=run_auth)

    # ── Market ──
    market_parser = subparsers.add_parser("market", help="Market data commands")
    market_subparsers = market_parser.add_subparsers(
        dest="market_command", required=True
    )

    quote_parser = market_subparsers.add_parser("quote", help="Fetch a quote")
    quote_parser.add_argument("--symbol", default="SPY")
    quote_parser.set_defaults(func=run_quote)

    # ── Options ──
    options_parser = subparsers.add_parser("options", help="Options chain commands")
    options_subparsers = options_parser.add_subparsers(
        dest="options_command", required=True
    )

    expirations_parser = options_subparsers.add_parser(
        "expirations", help="Fetch option expirations"
    )
    expirations_parser.add_argument("--symbol", default="SPY")
    expirations_parser.set_defaults(func=run_expirations)

    fetch_parser = options_subparsers.add_parser(
        "fetch", help="Fetch normalized option rows"
    )
    add_option_chain_arguments(fetch_parser)
    fetch_parser.add_argument("--output", default="out/options.csv")
    fetch_parser.add_argument("--json-output", help="Optional raw JSON output path")
    fetch_parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    fetch_parser.add_argument("--persist-db", action="store_true")
    fetch_parser.set_defaults(func=run_fetch_options)

    # ── IV Term Structure ──
    from gex.iv_term import register_parser as _reg_iv_term
    _reg_iv_term(subparsers)

    # ── Universe Scanner ──
    universe_parser = subparsers.add_parser(
        "universe", help="Scan and rank stocks for options trading"
    )
    universe_subparsers = universe_parser.add_subparsers(
        dest="universe_command", required=True
    )
    universe_scan_parser = universe_subparsers.add_parser(
        "scan", help="Run universe scan now"
    )
    universe_scan_parser.add_argument("--top", type=int, default=None,
                                       help="Override max names to select")
    universe_scan_parser.add_argument("--save", action="store_true",
                                       help="Save selected tickers to config file")

    def _run_universe_scan(args):
        import subprocess
        import sys as _sys
        script = str(Path(__file__).parent / "scripts" / "universe_scanner.py")
        cmd = [_sys.executable, script, "--scan"]
        if args.top:
            cmd += ["--top", str(args.top)]
        if args.save:
            cmd.append("--save")
        result = subprocess.run(cmd)
        return result.returncode

    universe_scan_parser.set_defaults(func=_run_universe_scan)

    # ── Exposure ──
    exposure_parser = subparsers.add_parser(
        "exposure", help="Exposure and persistence commands"
    )
    exposure_subparsers = exposure_parser.add_subparsers(
        dest="exposure_command", required=True
    )

    gex_parser = exposure_subparsers.add_parser(
        "gex", help="Compute GEX from option chain rows"
    )
    add_option_chain_arguments(gex_parser)
    gex_parser.add_argument("--output", help="Optional JSON report output path")
    gex_parser.add_argument("--json-output", help="Optional raw JSON output path")
    gex_parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    gex_parser.add_argument("--persist-db", action="store_true")
    gex_parser.set_defaults(func=run_gex)

    history_parser = exposure_subparsers.add_parser(
        "history", help="Show recent persisted exposure snapshots"
    )
    history_parser.add_argument("--symbol", default="SPY")
    history_parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    history_parser.add_argument("--limit", type=int, default=10)
    history_parser.set_defaults(func=run_gex_history)

    # ── Chart ──
    chart_parser = subparsers.add_parser(
        "chart", help="Chart rendering and publishing commands"
    )
    chart_subparsers = chart_parser.add_subparsers(dest="chart_command", required=True)

    chart_render_parser = chart_subparsers.add_parser(
        "render", help="Render hourly price chart with current GEX levels"
    )
    add_option_chain_arguments(chart_render_parser)
    chart_render_parser.add_argument("--history-days", type=int, default=60)
    chart_render_parser.add_argument("--interval-hours", type=int, default=1)
    chart_render_parser.add_argument("--max-levels", type=int, default=10)
    chart_render_parser.add_argument("--output", default="out/gex_price_overlay.png")
    chart_render_parser.add_argument("--extended-hours", action="store_true")
    chart_render_parser.add_argument(
        "--discord", action="store_true", help="Upload the rendered PNG to Discord"
    )
    chart_render_parser.set_defaults(func=run_gex_chart)

    chart_post_parser = chart_subparsers.add_parser(
        "post", help="Render a GEX chart and upload it to Discord"
    )
    add_option_chain_arguments(chart_post_parser)
    chart_post_parser.add_argument("--history-days", type=int, default=60)
    chart_post_parser.add_argument("--interval-hours", type=int, default=1)
    chart_post_parser.add_argument("--max-levels", type=int, default=10)
    chart_post_parser.add_argument("--output", default="out/gex_price_overlay.png")
    chart_post_parser.add_argument("--extended-hours", action="store_true")
    chart_post_parser.add_argument(
        "--discord", action="store_true", help="Upload the rendered PNG to Discord"
    )
    chart_post_parser.set_defaults(func=run_gex_chart_discord)

    chart_send_parser = chart_subparsers.add_parser(
        "send", help="Upload a PNG file to a Discord webhook"
    )
    chart_send_parser.add_argument("--file", required=True)
    chart_send_parser.set_defaults(func=run_discord_send)

    # ── Legacy top-level commands ──
    legacy_fetch_parser = subparsers.add_parser(
        "fetch-options", help="Fetch normalized option rows"
    )
    add_option_chain_arguments(legacy_fetch_parser)
    legacy_fetch_parser.add_argument("--output", default="out/options.csv")
    legacy_fetch_parser.add_argument(
        "--json-output", help="Optional raw JSON output path"
    )
    legacy_fetch_parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    legacy_fetch_parser.add_argument("--persist-db", action="store_true")
    legacy_fetch_parser.set_defaults(func=run_fetch_options)

    legacy_gex_parser = subparsers.add_parser(
        "gex", help="Compute GEX from option chain rows"
    )
    add_option_chain_arguments(legacy_gex_parser)
    legacy_gex_parser.add_argument("--output", help="Optional JSON report output path")
    legacy_gex_parser.add_argument(
        "--json-output", help="Optional raw JSON output path"
    )
    legacy_gex_parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    legacy_gex_parser.add_argument("--persist-db", action="store_true")
    legacy_gex_parser.set_defaults(func=run_gex)

    legacy_history_parser = subparsers.add_parser(
        "gex-history", help="Show recent persisted exposure snapshots"
    )
    legacy_history_parser.add_argument("--symbol", default="SPY")
    legacy_history_parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    legacy_history_parser.add_argument("--limit", type=int, default=10)
    legacy_history_parser.set_defaults(func=run_gex_history)

    legacy_chart_parser = subparsers.add_parser(
        "gex-chart", help="Render hourly price chart with current GEX levels"
    )
    add_option_chain_arguments(legacy_chart_parser)
    legacy_chart_parser.add_argument("--history-days", type=int, default=60)
    legacy_chart_parser.add_argument("--interval-hours", type=int, default=1)
    legacy_chart_parser.add_argument("--max-levels", type=int, default=10)
    legacy_chart_parser.add_argument("--output", default="out/gex_price_overlay.png")
    legacy_chart_parser.add_argument("--extended-hours", action="store_true")
    legacy_chart_parser.set_defaults(func=run_gex_chart)

    legacy_discord_send_parser = subparsers.add_parser(
        "discord-send", help="Upload a PNG file to a Discord webhook"
    )
    legacy_discord_send_parser.add_argument("--file", required=True)
    legacy_discord_send_parser.set_defaults(func=run_discord_send)

    legacy_chart_discord_parser = subparsers.add_parser(
        "gex-chart-discord",
        help="Render GEX chart locally and upload the PNG to Discord",
    )
    add_option_chain_arguments(legacy_chart_discord_parser)
    legacy_chart_discord_parser.add_argument("--history-days", type=int, default=60)
    legacy_chart_discord_parser.add_argument("--interval-hours", type=int, default=1)
    legacy_chart_discord_parser.add_argument("--max-levels", type=int, default=10)
    legacy_chart_discord_parser.add_argument(
        "--output", default="out/gex_price_overlay.png"
    )
    legacy_chart_discord_parser.add_argument("--extended-hours", action="store_true")
    legacy_chart_discord_parser.set_defaults(func=run_gex_chart_discord)

    legacy_quote_parser = subparsers.add_parser("quote", help="Fetch a quote")
    legacy_quote_parser.add_argument("--symbol", default="SPY")
    legacy_quote_parser.set_defaults(func=run_quote)

    legacy_expirations_parser = subparsers.add_parser(
        "expirations", help="Fetch option expirations"
    )
    legacy_expirations_parser.add_argument("--symbol", default="SPY")
    legacy_expirations_parser.set_defaults(func=run_expirations)

    return parser


def add_option_chain_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--from-date")
    parser.add_argument("--to-date")
    parser.add_argument("--contract-type", default="ALL")
    parser.add_argument("--option-range", default="OTM")
    parser.add_argument("--strike-range")
    parser.add_argument("--interval", default="1")
    parser.add_argument("--strategy", default="SINGLE")


def _resolve_dates(args: argparse.Namespace) -> tuple[str, str]:
    if args.from_date:
        start = datetime.fromisoformat(args.from_date).date()
    else:
        start = date.today()

    if args.to_date:
        end = datetime.fromisoformat(args.to_date).date()
    else:
        end = start + timedelta(days=args.days)

    return start.isoformat(), end.isoformat()


def _write_json(path: str | None, payload: Any) -> None:
    if not path:
        return
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )


def _write_csv(path: str, rows: list[dict[str, Any]]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        output_path.write_text("", encoding="utf-8")
        return

    fieldnames = [key for key in rows[0].keys() if key != "raw"]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def _load_chain_and_rows(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from_date, to_date = _resolve_dates(args)
    chain = get_option_chain(
        symbol=args.symbol,
        from_date=from_date,
        to_date=to_date,
        contract_type=args.contract_type,
        option_range=args.option_range,
        strike_range=args.strike_range,
        strategy=args.strategy,
        interval=args.interval,
    )
    rows = get_option_chain_rows(
        symbol=args.symbol,
        from_date=from_date,
        to_date=to_date,
        contract_type=args.contract_type,
        option_range=args.option_range,
        strike_range=args.strike_range,
        strategy=args.strategy,
        interval=args.interval,
    )
    return chain, rows


def _persist_snapshot(
    db_path: str,
    source: str,
    chain: dict[str, Any],
    rows: list[dict[str, Any]],
    skip_raw_json: bool = False,
) -> int:
    if not rows:
        return 0
    captured_at = str(rows[0].get("snapshot_captured_at") or datetime.now().isoformat())
    spot = next(
        (
            float(row["underlying_price"])
            for row in rows
            if row.get("underlying_price") not in (None, "")
        ),
        None,
    )
    snapshot_symbol = str(
        chain.get("symbol")
        or rows[0].get("underlying_symbol")
        or rows[0].get("symbol")
        or ""
    ).upper()
    connection = get_connection(db_path)
    try:
        init_db(connection)
        snapshot_id = insert_snapshot(
            connection,
            symbol=snapshot_symbol,
            captured_at=captured_at,
            underlying_price=spot,
            source=source,
            chain_payload=chain,
            skip_raw_json=skip_raw_json,
        )
        insert_option_contracts(
            connection, snapshot_id, rows, skip_raw_json=skip_raw_json
        )
        exposure_report = compute_exposure_report(rows)
        strike_rows = []
        for row in exposure_report["by_strike"]:
            strike_rows.append(
                {
                    "snapshot_id": snapshot_id,
                    "strike": row["strike"],
                    "net_gex": row["net_gex"],
                    "call_gex": row["call_gex"],
                    "put_gex": row["put_gex"],
                    "net_dex": row["net_dex"],
                    "net_vex": row["net_vex"],
                    "net_tex": row["net_tex"],
                    "open_interest_total": row["total_oi"],
                    "volume_total": row["total_volume"],
                    "contracts_count": row["contracts_count"],
                    "expirations_json": row["expirations"],
                }
            )
        expiry_rows = []
        for row in exposure_report["by_expiration"]:
            expiry_rows.append(
                {
                    "snapshot_id": snapshot_id,
                    "expiration_date": row["expiration_date"],
                    "dte": row["dte"],
                    "net_gex": row["net_gex"],
                    "call_gex": row["call_gex"],
                    "put_gex": row["put_gex"],
                    "net_dex": row["net_dex"],
                    "net_vex": row["net_vex"],
                    "net_tex": row["net_tex"],
                    "call_oi": row["call_oi"],
                    "put_oi": row["put_oi"],
                    "total_oi": row["total_oi"],
                    "total_volume": row["total_volume"],
                    "pcr_oi": row["pcr_oi"],
                    "pcr_volume": row["pcr_volume"],
                    "atm_iv": row["atm_iv"],
                }
            )
        bucket_rows = []
        for row in exposure_report["by_bucket"]:
            bucket_rows.append(
                {
                    "snapshot_id": snapshot_id,
                    "bucket_type": row["bucket_type"],
                    "bucket_label": row["bucket_label"],
                    "net_gex": row["net_gex"],
                    "net_dex": row["net_dex"],
                    "net_vex": row["net_vex"],
                    "net_tex": row["net_tex"],
                    "call_oi": row["call_oi"],
                    "put_oi": row["put_oi"],
                    "total_oi": row["total_oi"],
                    "total_volume": row["total_volume"],
                    "contracts_count": row["contracts_count"],
                }
            )
        insert_aggregate_rows(connection, "aggregates_by_strike", strike_rows)
        insert_aggregate_rows(connection, "aggregates_by_expiry", expiry_rows)
        insert_aggregate_rows(connection, "aggregates_by_bucket", bucket_rows)
        return snapshot_id
    finally:
        connection.close()


def run_auth(args: argparse.Namespace) -> None:
    callback_url = args.callback_url
    if args.prompt and not callback_url:
        callback_url = input("Paste Schwab callback URL: ").strip()

    if callback_url:
        client = create_client(call_on_auth=lambda _: callback_url)
        client.update_tokens(force_refresh_token=True)
        print("Authentication completed.")
        return

    print(build_authorize_url())


def run_quote(args: argparse.Namespace) -> None:
    payload = get_quote(args.symbol)
    print(json.dumps(payload, indent=2, sort_keys=True))


def run_expirations(args: argparse.Namespace) -> None:
    payload = get_expirations(args.symbol)
    print(json.dumps(payload, indent=2, sort_keys=True))


def run_fetch_options(args: argparse.Namespace) -> None:
    chain, rows = _load_chain_and_rows(args)
    _write_json(args.json_output, chain)
    _write_csv(args.output, rows)
    snapshot_message = ""
    if args.persist_db:
        snapshot_id = _persist_snapshot(args.db_path, "fetch-options", chain, rows)
        snapshot_message = f" and persisted snapshot {snapshot_id} to {args.db_path}"
    print(f"Wrote {len(rows)} option rows to {args.output}{snapshot_message}")


def run_gex(args: argparse.Namespace) -> None:
    chain, rows = _load_chain_and_rows(args)
    _write_json(args.json_output, chain)
    report = compute_exposure_report(rows)
    report["headline_gex"] = compute_gex(rows)
    if args.persist_db:
        snapshot_id = _persist_snapshot(args.db_path, "gex", chain, rows)
        report["snapshot_id"] = snapshot_id
    if args.output:
        _write_json(args.output, report)
        print(f"Wrote GEX report to {args.output}")
        return
    print(json.dumps(report, indent=2, sort_keys=True))


def run_gex_history(args: argparse.Namespace) -> None:
    connection = get_connection(args.db_path)
    try:
        init_db(connection)
        rows = connection.execute(
            """
            SELECT id, symbol, captured_at, underlying_price, source
            FROM snapshots
            WHERE symbol = ?
            ORDER BY captured_at DESC
            LIMIT ?
            """,
            (args.symbol.upper(), args.limit),
        ).fetchall()
    finally:
        connection.close()

    payload = [dict(row) for row in rows]
    print(json.dumps(payload, indent=2, sort_keys=True))


def run_gex_chart(args: argparse.Namespace) -> None:
    result = generate_chart(
        symbol=args.symbol,
        days=args.days,
        history_days=args.history_days,
        interval_hours=args.interval_hours,
        max_levels=args.max_levels,
        output=args.output,
        contract_type=args.contract_type,
        option_range=args.option_range,
        strike_range=args.strike_range,
        strategy=args.strategy,
        extended_hours=args.extended_hours,
    )
    print(
        f"Wrote GEX overlay chart for {result['symbol']} to {result['output']} "
        f"using {result['option_contracts']} option rows and {result['hourly_candles']} candles."
    )
    if getattr(args, "discord", False):
        send_png(result["png_output"])
        print(f"Uploaded PNG to Discord webhook: {result['png_output']}")


def run_discord_send(args: argparse.Namespace) -> None:
    send_png(args.file)
    print(f"Uploaded PNG to Discord webhook: {args.file}")


def run_gex_chart_discord(args: argparse.Namespace) -> None:
    result = generate_chart(
        symbol=args.symbol,
        days=args.days,
        history_days=args.history_days,
        interval_hours=args.interval_hours,
        max_levels=args.max_levels,
        output=args.output,
        contract_type=args.contract_type,
        option_range=args.option_range,
        strike_range=args.strike_range,
        strategy=args.strategy,
        extended_hours=args.extended_hours,
    )
    send_png(result["png_output"])
    print(
        f"Wrote GEX overlay chart for {result['symbol']} to {result['png_output']} and {result['html_output']} and uploaded the PNG to Discord "
        f"using {result['option_contracts']} option rows and {result['hourly_candles']} candles."
    )


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from discord.webhook import DiscordWebhookError, send_message, send_png
from gex import compute_exposure_report, compute_gex
from options_analysis import build_options_analysis
from gex.chart import generate_chart
from gex.storage import DEFAULT_DB_PATH, get_connection, init_db, insert_aggregate_rows, insert_option_contracts, insert_snapshot
from market_report import MarketReportError, build_market_report, validate_market_report_time
from schwab.api import get_expirations, get_option_chain, get_option_chain_rows, get_quote
from schwab.client import SchwabConfigError, build_authorize_url, create_client


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        args.func(args)
    except SchwabConfigError as exc:
        raise SystemExit(str(exc)) from exc
    except MarketReportError as exc:
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

    auth_parser = subparsers.add_parser("auth", help="Authentication commands")
    auth_parser.add_argument("--callback-url", help="OAuth callback URL to exchange")
    auth_parser.add_argument("--prompt", action="store_true", help="Read callback URL from stdin")
    auth_parser.set_defaults(func=run_auth)
    auth_subparsers = auth_parser.add_subparsers(dest="auth_command")

    auth_login_parser = auth_subparsers.add_parser("login", help="Print auth URL or exchange callback URL")
    auth_login_parser.add_argument("--callback-url", help="OAuth callback URL to exchange")
    auth_login_parser.add_argument("--prompt", action="store_true", help="Read callback URL from stdin")
    auth_login_parser.set_defaults(func=run_auth)

    market_parser = subparsers.add_parser("market", help="Market data commands")
    market_subparsers = market_parser.add_subparsers(dest="market_command", required=True)

    quote_parser = market_subparsers.add_parser("quote", help="Fetch a quote")
    quote_parser.add_argument("--symbol", default="SPY")
    quote_parser.set_defaults(func=run_quote)

    report_parser = subparsers.add_parser("report", help="Report commands")
    report_subparsers = report_parser.add_subparsers(dest="report_command", required=True)

    market_report_parser = report_subparsers.add_parser("market", help="Build an hourly market report")
    market_report_parser.add_argument("--force", action="store_true")
    market_report_parser.add_argument("--discord", action="store_true", help="Send the report to Discord")
    market_report_parser.set_defaults(func=run_market_report)

    options_parser = subparsers.add_parser("options", help="Options chain commands")
    options_subparsers = options_parser.add_subparsers(dest="options_command", required=True)

    expirations_parser = options_subparsers.add_parser("expirations", help="Fetch option expirations")
    expirations_parser.add_argument("--symbol", default="SPY")
    expirations_parser.set_defaults(func=run_expirations)

    fetch_parser = options_subparsers.add_parser("fetch", help="Fetch normalized option rows")
    add_option_chain_arguments(fetch_parser)
    fetch_parser.add_argument("--output", default="out/options.csv")
    fetch_parser.add_argument("--json-output", help="Optional raw JSON output path")
    fetch_parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    fetch_parser.add_argument("--persist-db", action="store_true")
    fetch_parser.set_defaults(func=run_fetch_options)

    # 0DTE Live Premium Flow commands
    from z0dte.backtest.live_runner import LiveRunner
    
    def run_zodte_live(args):
        runner = LiveRunner(
            symbol=args.symbol,
            interval_minutes=args.interval,
            dry_run=args.dry_run,
        )
        runner.run_loop(max_iterations=args.count)
    
    def run_zodte_snapshot(args):
        from z0dte.sources.live import LiveDataSource
        from z0dte.ingestion.pipeline import IngestionPipeline
        from z0dte.signals.net_premium_flow import NetPremiumFlow
        from z0dte.db.connection import get_connection
        
        conn = get_connection()
        source = LiveDataSource()
        pipeline = IngestionPipeline(source, conn, [NetPremiumFlow()])
        snapshot_id = pipeline.run_one(args.symbol)
        
        result = conn.execute(
            "SELECT * FROM signal_premium_flow WHERE snapshot_id = %s",
            (snapshot_id,)
        ).fetchone()
        
        if result:
            direction = "BULLISH" if result["net_premium_flow"] > 0 else "BEARISH"
            print(f"\n0DTE Premium Flow Snapshot")
            print(f"=" * 40)
            print(f"Symbol:     {result['symbol']}")
            print(f"Time:       {result['captured_at']}")
            print(f"SPY:        ${result['price_at_bar']:.2f}")
            print(f"Direction:  {direction}")
            print(f"Net Flow:  ${result['net_premium_flow']:+,.0f}")
            print(f"Call Ask:  ${result['call_premium_at_ask']:+,.0f}")
            print(f"Call Bid:  ${result['call_premium_at_bid']:+,.0f}")
            print(f"Put Ask:   ${result['put_premium_at_ask']:+,.0f}")
            print(f"Put Bid:   ${result['put_premium_at_bid']:+,.0f}")
            print(f"Cumulative:${result['cumulative_flow']:+,.0f}")
        else:
            print("No result found")
    
    zodte_parser = subparsers.add_parser("zodte", help="0DTE premium flow commands")
    zodte_subparsers = zodte_parser.add_subparsers(dest="zodte_command", required=True)
    
    # Live watch mode
    zodte_live_parser = zodte_subparsers.add_parser("watch", help="Run live premium flow monitoring")
    zodte_live_parser.add_argument("--symbol", default="SPY", help="Underlying symbol")
    zodte_live_parser.add_argument("--interval", type=int, default=15, help="Minutes between API calls (default: 15)")
    zodte_live_parser.add_argument("--count", type=int, default=None, help="Number of iterations (default: run forever)")
    zodte_live_parser.add_argument("--dry-run", action="store_true", help="Parse data but skip database writes")
    zodte_live_parser.set_defaults(func=run_zodte_live)
    
    # Single snapshot
    zodte_snapshot_parser = zodte_subparsers.add_parser("snapshot", help="Fetch single premium flow snapshot")
    zodte_snapshot_parser.add_argument("--symbol", default="SPY", help="Underlying symbol")
    zodte_snapshot_parser.set_defaults(func=run_zodte_snapshot)

    analysis_parser = subparsers.add_parser("analysis", help="Higher-level analysis commands")
    analysis_subparsers = analysis_parser.add_subparsers(dest="analysis_command", required=True)

    options_analysis_parser = analysis_subparsers.add_parser(
        "options",
        help="Run standalone options analysis from option chain rows",
    )
    add_option_chain_arguments(options_analysis_parser)
    options_analysis_parser.add_argument("--output", help="Optional JSON analysis output path")
    options_analysis_parser.add_argument("--json-output", help="Optional raw JSON output path")
    options_analysis_parser.add_argument("--prior-regime", choices=["pinned", "balanced", "transition", "expansion", "exhaustion"])
    options_analysis_parser.add_argument("--discord", action="store_true", help="Send the analysis summary to Discord")
    options_analysis_parser.add_argument("--no-discord", action="store_true", help="Skip Discord post for this run")
    options_analysis_parser.set_defaults(func=run_options_analysis)

    exposure_parser = subparsers.add_parser("exposure", help="Exposure and persistence commands")
    exposure_subparsers = exposure_parser.add_subparsers(dest="exposure_command", required=True)

    gex_parser = exposure_subparsers.add_parser("gex", help="Compute GEX from option chain rows")
    add_option_chain_arguments(gex_parser)
    gex_parser.add_argument("--output", help="Optional JSON report output path")
    gex_parser.add_argument("--json-output", help="Optional raw JSON output path")
    gex_parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    gex_parser.add_argument("--persist-db", action="store_true")
    gex_parser.set_defaults(func=run_gex)

    history_parser = exposure_subparsers.add_parser("history", help="Show recent persisted exposure snapshots")
    history_parser.add_argument("--symbol", default="SPY")
    history_parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    history_parser.add_argument("--limit", type=int, default=10)
    history_parser.set_defaults(func=run_gex_history)

    chart_parser = subparsers.add_parser("chart", help="Chart rendering and publishing commands")
    chart_subparsers = chart_parser.add_subparsers(dest="chart_command", required=True)

    chart_render_parser = chart_subparsers.add_parser("render", help="Render hourly price chart with current GEX levels")
    add_option_chain_arguments(chart_render_parser)
    chart_render_parser.add_argument("--history-days", type=int, default=60)
    chart_render_parser.add_argument("--interval-hours", type=int, default=1)
    chart_render_parser.add_argument("--max-levels", type=int, default=10)
    chart_render_parser.add_argument("--output", default="out/gex_price_overlay.png")
    chart_render_parser.add_argument("--extended-hours", action="store_true")
    chart_render_parser.add_argument("--discord", action="store_true", help="Upload the rendered PNG to Discord")
    chart_render_parser.set_defaults(func=run_gex_chart)

    chart_post_parser = chart_subparsers.add_parser("post", help="Render a GEX chart and upload it to Discord")
    add_option_chain_arguments(chart_post_parser)
    chart_post_parser.add_argument("--history-days", type=int, default=60)
    chart_post_parser.add_argument("--interval-hours", type=int, default=1)
    chart_post_parser.add_argument("--max-levels", type=int, default=10)
    chart_post_parser.add_argument("--output", default="out/gex_price_overlay.png")
    chart_post_parser.add_argument("--extended-hours", action="store_true")
    chart_post_parser.add_argument("--discord", action="store_true", help="Upload the rendered PNG to Discord")
    chart_post_parser.set_defaults(func=run_gex_chart_discord)

    chart_send_parser = chart_subparsers.add_parser("send", help="Upload a PNG file to a Discord webhook")
    chart_send_parser.add_argument("--file", required=True)
    chart_send_parser.set_defaults(func=run_discord_send)

    legacy_fetch_parser = subparsers.add_parser("fetch-options", help="Fetch normalized option rows")
    add_option_chain_arguments(legacy_fetch_parser)
    legacy_fetch_parser.add_argument("--output", default="out/options.csv")
    legacy_fetch_parser.add_argument("--json-output", help="Optional raw JSON output path")
    legacy_fetch_parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    legacy_fetch_parser.add_argument("--persist-db", action="store_true")
    legacy_fetch_parser.set_defaults(func=run_fetch_options)

    legacy_gex_parser = subparsers.add_parser("gex", help="Compute GEX from option chain rows")
    add_option_chain_arguments(legacy_gex_parser)
    legacy_gex_parser.add_argument("--output", help="Optional JSON report output path")
    legacy_gex_parser.add_argument("--json-output", help="Optional raw JSON output path")
    legacy_gex_parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    legacy_gex_parser.add_argument("--persist-db", action="store_true")
    legacy_gex_parser.set_defaults(func=run_gex)

    legacy_options_analysis_parser = subparsers.add_parser(
        "options-analysis",
        help="Run standalone options analysis from option chain rows",
    )
    add_option_chain_arguments(legacy_options_analysis_parser)
    legacy_options_analysis_parser.add_argument("--output", help="Optional JSON analysis output path")
    legacy_options_analysis_parser.add_argument("--json-output", help="Optional raw JSON output path")
    legacy_options_analysis_parser.add_argument("--prior-regime", choices=["pinned", "balanced", "transition", "expansion", "exhaustion"])
    legacy_options_analysis_parser.add_argument("--no-discord", action="store_true", help="Skip Discord post for this run")
    legacy_options_analysis_parser.set_defaults(func=run_options_analysis)

    legacy_history_parser = subparsers.add_parser("gex-history", help="Show recent persisted exposure snapshots")
    legacy_history_parser.add_argument("--symbol", default="SPY")
    legacy_history_parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    legacy_history_parser.add_argument("--limit", type=int, default=10)
    legacy_history_parser.set_defaults(func=run_gex_history)

    legacy_chart_parser = subparsers.add_parser("gex-chart", help="Render hourly price chart with current GEX levels")
    add_option_chain_arguments(legacy_chart_parser)
    legacy_chart_parser.add_argument("--history-days", type=int, default=60)
    legacy_chart_parser.add_argument("--interval-hours", type=int, default=1)
    legacy_chart_parser.add_argument("--max-levels", type=int, default=10)
    legacy_chart_parser.add_argument("--output", default="out/gex_price_overlay.png")
    legacy_chart_parser.add_argument("--extended-hours", action="store_true")
    legacy_chart_parser.set_defaults(func=run_gex_chart)

    legacy_discord_send_parser = subparsers.add_parser("discord-send", help="Upload a PNG file to a Discord webhook")
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
    legacy_chart_discord_parser.add_argument("--output", default="out/gex_price_overlay.png")
    legacy_chart_discord_parser.add_argument("--extended-hours", action="store_true")
    legacy_chart_discord_parser.set_defaults(func=run_gex_chart_discord)

    legacy_market_report_parser = subparsers.add_parser(
        "market-report-discord",
        help="Post an hourly text market report to Discord",
    )
    legacy_market_report_parser.add_argument("--force", action="store_true")
    legacy_market_report_parser.set_defaults(func=run_market_report_discord)

    legacy_quote_parser = subparsers.add_parser("quote", help="Fetch a quote")
    legacy_quote_parser.add_argument("--symbol", default="SPY")
    legacy_quote_parser.set_defaults(func=run_quote)

    legacy_expirations_parser = subparsers.add_parser("expirations", help="Fetch option expirations")
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
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


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


def _format_options_analysis_discord_message(symbol: str, analysis: dict[str, Any]) -> str:
    regime = analysis.get("regime", {})
    key_levels = analysis.get("key_levels", {})
    strategies = analysis.get("strategies", [])
    strikes = analysis.get("strikes", [])
    expirations = analysis.get("expirations", [])
    narrative = analysis.get("narrative", {})
    completeness = analysis.get("data_completeness", {})
    trade_suggestion = analysis.get("trade_suggestion", {})
    scenarios = analysis.get("scenarios", [])

    confidence = float(regime.get("confidence", 0.0) or 0.0)
    completeness_ratio = float(completeness.get("completeness_ratio", 0.0) or 0.0)
    spot_price = key_levels.get("spot_price")
    call_wall = (key_levels.get("call_wall") or {}).get("strike")
    put_wall = (key_levels.get("put_wall") or {}).get("strike")
    top_strike = key_levels.get("top_strike")
    gamma_flip = key_levels.get("gamma_flip")

    def _fmt_level(value: Any) -> str:
        return f"{value:.2f}" if isinstance(value, (int, float)) else "n/a"

    def _fmt_trade_strikes(target: Any, secondary: Any) -> str:
        target_text = _fmt_level(target)
        secondary_text = _fmt_level(secondary)
        if secondary_text != "n/a":
            return f"{target_text} / {secondary_text}"
        return target_text

    def _fmt_tags(structural: list, opportunity: list) -> str:
        all_tags = []
        if structural:
            all_tags.extend(structural)
        if opportunity:
            all_tags.extend(opportunity)
        return ", ".join(all_tags) if all_tags else "no_tags"

    top_strategy_lines = [
        f"{index}. {item.get('strategy', 'n/a')} ({float(item.get('fit_score', 0.0)):.2f})"
        for index, item in enumerate(strategies[:2], start=1)
    ]
    top_strike_lines = [
        f"- {_fmt_level(item.get('strike'))} [{_fmt_tags(item.get('structural_tags', []), item.get('opportunity_tags', []))}]"
        for item in strikes[:2]
    ]
    top_expiration_lines = [
        f"- {item.get('expiration', 'n/a')} ({item.get('dte', 'n/a')} DTE) [{_fmt_tags(item.get('structural_tags', []), item.get('opportunity_tags', []))}]"
        for item in expirations[:1]
    ]
    reason_lines = [f"- {reason}" for reason in regime.get("reasons", [])[:1]]
    rationale_lines = [f"- {reason}" for reason in trade_suggestion.get("rationale", [])[:2]]
    leg_lines = [
        f"- {leg.get('side', 'n/a')} {leg.get('option_type', 'n/a')} {_fmt_level(leg.get('strike'))} {leg.get('expiration', 'n/a')}"
        for leg in trade_suggestion.get("legs", [])[:2]
    ]

    supporting_tags = trade_suggestion.get("supporting_tags", [])
    conflicting_tags = trade_suggestion.get("conflicting_tags", [])
    context_limitations = trade_suggestion.get("context_limitations", [])

    supporting_text = f"Supporting: [{', '.join(supporting_tags[:3])}]" if supporting_tags else ""
    conflicting_text = f"Conflicting: [{', '.join(conflicting_tags[:3])}]" if conflicting_tags else ""

    scenario_lines = []
    if scenarios:
        scenario_lines = ["", "Key scenarios:"]
        for s in scenarios[:3]:
            scenario_lines.append(
                f"- {s.get('scenario_name', 'n/a')}: spot {s.get('spot_change_pct', 0):+.0f}%, IV {s.get('iv_change', 0):+.0f}pts"
            )

    context_limit_lines = []
    if context_limitations:
        context_limit_lines = [f"- {lim}" for lim in context_limitations[:2]]
    else:
        context_limit_lines = ["- None noted"]

    gamma_flip_text = f"{gamma_flip:.2f}" if isinstance(gamma_flip, (int, float)) else "n/a"
    top_strike_text = _fmt_level(top_strike)

    sections = [
        f"Options Analysis - {symbol}",
        f"Regime: {regime.get('name', 'unknown')} ({confidence:.2f})",
        f"Spot: {_fmt_level(spot_price)}",
        f"Top strike: {top_strike_text}",
        f"Call wall: {_fmt_level(call_wall)}",
        f"Put wall: {_fmt_level(put_wall)}",
        f"Gamma flip: {gamma_flip_text}",
        "",
        "Top strategies:",
        *(top_strategy_lines or ["- n/a"]),
        "",
        "Top strikes:",
        *(top_strike_lines or ["- n/a"]),
        "",
        "Top expirations:",
        *(top_expiration_lines or ["- n/a"]),
        "",
        "Regime drivers:",
        *(reason_lines or ["- n/a"]),
        "",
        "Suggested trade:",
        f"- Strategy: {trade_suggestion.get('strategy', 'n/a')} | Direction: {trade_suggestion.get('direction', 'n/a')}",
        f"- Expiration: {trade_suggestion.get('expiration', 'n/a')}",
        f"- Strikes: {_fmt_trade_strikes(trade_suggestion.get('target_strike'), trade_suggestion.get('secondary_strike'))}",
        f"- {trade_suggestion.get('probability_type', 'POP estimate')}: {float(trade_suggestion.get('probability_of_profit', 0.0) or 0.0):.2f}",
        f"- Confidence: {float(trade_suggestion.get('confidence', 0.0) or 0.0):.2f}",
        "",
        "Trade thesis:",
        f"- {trade_suggestion.get('entry_thesis', 'n/a')}",
        "",
        supporting_text,
        conflicting_text,
        "",
        "Valid while:",
        f"- {trade_suggestion.get('valid_while', 'n/a')}",
        "",
        "Invalidation:",
        f"- {trade_suggestion.get('invalidation', 'n/a')}",
        "",
        "Why this trade:",
        *(rationale_lines or ["- n/a"]),
        *(["", "Trade legs:", *leg_lines] if leg_lines else []),
        "",
        *scenario_lines,
        "",
        "Quality:",
        f"- Completeness: {completeness_ratio:.0%}",
        f"- {narrative.get('quality_note', 'No additional quality notes.')}",
    ]

    return "\n".join(sections)


def _load_chain_and_rows(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]]]:
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


def _persist_snapshot(db_path: str, source: str, chain: dict[str, Any], rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    captured_at = str(rows[0].get("snapshot_captured_at") or datetime.now().isoformat())
    spot = next((float(row["underlying_price"]) for row in rows if row.get("underlying_price") not in (None, "")), None)
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
        )
        insert_option_contracts(connection, snapshot_id, rows)
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


def run_options_analysis(args: argparse.Namespace) -> None:
    from options_analysis.scenarios import run_scenario_analysis
    chain, rows = _load_chain_and_rows(args)
    _write_json(args.json_output, chain)
    report = compute_exposure_report(rows)
    analysis = build_options_analysis(report, rows, prior_regime=args.prior_regime)
    scenarios = run_scenario_analysis(analysis)
    if scenarios:
        analysis["scenarios"] = scenarios
    payload = {
        "symbol": str(chain.get("symbol") or args.symbol).upper(),
        "options_analysis": analysis,
    }
    payload_text = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        _write_json(args.output, payload)
        print(f"Wrote options analysis to {args.output}")
    else:
        print(payload_text)

    should_send_discord = bool(getattr(args, "discord", False)) or not bool(getattr(args, "no_discord", False))
    if should_send_discord:
        send_message(_format_options_analysis_discord_message(payload["symbol"], analysis))
        print("Posted options analysis to Discord webhook.")


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


def run_market_report_discord(args: argparse.Namespace) -> None:
    validate_market_report_time(force=args.force)
    report = build_market_report()
    send_message(report)
    print("Posted market report to Discord webhook.")


def run_market_report(args: argparse.Namespace) -> None:
    validate_market_report_time(force=args.force)
    report = build_market_report()
    print(report)
    if getattr(args, "discord", False):
        send_message(report)
        print("Posted market report to Discord webhook.")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
import sqlite3

import pytest

import cli


def test_run_gex_persist_db_writes_report_and_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    option_chain_fixture: dict,
    option_rows_fixture: list[dict],
) -> None:
    db_path = tmp_path / "options_history.sqlite3"
    output_path = tmp_path / "gex_report.json"

    monkeypatch.setattr(cli, "_load_chain_and_rows", lambda args: (option_chain_fixture, option_rows_fixture))

    args = argparse.Namespace(
        symbol="SPY",
        days=30,
        json_output=None,
        output=str(output_path),
        db_path=str(db_path),
        persist_db=True,
    )

    cli.run_gex(args)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert set(payload) >= {"snapshot", "by_strike", "by_expiration", "by_dte_bucket", "by_bucket", "dealer_regime", "headline_gex", "snapshot_id"}
    assert payload["snapshot"]["spot_price"] == 500.0
    assert payload["headline_gex"]["total_gex"] == payload["snapshot"]["total_gex"]
    assert payload["dealer_regime"]["gamma_flip_estimate"] is None or 490.0 < payload["dealer_regime"]["gamma_flip_estimate"] < 510.0
    assert "options_analysis" not in payload

    connection = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {"snapshots", "option_contracts", "aggregates_by_strike", "aggregates_by_expiry", "aggregates_by_bucket"}.issubset(tables)
        assert connection.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM option_contracts").fetchone()[0] == len(option_rows_fixture)
        assert connection.execute("SELECT COUNT(*) FROM aggregates_by_strike").fetchone()[0] > 0
        assert connection.execute("SELECT COUNT(*) FROM aggregates_by_expiry").fetchone()[0] > 0
        assert connection.execute("SELECT COUNT(*) FROM aggregates_by_bucket").fetchone()[0] > 0
    finally:
        connection.close()


def test_persisted_snapshot_symbol_uses_chain_symbol_for_history(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    option_chain_fixture: dict,
    option_rows_fixture: list[dict],
) -> None:
    db_path = tmp_path / "history.sqlite3"
    rows = [dict(row, underlying_symbol="SPX") for row in option_rows_fixture]

    monkeypatch.setattr(cli, "_load_chain_and_rows", lambda args: (option_chain_fixture, rows))

    cli.run_gex(
        argparse.Namespace(
            symbol="SPY",
            days=30,
            json_output=None,
            output=None,
            db_path=str(db_path),
            persist_db=True,
        )
    )
    capsys.readouterr()

    cli.run_gex_history(argparse.Namespace(symbol="SPY", db_path=str(db_path), limit=5))
    payload = json.loads(capsys.readouterr().out)

    assert len(payload) == 1
    assert payload[0]["symbol"] == "SPY"


def test_run_gex_history_filters_by_symbol_and_returns_latest(
    capsys: pytest.CaptureFixture[str],
    tmp_path,
) -> None:
    db_path = tmp_path / "history.sqlite3"
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript(
            """
            CREATE TABLE snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                underlying_price REAL,
                source TEXT NOT NULL,
                chain_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO snapshots (symbol, captured_at, underlying_price, source) VALUES
                ('SPY', '2026-03-30T10:00:00', 500.0, 'gex'),
                ('QQQ', '2026-03-30T11:00:00', 400.0, 'gex'),
                ('SPY', '2026-03-30T12:00:00', 501.0, 'fetch-options');
            """
        )
        connection.commit()
    finally:
        connection.close()

    args = argparse.Namespace(symbol="SPY", db_path=str(db_path), limit=5)
    cli.run_gex_history(args)

    payload = json.loads(capsys.readouterr().out)
    assert [row["symbol"] for row in payload] == ["SPY", "SPY"]
    assert payload[0]["captured_at"] == "2026-03-30T12:00:00"


def test_run_market_report_discord_posts_message(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(cli, "validate_market_report_time", lambda force: None)
    monkeypatch.setattr(cli, "build_market_report", lambda: "Market Update - 10:30 AM CT")
    monkeypatch.setattr(cli, "send_message", lambda content: calls.append(content))

    cli.run_market_report_discord(argparse.Namespace(force=False))

    assert calls == ["Market Update - 10:30 AM CT"]
    assert "Posted market report to Discord webhook." in capsys.readouterr().out


def test_build_parser_includes_market_report_command() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(["market-report-discord", "--force"])

    assert args.command == "market-report-discord"
    assert args.force is True
    assert args.func is cli.run_market_report_discord


def test_build_parser_includes_grouped_market_report_command() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(["report", "market", "--force", "--discord"])

    assert args.command == "report"
    assert args.report_command == "market"
    assert args.force is True
    assert args.discord is True
    assert args.func is cli.run_market_report


def test_run_options_analysis_writes_standalone_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    option_chain_fixture: dict,
    option_rows_fixture: list[dict],
) -> None:
    output_path = tmp_path / "options_analysis.json"
    calls: list[str] = []

    monkeypatch.setattr(cli, "_load_chain_and_rows", lambda args: (option_chain_fixture, option_rows_fixture))
    monkeypatch.setattr(cli, "send_message", lambda content: calls.append(content))

    cli.run_options_analysis(
        argparse.Namespace(
            symbol="SPY",
            days=30,
            json_output=None,
            output=str(output_path),
            prior_regime="balanced",
            no_discord=False,
        )
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["symbol"] == "SPY"
    assert payload["options_analysis"]["regime"]["prior_regime"] == "balanced"
    assert payload["options_analysis"]["strikes"]
    assert calls
    assert "Options Analysis - SPY" in calls[0]
    assert "Top strategies:" in calls[0]
    assert "Top strikes:" in calls[0]
    assert "Top expirations:" in calls[0]
    assert "Suggested trade:" in calls[0]
    assert "Trade thesis:" in calls[0]
    assert "Valid while:" in calls[0]
    assert "Invalidation:" in calls[0]
    assert "Why this trade:" in calls[0]
    assert "Quality:" in calls[0]
    assert payload["options_analysis"]["trade_suggestion"]["strategy"]
    assert payload["options_analysis"]["trade_suggestion"]["probability_type"] == "POP estimate"


def test_run_options_analysis_can_skip_discord(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    option_chain_fixture: dict,
    option_rows_fixture: list[dict],
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(cli, "_load_chain_and_rows", lambda args: (option_chain_fixture, option_rows_fixture))
    monkeypatch.setattr(cli, "send_message", lambda content: calls.append(content))

    cli.run_options_analysis(
        argparse.Namespace(
            symbol="SPY",
            days=30,
            json_output=None,
            output=None,
            prior_regime=None,
            no_discord=True,
        )
    )

    assert calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["symbol"] == "SPY"


def test_build_parser_includes_options_analysis_command() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(["options-analysis", "--symbol", "SPY", "--prior-regime", "transition", "--no-discord"])

    assert args.command == "options-analysis"
    assert args.symbol == "SPY"
    assert args.prior_regime == "transition"
    assert args.no_discord is True
    assert args.func is cli.run_options_analysis


def test_build_parser_includes_grouped_options_analysis_command() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(["analysis", "options", "--symbol", "SPY", "--prior-regime", "transition", "--discord"])

    assert args.command == "analysis"
    assert args.analysis_command == "options"
    assert args.symbol == "SPY"
    assert args.prior_regime == "transition"
    assert args.discord is True
    assert args.func is cli.run_options_analysis


def test_build_parser_includes_grouped_chart_render_command() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(["chart", "render", "--symbol", "SPY", "--discord"])

    assert args.command == "chart"
    assert args.chart_command == "render"
    assert args.symbol == "SPY"
    assert args.discord is True
    assert args.func is cli.run_gex_chart


def test_run_market_report_prints_and_optionally_posts_to_discord(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(cli, "validate_market_report_time", lambda force: None)
    monkeypatch.setattr(cli, "build_market_report", lambda: "Market Update - 10:30 AM CT")
    monkeypatch.setattr(cli, "send_message", lambda content: calls.append(content))

    cli.run_market_report(argparse.Namespace(force=False, discord=True))

    output = capsys.readouterr().out
    assert "Market Update - 10:30 AM CT" in output
    assert "Posted market report to Discord webhook." in output
    assert calls == ["Market Update - 10:30 AM CT"]


def test_run_gex_chart_can_upload_with_discord_flag(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    uploads: list[str] = []

    monkeypatch.setattr(
        cli,
        "generate_chart",
        lambda **kwargs: {
            "symbol": "SPY",
            "output": "out/gex_price_overlay.png",
            "png_output": "out/gex_price_overlay.png",
            "html_output": "out/gex_price_overlay.html",
            "option_contracts": 123,
            "hourly_candles": 45,
        },
    )
    monkeypatch.setattr(cli, "send_png", lambda path: uploads.append(path))

    cli.run_gex_chart(
        argparse.Namespace(
            symbol="SPY",
            days=30,
            history_days=60,
            interval_hours=1,
            max_levels=10,
            output="out/gex_price_overlay.png",
            contract_type="ALL",
            option_range="OTM",
            strike_range=None,
            strategy="SINGLE",
            extended_hours=False,
            discord=True,
        )
    )

    output = capsys.readouterr().out
    assert "Wrote GEX overlay chart for SPY" in output
    assert "Uploaded PNG to Discord webhook: out/gex_price_overlay.png" in output
    assert uploads == ["out/gex_price_overlay.png"]


def test_run_options_analysis_default_and_no_discord_emit_same_payload(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    option_chain_fixture: dict,
    option_rows_fixture: list[dict],
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(cli, "_load_chain_and_rows", lambda args: (option_chain_fixture, option_rows_fixture))
    monkeypatch.setattr(cli, "send_message", lambda content: calls.append(content))

    cli.run_options_analysis(
        argparse.Namespace(
            symbol="SPY",
            days=30,
            json_output=None,
            output=None,
            prior_regime=None,
            no_discord=False,
        )
    )
    default_output = capsys.readouterr().out

    cli.run_options_analysis(
        argparse.Namespace(
            symbol="SPY",
            days=30,
            json_output=None,
            output=None,
            prior_regime=None,
            no_discord=True,
        )
    )
    local_output = capsys.readouterr().out

    default_payload = json.loads(default_output.split("\nPosted options analysis to Discord webhook.\n", 1)[0])
    local_payload = json.loads(local_output)

    assert calls
    assert default_payload == local_payload

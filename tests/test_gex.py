from __future__ import annotations

import math

from gex import compute_exposure_report, compute_gex, compute_gex_levels
from options_analysis import apply_regime_hysteresis, audit_balanced_regime_frequency, build_options_analysis, classify_regime
from options_analysis.config import OptionsAnalysisConfig


def test_compute_gex_returns_expected_headline_totals(option_rows_fixture: list[dict]) -> None:
    result = compute_gex(option_rows_fixture)

    assert result["spot_price"] == 500.0
    assert result["total_gex"] == 8500000.0
    assert result["total_dex"] == 1050000.0
    assert result["total_vex"] == 4540.0
    assert result["total_tex"] == -6630.0
    assert result["by_dte_bucket"] == {"1-3DTE": 20750000.0, "8-30DTE": -12250000.0}


def test_compute_exposure_report_reconciles_all_rollups(option_rows_fixture: list[dict]) -> None:
    report = compute_exposure_report(option_rows_fixture)
    snapshot = report["snapshot"]

    assert snapshot["total_gex"] == 8500000.0
    assert sum(row["net_gex"] for row in report["by_strike"]) == snapshot["total_gex"]
    assert sum(row["net_gex"] for row in report["by_expiration"]) == snapshot["total_gex"]
    assert sum(row["net_gex"] for row in report["by_dte_bucket"]) == snapshot["total_gex"]
    assert sum(row["net_dex"] for row in report["by_expiration"]) == snapshot["total_dex"]
    assert sum(row["net_vex"] for row in report["by_expiration"]) == snapshot["total_vex"]
    assert sum(row["net_tex"] for row in report["by_expiration"]) == snapshot["total_tex"]
    assert {row["bucket_label"] for row in report["by_dte_bucket"]} == {"1-3DTE", "8-30DTE"}
    assert report["dealer_regime"]["positive_gamma_total"] == 20750000.0
    assert report["dealer_regime"]["negative_gamma_total"] == -12250000.0
    assert math.isclose(report["dealer_regime"]["gamma_flip_estimate"], 497.5)

    for row in report["by_expiration"] + report["by_dte_bucket"] + report["by_bucket"]:
        assert row["call_oi"] + row["put_oi"] == row["total_oi"]


def test_compute_exposure_report_bucket_counts_and_wall_shape(option_rows_fixture: list[dict]) -> None:
    report = compute_exposure_report(option_rows_fixture)

    assert len(report["by_expiration"]) == 2
    assert len(report["by_strike"]) == 4
    assert len(report["by_dte_bucket"]) == 2
    assert report["dealer_regime"]["largest_call_wall"] == {"strike": 495.0, "call_gex": 25000000.0}
    assert report["dealer_regime"]["largest_put_wall"] == {"strike": 495.0, "put_gex": -20250000.0}
    assert report["dealer_regime"]["largest_net_wall"] == {"strike": 505.0, "net_gex": 16000000.0}
    levels_sorted = report["dealer_regime"]["top_walls"]
    assert levels_sorted[0]["strike"] == 505.0


def test_compute_gex_levels_preserves_chart_output_shape(option_rows_fixture: list[dict]) -> None:
    levels = compute_gex_levels(option_rows_fixture, max_levels=10, min_dte=0, max_dte=30, spot_range_pct=None)

    assert len(levels) == 4
    for level in levels:
        assert set(level) == {"strike", "net_gex", "abs_gex", "dominant_side", "expirations_contributing"}
        assert isinstance(level["expirations_contributing"], list)
    assert levels[0]["strike"] == 505.0
    assert levels[0]["dominant_side"] == "CALL"


def test_build_options_analysis_returns_regime_rankings_and_strategies(option_rows_fixture: list[dict]) -> None:
    report = compute_exposure_report(option_rows_fixture)

    analysis = build_options_analysis(report, option_rows_fixture)

    assert analysis["regime"]["name"] in {"balanced", "pinned", "transition", "expansion"}
    assert analysis["regime"]["gamma_flip"] is None or math.isclose(analysis["regime"]["gamma_flip"], 497.5)
    assert analysis["data_completeness"]["is_sufficient"] is True
    assert set(analysis["regime"]["all_scores"]) == {"balanced", "expansion", "pinned", "transition"}
    assert analysis["regime"]["score_spread"] >= 0.0
    assert analysis["key_levels"]["call_wall"]["strike"] == 495.0
    assert analysis["key_levels"]["put_wall"]["strike"] == 495.0
    assert analysis["strikes"]
    assert analysis["strikes"][0]["strike"] == 505.0
    assert analysis["expirations"]
    assert analysis["strategies"]
    assert analysis["narrative"]["market_view"]
    assert analysis["trade_suggestion"]["probability_type"] == "POP estimate"
    assert analysis["trade_suggestion"]["invalidation"]
    assert analysis["trade_suggestion"]["rationale"]


def test_trade_suggestion_expansion_prefers_defined_risk_bearish_trade() -> None:
    report = {
        "snapshot": {"spot_price": 635.0, "total_gex": -2500000.0},
        "dealer_regime": {
            "gamma_flip_estimate": 640.0,
            "largest_call_wall": {"strike": 640.0, "call_gex": 3500000.0},
            "largest_put_wall": {"strike": 630.0, "put_gex": -5000000.0},
            "top_abs_gex_concentration": 0.68,
        },
        "by_strike": [
            {"strike": 630.0, "net_gex": -4200000.0, "call_gex": 500000.0, "put_gex": -4700000.0},
            {"strike": 640.0, "net_gex": 2100000.0, "call_gex": 2100000.0, "put_gex": -200000.0},
            {"strike": 635.0, "net_gex": -1800000.0, "call_gex": 400000.0, "put_gex": -2200000.0},
        ],
        "by_expiration": [
            {"expiration_date": "2026-04-17", "dte": 17, "net_gex": -6000000.0, "total_oi": 20000.0, "total_volume": 8000.0, "atm_iv": 0.24},
            {"expiration_date": "2026-05-15", "dte": 45, "net_gex": -2500000.0, "total_oi": 16000.0, "total_volume": 5000.0, "atm_iv": 0.23},
        ],
    }
    contracts = [{"volatility": 0.2, "delta": 0.4, "gamma": 0.01, "theta": -0.1, "vega": 0.1}]

    analysis = build_options_analysis(report, contracts)

    if analysis["regime"]["name"] == "expansion":
        assert analysis["trade_suggestion"]["strategy"] in {"put_debit_spread", "long_put"}
        assert analysis["trade_suggestion"]["direction"] == "bearish"
        assert analysis["trade_suggestion"]["expiration"] == "2026-04-17"
        assert analysis["trade_suggestion"]["target_strike"] == 630.0
    else:
        assert analysis["trade_suggestion"]["strategy"] in {"iron_condor", "calendar_spread"}
        assert analysis["trade_suggestion"]["direction"] == "neutral"


def test_trade_suggestion_transition_can_choose_long_vol_trade() -> None:
    report = {
        "snapshot": {"spot_price": 500.0, "total_gex": -300000.0},
        "dealer_regime": {
            "gamma_flip_estimate": 501.0,
            "largest_call_wall": {"strike": 505.0, "call_gex": 2500000.0},
            "largest_put_wall": {"strike": 495.0, "put_gex": -2400000.0},
            "top_abs_gex_concentration": 0.35,
        },
        "by_strike": [
            {"strike": 500.0, "net_gex": -500000.0, "call_gex": 400000.0, "put_gex": -900000.0},
            {"strike": 505.0, "net_gex": 400000.0, "call_gex": 800000.0, "put_gex": -400000.0},
            {"strike": 495.0, "net_gex": -450000.0, "call_gex": 300000.0, "put_gex": -750000.0},
        ],
        "by_expiration": [
            {"expiration_date": "2026-04-10", "dte": 10, "net_gex": -800000.0, "total_oi": 10000.0, "total_volume": 6000.0, "atm_iv": 0.26},
            {"expiration_date": "2026-04-24", "dte": 24, "net_gex": 200000.0, "total_oi": 15000.0, "total_volume": 4000.0, "atm_iv": 0.25},
        ],
    }
    contracts = [{"volatility": 0.2, "delta": 0.4, "gamma": 0.01, "theta": -0.1, "vega": 0.1}]

    analysis = build_options_analysis(report, contracts)

    if analysis["regime"]["name"] == "transition":
        assert analysis["trade_suggestion"]["strategy"] in {"long_straddle", "calendar_spread"}
        assert analysis["trade_suggestion"]["direction"] == "neutral"
    else:
        assert analysis["trade_suggestion"]["strategy"] in {"put_debit_spread", "long_put", "call_debit_spread", "long_call", "long_straddle"}


def test_trade_suggestion_balanced_chooses_neutral_range_trade() -> None:
    report = {
        "snapshot": {"spot_price": 500.0, "total_gex": 5500000.0},
        "dealer_regime": {
            "gamma_flip_estimate": 500.0,
            "largest_call_wall": {"strike": 505.0, "call_gex": 6000000.0},
            "largest_put_wall": {"strike": 495.0, "put_gex": -5800000.0},
            "top_abs_gex_concentration": 0.78,
        },
        "by_strike": [
            {"strike": 500.0, "net_gex": 3200000.0, "call_gex": 2000000.0, "put_gex": -1000000.0},
            {"strike": 505.0, "net_gex": 2800000.0, "call_gex": 2800000.0, "put_gex": -300000.0},
            {"strike": 495.0, "net_gex": 2500000.0, "call_gex": 500000.0, "put_gex": -2600000.0},
        ],
        "by_expiration": [
            {"expiration_date": "2026-05-15", "dte": 45, "net_gex": 5000000.0, "total_oi": 24000.0, "total_volume": 5000.0, "atm_iv": 0.18},
            {"expiration_date": "2026-04-17", "dte": 17, "net_gex": 2200000.0, "total_oi": 20000.0, "total_volume": 3000.0, "atm_iv": 0.19},
        ],
    }
    contracts = [{"volatility": 0.19, "delta": 0.4, "gamma": 0.01, "theta": -0.1, "vega": 0.1}]

    analysis = build_options_analysis(report, contracts)

    assert analysis["regime"]["name"] in {"balanced", "pinned"}
    assert analysis["trade_suggestion"]["strategy"] in {"iron_condor", "calendar_spread"}
    assert analysis["trade_suggestion"]["direction"] == "neutral"


def test_trade_suggestion_degraded_data_lowers_pop_or_uses_safer_template() -> None:
    report = {
        "snapshot": {"spot_price": 635.0, "total_gex": -2500000.0},
        "dealer_regime": {
            "gamma_flip_estimate": None,
            "largest_call_wall": {"strike": 640.0, "call_gex": 3500000.0},
            "largest_put_wall": {},
            "top_abs_gex_concentration": 0.68,
        },
        "by_strike": [
            {"strike": 640.0, "net_gex": -2000000.0, "call_gex": 1800000.0, "put_gex": -2200000.0},
        ],
        "by_expiration": [
            {"expiration_date": "2026-04-17", "dte": 17, "net_gex": -6000000.0, "total_oi": 20000.0, "total_volume": 8000.0, "atm_iv": None},
        ],
    }
    contracts = [{"volatility": None, "delta": None, "gamma": 0.01, "theta": -0.1, "vega": 0.1}]

    analysis = build_options_analysis(report, contracts)

    assert analysis["trade_suggestion"]["probability_of_profit"] <= 0.65
    assert analysis["trade_suggestion"]["confidence"] <= 0.7
    assert analysis["trade_suggestion"]["strategy"] in {"long_put", "long_straddle", "calendar_spread"}


def test_trade_suggestion_pop_estimate_is_bounded() -> None:
    report = {
        "snapshot": {"spot_price": 500.0, "total_gex": -1000000.0},
        "dealer_regime": {
            "gamma_flip_estimate": 501.0,
            "largest_call_wall": {"strike": 505.0, "call_gex": 2500000.0},
            "largest_put_wall": {"strike": 495.0, "put_gex": -2400000.0},
            "top_abs_gex_concentration": 0.35,
        },
        "by_strike": [
            {"strike": 495.0, "net_gex": -500000.0, "call_gex": 400000.0, "put_gex": -900000.0},
        ],
        "by_expiration": [
            {"expiration_date": "2026-04-10", "dte": 10, "net_gex": -800000.0, "total_oi": 10000.0, "total_volume": 6000.0, "atm_iv": 0.26},
        ],
    }
    contracts = [{"volatility": 0.2, "delta": 0.4, "gamma": 0.01, "theta": -0.1, "vega": 0.1}]

    analysis = build_options_analysis(report, contracts)

    assert 0.35 <= analysis["trade_suggestion"]["probability_of_profit"] <= 0.75


def test_apply_regime_hysteresis_keeps_prior_regime_when_margin_not_cleared() -> None:
    selected, changed = apply_regime_hysteresis(
        {"balanced": 0.58, "transition": 0.63, "pinned": 0.32, "expansion": 0.11},
        prior_regime="balanced",
        margin=0.08,
    )

    assert selected == "balanced"
    assert changed is False


def test_apply_regime_hysteresis_switches_when_margin_is_cleared() -> None:
    selected, changed = apply_regime_hysteresis(
        {"balanced": 0.51, "transition": 0.68, "pinned": 0.22, "expansion": 0.15},
        prior_regime="balanced",
        margin=0.08,
    )

    assert selected == "transition"
    assert changed is True


def test_classify_regime_records_hysteresis_when_prior_regime_is_retained(option_rows_fixture: list[dict]) -> None:
    report = compute_exposure_report(option_rows_fixture)

    result = classify_regime(report["snapshot"], report["dealer_regime"], prior_regime="expansion")

    assert result.prior_regime == "expansion"
    assert result.hysteresis_applied is True
    assert result.name in {"expansion", "balanced", "pinned", "transition"}
    assert result.all_scores["pinned"] >= 0.0


def test_build_options_analysis_respects_prior_regime_hysteresis(option_rows_fixture: list[dict]) -> None:
    report = compute_exposure_report(option_rows_fixture)

    analysis = build_options_analysis(report, option_rows_fixture, prior_regime="transition")

    assert analysis["regime"]["prior_regime"] == "transition"
    assert analysis["regime"]["hysteresis_applied"] is True
    assert analysis["regime"]["name"] in {"transition", "balanced", "pinned", "expansion"}


def test_audit_balanced_regime_frequency_flags_overuse() -> None:
    audit = audit_balanced_regime_frequency([
        "balanced",
        "balanced",
        "transition",
        "balanced",
        "expansion",
    ])

    assert audit["sample_size"] == 5
    assert math.isclose(audit["frequencies"]["balanced"], 0.6)
    assert audit["warnings"]


def test_build_options_analysis_filters_far_from_spot_strikes() -> None:
    report = {
        "snapshot": {"spot_price": 500.0, "total_gex": -1000000.0},
        "dealer_regime": {
            "gamma_flip_estimate": 300.0,
            "largest_call_wall": {"strike": 630.0, "call_gex": 5000000.0},
            "largest_put_wall": {"strike": 490.0, "put_gex": -4000000.0},
            "top_abs_gex_concentration": 0.2,
        },
        "by_strike": [
            {"strike": 630.0, "net_gex": 12000000.0, "call_gex": 12000000.0, "put_gex": 0.0},
            {"strike": 505.0, "net_gex": 3000000.0, "call_gex": 3000000.0, "put_gex": 0.0},
            {"strike": 490.0, "net_gex": -2500000.0, "call_gex": 0.0, "put_gex": -2500000.0},
        ],
        "by_expiration": [],
    }
    contracts = [{"volatility": 0.2, "delta": 0.4, "gamma": 0.01, "theta": -0.1, "vega": 0.1}]

    analysis = build_options_analysis(
        report,
        contracts,
        config=OptionsAnalysisConfig(),
    )

    assert analysis["key_levels"]["gamma_flip"] is None
    assert analysis["strikes"][0]["strike"] == 505.0
    assert all(strike["strike"] != 630.0 for strike in analysis["strikes"])
    assert "Gamma flip was excluded from active analysis" in analysis["narrative"]["quality_note"]


def test_classify_regime_ignores_implausible_gamma_flip() -> None:
    result = classify_regime(
        {"spot_price": 500.0, "total_gex": -1500000.0},
        {
            "gamma_flip_estimate": 300.0,
            "largest_call_wall": {"strike": 630.0, "call_gex": 5000000.0},
            "largest_put_wall": {"strike": 490.0, "put_gex": -4000000.0},
            "top_abs_gex_concentration": 0.2,
        },
        config=OptionsAnalysisConfig(),
    )

    assert result.gamma_flip is None
    assert any("ignored because it is too far from spot" in reason for reason in result.reasons)

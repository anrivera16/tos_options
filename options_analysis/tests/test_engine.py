from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from options_analysis.engine import build_options_analysis
from options_analysis.regime import classify_regime
from options_analysis.safeguards import apply_regime_hysteresis, audit_balanced_regime_frequency
from options_analysis.config import DEFAULT_CONFIG
from options_analysis.constants import (
    REGIME_PINNED,
    REGIME_EXPANSION,
    REGIME_BALANCED,
    REGIME_TRANSITION,
    GEX_POSITIVE_MEANS_STABILIZING,
)


class TestGexSignConvention:
    def test_positive_gex_means_stabilizing(self):
        assert GEX_POSITIVE_MEANS_STABILIZING is True

    def test_positive_total_gex_spot_near_dominant_strike_returns_pinned(self, pinned_chain):
        result = classify_regime(
            pinned_chain["snapshot"],
            pinned_chain["dealer_regime"],
            prior_regime=None,
            config=DEFAULT_CONFIG,
        )
        assert result.name == REGIME_PINNED

    def test_negative_total_gex_spot_beyond_flip_returns_expansion(self, short_gamma_breakout_chain):
        result = classify_regime(
            short_gamma_breakout_chain["snapshot"],
            short_gamma_breakout_chain["dealer_regime"],
            prior_regime=None,
            config=DEFAULT_CONFIG,
        )
        assert result.name == REGIME_EXPANSION


class TestRegimeHysteresis:
    def test_hysteresis_prevents_flicker_on_small_change(self):
        scores = {REGIME_PINNED: 0.72, REGIME_BALANCED: 0.70}
        winner, changed = apply_regime_hysteresis(scores, REGIME_PINNED, margin=0.08)
        assert winner == REGIME_PINNED
        assert changed is False

    def test_hysteresis_allows_switch_on_large_change(self):
        scores = {REGIME_PINNED: 0.80, REGIME_BALANCED: 0.65}
        winner, changed = apply_regime_hysteresis(scores, REGIME_PINNED, margin=0.08)
        assert winner == REGIME_PINNED
        assert changed is False

        scores_large = {REGIME_PINNED: 0.70, REGIME_EXPANSION: 0.85}
        winner, changed = apply_regime_hysteresis(scores_large, REGIME_PINNED, margin=0.08)
        assert winner == REGIME_EXPANSION
        assert changed is True

    def test_hysteresis_first_run_always_picks_highest_scorer(self):
        scores = {REGIME_BALANCED: 0.60, REGIME_EXPANSION: 0.55}
        winner, changed = apply_regime_hysteresis(scores, None, margin=0.08)
        assert winner == REGIME_BALANCED
        assert changed is True


class TestRegimeClassification:
    def test_pinned_regime_when_spot_near_high_gamma_cluster(self, pinned_chain):
        result = classify_regime(
            pinned_chain["snapshot"],
            pinned_chain["dealer_regime"],
            prior_regime=None,
            config=DEFAULT_CONFIG,
        )
        assert result.name == REGIME_PINNED
        assert result.confidence > 0.5

    def test_expansion_regime_when_total_gex_negative_and_spot_beyond_flip(self, short_gamma_breakout_chain):
        result = classify_regime(
            short_gamma_breakout_chain["snapshot"],
            short_gamma_breakout_chain["dealer_regime"],
            prior_regime=None,
            config=DEFAULT_CONFIG,
        )
        assert result.name == REGIME_EXPANSION

    def test_balanced_regime_with_moderate_structure(self, balanced_chain):
        result = classify_regime(
            balanced_chain["snapshot"],
            balanced_chain["dealer_regime"],
            prior_regime=None,
            config=DEFAULT_CONFIG,
        )
        assert result.name == REGIME_BALANCED

    def test_missing_gamma_flip_falls_back_to_balanced(self):
        snapshot = {
            "spot_price": 500.0,
            "total_gex": 0.0,
        }
        dealer_regime = {
            "gamma_flip_estimate": None,
            "largest_call_wall": None,
            "largest_put_wall": None,
            "top_abs_gex_concentration": 0.3,
        }
        result = classify_regime(snapshot, dealer_regime, prior_regime=None, config=DEFAULT_CONFIG)
        assert result.name == REGIME_BALANCED


class TestStrikeRanking:
    def test_strike_ranking_prioritizes_nearby_strikes(self, pinned_chain):
        result = build_options_analysis(pinned_chain, [], prior_regime=None, config=DEFAULT_CONFIG)
        strikes = result["strikes"]
        assert len(strikes) > 0
        top_strike = strikes[0]
        assert top_strike["strike"] is not None

    def test_strike_distance_gate_excludes_far_strikes(self, pinned_chain):
        config = DEFAULT_CONFIG
        result = build_options_analysis(pinned_chain, [], prior_regime=None, config=config)
        strikes = result["strikes"]
        for strike_data in strikes:
            if strike_data["distance_from_spot_pct"] is not None:
                assert strike_data["distance_from_spot_pct"] <= config.active_strike_distance_pct * 100

    def test_strikes_have_structural_tags(self, pinned_chain):
        result = build_options_analysis(pinned_chain, [], prior_regime=None, config=DEFAULT_CONFIG)
        strikes = result["strikes"]
        assert len(strikes) > 0
        for strike_data in strikes:
            assert "structural_tags" in strike_data


class TestExpirationRanking:
    def test_expiration_ranking_returns_results(self, pinned_chain):
        result = build_options_analysis(pinned_chain, [], prior_regime=None, config=DEFAULT_CONFIG)
        expirations = result["expirations"]
        assert len(expirations) > 0

    def test_expirations_have_opportunity_tags(self, high_iv_chain):
        result = build_options_analysis(high_iv_chain, [], prior_regime=None, config=DEFAULT_CONFIG)
        expirations = result["expirations"]
        assert len(expirations) > 0
        for exp in expirations:
            assert "opportunity_tags" in exp

    def test_high_iv_chain_has_vol_sale_tag(self, high_iv_chain):
        result = build_options_analysis(high_iv_chain, [], prior_regime=None, config=DEFAULT_CONFIG)
        expirations = result["expirations"]
        vol_sale_found = any("vol_sale" in exp.get("opportunity_tags", []) for exp in expirations)
        assert vol_sale_found

    def test_derived_metrics_include_term_structure_and_volatility_overview(self, high_iv_chain):
        contracts = [
            {"expiration": "2024-04-05", "dte": 7, "strike": 495.0, "option_type": "put", "volatility": 0.34, "delta": -0.25},
            {"expiration": "2024-04-05", "dte": 7, "strike": 500.0, "option_type": "call", "volatility": 0.29, "delta": 0.50},
            {"expiration": "2024-04-05", "dte": 7, "strike": 505.0, "option_type": "call", "volatility": 0.24, "delta": 0.25},
        ]
        result = build_options_analysis(high_iv_chain, contracts, prior_regime=None, config=DEFAULT_CONFIG)
        derived = result["derived_metrics"]
        assert "term_structure" in derived
        assert "volatility_overview" in derived
        assert "vol_regime" in derived["volatility_overview"]
        assert "forward_volatility_curve" in derived
        assert "calendar_relative_value" in derived
        assert "skew_metrics" in derived
        assert derived["volatility_overview"]["put_call_25d_skew"] == 0.10


class TestDataCompleteness:
    def test_full_data_chain_has_high_completeness(self, pinned_chain):
        result = build_options_analysis(pinned_chain, [], prior_regime=None, config=DEFAULT_CONFIG)
        completeness = result["data_completeness"]
        assert completeness["is_sufficient"] is True
        assert completeness["completeness_ratio"] > 0.5

    def test_partial_data_chain_has_low_completeness(self, partial_data_chain):
        result = build_options_analysis(partial_data_chain, [], prior_regime=None, config=DEFAULT_CONFIG)
        completeness = result["data_completeness"]
        assert completeness["is_sufficient"] is False
        assert completeness["completeness_ratio"] < 0.5
        assert len(completeness["missing_fields"]) > 0

    def test_data_completeness_tracks_missing_fields(self, partial_data_chain):
        result = build_options_analysis(partial_data_chain, [], prior_regime=None, config=DEFAULT_CONFIG)
        completeness = result["data_completeness"]
        assert "gamma_flip" in completeness["missing_fields"]
        assert "total_gex" in completeness["missing_fields"]


class TestEngineOutputs:
    def test_engine_returns_all_required_fields(self, pinned_chain):
        result = build_options_analysis(pinned_chain, [], prior_regime=None, config=DEFAULT_CONFIG)
        assert "regime" in result
        assert "data_completeness" in result
        assert "key_levels" in result
        assert "strikes" in result
        assert "expirations" in result
        assert "strategies" in result
        assert "trade_suggestion" in result
        assert "narrative" in result

    def test_strategies_include_vol_fit_scoring(self, high_iv_chain):
        result = build_options_analysis(high_iv_chain, [], prior_regime=None, config=DEFAULT_CONFIG)
        strategies = result["strategies"]
        assert len(strategies) > 0
        for strategy in strategies:
            assert "vol_fit_score" in strategy or "regime_fit_score" in strategy

    def test_trade_suggestion_has_context_limitations(self, pinned_chain):
        result = build_options_analysis(pinned_chain, [], prior_regime=None, config=DEFAULT_CONFIG)
        suggestion = result["trade_suggestion"]
        assert suggestion is not None
        assert "context_limitations" in suggestion
        assert len(suggestion["context_limitations"]) > 0
        assert "Assumes no existing position in this name" in suggestion["context_limitations"]

    def test_trade_suggestion_has_supporting_and_conflicting_tags(self, pinned_chain):
        result = build_options_analysis(pinned_chain, [], prior_regime=None, config=DEFAULT_CONFIG)
        suggestion = result["trade_suggestion"]
        assert suggestion is not None
        assert "supporting_tags" in suggestion
        assert "conflicting_tags" in suggestion

    def test_engine_returns_backtest_blueprints(self, high_iv_chain):
        result = build_options_analysis(high_iv_chain, [], prior_regime=None, config=DEFAULT_CONFIG)
        assert "backtest_blueprints" in result
        assert len(result["backtest_blueprints"]) >= 3
        assert result["backtest_blueprints"][0]["entry_rules"]

    def test_data_completeness_includes_vol_environment(self, high_iv_chain):
        contracts = [
            {"expiration": "2024-04-05", "dte": 7, "strike": 495.0, "option_type": "put", "volatility": 0.34, "delta": -0.25},
            {"expiration": "2024-04-05", "dte": 7, "strike": 500.0, "option_type": "call", "volatility": 0.29, "delta": 0.50},
            {"expiration": "2024-04-05", "dte": 7, "strike": 505.0, "option_type": "call", "volatility": 0.24, "delta": 0.25},
        ]
        result = build_options_analysis(high_iv_chain, contracts, prior_regime=None, config=DEFAULT_CONFIG)
        completeness = result["data_completeness"]
        assert "vol_environment" in completeness
        assert completeness["vol_environment"]["vol_regime"] in {"premium_rich", "premium_cheap", "fair_value", "unknown"}
        assert completeness["vol_environment"]["put_call_25d_skew"] == 0.10


class TestBalancedRegimeAudit:
    def test_audit_balanced_regime_frequency_warns_when_threshold_exceeded(self):
        regimes = ["balanced", "balanced", "balanced", "pinned"]
        result = audit_balanced_regime_frequency(regimes, alert_threshold=0.4)
        assert result["sample_size"] == 4
        assert len(result["warnings"]) > 0
        assert "balanced" in result["warnings"][0]

    def test_audit_balanced_regime_frequency_no_warn_when_below_threshold(self):
        regimes = ["pinned", "expansion", "balanced", "pinned"]
        result = audit_balanced_regime_frequency(regimes, alert_threshold=0.4)
        assert len(result["warnings"]) == 0


class TestStrategyScoring:
    def test_pinned_regime_prefers_condor_or_fly(self, pinned_chain):
        result = build_options_analysis(pinned_chain, [], prior_regime=None, config=DEFAULT_CONFIG)
        strategies = result["strategies"]
        top_strategy = strategies[0]
        assert top_strategy["strategy"] in ["iron_condor", "iron_fly", "butterfly_spread"]

    def test_expansion_regime_prefers_long_gamma_strategies(self, short_gamma_breakout_chain):
        result = build_options_analysis(short_gamma_breakout_chain, [], prior_regime=None, config=DEFAULT_CONFIG)
        strategies = result["strategies"]
        top_strategy = strategies[0]
        assert top_strategy["strategy"] in [
            "long_straddle",
            "long_strangle",
            "debit_call_spread",
            "debit_put_spread",
            "gamma_scalp_straddle",
        ]

    def test_strategy_scoring_has_supporting_and_conflicting_tags(self, pinned_chain):
        result = build_options_analysis(pinned_chain, [], prior_regime=None, config=DEFAULT_CONFIG)
        strategies = result["strategies"]
        for strategy in strategies:
            assert "supporting_tags" in strategy
            assert "conflicting_tags" in strategy

    def test_strategy_set_includes_new_volatility_strategies(self, high_iv_chain):
        result = build_options_analysis(high_iv_chain, [], prior_regime=None, config=DEFAULT_CONFIG)
        strategy_names = {strategy["strategy"] for strategy in result["strategies"]}
        assert strategy_names & {"gamma_scalp_straddle", "short_strangle_iv_rich", "calendar_spread"}

    def test_calendar_strategy_benefits_from_forward_vol_and_skew_inputs(self, balanced_chain):
        contracts = [
            {"expiration": "2024-04-05", "dte": 7, "strike": 495.0, "option_type": "put", "volatility": 0.29, "delta": -0.25},
            {"expiration": "2024-04-05", "dte": 7, "strike": 500.0, "option_type": "call", "volatility": 0.24, "delta": 0.50},
            {"expiration": "2024-04-05", "dte": 7, "strike": 505.0, "option_type": "call", "volatility": 0.22, "delta": 0.25},
        ]
        custom_chain = dict(balanced_chain)
        custom_chain["by_expiration"] = [
            {"expiration_date": "2024-04-05", "dte": 7, "net_gex": 1000000.0, "abs_gex": 1000000.0, "total_oi": 20000, "total_volume": 14000, "atm_iv": 0.30},
            {"expiration_date": "2024-04-19", "dte": 21, "net_gex": 1200000.0, "abs_gex": 1200000.0, "total_oi": 24000, "total_volume": 18000, "atm_iv": 0.22},
            {"expiration_date": "2024-05-17", "dte": 45, "net_gex": 1300000.0, "abs_gex": 1300000.0, "total_oi": 26000, "total_volume": 16000, "atm_iv": 0.21},
        ]
        result = build_options_analysis(custom_chain, contracts, prior_regime=None, config=DEFAULT_CONFIG)
        strategy_names = [strategy["strategy"] for strategy in result["strategies"]]
        assert "calendar_spread" in strategy_names
        calendar_pairs = result["derived_metrics"]["calendar_relative_value"]
        assert calendar_pairs
        assert calendar_pairs[0]["mispricing_score"] > 0


class TestTradeSuggestion:
    def test_trade_suggestion_uses_calendar_when_forward_vol_is_dislocated(self, balanced_chain):
        contracts = [
            {"expiration": "2024-04-05", "dte": 7, "strike": 495.0, "option_type": "put", "volatility": 0.31, "delta": -0.25},
            {"expiration": "2024-04-05", "dte": 7, "strike": 500.0, "option_type": "call", "volatility": 0.25, "delta": 0.50},
            {"expiration": "2024-04-05", "dte": 7, "strike": 505.0, "option_type": "call", "volatility": 0.23, "delta": 0.25},
        ]
        custom_chain = dict(balanced_chain)
        custom_chain["by_expiration"] = [
            {"expiration_date": "2024-04-05", "dte": 7, "net_gex": 1000000.0, "abs_gex": 1000000.0, "total_oi": 20000, "total_volume": 14000, "atm_iv": 0.32},
            {"expiration_date": "2024-04-19", "dte": 21, "net_gex": 1200000.0, "abs_gex": 1200000.0, "total_oi": 24000, "total_volume": 18000, "atm_iv": 0.22},
            {"expiration_date": "2024-05-17", "dte": 45, "net_gex": 1300000.0, "abs_gex": 1300000.0, "total_oi": 26000, "total_volume": 16000, "atm_iv": 0.21},
        ]
        result = build_options_analysis(custom_chain, contracts, prior_regime=None, config=DEFAULT_CONFIG)
        suggestion = result["trade_suggestion"]
        assert suggestion["strategy"] == "calendar_spread"
        assert any("forward volatility" in reason for reason in suggestion["rationale"])
        assert any("mispricing score" in reason for reason in suggestion["rationale"])


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])

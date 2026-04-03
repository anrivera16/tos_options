from __future__ import annotations

from typing import Any

from .constants import REGIME_NAMES


def apply_regime_hysteresis(scores: dict[str, float], prior_regime: str | None, margin: float) -> tuple[str, bool]:
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    winner = ordered[0][0]
    if prior_regime is None or prior_regime not in scores:
        return winner, winner != prior_regime
    if winner == prior_regime:
        return winner, False
    if scores[winner] - scores[prior_regime] >= margin:
        return winner, True
    return prior_regime, False


def audit_balanced_regime_frequency(regimes: list[str], alert_threshold: float = 0.4) -> dict[str, Any]:
    total = len(regimes)
    counts = {name: 0 for name in REGIME_NAMES}
    for regime in regimes:
        if regime in counts:
            counts[regime] += 1
    frequencies = {name: (counts[name] / total if total else 0.0) for name in REGIME_NAMES}
    balanced_frequency = frequencies.get("balanced", 0.0)
    warnings: list[str] = []
    if total and balanced_frequency > alert_threshold:
        warnings.append(
            f"balanced regime frequency is {balanced_frequency:.2%}, which exceeds the audit threshold of {alert_threshold:.2%}"
        )
    return {
        "sample_size": total,
        "counts": counts,
        "frequencies": frequencies,
        "warnings": warnings,
    }

"""
Module 5: OI/Volume Wall Detector

Identifies support and resistance levels from open interest and volume
concentrations at specific strikes. Walls are price levels where
market makers have large positions that tend to act as magnets or barriers.
"""
from __future__ import annotations

import logging
from typing import Any

from algo.types import OIWall
from algo.config import WallConfig

logger = logging.getLogger(__name__)


def detect_walls(
    strike_data: list[dict[str, Any]],
    underlying_price: float,
    config: WallConfig,
) -> list[OIWall]:
    """
    Detect OI/Volume walls from strike-level data.

    Args:
        strike_data: List of dicts with keys:
            strike, put_call, total_oi, total_volume
        underlying_price: Current price

    Returns:
        List of OIWall objects, sorted by wall_score descending
    """
    if not strike_data:
        return []

    # Aggregate OI and volume by strike
    strike_stats: dict[float, dict] = {}
    for row in strike_data:
        strike = float(row.get("strike", 0))
        pc = row.get("put_call", "")
        oi = int(row.get("total_oi", 0) or 0)
        vol = int(row.get("total_volume", 0) or 0)

        if strike not in strike_stats:
            strike_stats[strike] = {"put_oi": 0, "call_oi": 0, "put_vol": 0, "call_vol": 0}

        if pc == "PUT":
            strike_stats[strike]["put_oi"] += oi
            strike_stats[strike]["put_vol"] += vol
        else:
            strike_stats[strike]["call_oi"] += oi
            strike_stats[strike]["call_vol"] += vol

    # Compute max values for normalization
    all_oi = []
    all_vol = []
    for stats in strike_stats.values():
        all_oi.append(stats["put_oi"] + stats["call_oi"])
        all_vol.append(stats["put_vol"] + stats["call_vol"])

    max_oi = max(all_oi) if all_oi else 1
    max_vol = max(all_vol) if all_vol else 1
    if max_oi == 0:
        max_oi = 1
    if max_vol == 0:
        max_vol = 1

    # Build walls for each strike
    walls: list[OIWall] = []
    for strike, stats in strike_stats.items():
        total_oi = stats["put_oi"] + stats["call_oi"]
        total_vol = stats["put_vol"] + stats["call_vol"]

        if total_oi < config.min_wall_oi:
            continue

        # Combined score
        oi_norm = total_oi / max_oi
        vol_norm = total_vol / max_vol
        score = oi_norm * config.oi_weight + vol_norm * config.volume_weight

        # Determine wall type based on dominant side
        if stats["put_oi"] > stats["call_oi"]:
            wall_type = "support" if strike < underlying_price else "resistance"
            dominant_side = "PUT"
        else:
            wall_type = "resistance" if strike > underlying_price else "support"
            dominant_side = "CALL"

        walls.append(OIWall(
            strike=strike,
            wall_type=wall_type,
            wall_score=round(score, 4),
            total_oi=total_oi,
            total_volume=total_vol,
            put_call=dominant_side,
        ))

    # Sort by score, take top N
    walls.sort(key=lambda w: w.wall_score, reverse=True)
    walls = walls[:config.top_n_walls]

    logger.info(f"Detected {len(walls)} OI walls (top {config.top_n_walls})")
    for w in walls:
        logger.debug(f"  {w.wall_type} at {w.strike} (score={w.wall_score:.3f}, OI={w.total_oi:,})")

    return walls


def fetch_strike_data_from_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Aggregate option chain rows into per-strike OI/volume summaries.

    Groups by (strike, put_call) and sums OI and volume across all expirations.
    """
    agg: dict[tuple[float, str], dict] = {}
    for row in rows:
        strike = float(row.get("strike", 0))
        pc = row.get("put_call", "")
        key = (strike, pc)

        if key not in agg:
            agg[key] = {
                "strike": strike,
                "put_call": pc,
                "total_oi": 0,
                "total_volume": 0,
            }

        oi = int(row.get("open_interest", 0) or 0)
        vol = int(row.get("total_volume", 0) or 0)
        agg[key]["total_oi"] += oi
        agg[key]["total_volume"] += vol

    return list(agg.values())

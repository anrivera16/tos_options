from __future__ import annotations

from collections import defaultdict
from typing import Any

from base import Signal


def find_atm_strike(contracts: list[dict], underlying_price: float) -> float | None:
    strikes = sorted(set(c["strike"] for c in contracts if c.get("strike") is not None))
    if not strikes:
        return None
    return min(strikes, key=lambda s: abs(s - underlying_price))


def extract_atm_iv(
    contracts: list[dict],
    expiration_date: str,
    atm_strike: float | None,
) -> float | None:
    if atm_strike is None:
        return None
    atm_contracts = [
        c for c in contracts
        if str(c.get("expiration_date") or "") == str(expiration_date)
        and c.get("strike") == atm_strike
        and c.get("volatility") is not None
        and c.get("volatility", 0) > 0
    ]
    if not atm_contracts:
        return None
    ivs = [c["volatility"] for c in atm_contracts]
    return sum(ivs) / len(ivs)


def identify_expiry_pair(contracts: list[dict]) -> tuple[str, str] | None:
    expiry_ivs: dict = defaultdict(list)
    for c in contracts:
        exp = str(c.get("expiration_date") or "")
        iv = c.get("volatility")
        if exp and iv and iv > 0:
            expiry_ivs[exp].append(iv)

    valid_expiries = [e for e, ivs in expiry_ivs.items() if ivs]
    if len(valid_expiries) < 2:
        return None

    valid_expiries.sort()
    return (valid_expiries[0], valid_expiries[1])


def compute_iv_slope(
    contracts: list[dict],
    underlying_price: float,
) -> dict | None:
    pair = identify_expiry_pair(contracts)
    if pair is None:
        return None

    front_expiry, back_expiry = pair
    atm_strike = find_atm_strike(contracts, underlying_price)
    if atm_strike is None:
        return None

    front_contracts = [c for c in contracts if str(c.get("expiration_date") or "") == front_expiry]
    back_contracts = [c for c in contracts if str(c.get("expiration_date") or "") == back_expiry]

    front_atm = find_atm_strike(front_contracts, underlying_price)
    back_atm = find_atm_strike(back_contracts, underlying_price)

    front_iv = extract_atm_iv(contracts, front_expiry, front_atm)
    back_iv = extract_atm_iv(contracts, back_expiry, back_atm)

    if front_iv is None or back_iv is None:
        return None

    iv_slope = front_iv - back_iv
    iv_slope_ratio = front_iv / back_iv if back_iv > 0 else None

    return {
        "front_expiry": front_expiry,
        "front_atm_iv": front_iv,
        "back_expiry": back_expiry,
        "back_atm_iv": back_iv,
        "iv_slope": iv_slope,
        "iv_slope_ratio": iv_slope_ratio,
    }


def compute_slope_change(current_slope: float, prior_slope: float | None) -> float | None:
    if prior_slope is None:
        return None
    return current_slope - prior_slope


def classify_slope_regime(
    iv_slope: float,
    slope_change: float | None,
    thresholds: dict | None = None,
) -> str:
    t = thresholds or {
        "steep_threshold": 0.02,
        "flat_threshold": 0.005,
        "change_threshold": 0.005,
    }

    if iv_slope < -t["steep_threshold"]:
        return "inverted"

    if iv_slope > t["steep_threshold"]:
        return "steepening"

    if slope_change is not None and slope_change < -t["change_threshold"]:
        return "flattening"

    return "flat"


class IVTermStructure(Signal):
    name = "iv_term_structure"
    table = "signal_iv_slope"

    def compute(self, snapshot_id: int, db_conn: Any) -> None:
        contracts = self._load_contracts(snapshot_id, db_conn)
        snapshot = self._load_snapshot(snapshot_id, db_conn)

        slope_data = compute_iv_slope(contracts, snapshot["underlying_price"])
        if slope_data is None:
            return

        prior = self._get_prior_slope(snapshot, db_conn)
        slope_change = compute_slope_change(
            slope_data["iv_slope"],
            prior["iv_slope"] if prior else None,
        )

        regime = classify_slope_regime(
            slope_data["iv_slope"],
            slope_change,
        )

        db_conn.execute(
            """
            INSERT INTO signal_iv_slope
                (snapshot_id, symbol, captured_at,
                 front_expiry, front_atm_iv,
                 back_expiry, back_atm_iv,
                 iv_slope, iv_slope_ratio, slope_change,
                 slope_regime)
            VALUES (%(snapshot_id)s, %(symbol)s, %(captured_at)s,
                    %(front)s, %(front_iv)s,
                    %(back)s, %(back_iv)s,
                    %(slope)s, %(ratio)s, %(change)s,
                    %(regime)s)
            """,
            {
                "snapshot_id": snapshot_id,
                "symbol": snapshot["symbol"],
                "captured_at": snapshot["captured_at"],
                "front": slope_data["front_expiry"],
                "front_iv": slope_data["front_atm_iv"],
                "back": slope_data["back_expiry"],
                "back_iv": slope_data["back_atm_iv"],
                "slope": slope_data["iv_slope"],
                "ratio": slope_data["iv_slope_ratio"],
                "change": slope_change,
                "regime": regime,
            },
        )
        db_conn.commit()

    def _get_prior_slope(self, snapshot: dict, db_conn: Any) -> dict | None:
        result = db_conn.execute(
            """
            SELECT iv_slope FROM signal_iv_slope sis
            JOIN snapshots_0dte s ON s.id = sis.snapshot_id
            WHERE s.symbol = %(symbol)s
              AND s.captured_at < %(current_time)s
              AND DATE(s.captured_at AT TIME ZONE 'US/Eastern') =
                  DATE(%(current_time)s AT TIME ZONE 'US/Eastern')
            ORDER BY s.captured_at DESC
            LIMIT 1
            """,
            {
                "symbol": snapshot["symbol"],
                "current_time": snapshot["captured_at"],
            },
        ).fetchone()
        return result

from __future__ import annotations

from typing import Any

from gex.calculations import CONTRACT_MULTIPLIER

from base import Signal


def compute_bar_gex(
    contracts: list[dict],
    underlying_price: float,
    max_dte: int = 2,
    strike_range_pct: float = 0.05,
) -> dict:
    strike_min = underlying_price * (1 - strike_range_pct)
    strike_max = underlying_price * (1 + strike_range_pct)

    total_gex = 0.0
    atm_gex = 0.0
    atm_strike = None
    min_distance = float("inf")

    atm_contracts: list[dict] = []

    for c in contracts:
        if c.get("dte") is None or c["dte"] > max_dte:
            continue
        if not (strike_min <= (c.get("strike") or 0) <= strike_max):
            continue
        if c.get("gamma") is None or c.get("open_interest") is None:
            continue

        side = 1.0 if str(c.get("put_call") or "").upper() == "CALL" else -1.0
        oi = c.get("open_interest") or 0
        gamma = c.get("gamma") or 0
        gex = side * gamma * oi * CONTRACT_MULTIPLIER * (underlying_price ** 2)
        total_gex += gex

        distance = abs((c.get("strike") or 0) - underlying_price)
        if distance < min_distance:
            min_distance = distance
            atm_strike = c.get("strike")

        if atm_strike is not None and c.get("strike") == atm_strike:
            atm_contracts.append(c)

    if atm_contracts:
        atm_gex = sum(
            (1.0 if str(c.get("put_call") or "").upper() == "CALL" else -1.0)
            * (c.get("gamma") or 0)
            * (c.get("open_interest") or 0)
            * CONTRACT_MULTIPLIER
            * (underlying_price ** 2)
            for c in atm_contracts
        )

    return {
        "total_gex": total_gex,
        "atm_gex": atm_gex,
    }


def compute_gex_delta(
    current_gex: float,
    prior_gex: float | None,
) -> float | None:
    if prior_gex is None:
        return None
    return current_gex - prior_gex


def compute_gex_acceleration(
    current_delta: float | None,
    prior_delta: float | None,
) -> float | None:
    if current_delta is None or prior_delta is None:
        return None
    return current_delta - prior_delta


def classify_acceleration_regime(
    acceleration: float | None,
    total_gex: float,
    thresholds: dict | None = None,
) -> tuple[str, bool]:
    t = thresholds or {
        "accel_threshold_pct": 0.10,
        "spike_multiplier": 2.0,
    }

    if acceleration is None:
        return ("stable", False)

    threshold = abs(total_gex) * t["accel_threshold_pct"] if total_gex != 0 else 0
    spike_threshold = threshold * t["spike_multiplier"]

    is_spike = abs(acceleration) > spike_threshold

    if acceleration > threshold:
        return ("accelerating", is_spike)
    elif acceleration < -threshold:
        return ("decelerating", is_spike)
    else:
        return ("stable", is_spike)


class GammaDecayRate(Signal):
    name = "gamma_decay_rate"
    table = "signal_gamma_decay"

    def compute(self, snapshot_id: int, db_conn: Any) -> None:
        contracts = self._load_contracts(snapshot_id, db_conn)
        snapshot = self._load_snapshot(snapshot_id, db_conn)

        gex_data = compute_bar_gex(contracts, snapshot["underlying_price"])

        prior_bars = self._get_prior_bars(snapshot, db_conn, limit=2)

        prior_gex = prior_bars[0]["total_gex"] if prior_bars else None
        gex_delta = compute_gex_delta(gex_data["total_gex"], prior_gex)

        prior_delta = (
            prior_bars[0]["gex_delta"]
            if prior_bars and prior_bars[0].get("gex_delta") is not None
            else None
        )
        gex_acceleration = compute_gex_acceleration(gex_delta, prior_delta)

        regime, is_spike = classify_acceleration_regime(
            gex_acceleration, gex_data["total_gex"]
        )

        db_conn.execute(
            """
            INSERT INTO signal_gamma_decay
                (snapshot_id, symbol, captured_at,
                 total_gex, atm_gex,
                 gex_delta, gex_acceleration,
                 acceleration_regime, is_spike)
            VALUES (%(sid)s, %(sym)s, %(time)s,
                    %(gex)s, %(atm)s,
                    %(delta)s, %(accel)s,
                    %(regime)s, %(spike)s)
            """,
            {
                "sid": snapshot_id,
                "sym": snapshot["symbol"],
                "time": snapshot["captured_at"],
                "gex": gex_data["total_gex"],
                "atm": gex_data["atm_gex"],
                "delta": gex_delta,
                "accel": gex_acceleration,
                "regime": regime,
                "spike": is_spike,
            },
        )
        db_conn.commit()

    def _get_prior_bars(self, snapshot: dict, db_conn: Any, limit: int = 2) -> list[dict]:
        results = db_conn.execute(
            """
            SELECT sgd.total_gex, sgd.gex_delta, sgd.gex_acceleration
            FROM signal_gamma_decay sgd
            JOIN snapshots_0dte s ON s.id = sgd.snapshot_id
            WHERE s.symbol = %(symbol)s
              AND s.captured_at < %(current_time)s
              AND DATE(s.captured_at AT TIME ZONE 'US/Eastern') =
                  DATE(%(current_time)s AT TIME ZONE 'US/Eastern')
            ORDER BY s.captured_at DESC
            LIMIT %(limit)s
            """,
            {
                "symbol": snapshot["symbol"],
                "current_time": snapshot["captured_at"],
                "limit": limit,
            },
        ).fetchall()
        return results

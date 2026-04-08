from __future__ import annotations

from collections import defaultdict
from typing import Any

from base import Signal


OI_WALL_FILTERS = {
    "max_dte": 7,
    "strike_range_pct": 0.05,
    "min_oi_threshold": 500,
}


def aggregate_oi_by_strike(
    contracts: list[dict],
    underlying_price: float,
    max_dte: int = 7,
    strike_range_pct: float = 0.05,
) -> list[dict]:
    strike_min = underlying_price * (1 - strike_range_pct)
    strike_max = underlying_price * (1 + strike_range_pct)

    relevant = [
        c for c in contracts
        if c.get("dte") is not None and c["dte"] <= max_dte
        and strike_min <= (c.get("strike") or 0) <= strike_max
        and c.get("open_interest") is not None and c["open_interest"] > 0
    ]

    by_strike: dict = defaultdict(
        lambda: {
            "call_oi": 0, "put_oi": 0,
            "call_volume": 0, "put_volume": 0,
            "total_oi": 0,
        }
    )

    for c in relevant:
        s = by_strike[c["strike"]]
        oi = c.get("open_interest") or 0
        vol = c.get("total_volume") or 0
        put_call = str(c.get("put_call") or "").upper()

        if put_call == "CALL":
            s["call_oi"] += oi
            s["call_volume"] += vol
        else:
            s["put_oi"] += oi
            s["put_volume"] += vol
        s["total_oi"] += oi

    results = []
    for strike, data in sorted(by_strike.items()):
        if data["total_oi"] < OI_WALL_FILTERS["min_oi_threshold"]:
            continue
        data["strike"] = strike
        results.append(data)

    return results


def classify_walls(
    strike_data: list[dict],
    underlying_price: float,
) -> list[dict]:
    if not strike_data:
        return []

    max_oi = max(d["total_oi"] for d in strike_data)

    for d in strike_data:
        strike = d["strike"]
        call_oi = d.get("call_oi", 0)
        put_oi = d.get("put_oi", 0)

        if call_oi > put_oi * 2:
            d["wall_type"] = "call_wall"
        elif put_oi > call_oi * 2:
            d["wall_type"] = "put_wall"
        else:
            d["wall_type"] = "mixed"

        d["wall_strength"] = d["total_oi"] / max_oi if max_oi > 0 else 0
        d["distance_from_spot"] = (strike - underlying_price) / underlying_price

        if d["wall_type"] == "call_wall":
            d["dealer_hedge_direction"] = "buying_stock"
        elif d["wall_type"] == "put_wall":
            d["dealer_hedge_direction"] = "selling_stock"
        else:
            if call_oi > put_oi:
                d["dealer_hedge_direction"] = "buying_stock"
            else:
                d["dealer_hedge_direction"] = "selling_stock"

    return strike_data


def identify_top_walls(
    classified_strikes: list[dict],
    top_n: int = 5,
) -> dict:
    call_walls = sorted(
        [s for s in classified_strikes if s.get("wall_type") == "call_wall"],
        key=lambda s: s.get("call_oi", 0),
        reverse=True,
    )[:top_n]

    put_walls = sorted(
        [s for s in classified_strikes if s.get("wall_type") == "put_wall"],
        key=lambda s: s.get("put_oi", 0),
        reverse=True,
    )[:top_n]

    call_above = [s for s in call_walls if s.get("distance_from_spot", 0) > 0]
    put_below = [s for s in put_walls if s.get("distance_from_spot", 0) < 0]

    pin_range = None
    if call_above and put_below:
        nearest_call = min(call_above, key=lambda s: s.get("distance_from_spot", 0))
        nearest_put = max(put_below, key=lambda s: s.get("distance_from_spot", 0))
        pin_width = nearest_call["strike"] - nearest_put["strike"]

        pin_range = {
            "upper_bound": nearest_call["strike"],
            "lower_bound": nearest_put["strike"],
            "width": pin_width,
            "width_pct": pin_width / ((nearest_call["strike"] + nearest_put["strike"]) / 2),
        }

    return {
        "top_call_walls": call_walls,
        "top_put_walls": put_walls,
        "pin_range": pin_range,
    }


class OIWalls(Signal):
    name = "oi_walls"
    table = "signal_oi_walls"

    def compute(self, snapshot_id: int, db_conn: Any) -> None:
        contracts = self._load_contracts(snapshot_id, db_conn)
        snapshot = self._load_snapshot(snapshot_id, db_conn)
        underlying_price = snapshot["underlying_price"]

        strike_data = aggregate_oi_by_strike(contracts, underlying_price)
        classified = classify_walls(strike_data, underlying_price)

        for wall in classified:
            db_conn.execute(
                """
                INSERT INTO signal_oi_walls
                    (snapshot_id, symbol, captured_at, strike,
                     call_oi, put_oi, total_oi,
                     call_volume, put_volume,
                     wall_type, wall_strength,
                     dealer_hedge_direction, distance_from_spot)
                VALUES (%(sid)s, %(sym)s, %(time)s, %(strike)s,
                        %(coi)s, %(poi)s, %(toi)s,
                        %(cvol)s, %(pvol)s,
                        %(wtype)s, %(wstr)s,
                        %(hedge)s, %(dist)s)
                """,
                {
                    "sid": snapshot_id,
                    "sym": snapshot["symbol"],
                    "time": snapshot["captured_at"],
                    "strike": wall["strike"],
                    "coi": wall.get("call_oi", 0),
                    "poi": wall.get("put_oi", 0),
                    "toi": wall.get("total_oi", 0),
                    "cvol": wall.get("call_volume", 0),
                    "pvol": wall.get("put_volume", 0),
                    "wtype": wall.get("wall_type"),
                    "wstr": wall.get("wall_strength"),
                    "hedge": wall.get("dealer_hedge_direction"),
                    "dist": wall.get("distance_from_spot"),
                },
            )

        db_conn.commit()

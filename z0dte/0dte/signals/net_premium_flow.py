from __future__ import annotations

from typing import Any

from gex.calculations import CONTRACT_MULTIPLIER

from base import Signal


def classify_trade_side(bid: float | None, ask: float | None, last: float | None) -> str:
    if bid is None or ask is None or last is None:
        return "unknown"
    mid = (bid + ask) / 2
    if last >= mid:
        return "at_ask"
    else:
        return "at_bid"


def compute_premium_flow(contracts: list[dict], underlying_price: float) -> dict:
    call_at_ask = 0.0
    call_at_bid = 0.0
    put_at_ask = 0.0
    put_at_bid = 0.0

    for c in contracts:
        if not c.get("total_volume") or c["total_volume"] == 0:
            continue
        mark = c.get("mark")
        if mark is None or mark <= 0:
            continue

        dollar_premium = c["total_volume"] * mark * CONTRACT_MULTIPLIER
        side = classify_trade_side(c.get("bid"), c.get("ask"), c.get("last"))
        put_call = str(c.get("put_call") or "").upper()

        if put_call == "CALL":
            if side == "at_ask":
                call_at_ask += dollar_premium
            elif side == "at_bid":
                call_at_bid += dollar_premium
            else:
                call_at_ask += dollar_premium * 0.5
                call_at_bid += dollar_premium * 0.5
        else:
            if side == "at_ask":
                put_at_ask += dollar_premium
            elif side == "at_bid":
                put_at_bid += dollar_premium
            else:
                put_at_ask += dollar_premium * 0.5
                put_at_bid += dollar_premium * 0.5

    net_flow = (call_at_ask - call_at_bid) - (put_at_ask - put_at_bid)

    return {
        "call_premium_at_ask": call_at_ask,
        "call_premium_at_bid": call_at_bid,
        "put_premium_at_ask": put_at_ask,
        "put_premium_at_bid": put_at_bid,
        "net_premium_flow": net_flow,
    }


def compute_cumulative_flow(snapshot_id: int, db_conn: Any, symbol: str, captured_at: Any) -> float:
    result = db_conn.execute(
        """
        SELECT COALESCE(SUM(spf.net_premium_flow), 0) as cumulative
        FROM signal_premium_flow spf
        JOIN snapshots_0dte s ON s.id = spf.snapshot_id
        WHERE s.symbol = %(symbol)s
          AND DATE(s.captured_at AT TIME ZONE 'US/Eastern') = DATE(%(captured_at)s AT TIME ZONE 'US/Eastern')
          AND s.captured_at < %(captured_at)s
        """,
        {"symbol": symbol, "captured_at": captured_at},
    ).fetchone()
    return float(result["cumulative"]) if result else 0.0


def compute_flow_velocity(current_flow: float, prior_flow: float | None) -> float | None:
    if prior_flow is None:
        return None
    return current_flow - prior_flow


def detect_divergence(
    flow_series: list[dict],
    lookback: int = 4,
) -> dict:
    if len(flow_series) < lookback:
        return {"divergence": "insufficient_data"}

    recent = flow_series[-lookback:]
    first, last = recent[0], recent[-1]

    price_change_pct = (last["price"] - first["price"]) / first["price"]
    flow_change = last["cumulative_flow"] - first["cumulative_flow"]

    price_flat_threshold = 0.001
    flow_significant = abs(first.get("cumulative_flow", 1)) * 0.1

    if abs(price_change_pct) < price_flat_threshold and flow_change > flow_significant:
        return {"divergence": "bullish", "flow_delta": flow_change, "price_delta_pct": price_change_pct}
    elif abs(price_change_pct) < price_flat_threshold and flow_change < -flow_significant:
        return {"divergence": "bearish", "flow_delta": flow_change, "price_delta_pct": price_change_pct}
    elif price_change_pct > price_flat_threshold and flow_change < -flow_significant:
        return {"divergence": "bearish", "flow_delta": flow_change, "price_delta_pct": price_change_pct}
    elif price_change_pct < -price_flat_threshold and flow_change > flow_significant:
        return {"divergence": "bullish", "flow_delta": flow_change, "price_delta_pct": price_change_pct}
    else:
        return {"divergence": "none", "flow_delta": flow_change, "price_delta_pct": price_change_pct}


def _get_prior_bar_flow(snapshot: dict, db_conn: Any) -> float | None:
    result = db_conn.execute(
        """
        SELECT spf.net_premium_flow
        FROM signal_premium_flow spf
        JOIN snapshots_0dte s ON s.id = spf.snapshot_id
        WHERE s.symbol = %(symbol)s
          AND s.captured_at < %(current_time)s
          AND DATE(s.captured_at AT TIME ZONE 'US/Eastern') =
              DATE(%(current_time)s AT TIME ZONE 'US/Eastern')
        ORDER BY s.captured_at DESC
        LIMIT 1
        """,
        {"symbol": snapshot["symbol"], "current_time": snapshot["captured_at"]},
    ).fetchone()
    return float(result["net_premium_flow"]) if result else None


class NetPremiumFlow(Signal):
    name = "net_premium_flow"
    table = "signal_premium_flow"

    def compute(self, snapshot_id: int, db_conn: Any) -> None:
        contracts = self._load_contracts(snapshot_id, db_conn)
        snapshot = self._load_snapshot(snapshot_id, db_conn)

        flow = compute_premium_flow(contracts, snapshot["underlying_price"])
        cumulative = compute_cumulative_flow(
            snapshot_id, db_conn, snapshot["symbol"], snapshot["captured_at"]
        )
        prior = _get_prior_bar_flow(snapshot, db_conn)
        velocity = compute_flow_velocity(flow["net_premium_flow"], prior)

        db_conn.execute(
            """
            INSERT INTO signal_premium_flow
                (snapshot_id, symbol, captured_at,
                 call_premium_at_ask, call_premium_at_bid,
                 put_premium_at_ask, put_premium_at_bid,
                 net_premium_flow, cumulative_flow,
                 flow_velocity, price_at_bar)
            VALUES (%(snapshot_id)s, %(symbol)s, %(captured_at)s,
                    %(call_at_ask)s, %(call_at_bid)s,
                    %(put_at_ask)s, %(put_at_bid)s,
                    %(net_flow)s, %(cumulative)s,
                    %(velocity)s, %(price)s)
            """,
            {
                "snapshot_id": snapshot_id,
                "symbol": snapshot["symbol"],
                "captured_at": snapshot["captured_at"],
                "call_at_ask": flow["call_premium_at_ask"],
                "call_at_bid": flow["call_premium_at_bid"],
                "put_at_ask": flow["put_premium_at_ask"],
                "put_at_bid": flow["put_premium_at_bid"],
                "net_flow": flow["net_premium_flow"],
                "cumulative": cumulative + flow["net_premium_flow"],
                "velocity": velocity,
                "price": snapshot["underlying_price"],
            },
        )
        db_conn.commit()
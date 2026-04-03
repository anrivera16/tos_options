from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from gex.calculations import compute_gex_levels
from schwab.api import SchwabApiError, get_option_chain_rows, get_price_history


POSITIVE_COLOR = "#1f9d55"
NEGATIVE_COLOR = "#c0392b"
PRICE_COLOR = "#1b263b"
SPOT_COLOR = "#f39c12"
BACKGROUND_COLOR = "#f7f4ee"
GRID_COLOR = "#d8d3c9"
ZERO_COLOR = "#374151"
OUTPUT_HTML_DIR = "out/html"
OUTPUT_DISCORD_DIR = "out/discord"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a Plotly GEX price chart")
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--history-days", type=int, default=60)
    parser.add_argument("--interval-hours", type=int, default=1)
    parser.add_argument("--max-levels", type=int, default=10)
    parser.add_argument("--output", help="Optional explicit PNG output path")
    parser.add_argument("--html-output", help="Optional explicit HTML output path")
    parser.add_argument("--contract-type", default="ALL")
    parser.add_argument("--option-range", default="OTM")
    parser.add_argument("--strike-range")
    parser.add_argument("--strategy", default="SINGLE")
    parser.add_argument("--extended-hours", action="store_true")
    return parser


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_hourly_candles(
    symbol: str,
    history_days: int,
    interval_hours: int,
    need_extended_hours: bool,
) -> list[dict[str, Any]]:
    end_datetime = datetime.now()
    start_datetime = end_datetime - timedelta(days=min(history_days, 10))
    candles = get_price_history(
        symbol=symbol,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        frequency_type="hourly",
        frequency=interval_hours,
        need_extended_hours=need_extended_hours,
    )

    if history_days > 10:
        daily_end = end_datetime - timedelta(days=10)
        daily_start = end_datetime - timedelta(days=history_days)
        daily_candles = get_price_history(
            symbol=symbol,
            start_datetime=daily_start,
            end_datetime=daily_end,
            period_type="month",
            period=max(1, min(6, (history_days + 29) // 30)),
            frequency_type="daily",
            frequency=1,
            need_extended_hours=need_extended_hours,
        )
        candles = daily_candles + candles

    normalized: list[dict[str, Any]] = []
    for candle in candles:
        timestamp = candle.get("timestamp")
        close = _coerce_float(candle.get("close"))
        if not timestamp or close is None:
            continue
        try:
            dt = datetime.fromisoformat(str(timestamp))
        except ValueError:
            continue
        open_value = _coerce_float(candle.get("open"))
        high_value = _coerce_float(candle.get("high"))
        low_value = _coerce_float(candle.get("low"))
        normalized.append(
            {
                "datetime": dt,
                "open": open_value if open_value is not None else close,
                "high": high_value if high_value is not None else close,
                "low": low_value if low_value is not None else close,
                "close": close,
                "volume": _coerce_float(candle.get("volume")),
            }
        )

    normalized.sort(key=lambda candle: candle["datetime"])
    return normalized


def _format_gex(value: float) -> str:
    abs_value = abs(value)
    if abs_value >= 1_000_000_000:
        return f"{value / 1_000_000_000:+.2f}B"
    if abs_value >= 1_000_000:
        return f"{value / 1_000_000:+.2f}M"
    if abs_value >= 1_000:
        return f"{value / 1_000:+.2f}K"
    return f"{value:+.0f}"


def _filter_close_levels(levels: list[dict[str, Any]], min_spacing: float) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for level in levels:
        strike = float(level["strike"])
        if any(abs(strike - float(existing["strike"])) < min_spacing for existing in selected):
            continue
        selected.append(level)
    return selected


def _filter_levels_for_chart(levels: list[dict[str, Any]], latest_close: float) -> list[dict[str, Any]]:
    if not levels:
        return levels
    lower_bound = latest_close * 0.85
    upper_bound = latest_close * 1.15
    nearby = [level for level in levels if lower_bound <= float(level["strike"]) <= upper_bound]
    return nearby or levels


def _find_gamma_flip(levels: list[dict[str, Any]]) -> float | None:
    if len(levels) < 2:
        return None

    ordered = sorted(levels, key=lambda level: float(level["strike"]))
    previous = ordered[0]
    previous_gex = float(previous["net_gex"])
    if previous_gex == 0:
        return float(previous["strike"])

    for current in ordered[1:]:
        current_gex = float(current["net_gex"])
        if current_gex == 0:
            return float(current["strike"])
        if previous_gex * current_gex < 0:
            prev_strike = float(previous["strike"])
            curr_strike = float(current["strike"])
            weight = abs(previous_gex) / (abs(previous_gex) + abs(current_gex))
            return prev_strike + ((curr_strike - prev_strike) * weight)
        previous = current
        previous_gex = current_gex

    return None


def _default_output_paths(symbol: str) -> tuple[Path, Path]:
    slug = symbol.lower()
    return (
        Path(OUTPUT_HTML_DIR) / f"{slug}_gex_price_overlay.html",
        Path(OUTPUT_DISCORD_DIR) / f"{slug}_gex_price_overlay.png",
    )


def _build_figure(
    symbol: str,
    candles: list[dict[str, Any]],
    levels: list[dict[str, Any]],
    option_days: int,
    history_days: int,
) -> tuple[go.Figure, list[dict[str, Any]], float | None]:
    if not candles:
        raise SchwabApiError(f"No hourly price history returned for {symbol}.")

    dates = [candle["datetime"] for candle in candles]
    latest_close = float(candles[-1]["close"])
    closes = [float(candle["close"]) for candle in candles]
    price_min = min(closes)
    price_max = max(closes)
    strike_span = max(price_max - price_min, max(latest_close * 0.015, 1.0))
    display_levels = _filter_levels_for_chart(levels, latest_close)
    filtered_levels = _filter_close_levels(display_levels, min_spacing=max(strike_span / 12.0, 0.5))
    gamma_flip = _find_gamma_flip(filtered_levels)

    fig = make_subplots(
        rows=1,
        cols=2,
        shared_yaxes=True,
        column_widths=[0.76, 0.24],
        horizontal_spacing=0.04,
        specs=[[{"type": "xy"}, {"type": "bar"}]],
    )

    fig.add_trace(
        go.Candlestick(
            x=dates,
            open=[float(candle["open"]) for candle in candles],
            high=[float(candle["high"]) for candle in candles],
            low=[float(candle["low"]) for candle in candles],
            close=closes,
            name=f"{symbol} price",
            increasing_line_color=POSITIVE_COLOR,
            decreasing_line_color=NEGATIVE_COLOR,
            increasing_fillcolor=POSITIVE_COLOR,
            decreasing_fillcolor=NEGATIVE_COLOR,
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=[dates[-1]],
            y=[latest_close],
            mode="markers+text",
            name="Spot",
            text=[f"Spot {latest_close:.2f}"],
            textposition="top right",
            marker={"size": 11, "color": SPOT_COLOR, "line": {"width": 1, "color": PRICE_COLOR}},
            hovertemplate="Spot: %{y:.2f}<extra></extra>",
        ),
        row=1,
        col=1,
    )

    for index, level in enumerate(filtered_levels):
        strike = float(level["strike"])
        net_gex = float(level["net_gex"])
        color = POSITIVE_COLOR if net_gex >= 0 else NEGATIVE_COLOR
        alpha = max(0.25, 0.7 - (index * 0.04))
        rgba = _hex_to_rgba(color, alpha)
        fig.add_hline(y=strike, line_color=rgba, line_dash="dash", line_width=1.5, row=1, col=1)
        fig.add_annotation(
            x=dates[-1],
            y=strike,
            xanchor="left",
            xshift=12,
            text=f"{strike:.2f} {_format_gex(net_gex)}",
            showarrow=False,
            font={"size": 10, "color": color},
            bgcolor="rgba(247, 244, 238, 0.88)",
            bordercolor="rgba(0,0,0,0)",
            row=1,
            col=1,
        )

    if gamma_flip is not None:
        fig.add_hline(y=gamma_flip, line_color=ZERO_COLOR, line_width=2.2, row=1, col=1)
        fig.add_annotation(
            x=dates[0],
            y=gamma_flip,
            xanchor="left",
            yshift=10,
            text=f"Gamma flip {gamma_flip:.2f}",
            showarrow=False,
            font={"size": 10, "color": ZERO_COLOR},
            bgcolor="rgba(247, 244, 238, 0.92)",
            bordercolor="rgba(0,0,0,0)",
            row=1,
            col=1,
        )

    strikes = [float(level["strike"]) for level in filtered_levels]
    gex_values = [float(level["net_gex"]) / 1_000_000 for level in filtered_levels]
    bar_colors = [POSITIVE_COLOR if value >= 0 else NEGATIVE_COLOR for value in gex_values]
    fig.add_trace(
        go.Bar(
            x=gex_values,
            y=strikes,
            orientation="h",
            name="Net GEX by Strike",
            marker={"color": bar_colors},
            hovertemplate="Strike %{y:.2f}<br>Net GEX %{x:.2f}M<extra></extra>",
        ),
        row=1,
        col=2,
    )

    fig.add_vline(x=0, line_color=ZERO_COLOR, line_width=2.0, row=1, col=2)
    if gamma_flip is not None:
        fig.add_hline(y=gamma_flip, line_color=ZERO_COLOR, line_dash="dot", line_width=1.4, row=1, col=2)

    relevant_prices = closes + strikes
    lower = min(relevant_prices)
    upper = max(relevant_prices)
    padding = max((upper - lower) * 0.05, latest_close * 0.01, 1.0)

    fig.update_layout(
        title={
            "text": (
                f"{symbol} hourly price with current next-{option_days}-day GEX levels"
                f"<br><sup>Current option-chain snapshot over last {history_days} days of price history</sup>"
            ),
            "x": 0.5,
        },
        paper_bgcolor=BACKGROUND_COLOR,
        plot_bgcolor=BACKGROUND_COLOR,
        font={"color": PRICE_COLOR},
        hovermode="x unified",
        showlegend=False,
        xaxis_rangeslider_visible=False,
        margin={"l": 60, "r": 90, "t": 90, "b": 60},
    )
    fig.update_xaxes(showgrid=True, gridcolor=GRID_COLOR, zeroline=False, row=1, col=1)
    fig.update_xaxes(showgrid=True, gridcolor=GRID_COLOR, zeroline=False, title_text="$M", row=1, col=2)
    fig.update_yaxes(title_text="Price", range=[lower - padding, upper + padding], showgrid=True, gridcolor=GRID_COLOR, row=1, col=1)
    fig.update_yaxes(showgrid=False, row=1, col=2, side="right")

    return fig, filtered_levels, gamma_flip


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    hex_value = hex_color.lstrip("#")
    red = int(hex_value[0:2], 16)
    green = int(hex_value[2:4], 16)
    blue = int(hex_value[4:6], 16)
    return f"rgba({red}, {green}, {blue}, {alpha:.3f})"


def render_chart(
    symbol: str,
    candles: list[dict[str, Any]],
    levels: list[dict[str, Any]],
    png_output_path: str,
    html_output_path: str,
    option_days: int,
    history_days: int,
) -> dict[str, Any]:
    figure, filtered_levels, gamma_flip = _build_figure(symbol, candles, levels, option_days, history_days)

    png_output = Path(png_output_path)
    html_output = Path(html_output_path)
    png_output.parent.mkdir(parents=True, exist_ok=True)
    html_output.parent.mkdir(parents=True, exist_ok=True)

    figure.write_html(html_output, include_plotlyjs=True, full_html=True)
    figure.write_image(png_output, format="png", width=1800, height=900, scale=2)
    return {
        "png_output": str(png_output),
        "html_output": str(html_output),
        "display_levels": filtered_levels,
        "gamma_flip": gamma_flip,
    }


def generate_chart(
    symbol: str,
    days: int,
    history_days: int,
    interval_hours: int,
    max_levels: int,
    output: str | None = None,
    html_output: str | None = None,
    contract_type: str = "ALL",
    option_range: str = "OTM",
    strike_range: str | None = None,
    strategy: str = "SINGLE",
    extended_hours: bool = False,
) -> dict[str, Any]:
    option_rows = get_option_chain_rows(
        symbol=symbol,
        days=days,
        contract_type=contract_type,
        option_range=option_range,
        strike_range=strike_range,
        strategy=strategy,
    )
    levels = compute_gex_levels(option_rows, max_levels=max_levels, min_dte=0, max_dte=days)
    candles = _load_hourly_candles(
        symbol=symbol,
        history_days=history_days,
        interval_hours=interval_hours,
        need_extended_hours=extended_hours,
    )

    if not levels:
        raise SchwabApiError(f"No GEX levels could be computed for {symbol} from the current option chain.")

    default_html_output, default_png_output = _default_output_paths(symbol)
    render_result = render_chart(
        symbol=symbol,
        candles=candles,
        levels=levels,
        png_output_path=output or str(default_png_output),
        html_output_path=html_output or str(default_html_output),
        option_days=days,
        history_days=history_days,
    )

    return {
        "symbol": symbol,
        "png_output": render_result["png_output"],
        "html_output": render_result["html_output"],
        "option_contracts": len(option_rows),
        "hourly_candles": len(candles),
        "levels": levels,
    }


def main() -> None:
    args = build_parser().parse_args()
    result = generate_chart(
        symbol=args.symbol,
        days=args.days,
        history_days=args.history_days,
        interval_hours=args.interval_hours,
        max_levels=args.max_levels,
        output=args.output,
        html_output=args.html_output,
        contract_type=args.contract_type,
        option_range=args.option_range,
        strike_range=args.strike_range,
        strategy=args.strategy,
        extended_hours=args.extended_hours,
    )
    print(
        f"Wrote Plotly GEX chart for {result['symbol']} to {result['png_output']} and {result['html_output']} "
        f"using {result['option_contracts']} option rows and {result['hourly_candles']} candles."
    )


if __name__ == "__main__":
    main()

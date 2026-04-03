import json
import sys

from schwab.api import get_option_chain_rows


def main() -> None:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "SPY"
    rows = get_option_chain_rows(symbol, days=30)
    print(json.dumps(rows[:3], indent=2, sort_keys=True))
    print(f"Fetched {len(rows)} normalized option rows for {symbol}.")


if __name__ == "__main__":
    main()

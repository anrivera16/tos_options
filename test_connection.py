from schwab.api import get_quote


def main() -> None:
    quote = get_quote("SPY")
    last_price = quote.get("quote", {}).get("lastPrice")
    print("Authenticated quote request succeeded.")
    print(f"SPY last price: {last_price}")


if __name__ == "__main__":
    main()

from __future__ import annotations

from schwab import api


def test_normalize_option_chain_symbol_maps_spx_to_dollar_prefixed_index() -> None:
    assert api.normalize_option_chain_symbol("SPX") == "$SPX"
    assert api.normalize_option_chain_symbol("$SPX") == "$SPX"


def test_get_option_chain_uses_normalized_symbol(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_request_json(request_fn, endpoint: str, **kwargs):
        class FakeClient:
            def option_chains(self, symbol: str, **params):
                captured["symbol"] = symbol
                captured["contractType"] = params["contractType"]
                return {"symbol": symbol}

        response = request_fn(FakeClient())
        captured["endpoint"] = endpoint
        return response

    monkeypatch.setattr(api, "_request_json", fake_request_json)

    result = api.get_option_chain(symbol="SPX", days=30)

    assert captured["symbol"] == "$SPX"
    assert captured["endpoint"] == "option_chains($SPX)"
    assert captured["contractType"] == "ALL"
    assert result["symbol"] == "$SPX"

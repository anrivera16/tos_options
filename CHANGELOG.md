# Changelog

## 2026-04-10 — SPX 0DTE Chain Capture Research

### Completed
- Deep research on SPX 0DTE/1DTE options chain capture via Polygon.io (Massive API)
- Confirmed Polygon endpoint: `GET /v3/snapshot/options/I:SPX` supports full chain with greeks, IV, OI, quotes
- Identified 7 concrete strategies rated by 15-minute delay tolerance
- Documented SPX vs SPY structural differences
- Mapped required codebase changes in `z0dte/` module (schema, API source, ingestion)

### Artifacts
- `outputs/spx-0dte-chain-capture-strategies.md` — main research brief (18 sources cited)
- `outputs/spx-0dte-chain-capture-strategies.provenance.md` — provenance record
- `outputs/.plans/spx-0dte-chain-capture-strategies.md` — research plan

### Next Steps
- [ ] Verify exact Polygon plan tier for options data
- [ ] Update `massive_api.py` to use correct chain snapshot endpoint
- [ ] Add SPX support to normalizer and schema
- [ ] Implement max pain signal (`signal_max_pain` table)
- [ ] Backtest delay-tolerance ratings against actual 15-min delayed data

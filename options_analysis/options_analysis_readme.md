# `options_analysis` README

## Latest update

The module now includes a dedicated volatility analysis layer that extends the original regime engine with:

- IV surface sampling from contract-level data
- term structure extraction from expiration aggregates
- forward volatility extraction between adjacent expirations
- 25-delta skew measurements for puts, calls, and ATM references
- realized-vs-implied volatility spread classification
- volatility regime labels such as `premium_rich`, `premium_cheap`, and `fair_value`
- strategy scoring that can recognize calendar, gamma scalp, and IV-rich short premium setups
- built-in backtest blueprints for the new volatility strategies

These additions make the engine more useful for testing book-inspired volatility ideas instead of only reading GEX structure.

## Purpose

`options_analysis` is a standalone Python feature folder that transforms an already-aggregated full options chain into a structured **regime + strike/date + strategy analysis engine**.

The goal is not to merely display option data. The goal is to answer:

- What is the current **options market regime**?
- Which **strikes** are the most important right now?
- Which **expirations** matter the most?
- What **behavior** is the market structure implying?
- **Where might there be a tradeable edge** given the current regime and structure?
- Which **option strategies** fit the current regime and volatility environment?
- How can we test this logic so it remains reliable as the code evolves?

This module is designed as a deterministic, testable, pure-analysis layer that sits on top of your existing options aggregation pipeline.

---

# High-level concept

You already have the data aggregation piece.

This feature should consume:
- spot price
- full chain by expiration/strike
- Greeks/exposure data if available
- open interest / volume
- implied vol data
- any aggregated GEX-related fields your current code already computes

It should then produce:
1. **Regime classification** (with confidence and data completeness tracking)
2. **Interesting strike selection** (with opportunity tags identifying potential edge)
3. **Interesting expiration selection** (with opportunity tags)
4. **Strategy suitability scoring**
5. **One best trade suggestion** with a transparent POP estimate, invalidation, and rationale
6. **Scenario-based analysis**
7. **Final output structure for UI / CLI / API consumption**

---

# Core product definition

`options_analysis` should be a **regime-aware options decision engine**.

It should:
- identify likely pinning / expansion / transition behavior
- rank key strikes and expirations by relevance
- **tag strikes and expirations with actionable opportunity labels** (e.g., long gamma, short gamma, directional edge, vol sale)
- surface strategy ideas matched to the current market structure
- emit one standalone trade suggestion under `trade_suggestion`
- explain why those strikes/dates/strategies matter
- **track data completeness so output confidence is transparent**
- remain fully testable with deterministic inputs

## Current MVP trade suggestion

The current MVP appends a deterministic `trade_suggestion` block to the analysis payload.

It is intentionally separate from `gex` and only consumes outputs already built inside `build_options_analysis()` plus the upstream report passed into that function.

The suggestion returns a single best idea with:
- strategy
- direction
- expiration
- target strike and optional secondary strike
- entry thesis
- invalidation
- `probability_type` set to `POP estimate`
- heuristic `probability_of_profit`
- confidence
- rationale

Directional `expansion` suggestions default to defined-risk spreads first, with simpler single-leg fallbacks when data quality is degraded.

---

# Design principles

## 1. Deterministic first
The logic should be mostly rule-based and reproducible.

Avoid hidden heuristics that are hard to explain unless they are clearly encapsulated and tested.

## 2. Explainability matters
Every major output should have a reason attached:
- why the regime was chosen
- why a strike was flagged
- why an expiration was highlighted
- why a strategy fits
- **what would invalidate each conclusion**

## 3. Separate calculation from interpretation
Keep raw calculations separate from labels and narrative.

Example:
- calculate gamma concentration score
- then interpret it as "pinning risk elevated"

## 4. Modular scoring
Most of this feature should use composable scores:
- strike importance score
- expiration importance score
- regime confidence score
- strategy fit score
- **opportunity conviction score**

## 5. Test every classifier and score path
This system should be stable over time, so tests are not optional.

## 6. Never trust thin data silently
Every analysis output must carry a data completeness indicator. If key inputs are `None`, the engine should still run — but it must declare what it could not evaluate so the consumer knows when a regime call or opportunity tag is based on partial information.

---

# Proposed folder structure

```text
options_analysis/
├── README.md
├── __init__.py
├── config.py
├── types.py
├── constants.py
├── engine.py
├── safeguards.py
├── regime/
│   ├── __init__.py
│   ├── classifier.py
│   ├── scoring.py
│   ├── transitions.py
│   └── explanations.py
├── strikes/
│   ├── __init__.py
│   ├── ranking.py
│   ├── clustering.py
│   ├── significance.py
│   ├── opportunity.py
│   └── explanations.py
├── expirations/
│   ├── __init__.py
│   ├── ranking.py
│   ├── term_structure.py
│   ├── weighting.py
│   ├── opportunity.py
│   └── explanations.py
├── strategies/
│   ├── __init__.py
│   ├── templates.py
│   ├── fitter.py
│   ├── scoring.py
│   ├── risk_profiles.py
│   └── explanations.py
├── scenarios/
│   ├── __init__.py
│   ├── generators.py
│   ├── stress.py
│   └── pnl.py
├── metrics/
│   ├── __init__.py
│   ├── regime_metrics.py
│   ├── strike_metrics.py
│   ├── expiration_metrics.py
│   ├── volatility_metrics.py
│   └── normalization.py
├── output/
│   ├── __init__.py
│   ├── schemas.py
│   ├── serializers.py
│   └── narrative.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── fixtures/
    │   ├── balanced_chain.json
    │   ├── pinned_chain.json
    │   ├── short_gamma_breakout_chain.json
    │   ├── high_iv_chain.json
    │   ├── low_iv_chain.json
    │   └── partial_data_chain.json
    ├── test_regime_classifier.py
    ├── test_strike_ranking.py
    ├── test_expiration_ranking.py
    ├── test_opportunity_tagging.py
    ├── test_strategy_scoring.py
    ├── test_scenarios.py
    ├── test_engine_outputs.py
    ├── test_explanations.py
    ├── test_data_completeness.py
    └── test_regime_hysteresis.py
```

---

# Core responsibilities by module

## `engine.py`
Top-level orchestrator.

Responsibilities:
- accept normalized input
- **assess data completeness before analysis begins**
- call metric calculators
- call regime classifier (with hysteresis if prior regime is available)
- rank strikes
- **tag strikes with opportunity labels**
- rank expirations
- **tag expirations with opportunity labels**
- score strategies (informed by opportunity tags)
- run scenarios
- produce final analysis object

This should be the main entry point for the feature.

---

## `safeguards.py`
Cross-cutting safety and quality checks.

Responsibilities:
- **Data completeness scoring**: track which metric paths had real data vs. fell through to defaults
- **Regime hysteresis**: prevent regime flickering on small input changes
- **Distance gating**: enforce proximity filters before strike scoring
- **GEX sign convention validation**: ensure upstream GEX sign matches expected convention
- **Balanced regime auditing**: track classification frequency to detect over-reliance on the fallback regime

This module is called by the engine and by individual classifiers/rankers to enforce quality constraints.

---

## `types.py`
Contains data models for:
- input chain objects
- aggregated exposure objects
- regime outputs
- strike ranking outputs
- **opportunity tag objects**
- expiration ranking outputs
- strategy suggestions
- scenario result objects
- **data completeness report**
- final report payload

Use:
- `dataclasses`
or
- `pydantic`
depending on your current project conventions

If the project is already strongly typed, prefer `pydantic` for validation at module boundaries.

---

## `config.py`
Holds configurable thresholds:
- gamma flip distance threshold
- strike importance weighting
- DTE buckets
- minimum OI / liquidity filters
- regime confidence thresholds
- high IV / low IV cutoffs
- strategy score weights
- **regime hysteresis margin** (how much the new regime must win by before switching)
- **strike distance gate** (max % from spot before a strike is excluded from active scoring)
- **opportunity conviction thresholds** (minimum conviction to emit a tag)
- **balanced regime frequency alert threshold** (e.g., warn if > 40% of classifications are balanced)

All thresholds should be configurable and testable.

---

## `constants.py`
Static labels and enums:
- regime names
- strategy names
- explanation categories
- risk descriptors
- **opportunity tag names**
- **GEX sign convention documentation**

Example:
```python
REGIME_PINNED = "pinned"
REGIME_TRANSITION = "transition"
REGIME_EXPANSION = "expansion"
REGIME_BALANCED = "balanced"

# Opportunity tag constants
OPP_LONG_GAMMA = "long_gamma_here"
OPP_SHORT_GAMMA = "short_gamma_here"
OPP_LONG_DELTA_CALL = "long_delta_call"
OPP_LONG_DELTA_PUT = "long_delta_put"
OPP_VOL_SALE = "vol_sale"
OPP_VOL_BUY = "vol_buy"
OPP_PIN_TARGET = "pin_target"
OPP_BREAKOUT_TRIGGER = "breakout_trigger"
OPP_CALENDAR_NODE = "calendar_spread_node"

# GEX sign convention (CRITICAL — document once, enforce everywhere)
# Positive total_gex = dealers are NET LONG gamma = stabilizing / pinning
# Negative total_gex = dealers are NET SHORT gamma = destabilizing / accelerating
# If your upstream pipeline uses the opposite convention, flip the sign
# BEFORE passing data into this module. Do NOT mix conventions.
GEX_POSITIVE_MEANS_STABILIZING = True
```

---

# Input contract

This module should not care how data was fetched.

It should accept a fully normalized analysis input, something like:

```python
from dataclasses import dataclass

@dataclass
class OptionContract:
    expiration: str
    dte: int
    strike: float
    option_type: str  # "call" or "put"
    bid: float
    ask: float
    mid: float
    last: float | None
    iv: float | None
    delta: float | None
    gamma: float | None
    theta: float | None
    vega: float | None
    open_interest: int
    volume: int

@dataclass
class AggregatedStrikeData:
    strike: float
    total_call_oi: int
    total_put_oi: int
    call_gex: float | None
    put_gex: float | None
    net_gex: float | None
    abs_gex: float | None
    call_volume: int
    put_volume: int

@dataclass
class AggregatedExpirationData:
    expiration: str
    dte: int
    total_oi: int
    total_volume: int
    total_gex: float | None
    abs_gex: float | None
    atm_iv: float | None

@dataclass
class OptionsAnalysisInput:
    symbol: str
    spot_price: float
    timestamp: str
    contracts: list[OptionContract]
    strikes: list[AggregatedStrikeData]
    expirations: list[AggregatedExpirationData]
    gamma_flip: float | None
    call_wall: float | None
    put_wall: float | None
    total_gex: float | None
    atm_iv: float | None
    rv_20: float | None
    iv_rank: float | None
```

This is only an example. The exact structure should fit your existing pipeline.

---

# Core analysis flow

## New volatility analytics

The engine now emits additional volatility-aware outputs inside `derived_metrics` and `data_completeness`:

- `derived_metrics.iv_surface`: sampled contract points with expiration, strike, option type, moneyness, and delta bucket
- `derived_metrics.term_structure`: ATM IV by expiry with slope versus the prior tenor
- `derived_metrics.forward_volatility_curve`: implied forward volatilities between adjacent expirations
- `derived_metrics.skew_metrics`: 25-delta put/call skew and ATM-relative skew measures
- `derived_metrics.volatility_overview`: compact summary of IV rank, IV percentile, ATM IV, RV20, realized-implied spread, term-structure slope, surface shape, and vol regime
- `data_completeness.vol_environment`: same volatility context attached to the completeness report for downstream explainability
- `backtest_blueprints`: strategy templates with entry rules, exit rules, and metrics to track

### Example derived volatility outputs

```python
analysis["derived_metrics"]["volatility_overview"] == {
    "iv_rank": 72.0,
    "iv_percentile": 81.0,
    "atm_iv": 0.24,
    "rv_20": 0.17,
    "realized_implied_spread": 0.07,
    "term_structure_slope": -0.03,
    "surface_shape": "backwardation",
    "vol_regime": "premium_rich",
    "put_call_25d_skew": 0.06,
    "put_atm_skew": 0.04,
    "call_atm_skew": -0.02,
}
```

### New strategy research templates

The engine now emits backtest blueprints for:

- `short_premium_iv_rank`
- `long_gamma_scalp`
- `calendar_term_structure`
- `event_premium_fade` when the curve is backwardated

These are not execution-ready order tickets. They are deterministic, book-inspired strategy definitions meant to plug into your existing backtest runner.

## Step 1: Normalize, validate, and assess data completeness

Before analysis:
- ensure spot > 0
- ensure strikes are sorted
- ensure expirations have valid DTE
- ensure missing Greeks/IV fields are handled gracefully
- ensure gamma flip and walls can be `None`
- **compute a `DataCompletenessReport` that records which key fields are present vs. missing**

This avoids downstream logic becoming messy and ensures the final output is honest about what it could and could not evaluate.

### Data completeness tracking

```python
from dataclasses import dataclass, field

@dataclass
class DataCompletenessReport:
    total_signals: int                      # total possible signal paths
    available_signals: int                  # signal paths with real data
    completeness_ratio: float               # available / total
    missing_fields: list[str]               # e.g. ["gamma_flip", "rv_20", "iv_rank"]
    degraded_analyses: list[str]            # e.g. ["transition regime detection disabled — no gamma_flip"]
    
    @property
    def is_sufficient(self) -> bool:
        """Minimum threshold for trusting the output."""
        return self.completeness_ratio >= 0.5
```

Key signal fields to track:
- `gamma_flip` — required for transition regime and breakout trigger tags
- `total_gex` — required for expansion/pinned regime separation
- `call_wall` / `put_wall` — required for directional opportunity tags
- `atm_iv` / `rv_20` — required for vol-based opportunity tags and strategy vol-fit scoring
- `iv_rank` — used for vol_sale / vol_buy conviction
- per-contract `gamma` — required for GEX concentration metrics
- per-contract `iv` — required for skew and term structure analysis

If a field is `None`, the metric that depends on it should return `None` (not a default), and the classifier/tagger should skip that signal path and record the skip in `degraded_analyses`.

---

## Step 2: Compute regime metrics
Build reusable metrics, such as:

- distance from spot to gamma flip
- normalized distance to call wall
- normalized distance to put wall
- net GEX sign
- GEX concentration around spot
- nearby OI concentration
- front-expiration concentration
- IV vs RV spread
- skew slope if available
- nearest large gamma cluster distance
- chain asymmetry score

These metrics should be numeric and explainable.

**All distance metrics must be percentage-based, never absolute dollar values.** A 1% move in SPY covers ~5 strikes; in a $30 biotech it might not even be one strike width. Percentage normalization ensures the engine behaves consistently across symbols and price levels.

Example:
```python
from dataclasses import dataclass

@dataclass
class RegimeMetrics:
    spot_price: float
    gamma_flip: float | None
    distance_to_flip_pct: float | None
    distance_to_call_wall_pct: float | None
    distance_to_put_wall_pct: float | None
    total_gex: float | None
    nearby_gex_concentration: float
    nearby_oi_concentration: float
    iv_minus_rv: float | None
    front_dte_weight: float
```

---

## Step 3: Classify regime

Use the metrics to assign one of several regimes.

Suggested initial regimes:

### 1. `pinned`
Characteristics:
- spot near major gamma strike / wall
- positive gamma or stabilizing structure
- high local concentration around spot
- expected suppressed movement

### 2. `balanced`
Characteristics:
- no strong directional pressure
- no close unstable transition
- moderate concentration but no obvious pin
- neutral behavior expectations

### 3. `transition`
Characteristics:
- spot close to gamma flip
- opposing walls nearby
- low confidence / unstable environment
- behavior could shift quickly

### 4. `expansion`
Characteristics:
- negative gamma / destabilizing structure
- spot beyond stabilizing zone
- elevated likelihood of directional movement

### 5. `exhaustion`
Characteristics:
- large move into extreme strike cluster / wall
- potential slowing, pausing, or reversal near a major level

You do not need all of these on day one. A strong MVP can start with:
- `pinned`
- `transition`
- `expansion`
- `balanced`

---

# Regime classification logic

Use scoring instead of pure if/else whenever possible.

Example approach:

```python
regime_scores = {
    "pinned": 0.0,
    "balanced": 0.0,
    "transition": 0.0,
    "expansion": 0.0,
}
```

Then add points based on conditions.

Example signals:

## Pinned score increases when:
- spot very close to dominant strike
- total GEX positive
- gamma concentration around spot is high
- call wall and put wall compress spot into a narrow zone
- realized movement is low

## Transition score increases when:
- spot is close to gamma flip
- total GEX is near zero or unstable
- flip is within a short distance threshold
- wall distances are asymmetric but unresolved

## Expansion score increases when:
- total GEX is negative
- spot is beyond flip in destabilizing direction
- nearest major strike is not acting as a pin
- local concentration is weaker
- expected move / realized movement is increasing

## Balanced score increases when:
- no regime dominates
- concentration is moderate
- no nearby threshold is likely to trigger regime change

Then choose:
- highest score
- attach second-highest as alternative regime
- compute confidence from score spread
- **apply hysteresis before committing to a regime change**

This is much more testable than ad hoc branching.

### Regime hysteresis (CRITICAL SAFEGUARD)

Without hysteresis, tiny changes in spot or GEX can flip the regime on consecutive ticks. This makes strategy suggestions whipsaw and erodes trust in the output.

**Rule:** If a prior regime classification is available (e.g., from the previous analysis run), the new regime must win by a configurable margin before the engine switches.

```python
# config.py
REGIME_HYSTERESIS_MARGIN = 0.08  # new regime must beat current by 8% to switch

# classifier.py
def apply_hysteresis(
    scores: dict[str, float],
    prior_regime: str | None,
    margin: float,
) -> str:
    """
    If we have a prior regime, require the new winner to beat it by `margin`
    before switching. Otherwise return the prior regime.
    """
    winner = max(scores, key=scores.get)
    
    if prior_regime is None or prior_regime not in scores:
        return winner
    
    if winner == prior_regime:
        return winner
    
    if scores[winner] - scores[prior_regime] >= margin:
        return winner
    
    return prior_regime
```

The `RegimeResult` should always carry scores for ALL regimes so the consumer can see when the call was close:

```python
@dataclass
class RegimeResult:
    regime: str
    confidence: float
    all_scores: dict[str, float]        # every regime's raw score
    prior_regime: str | None            # what it was last time
    regime_changed: bool                # did hysteresis allow the switch?
    score_spread: float                 # gap between #1 and #2
    reasoning: list[str]
    signals_used: int                   # how many signal paths contributed
    signals_available: int              # how many signal paths had data
```

### Balanced regime auditing

`balanced` is the fallback when no regime clearly wins. This is correct behavior — but it's also where broken data and too-strict thresholds hide.

**Safeguard:** Track regime classification frequency over time. If `balanced` fires more than ~35-40% of the time across a meaningful sample of runs, investigate whether:
- other regime thresholds are too strict
- key input fields are consistently `None`
- a new regime category is needed

This is not enforced at runtime — it's an offline audit. But `safeguards.py` should expose a helper that accepts a list of recent regime results and returns a frequency breakdown with warnings.

---

# Should price be used to determine regime?

Yes, but not alone.

Use **price relative to structure**.

Price by itself is not enough. Spot becomes informative when combined with:
- gamma flip
- call wall
- put wall
- high OI strikes
- high gamma concentration areas
- expiration concentration

The right framing is:

> Regime is determined by **spot interacting with options structure**, not by spot in isolation.

That means:
- spot near dominant gamma cluster = possible pin
- spot near gamma flip = possible transition
- spot beyond stabilizing zone in negative gamma environment = possible expansion

So the answer is: **yes, price should be used, but only relationally**.

---

# GEX sign convention (CRITICAL SAFEGUARD)

The entire regime classification depends on GEX values being correctly signed. There is no universal industry standard.

**This module's convention:**
- **Positive total_gex** = dealers are net long gamma = stabilizing / pinning behavior
- **Negative total_gex** = dealers are net short gamma = destabilizing / accelerating behavior

If your upstream pipeline uses the opposite convention, **flip the sign in your normalization step** before passing data to this module. Never mix conventions.

**Enforcement:**
- Document the convention in `constants.py` (see above)
- Every test fixture must include a comment stating the sign convention used
- Write an explicit test: `positive_total_gex + spot_near_dominant_strike → pinned`
- Write the inverse test: `negative_total_gex + spot_beyond_flip → expansion`

If these two tests fail, the entire downstream analysis is inverted and every regime call will be wrong.

---

# Strike analysis

## Goal
Highlight the most important strikes and **tag each one with actionable opportunity labels** that identify where the edge might be.

The output should not just say "this strike matters." It should say "this strike matters, and here's the trade thesis."

---

# Current MVP status

An initial implementation now exists in `python_scripts/options_analysis/engine.py` and is wired into the existing `python -m cli gex` flow.

Current MVP behavior:

- consumes the existing exposure report generated from normalized option rows
- classifies regime with explicit scorecards using `total_gex`, `spot_price`, `gamma_flip_estimate`, wall proximity, and concentration
- supports prior-regime hysteresis so small score changes do not whipsaw the regime output
- filters active strike ranking to a configurable band around spot so far OTM levels do not dominate the analysis
- ignores gamma-flip values that are too far from spot to be a credible active-market reference
- emits a `data_completeness` block so degraded inputs are visible in the output
- ranks the most relevant strikes by net gamma and proximity to spot
- ranks the most relevant expirations by gamma, open interest, and volume
- suggests a small set of strategy templates matched to the inferred regime
- emits its own standalone CLI payload through `python -m cli options-analysis`

Current CLI entry point:

```bash
python -m cli options-analysis --symbol SPY --days 30
python -m cli options-analysis --symbol SPY --days 30 --output out/options_analysis.json
python -m cli options-analysis --symbol SPY --days 30 --prior-regime balanced
python -m cli options-analysis --symbol SPY --days 30 --no-discord
```

By default the command also posts a text summary to Discord. Use `--no-discord` when you want a local-only run.

This keeps the options-statistics layer runnable through its own command surface instead of attaching analysis to the default `gex` output.

This is intentionally an MVP layer on top of the current analytics pipeline, not the full module layout proposed in this document yet. The current shape is designed to be deterministic, easy to test, and simple to expand into the fuller architecture later.

It is also intended to stay separate from the core `gex` package logic. Right now it consumes the exposure report produced upstream, but its classifiers, safeguards, rankings, and narrative logic live under `python_scripts/options_analysis/` rather than being folded into `python_scripts/gex/`.

Example output shape:

```python
{
    "options_analysis": {
        "regime": {
            "name": "balanced",
            "confidence": 0.58,
            "reasons": [
                "net gamma is positive, which suggests dealer positioning is stabilizing",
            ],
            "gamma_flip": 497.5,
        },
        "data_completeness": {
            "total_signals": 10,
            "available_signals": 10,
            "completeness_ratio": 1.0,
            "missing_fields": [],
            "degraded_analyses": [],
            "is_sufficient": True,
        },
        "key_levels": {
            "spot_price": 500.0,
            "gamma_flip": 497.5,
            "call_wall": {"strike": 495.0, "call_gex": 25000000.0},
            "put_wall": {"strike": 495.0, "put_gex": -20250000.0},
            "top_strike": 505.0,
        },
        "strikes": [...],
        "expirations": [...],
        "strategies": [...],
        "narrative": {...},
        "derived_metrics": {...},
    }
}
```

Immediate next expansion points for this module:

- promote current dictionaries into typed dataclasses or pydantic models
- split ranking and explanation logic into dedicated submodules
- extend strategy fitting with IV-vs-RV and skew-aware scoring

## Distance gating (CRITICAL SAFEGUARD)

Before scoring, apply a hard distance gate. Only strikes within a configurable percentage of spot enter the active scoring pool.

```python
# config.py
STRIKE_DISTANCE_GATE_PCT = 0.08  # only score strikes within ±8% of spot

# Exceptions: call_wall and put_wall are always included regardless of distance,
# but tagged with "outside_active_zone" if they exceed the gate.
```

**Why this matters:** Without a gate, your `distance_weight` (0.20 in the scoring weights) only mildly penalizes far-away strikes. A massive OI cluster 15% away can still score highly on structural importance alone, pushing genuinely relevant near-spot strikes out of the top 5. The gate prevents this.

## Candidate strike types to flag
- call wall
- put wall
- gamma flip neighborhood
- highest absolute GEX strikes
- highest OI strikes
- high volume strikes
- near-spot strikes
- support/resistance candidate strikes
- acceleration trigger strikes
- pin/magnet strikes

---

## Strike scoring factors

### Structural importance
- absolute net GEX at strike
- total OI at strike
- volume at strike
- local cluster size

### Spot relevance
- distance from spot
- whether strike is ATM / slightly OTM / slightly ITM
- whether strike is within expected move

### Regime relevance
- if in pinned regime, emphasize nearby concentration strikes
- if in transition regime, emphasize flip-adjacent strikes
- if in expansion regime, emphasize trigger and acceleration strikes

### Expiration contribution
- does this strike matter across many expirations?
- is importance concentrated in front expiry or distributed?

### Uniqueness / prominence
- how much does this strike stand out compared to neighbors?

---

## Opportunity tagging for strikes

After a strike is ranked, a second pass tags it with **opportunity labels** that identify potential trades. This is what turns "interesting" from "structurally notable" into "here's where the edge might be."

### Opportunity tag model

```python
from dataclasses import dataclass

@dataclass
class OpportunityTag:
    tag: str                    # e.g. "long_gamma_here", "pin_target"
    direction: str              # "long" | "short" | "neutral"
    thesis: str                 # one-line explanation of why this edge exists
    conviction: float           # 0.0 - 1.0, factors in vol pricing and data quality
    regime_dependency: str      # which regime this tag depends on
    invalidation: str           # what kills this thesis
    valid_while: str            # condition that must remain true for the tag to hold
```

### Defined opportunity tags

| Tag | Direction | When it fires | Key dependencies |
|-----|-----------|---------------|------------------|
| `long_gamma_here` | long | Spot near gamma flip or in negative gamma zone; buying gamma at this strike benefits from acceleration | Regime = transition or expansion; gamma_flip must be non-None |
| `short_gamma_here` | short | Heavy positive dealer gamma pinning this strike; premium decay favors selling | Regime = pinned; nearby_gex_concentration high |
| `long_delta_call` | long | Call wall above with expansion regime; momentum could carry toward this strike | Regime = expansion; call_wall must be non-None |
| `long_delta_put` | long (puts) | Put wall below under pressure; expansion downside favors directional puts | Regime = expansion; put_wall must be non-None |
| `vol_sale` | short vol | IV elevated relative to RV at relevant expiration; premium is rich | atm_iv and rv_20 must be non-None; iv_minus_rv > threshold |
| `vol_buy` | long vol | IV compressed or below RV; cheap gamma available | atm_iv and rv_20 must be non-None; iv_minus_rv < threshold |
| `pin_target` | neutral | High probability of gravitating toward this strike into expiry | Regime = pinned; front DTE concentration at this strike |
| `breakout_trigger` | directional | If spot clears this level, dealer hedging accelerates the move | gamma_flip must be non-None; strike near flip |
| `calendar_spread_node` | neutral | Front expiry IV significantly diverges from back expiry at this strike | Multiple expirations must have IV data at this strike |

### Tagging rules and safeguards

**1. Tags must be strike-specific, not regime-echoes.**
If `expansion` always maps to `long_gamma_here` on every strike, the tags add no information. The same regime should produce *different* tags at different strikes. The gamma flip strike gets `breakout_trigger`, a strike 3% above spot gets `long_delta_call`, the ATM strike in pinned gets `pin_target`.

**Test for this:** Given a pinned regime fixture, assert that at least two different tag types appear across the top 5 strikes.

**2. Conflicting tags on the same strike must be resolved.**
A strike near the gamma flip could get both `long_gamma_here` and `short_gamma_here`. Resolution rules:
- The regime breaks the tie: expansion → favor long gamma; pinned → favor short gamma
- If regime is `transition`, allow both tags but the one aligned with the dominant score direction gets higher conviction
- Never emit two tags with opposite `direction` values at equal conviction

**3. Conviction must factor in vol pricing.**
A `long_gamma_here` tag at a strike where IV is 80 and RV is 20 is structurally correct but practically expensive. The conviction score must penalize tags where the vol environment works against the thesis.

```python
def adjust_conviction_for_vol(
    base_conviction: float,
    tag_direction: str,
    iv_minus_rv: float | None,
) -> float:
    """
    Penalize long-vol tags when IV >> RV (expensive).
    Penalize short-vol tags when IV << RV (cheap, likely to expand).
    """
    if iv_minus_rv is None:
        return base_conviction * 0.8  # unknown vol = reduce confidence
    
    if tag_direction == "long" and iv_minus_rv > 10:
        # buying expensive gamma — reduce conviction
        return base_conviction * max(0.3, 1.0 - (iv_minus_rv / 40))
    
    if tag_direction == "short" and iv_minus_rv < -5:
        # selling cheap premium — reduce conviction
        return base_conviction * max(0.3, 1.0 - (abs(iv_minus_rv) / 30))
    
    return base_conviction
```

**4. Every tag must carry an invalidation condition.**
The invalidation is what makes the tag actionable vs. decorative. Examples:
- `long_gamma_here` → "Invalidated if spot reclaims 555 and total GEX flips positive"
- `pin_target` → "Invalidated if front-expiry OI drops significantly or spot breaks beyond ±1% of strike"
- `breakout_trigger` → "Invalidated if gamma flip shifts away from this strike"

**5. Every tag must carry a `valid_while` condition.**
These tags are snapshot-based. A `breakout_trigger` at 550 is only valid while spot is below 550. The UI consumer should use `valid_while` to gray out stale tags between refreshes.

---

## Example strike output

```python
from dataclasses import dataclass

@dataclass
class StrikeHighlight:
    strike: float
    score: float
    tags: list[str]                             # structural tags: "call_wall", "pin_candidate", etc.
    opportunity_tags: list[OpportunityTag]       # actionable edge tags
    reason: str
    distance_from_spot_pct: float
    total_oi: int
    net_gex: float | None
    abs_gex: float | None
    significance_type: str                      # "wall", "pin", "trigger", "magnet", "support", "resistance"
    outside_active_zone: bool                   # True if beyond distance gate (included as wall exception)
```

Example populated output:
```python
StrikeHighlight(
    strike=515.0,
    score=0.87,
    tags=["call_wall", "high_oi", "resistance"],
    opportunity_tags=[
        OpportunityTag(
            tag="breakout_trigger",
            direction="long",
            thesis="Call wall at 515; if spot clears, dealer hedging accelerates upside move",
            conviction=0.72,
            regime_dependency="transition",
            invalidation="Invalidated if gamma flip moves above 515 or total GEX flips strongly positive",
            valid_while="spot < 515",
        ),
        OpportunityTag(
            tag="long_delta_call",
            direction="long",
            thesis="Expansion regime with momentum toward call wall; directional calls benefit",
            conviction=0.61,
            regime_dependency="expansion",
            invalidation="Invalidated if spot reverses below 510 or regime shifts to pinned",
            valid_while="regime == expansion and spot > 510",
        ),
    ],
    reason="Largest call OI concentration, nearest call wall, breakout catalyst if regime shifts to expansion",
    distance_from_spot_pct=0.98,
    total_oi=45200,
    net_gex=-12500.0,
    abs_gex=18700.0,
    significance_type="wall",
    outside_active_zone=False,
)
```

---

# Expiration analysis

## Goal
Highlight the most important dates and **tag each with opportunity labels**, not just nearest expiry.

Each expiration should be ranked based on how much it contributes to current structure and opportunity.

## Why dates matter
The chain can look very different by expiration:
- front expiry may dominate near-term pinning
- next week may dominate breakout structure
- monthly expiry may define larger walls
- event-related expirations may carry elevated IV

---

## Expiration scoring factors

### Structural weight
- total OI
- total GEX
- absolute GEX
- concentration near spot

### Time relevance
- DTE proximity
- front-expiration influence
- event alignment if known

### Vol relevance
- ATM IV
- front/back term structure
- unusual IV for that expiry

### Opportunity relevance
- strategy viability in that expiration
- liquidity quality
- expected move relative to structure

---

## Opportunity tagging for expirations

Expirations also get opportunity tags, though the tag vocabulary is slightly different:

| Tag | When it fires |
|-----|---------------|
| `vol_sale` | This expiration's IV is meaningfully above RV and above the term structure average |
| `vol_buy` | This expiration's IV is compressed relative to RV or the term structure |
| `calendar_front_leg` | Rich front-expiry IV relative to back — natural short leg of a calendar |
| `calendar_back_leg` | Cheap back-expiry IV relative to front — natural long leg of a calendar |
| `pin_expiry` | This expiration dominates pinning structure around spot; expiry gravity expected |
| `event_premium` | Unusual IV elevation for this expiry suggesting an event is priced in |
| `swing_structure` | Best DTE for expressing a directional view given current regime duration expectations |

The same `OpportunityTag` dataclass is used, with thesis, conviction, invalidation, and valid_while.

---

## Example expiration output

```python
from dataclasses import dataclass

@dataclass
class ExpirationHighlight:
    expiration: str
    dte: int
    score: float
    tags: list[str]                             # structural: "front_pin", "event_risk", etc.
    opportunity_tags: list[OpportunityTag]       # actionable edge tags
    reason: str
    total_oi: int
    total_gex: float | None
    atm_iv: float | None
    expected_move_pct: float | None
    relevance_type: str  # "front_pin", "event_risk", "swing_structure", "vol_opportunity"
```

---

# Strategy analysis

This should not start as a trade execution engine. It should start as a **strategy suitability engine**.

## Goal
Given the regime, spot location, vol context, **and opportunity tags**, identify strategies that structurally fit.

Suggested initial strategy set:
- long call
- long put
- call debit spread
- put debit spread
- bull put spread
- bear call spread
- iron condor
- iron fly
- long straddle
- long strangle
- calendar spread
- butterfly
- broken wing butterfly

Start smaller if needed. A strong MVP might only score:
- debit spread
- iron condor
- long straddle
- butterfly
- calendar

---

## Strategy fit dimensions

### Regime fit
Does the strategy fit expected movement behavior?

Examples:
- pinned -> condors, iron flies, butterflies, calendars
- expansion -> long straddles, debit spreads, backspreads
- transition -> defined-risk structures, lower-confidence directional structures
- balanced -> premium-selling or neutral defined-risk setups

### Vol fit
Does the strategy fit the IV environment?

Examples:
- high IV + pinning -> premium selling may fit
- low IV + expansion -> long premium may fit
- rich front IV + event -> calendars may fit

### Risk fit
Does the strategy control the dominant risk well?

Examples:
- unstable regime + naked short premium = poor fit
- defined-risk spread in transition = better fit

### Time fit
Does the selected expiration match the expected timeline?

Examples:
- intraday pinning -> shorter DTE
- swing breakout -> slightly longer DTE
- vol normalization view -> choose expiry carefully to express vega exposure

### Opportunity tag alignment (NEW)
Do the opportunity tags on the suggested strikes/expirations support this strategy?

Examples:
- if top strikes carry `long_gamma_here` and `breakout_trigger`, a long straddle or debit spread should score higher
- if top strikes carry `pin_target` and `short_gamma_here`, an iron condor or butterfly should score higher
- if top expirations carry `vol_sale`, premium-selling strategies should score higher
- if tags conflict (e.g., `long_gamma_here` on strike but `vol_sale` on the expiration), reduce confidence and flag the tension

---

## Strategy output

```python
from dataclasses import dataclass

@dataclass
class StrategySuggestion:
    strategy_name: str
    score: float
    rationale: list[str]
    best_expirations: list[str]
    target_strikes: list[float]
    directional_bias: str  # "bullish", "bearish", "neutral", "non-directional"
    vol_bias: str          # "long_vol", "short_vol", "neutral_vol"
    time_decay_profile: str
    risk_profile: str
    avoid_reasons: list[str]
    supporting_tags: list[str]              # which opportunity tags support this suggestion
    conflicting_tags: list[str]             # which opportunity tags argue against it
    context_limitations: list[str]          # what this suggestion does NOT account for
```

**Context limitations (CRITICAL SAFEGUARD):**
Every strategy suggestion must carry a `context_limitations` field. This module does not know:
- existing positions in the name
- account size or max risk per trade
- whether the trader is already expressing a similar view
- real-time bid/ask slippage

The `context_limitations` field should always include at minimum:
- `"Assumes no existing position in this name"`
- `"Does not account for real-time fill prices or slippage"`

This prevents the output from being mistaken for a trade recommendation.

---

# Scenario analysis

Scenario analysis is essential because regime logic alone is not enough.

For each strategy candidate, run deterministic scenario tests:

## Basic scenarios
- spot unchanged, 1 day passes
- spot +1%
- spot -1%
- spot +2%
- spot -2%
- IV +2 points
- IV -2 points
- combined move + vol expansion
- combined move + vol crush

If your existing code already has pricing/greek models, use those.
If not, start with a simpler approximation and make it explicit.

Scenario outputs should support:
- strategy comparison
- explanation generation
- testing

---

# Output schema

The final engine should produce a single structured output.

Example:

```python
from dataclasses import dataclass

@dataclass
class OptionsAnalysisReport:
    symbol: str
    spot_price: float
    timestamp: str
    regime: str
    regime_confidence: float
    regime_reasoning: list[str]
    data_completeness: DataCompletenessReport    # NEW — always present
    key_levels: dict
    highlighted_strikes: list[StrikeHighlight]   # now includes opportunity_tags
    highlighted_expirations: list[ExpirationHighlight]  # now includes opportunity_tags
    strategy_suggestions: list[StrategySuggestion]
    metrics: dict
    alternate_regimes: list[dict]
```

Possible `key_levels`:
```python
{
    "gamma_flip": 507.5,
    "call_wall": 515.0,
    "put_wall": 500.0,
    "largest_gamma_strike": 510.0
}
```

---

# Example analysis narrative

A useful narrative output might read:

> Current regime: `transition`
> Confidence: 0.71
> Data completeness: 9/11 signals available (missing: iv_rank, rv_20)
>
> Spot is trading close to the gamma flip, with strong nearby concentration at 510 and resistance at 515. Total GEX is near neutral, suggesting market behavior may shift quickly if price breaks above or below the current structure. Front-expiration positioning appears dominant.
>
> Most interesting strikes:
> - 510: largest nearby gamma concentration, likely magnet/pin level → **pin_target** (conviction 0.78, invalidated if spot breaks ±1%)
> - 515: call wall and breakout trigger → **breakout_trigger** (conviction 0.72, invalidated if gamma flip moves above 515) / **long_delta_call** (conviction 0.61, valid while regime = expansion and spot > 510)
> - 500: put wall and downside support → **long_delta_put** (conviction 0.55, invalidated if spot reclaims 508)
>
> Most interesting expirations:
> - 3 DTE: strongest near-term structural influence → **pin_expiry** (conviction 0.81)
> - 10 DTE: best balance of liquidity and directional expression → **swing_structure** (conviction 0.68)
>
> Best-fit strategies:
> - call debit spread if bullish break above 515 (supported by: breakout_trigger, long_delta_call)
> - long straddle if expecting regime transition to expansion (supported by: long_gamma_here)
> - butterfly if expecting continued pin behavior around 510 (supported by: pin_target, short_gamma_here)
>
> Note: These suggestions assume no existing position and do not account for real-time fill prices.
> Note: Vol-fit scoring was degraded — iv_rank and rv_20 were unavailable.

---

# Recommended implementation phases

## Phase 1: Base engine
Deliver:
- input normalization
- **data completeness tracking**
- regime metrics
- regime classifier **with hysteresis**
- strike ranking **with distance gating**
- expiration ranking
- **GEX sign convention tests**
- report schema

Do not include strategy fitting or opportunity tagging yet if speed matters.

## Phase 2: Opportunity tagging
Deliver:
- opportunity tag model and constants
- strike opportunity tagger
- expiration opportunity tagger
- conviction scoring with vol adjustment
- invalidation and valid_while generation
- tag conflict resolution logic
- **tag diversity tests** (ensure tags aren't just regime echoes)

## Phase 3: Strategy engine
Deliver:
- strategy templates
- strategy fit scoring **informed by opportunity tags**
- rationale generation
- risk-profile summaries
- **context_limitations on every suggestion**

## Phase 4: Scenario engine
Deliver:
- scenario definitions
- P&L/Greek scenario logic
- scenario comparisons in report

## Phase 5: Narrative and UX outputs
Deliver:
- human-readable explanations
- rank summaries
- API serializer
- markdown / JSON output modes

---

# Testing strategy

Tests should be a first-class requirement.

## What to test

### 1. Metric calculation tests
Verify:
- distance-to-flip
- distance-to-wall
- concentration scores
- IV-RV spread
- normalization rules
- **all distance metrics are percentage-based**

### 2. Regime classification tests
Given known fixture chains, verify:
- pinned case returns `pinned`
- short gamma unstable case returns `expansion`
- near-zero / near-flip case returns `transition`
- unremarkable case returns `balanced`
- **positive_total_gex + spot_near_dominant_strike = pinned** (GEX sign convention)
- **negative_total_gex + spot_beyond_flip = expansion** (GEX sign convention)

### 3. Regime hysteresis tests
Verify:
- small score changes do not flip the regime when prior regime is provided
- large score changes do flip the regime
- first-run (no prior regime) always picks the highest scorer

### 4. Strike ranking tests
Verify:
- top-ranked strike includes expected wall / cluster
- near-spot important strikes are prioritized correctly
- distant irrelevant strikes are not incorrectly ranked too high
- **distance gate excludes strikes beyond threshold (except walls)**
- **wall exceptions are tagged as outside_active_zone when applicable**

### 5. Opportunity tagging tests
Verify:
- tags are strike-specific, not uniform across all strikes in a regime
- conflicting tags on the same strike are resolved per the regime
- conviction is penalized when vol environment opposes the tag direction
- tags with missing dependencies (e.g., long_gamma_here without gamma_flip) are not emitted
- every emitted tag has a non-empty invalidation and valid_while
- **given a pinned fixture, at least 2 different tag types appear across top 5 strikes**

### 6. Expiration ranking tests
Verify:
- high-structure front expiry is ranked above low-impact expiries
- event-like or high-IV expiries are tagged properly
- low-liquidity expiries can be de-emphasized if desired

### 7. Strategy scoring tests
Verify:
- pinned regime scores condor/butterfly above long straddle
- expansion regime scores long gamma structures above short premium
- low-IV breakout environments favor debit/long-vol structures
- **supporting_tags and conflicting_tags are populated**
- **context_limitations is never empty**

### 8. Output schema tests
Verify:
- final report always contains required fields
- missing optional data does not crash analysis
- `None` handling is consistent
- **data_completeness is always present and accurate**

### 9. Data completeness tests
Verify:
- full data input produces completeness_ratio near 1.0
- input with all optional fields as None produces low ratio and lists degraded analyses
- specific missing fields (e.g., gamma_flip = None) result in specific degraded analyses listed
- engine does not crash on minimal input (only spot + contracts)

### 10. Explanation tests
Verify:
- explanations are generated
- key reasons reflect actual metrics
- narratives remain aligned with regime outputs
- **degraded analyses are mentioned in the narrative when present**

---

# Fixture design

Create synthetic fixtures that are intentionally clear.

## `pinned_chain.json`
Characteristics:
- spot near dominant strike
- positive nearby gamma concentration (NOTE: positive = dealers long gamma = stabilizing)
- strong local OI
- narrow key levels

Expected regime:
- `pinned`

Expected highlighted strikes:
- ATM strike
- nearby walls

Expected opportunity tags:
- `pin_target` on ATM strike
- `short_gamma_here` on high concentration strike

Expected strategies:
- butterfly / iron condor / iron fly score highly

---

## `short_gamma_breakout_chain.json`
Characteristics:
- negative total GEX (NOTE: negative = dealers short gamma = destabilizing)
- spot beyond flip
- weaker pinning concentration
- open path toward next major strike

Expected regime:
- `expansion`

Expected highlighted strikes:
- breakout trigger strike
- next destination strike

Expected opportunity tags:
- `breakout_trigger` on gamma flip strike
- `long_gamma_here` on near-spot strikes
- `long_delta_call` or `long_delta_put` on destination strike

Expected strategies:
- debit spread / long straddle score highly

---

## `balanced_chain.json`
Characteristics:
- no dominating concentration
- moderate structure
- no close flip stress

Expected regime:
- `balanced`

---

## `high_iv_chain.json`
Characteristics:
- elevated ATM IV
- IV significantly above RV
- maybe front-expiration premium

Expected effect:
- strategy scoring should shift away from expensive long-premium structures unless regime is very compelling
- `vol_sale` tags should appear on relevant strikes and expirations
- `long_gamma_here` tags should have reduced conviction due to expensive vol

---

## `partial_data_chain.json` (NEW)
Characteristics:
- spot and contracts present
- gamma_flip = None, total_gex = None, rv_20 = None, iv_rank = None
- some per-contract greeks present, some None

Expected behavior:
- engine does not crash
- regime classification falls back to what it can determine (likely `balanced` with low confidence)
- data_completeness shows low ratio and lists missing fields
- opportunity tags that depend on missing fields are not emitted
- narrative explicitly calls out degraded analysis

---

# Example test names

```python
def test_pinned_regime_when_spot_near_high_gamma_cluster():
    ...

def test_transition_regime_when_spot_near_gamma_flip():
    ...

def test_expansion_regime_when_total_gex_negative_and_spot_beyond_flip():
    ...

def test_regime_hysteresis_prevents_flicker_on_small_change():
    ...

def test_regime_hysteresis_allows_switch_on_large_change():
    ...

def test_strike_ranking_prioritizes_call_wall_near_spot():
    ...

def test_strike_distance_gate_excludes_far_strikes():
    ...

def test_strike_distance_gate_includes_walls_as_exceptions():
    ...

def test_opportunity_tags_are_strike_specific_not_uniform():
    ...

def test_opportunity_tag_conflict_resolved_by_regime():
    ...

def test_opportunity_conviction_penalized_when_vol_opposes():
    ...

def test_opportunity_tag_not_emitted_when_dependency_missing():
    ...

def test_expiration_ranking_favors_front_expiry_with_high_local_structure():
    ...

def test_strategy_scoring_prefers_condor_in_pinned_regime():
    ...

def test_strategy_scoring_prefers_long_gamma_in_expansion_regime():
    ...

def test_strategy_context_limitations_always_populated():
    ...

def test_engine_handles_missing_gamma_flip_without_crashing():
    ...

def test_data_completeness_tracks_missing_fields():
    ...

def test_data_completeness_degrades_narrative():
    ...

def test_gex_sign_convention_positive_means_stabilizing():
    ...
```

---

# Suggested scoring design

Use weighted scoring objects so tuning is easy.

Example:

```python
from dataclasses import dataclass

@dataclass
class ScoreWeights:
    gex_weight: float = 0.25
    oi_weight: float = 0.20
    distance_weight: float = 0.20
    volume_weight: float = 0.10
    concentration_weight: float = 0.15
    regime_relevance_weight: float = 0.10
```

For strategies:

```python
from dataclasses import dataclass

@dataclass
class StrategyScoreWeights:
    regime_fit: float = 0.30
    vol_fit: float = 0.20
    risk_fit: float = 0.15
    time_fit: float = 0.15
    opportunity_tag_alignment: float = 0.20   # NEW — how well do the tags support this strategy?
```

These should live in config and be easy to modify.

---

# Minimum viable regime rules

If you want a simple starting point, begin with these rough rules.

## `pinned`
- spot within X% of dominant strike
- local concentration > threshold
- total GEX positive or stabilizing
- no nearby flip break risk

## `transition`
- spot within Y% of gamma flip
- regime score difference narrow
- local structure mixed

## `expansion`
- total GEX negative
- spot has moved beyond flip / stabilizing zone
- local concentration insufficient to pin

## `balanced`
- fallback when no other state clearly dominates
- **monitor frequency — if balanced > 40%, investigate thresholds or missing data**

This is enough for MVP, then improve with score-based weighting.

---

# "Most interesting strikes and dates" logic

This is one of the most important product goals.

## Interesting strikes
A strike is interesting if it is:
- structurally important
- close enough to matter **(enforced by distance gate)**
- relevant to current regime
- likely to affect price behavior or strategy construction
- **associated with a tradeable thesis (opportunity tag)**

Examples:
- a huge strike 20% away is excluded by the distance gate unless it's a wall
- a strike near flip is very interesting in transition → tagged `breakout_trigger`
- a nearby call wall is interesting in bullish expansion → tagged `long_delta_call`
- the ATM strike with heavy gamma in a pinned regime → tagged `pin_target` + `short_gamma_here`

## Interesting dates
An expiration is interesting if it:
- dominates current structure
- provides the best expression of the regime
- carries unusual IV / event premium
- offers meaningful liquidity and expected move relevance
- **has an actionable opportunity tag (vol_sale, calendar leg, pin_expiry, etc.)**

The key is not "largest always wins."
The key is **market relevance now, with a thesis attached**.

---

# Suggested report sections

Your final report should ideally contain these sections:

## 1. Snapshot
- symbol
- spot
- timestamp
- current regime
- confidence
- **data completeness ratio and missing fields**

## 2. Key levels
- gamma flip
- call wall
- put wall
- nearest dominant strike

## 3. Regime interpretation
- short paragraph explaining behavior expectations
- **note if any signals were unavailable and how that affects confidence**

## 4. Important strikes
- top 5 ranked strikes with tags, **opportunity tags with conviction**, and reasons

## 5. Important expirations
- top 3-5 expirations with reasons and **opportunity tags**

## 6. Strategy fits
- top strategy candidates with rationale
- **supporting and conflicting opportunity tags per strategy**
- **context limitations on every suggestion**

## 7. Risk notes
- what could invalidate the analysis
- what could shift the regime quickly
- **which opportunity tag invalidation conditions are closest to triggering**

## 8. Optional scenarios
- +/- move and IV scenarios

---

# Example pseudo-code for the engine

```python
def analyze_options(
    input_data: OptionsAnalysisInput,
    prior_regime: str | None = None,
) -> OptionsAnalysisReport:
    normalized = normalize_input(input_data)
    
    # Step 1: Assess what we have to work with
    completeness = assess_data_completeness(normalized)

    # Step 2: Compute metrics (each returns None for missing dependencies)
    regime_metrics = compute_regime_metrics(normalized)
    volatility_metrics = compute_volatility_metrics(normalized)

    # Step 3: Classify regime with hysteresis
    regime_result = classify_regime(
        regime_metrics=regime_metrics,
        volatility_metrics=volatility_metrics,
        prior_regime=prior_regime,
        hysteresis_margin=config.REGIME_HYSTERESIS_MARGIN,
        completeness=completeness,
    )

    # Step 4: Rank strikes with distance gating
    strike_highlights = rank_interesting_strikes(
        input_data=normalized,
        regime_result=regime_result,
        distance_gate_pct=config.STRIKE_DISTANCE_GATE_PCT,
    )
    
    # Step 5: Tag strikes with opportunities
    strike_highlights = tag_strike_opportunities(
        strikes=strike_highlights,
        regime_result=regime_result,
        volatility_metrics=volatility_metrics,
        completeness=completeness,
    )

    # Step 6: Rank and tag expirations
    expiration_highlights = rank_interesting_expirations(
        input_data=normalized,
        regime_result=regime_result,
    )
    
    expiration_highlights = tag_expiration_opportunities(
        expirations=expiration_highlights,
        regime_result=regime_result,
        volatility_metrics=volatility_metrics,
        completeness=completeness,
    )

    # Step 7: Score strategies informed by opportunity tags
    strategy_suggestions = score_strategies(
        input_data=normalized,
        regime_result=regime_result,
        strike_highlights=strike_highlights,
        expiration_highlights=expiration_highlights,
        volatility_metrics=volatility_metrics,
    )

    return build_report(
        input_data=normalized,
        regime_result=regime_result,
        strike_highlights=strike_highlights,
        expiration_highlights=expiration_highlights,
        strategy_suggestions=strategy_suggestions,
        completeness=completeness,
        metrics={
            "regime": regime_metrics,
            "volatility": volatility_metrics,
        },
    )
```

---

# Future enhancements

After the initial version is stable, consider adding:

## 1. Regime transition probabilities
Estimate probability of moving from pinned -> transition -> expansion.

## 2. Multi-expiry structure fusion
Weight front expiry vs monthly expiry influence more intelligently.

## 3. Intraday regime updates
Track regime changes throughout the day.

## 4. Vanna/charm overlays
If your data supports it, these can improve transition/exhaustion analysis.

## 5. Historical backtesting
Compare regime labels against realized next-day or next-session behavior.

## 6. Strategy performance by regime
Track which strategies historically fit each regime best.

## 7. Opportunity tag hit rate tracking
Track which tags historically led to profitable outcomes by regime. This is the feedback loop that tunes conviction scores over time.

## 8. Position-aware strategy filtering
Accept optional current positions as input and filter/penalize strategies that duplicate existing exposure.

---

# Suggested MVP acceptance criteria

The feature is ready for first use when:

- it accepts a normalized full chain input
- it returns a valid structured analysis report
- **data completeness is tracked and reported**
- it classifies at least 4 regimes reliably
- **regime hysteresis prevents flickering on small changes**
- it ranks top strikes and expirations with explanations
- **strikes are gated by distance before scoring**
- **opportunity tags are emitted on ranked strikes and expirations**
- **opportunity tags are strike-specific (not uniform regime echoes)**
- **every opportunity tag has conviction, invalidation, and valid_while**
- it scores at least 4-6 strategy templates
- **every strategy suggestion carries context_limitations**
- all core classifiers and rankers have tests
- **GEX sign convention is documented and tested**
- fixture-based tests pass consistently
- missing optional data does not break execution

---

# Final recommendation on implementation focus

Prioritize these in order:

## Highest priority
1. typed input/output schema (including OpportunityTag, DataCompletenessReport)
2. data completeness tracking
3. GEX sign convention documentation and validation
4. regime metrics
5. regime classifier with hysteresis
6. strike ranking with distance gating
7. expiration ranking
8. fixture-based tests (including partial_data_chain)

## Second priority
9. opportunity tagging for strikes
10. opportunity tagging for expirations
11. conviction scoring with vol adjustment
12. tag conflict resolution
13. tag-specific tests

## Third priority
14. strategy fit engine (informed by tags)
15. rationale generation with supporting/conflicting tags
16. context_limitations enforcement
17. scenario analysis

## Fourth priority
18. narrative formatting
19. advanced vol/skew modeling
20. historical validation
21. opportunity tag hit rate tracking

---

# One-line mission statement

`options_analysis` converts a full options chain into a testable, explainable regime-and-strategy analysis report that highlights the most important strikes and expirations, tags each with actionable opportunity theses, and tracks data quality so you know when to trust the output.

---

# Implemented Enhancements

The following enhancements have been implemented based on the expansion plan:

## 1. Pydantic Models (`models.py`)

Typed models now exist at module boundaries for input/output validation:

- `OptionsAnalysisInput` - Input validation with spot_price positivity check
- `OptionsAnalysisOutput` - Complete output schema
- `DataCompletenessReport` - With vol_environment sub-object tracking IV/RV
- `RegimeResult` - Regime classification output
- `TradeSuggestion` - With context_limitations, supporting_tags, conflicting_tags
- `TradeLeg` - Option leg definition
- `ScenarioResult` - Scenario analysis output
- `OpportunityTag` - Tag model with conviction, invalidation, valid_while
- `StrategyFit` - With vol_fit_score, regime_fit_score, supporting/conflicting tags
- `StrikeData`, `ExpirationData` - With structural_tags and opportunity_tags

## 2. Exhaustion Regime (`regime.py`)

Added `REGIME_EXHAUSTION = "exhaustion"` to the regime classification:

- Triggers when spot is far from gamma flip (beyond exhaustion_strike_distance_pct)
- Spot at extreme distance from major structural levels
- Positive GEX with spot far from flip suggests dealer hedging exhaustion risk
- Not yet a dominant regime in MVP but available for scoring

## 3. Expiration Opportunity Tags (`engine.py:_rank_expirations`)

Expirations now receive opportunity tags:

| Tag | Trigger |
|-----|---------|
| `vol_sale` | IV significantly above RV (iv_minus_rv > threshold) |
| `vol_buy` | IV compressed relative to RV (iv_minus_rv < threshold) |
| `calendar_front_leg` | Front expiry IV elevated vs global ATM IV |
| `calendar_back_leg` | Back expiry IV compressed vs global ATM IV |
| `pin_expiry` | Short DTE (<=7) with high abs_gex |
| `swing_structure` | Medium DTE (14-45) for swing trade expression |
| `event_premium` | Expiry IV significantly elevated vs ATM IV |

## 4. IV/RV Integration

Vol environment tracking in completeness report:

- `rv_20` and `iv_rank` tracked as missing signals
- `iv_minus_rv` computed when both are available
- Vol-fit scoring affects strategy selection:
  - High IV vs RV (vol_sale) -> premium selling strategies score higher
  - Low IV vs RV (vol_buy) -> long vol strategies score higher
- `vol_sale_iv_rv_threshold: 0.05` (5 percentage points)
- `vol_buy_iv_rv_threshold: -0.05` (-5 percentage points)

## 5. Expanded Strategy Pool (`engine.py:_score_strategies`)

Now scores 10 strategies with regime_fit + vol_fit:

| Strategy | Best Regimes | Vol Fit Basis |
|----------|-------------|---------------|
| iron_condor | pinned, balanced | High IV vs RV |
| iron_fly | pinned, transition | Neutral |
| debit_call_spread | expansion (neg GEX) | Low IV vs RV |
| debit_put_spread | expansion (neg GEX) | Low IV vs RV |
| long_straddle | transition, expansion | Low IV vs RV |
| long_strangle | transition, expansion | Low IV vs RV |
| calendar_spread | near flip | High IV vs RV |
| butterfly_spread | pinned | High IV vs RV |
| credit_call_spread | balanced, exhaustion | High IV vs RV |
| credit_put_spread | balanced, exhaustion | High IV vs RV |

Each strategy carries:
- `regime_fit_score` (0.0-1.0)
- `vol_fit_score` (0.0-1.0)
- `fit_score` (weighted composite)
- `supporting_tags` (list)
- `conflicting_tags` (list)

## 6. Scenario Engine (`scenarios/`)

New `scenarios/` module with:

- `ScenarioParams` and `ScenarioResult` dataclasses
- `generate_scenarios()` - Produces 11 deterministic scenarios:
  - spot_unchanged (1 day pass)
  - spot_plus_1pct, spot_minus_1pct
  - spot_plus_2pct, spot_minus_2pct
  - iv_up_2pts, iv_down_2pts
  - spot_up_1pct_iv_up_2 (combined)
  - spot_down_1pct_iv_down_2 (combined)
  - spot_up_2pct_iv_up_3 (significant move)
  - spot_down_2pct_iv_up_3 (fear scenario)

Each scenario provides:
- new_spot, new_iv
- price_change, delta_exposure, gamma_exposure, vega_exposure, theta_exposure
- regime_shift detection

## 7. Context Limitations (`trade_suggestion.py`)

Trade suggestions now include `context_limitations`:

```python
DEFAULT_CONTEXT_LIMITATIONS = [
    "Assumes no existing position in this name",
    "Does not account for real-time fill prices or slippage",
    "Does not account for account size or max risk tolerance",
    "Does not account for similar existing positions in the portfolio",
]
```

## 8. Supporting/Conflicting Tags

Trade suggestions and strategy fits include:

- `supporting_tags` - Opportunity tags that support the strategy thesis
- `conflicting_tags` - Opportunity tags that argue against the strategy

Example:
```python
# In pinned regime:
supporting_tags: ["pin_target", "short_gamma"]
conflicting_tags: ["breakout_trigger", "long_gamma_here"]
```

## 9. Test Suite (`tests/`)

Comprehensive test suite with 28 passing tests covering:

### GEX Sign Convention
- `test_positive_gex_means_stabilizing` - GEX constant validation
- `test_positive_total_gex_spot_near_dominant_strike_returns_pinned`
- `test_negative_total_gex_spot_beyond_flip_returns_expansion`

### Regime Hysteresis
- `test_hysteresis_prevents_flicker_on_small_change`
- `test_hysteresis_allows_switch_on_large_change`
- `test_hysteresis_first_run_always_picks_highest_scorer`

### Regime Classification
- `test_pinned_regime_when_spot_near_high_gamma_cluster`
- `test_expansion_regime_when_total_gex_negative_and_spot_beyond_flip`
- `test_balanced_regime_with_moderate_structure`
- `test_missing_gamma_flip_falls_back_to_balanced`

### Strike Ranking
- `test_strike_ranking_prioritizes_nearby_strikes`
- `test_strike_distance_gate_excludes_far_strikes`
- `test_strikes_have_structural_tags`

### Expiration Ranking
- `test_expiration_ranking_returns_results`
- `test_expirations_have_opportunity_tags`
- `test_high_iv_chain_has_vol_sale_tag`

### Data Completeness
- `test_full_data_chain_has_high_completeness`
- `test_partial_data_chain_has_low_completeness`
- `test_data_completeness_tracks_missing_fields`

### Engine Outputs
- `test_engine_returns_all_required_fields`
- `test_strategies_include_vol_fit_scoring`
- `test_trade_suggestion_has_context_limitations`
- `test_trade_suggestion_has_supporting_and_conflicting_tags`

### Balanced Regime Audit
- `test_audit_balanced_regime_frequency_warns_when_threshold_exceeded`
- `test_audit_balanced_regime_frequency_no_warn_when_below_threshold`

### Strategy Scoring
- `test_pinned_regime_prefers_condor_or_fly`
- `test_expansion_regime_prefers_long_gamma_strategies`
- `test_strategy_scoring_has_supporting_and_conflicting_tags`

## Updated File Structure

```
options_analysis/
├── README.md
├── __init__.py
├── config.py          # Added vol thresholds, exhaustion threshold
├── constants.py       # Added exhaustion regime, opportunity tag constants
├── engine.py          # Added vol env tracking, expiration tags, expanded strategies
├── models.py          # NEW: Pydantic models for input/output
├── regime.py          # Added exhaustion regime scoring
├── safeguards.py      # Unchanged
├── trade_suggestion.py # Added context_limitations, supporting/conflicting tags
├── types.py           # Added new fields to TradeSuggestion
├── scenarios/         # NEW
│   ├── __init__.py
│   └── generators.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── fixtures/
    │   ├── balanced_chain.json
    │   ├── high_iv_chain.json
    │   ├── partial_data_chain.json
    │   ├── pinned_chain.json
    │   └── short_gamma_breakout_chain.json
    └── test_engine.py
```

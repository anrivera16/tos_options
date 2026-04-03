# `options_analysis` README

## Purpose

`options_analysis` is a standalone Python feature folder that transforms an already-aggregated full options chain into a structured **regime + strike/date + strategy analysis engine**.

The goal is not to merely display option data. The goal is to answer:

- What is the current **options market regime**?
- Which **strikes** are the most important right now?
- Which **expirations** matter the most?
- What **behavior** is the market structure implying?
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
1. **Regime classification**
2. **Interesting strike selection**
3. **Interesting expiration selection**
4. **Strategy suitability scoring**
5. **Scenario-based analysis**
6. **Final output structure for UI / CLI / API consumption**

---

# Core product definition

`options_analysis` should be a **regime-aware options decision engine**.

It should:
- identify likely pinning / expansion / transition behavior
- rank key strikes and expirations by relevance
- surface strategy ideas matched to the current market structure
- explain why those strikes/dates/strategies matter
- remain fully testable with deterministic inputs

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

## 5. Test every classifier and score path
This system should be stable over time, so tests are not optional.

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
│   └── explanations.py
├── expirations/
│   ├── __init__.py
│   ├── ranking.py
│   ├── term_structure.py
│   ├── weighting.py
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
    │   └── low_iv_chain.json
    ├── test_regime_classifier.py
    ├── test_strike_ranking.py
    ├── test_expiration_ranking.py
    ├── test_strategy_scoring.py
    ├── test_scenarios.py
    ├── test_engine_outputs.py
    └── test_explanations.py
```

---

# Core responsibilities by module

## `engine.py`
Top-level orchestrator.

Responsibilities:
- accept normalized input
- call metric calculators
- call regime classifier
- rank strikes
- rank expirations
- score strategies
- run scenarios
- produce final analysis object

This should be the main entry point for the feature.

---

## `types.py`
Contains data models for:
- input chain objects
- aggregated exposure objects
- regime outputs
- strike ranking outputs
- expiration ranking outputs
- strategy suggestions
- scenario result objects
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

All thresholds should be configurable and testable.

---

## `constants.py`
Static labels and enums:
- regime names
- strategy names
- explanation categories
- risk descriptors

Example:
```python
REGIME_PINNED = "pinned"
REGIME_TRANSITION = "transition"
REGIME_EXPANSION = "expansion"
REGIME_BALANCED = "balanced"
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

## Step 1: Normalize and validate input
Before analysis:
- ensure spot > 0
- ensure strikes are sorted
- ensure expirations have valid DTE
- ensure missing Greeks/IV fields are handled gracefully
- ensure gamma flip and walls can be `None`

This avoids downstream logic becoming messy.

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

This is much more testable than ad hoc branching.

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

# Strike analysis

## Goal
Highlight the most interesting strikes, not just the largest strikes.

Each strike should be ranked by a composite significance score.

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

Suggested scoring components:

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

## Example strike output

```python
from dataclasses import dataclass

@dataclass
class StrikeHighlight:
    strike: float
    score: float
    tags: list[str]
    reason: str
    distance_from_spot_pct: float
    total_oi: int
    net_gex: float | None
    abs_gex: float | None
    significance_type: str  # "wall", "pin", "trigger", "magnet", "support", "resistance"
```

Example tags:
- `[("call_wall", "resistance", "high_oi")]`
- `[("flip_adjacent", "transition_zone")]`
- `[("pin_candidate", "high_gamma_cluster")]`

---

# Expiration analysis

## Goal
Highlight the most important dates, not just nearest expiry.

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

## Example expiration output

```python
from dataclasses import dataclass

@dataclass
class ExpirationHighlight:
    expiration: str
    dte: int
    score: float
    tags: list[str]
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
Given the regime, spot location, and vol context, identify strategies that structurally fit.

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
```

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
    key_levels: dict
    highlighted_strikes: list[StrikeHighlight]
    highlighted_expirations: list[ExpirationHighlight]
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
> Spot is trading close to the gamma flip, with strong nearby concentration at 510 and resistance at 515. Total GEX is near neutral, suggesting market behavior may shift quickly if price breaks above or below the current structure. Front-expiration positioning appears dominant.

> Most interesting strikes:
> - 510: largest nearby gamma concentration, likely magnet/pin level
> - 515: call wall and breakout trigger
> - 500: put wall and downside support candidate

> Most interesting expirations:
> - 3 DTE: strongest near-term structural influence
> - 10 DTE: best balance of liquidity and directional expression

> Best-fit strategies:
> - call debit spread if bullish break above 515
> - long straddle if expecting regime transition to expansion
> - butterfly if expecting continued pin behavior around 510

---

# Recommended implementation phases

## Phase 1: Base engine
Deliver:
- input normalization
- regime metrics
- regime classifier
- strike ranking
- expiration ranking
- report schema

Do not include strategy fitting yet if speed matters.

## Phase 2: Strategy engine
Deliver:
- strategy templates
- strategy fit scoring
- rationale generation
- risk-profile summaries

## Phase 3: Scenario engine
Deliver:
- scenario definitions
- P&L/Greek scenario logic
- scenario comparisons in report

## Phase 4: Narrative and UX outputs
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

### 2. Regime classification tests
Given known fixture chains, verify:
- pinned case returns `pinned`
- short gamma unstable case returns `expansion`
- near-zero / near-flip case returns `transition`
- unremarkable case returns `balanced`

### 3. Strike ranking tests
Verify:
- top-ranked strike includes expected wall / cluster
- near-spot important strikes are prioritized correctly
- distant irrelevant strikes are not incorrectly ranked too high

### 4. Expiration ranking tests
Verify:
- high-structure front expiry is ranked above low-impact expiries
- event-like or high-IV expiries are tagged properly
- low-liquidity expiries can be de-emphasized if desired

### 5. Strategy scoring tests
Verify:
- pinned regime scores condor/butterfly above long straddle
- expansion regime scores long gamma structures above short premium
- low-IV breakout environments favor debit/long-vol structures

### 6. Output schema tests
Verify:
- final report always contains required fields
- missing optional data does not crash analysis
- `None` handling is consistent

### 7. Explanation tests
Verify:
- explanations are generated
- key reasons reflect actual metrics
- narratives remain aligned with regime outputs

---

# Fixture design

Create synthetic fixtures that are intentionally clear.

## `pinned_chain.json`
Characteristics:
- spot near dominant strike
- positive nearby gamma concentration
- strong local OI
- narrow key levels

Expected regime:
- `pinned`

Expected highlighted strikes:
- ATM strike
- nearby walls

Expected strategies:
- butterfly / iron condor / iron fly score highly

---

## `short_gamma_breakout_chain.json`
Characteristics:
- negative total GEX
- spot beyond flip
- weaker pinning concentration
- open path toward next major strike

Expected regime:
- `expansion`

Expected highlighted strikes:
- breakout trigger strike
- next destination strike

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

---

# Example test names

```python
def test_pinned_regime_when_spot_near_high_gamma_cluster():
    ...

def test_transition_regime_when_spot_near_gamma_flip():
    ...

def test_expansion_regime_when_total_gex_negative_and_spot_beyond_flip():
    ...

def test_strike_ranking_prioritizes_call_wall_near_spot():
    ...

def test_expiration_ranking_favors_front_expiry_with_high_local_structure():
    ...

def test_strategy_scoring_prefers_condor_in_pinned_regime():
    ...

def test_strategy_scoring_prefers_long_gamma_in_expansion_regime():
    ...

def test_engine_handles_missing_gamma_flip_without_crashing():
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
    regime_fit: float = 0.40
    vol_fit: float = 0.25
    risk_fit: float = 0.20
    time_fit: float = 0.15
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

This is enough for MVP, then improve with score-based weighting.

---

# "Most interesting strikes and dates" logic

This is one of the most important product goals.

## Interesting strikes
A strike is interesting if it is:
- structurally important
- close enough to matter
- relevant to current regime
- likely to affect price behavior or strategy construction

Examples:
- a huge strike 20% away may be less interesting than a slightly smaller but near-spot strike
- a strike near flip is very interesting in transition
- a nearby call wall is interesting in bullish expansion

## Interesting dates
An expiration is interesting if it:
- dominates current structure
- provides the best expression of the regime
- carries unusual IV / event premium
- offers meaningful liquidity and expected move relevance

The key is not "largest always wins."
The key is **market relevance now**.

---

# Suggested report sections

Your final report should ideally contain these sections:

## 1. Snapshot
- symbol
- spot
- timestamp
- current regime
- confidence

## 2. Key levels
- gamma flip
- call wall
- put wall
- nearest dominant strike

## 3. Regime interpretation
- short paragraph explaining behavior expectations

## 4. Important strikes
- top 5 ranked strikes with tags and reasons

## 5. Important expirations
- top 3-5 expirations with reasons

## 6. Strategy fits
- top strategy candidates with rationale

## 7. Risk notes
- what could invalidate the analysis
- what could shift the regime quickly

## 8. Optional scenarios
- +/- move and IV scenarios

---

# Example pseudo-code for the engine

```python
def analyze_options(input_data: OptionsAnalysisInput) -> OptionsAnalysisReport:
    normalized = normalize_input(input_data)

    regime_metrics = compute_regime_metrics(normalized)
    volatility_metrics = compute_volatility_metrics(normalized)

    regime_result = classify_regime(
        regime_metrics=regime_metrics,
        volatility_metrics=volatility_metrics
    )

    strike_highlights = rank_interesting_strikes(
        input_data=normalized,
        regime_result=regime_result
    )

    expiration_highlights = rank_interesting_expirations(
        input_data=normalized,
        regime_result=regime_result
    )

    strategy_suggestions = score_strategies(
        input_data=normalized,
        regime_result=regime_result,
        strike_highlights=strike_highlights,
        expiration_highlights=expiration_highlights,
        volatility_metrics=volatility_metrics
    )

    return build_report(
        input_data=normalized,
        regime_result=regime_result,
        strike_highlights=strike_highlights,
        expiration_highlights=expiration_highlights,
        strategy_suggestions=strategy_suggestions,
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

---

# Suggested MVP acceptance criteria

The feature is ready for first use when:

- it accepts a normalized full chain input
- it returns a valid structured analysis report
- it classifies at least 4 regimes reliably
- it ranks top strikes and expirations with explanations
- it scores at least 4-6 strategy templates
- all core classifiers and rankers have tests
- fixture-based tests pass consistently
- missing optional data does not break execution

---

# Final recommendation on implementation focus

Prioritize these in order:

## Highest priority
1. typed input/output schema
2. regime metrics
3. regime classifier
4. strike ranking
5. expiration ranking
6. fixture-based tests

## Second priority
7. strategy fit engine
8. rationale generation
9. scenario analysis

## Third priority
10. narrative formatting
11. advanced vol/skew modeling
12. historical validation

---

# One-line mission statement

`options_analysis` converts a full options chain into a testable, explainable regime-and-strategy analysis report that highlights the most important strikes, expirations, and structurally appropriate option setups.

# Polymarket Sports Hedge Research

## Project overview

This project began with an observation from the 2026 FIFA World Cup markets.
After a team won a match, its probability of winning the tournament did not
always move by the amount implied by its pre-match win probability. The
game-winner and tournament-winner markets appeared to be pricing related
events differently.

The research question was whether that mismatch could support a repeatable
dynamic hedge. The proposed trade combines:

1. A position on a team winning its next match, series, or advancement event.
2. A position on the same team **not** winning the championship.

If the team loses the triggering event, the championship-loss position protects
the trade. If the team wins, both positions are closed after the championship
market reprices. The trade is profitable when the championship probability
rises less than the move implied by the trigger market.

The project expanded this idea beyond FIFA to NBA, NHL, MLB, NFL, League of
Legends Worlds, men's Wimbledon, and men's UEFA Champions League markets. It
now includes a shared data-ingestion pipeline, an event-driven backtesting
engine, rule-based strategies, and ridge-regression experiments.

This is an exploratory quant-research project, not a live trading system.

## Research workflow

1. **Define the matches to collect.** Text files in `data/raw/` list each
   matchup, its kickoff time, and the post-event cutoff time. For example,
   `NHL_2025.txt` tells the ingestion program which NHL playoff series to find
   and when prices should be sampled.
2. **Find the corresponding Polymarket markets.** The ingestion program uses
   the configured event tag and Gamma API to find each match or series market
   and the related championship market. `data_ingestion/aliases.py` handles
   differences between fixture names and Polymarket names.
3. **Collect historical prices.** After identifying the correct market tokens,
   the program requests their historical prices from the CLOB API at the
   fixture's starting and ending times.
4. **Create a standardized dataset.** The collected values are written to a
   CSV in `data/match_data/`. Every team-side row contains the starting and
   ending trigger price and championship-loss price required by the strategy.
5. **Run the simulated hedge.** The strategy chooses qualifying rows, sizes the
   trigger and championship-loss positions, and sends the simulated orders to
   the backtesting engine.
6. **Evaluate strategies and models.** The project compares probability
   filters and regression models using P&L, return per hedge, drawdown, error
   metrics, and cross-sport performance.

## Collecting and preparing the data

Fixture schedules in [`data/raw/`](data/raw/) define the matchups and time
windows to collect. Each file contains the teams, event date, and the cutoff
used to sample the relevant Polymarket prices.

The shared ingestion package is under [`data_ingestion/`](data_ingestion/):

- [`aliases.py`](data_ingestion/aliases.py) centralizes team names, competition
  names, and Polymarket naming differences.
- [`polymarket.py`](data_ingestion/polymarket.py) contains the general event,
  market, token, and price-history collection logic.
- [`__main__.py`](data_ingestion/__main__.py) provides the command-line runner.

The Gamma API is used to find the configured sporting events and identify the
correct markets and tokens. The CLOB API supplies historical token prices. The
code then matches those markets to the fixture file using the centralized
aliases rather than embedding separate discovery logic for every sport.

For example, this command regenerates the FIFA World Cup match dataset using
the existing `World Cup` ingestion configuration:

```powershell
.\.venv\Scripts\python.exe -m data_ingestion `
  data/raw/World_Cup_2026.txt `
  --event-tag "World Cup" `
  --out data/match_data/polymarket_match_data.csv
```

The generated files are stored in [`data/match_data/`](data/match_data/). Each
team-side row contains:

- The team and matchup.
- The trigger market's start and end prices.
- The championship-loss market's start and end prices.
- The trigger and exit timestamps.

[`sport_strategy_config.py`](backtesting/sport_strategy_config.py) maps each
dataset to the correct columns. This allows one ingestion workflow and one
strategy implementation to support every configured sport.

The current dataset contains 10 sport-season configurations, 149 matchups, and
298 team-side observations:

```text
fifa
lol_worlds_2025
mlb
nba
nba_2025
nfl
nhl
nhl_2025
ucl_2026
wimbledon_2026
```

## How the dynamic hedge is backtested

[`paired_hedge_strategy.py`](backtesting/paired_hedge_strategy.py) selects and
sizes the two positions. [`engine.py`](backtesting/engine.py) handles cash,
positions, orders, trades, fees, equity, realized P&L, and drawdown.

Let:

- `p` be the team's starting probability of winning the trigger event.
- `l` be the starting price of the championship-loss token.
- `c = 1 - l` be the implied starting championship-win probability.
- `S` be the total stake assigned to one hedge.

With zero fees, the strategy purchases `S` shares of the championship-loss
token. That costs `S × l`. The remaining budget, `S × c`, purchases the trigger
token, giving a trigger quantity of:

```text
trigger quantity = S × c / p
```

The two opening positions therefore cost exactly `S`. If the team loses the
triggering event and the championship-loss token resolves to \$1, that leg
returns the original stake. If the team wins, the engine closes both legs at
their recorded post-event prices and measures whether the championship market
repriced by more or less than the trigger market implied.

For every selected hedge, the engine:

1. Loads the two start prices at the event time.
2. Validates available cash and position inventory.
3. Executes both opening orders and records their fees and cost basis.
4. Updates both instruments to their recorded end prices.
5. Sells both positions and records the resulting P&L.
6. Updates portfolio equity, drawdown, and aggregate statistics.

The backtest supports a proportional `--fee-rate`, but the headline results
below use a \$100 stake per hedge and a zero fee rate.

## Research progression

### 1. Middle-teams probability filter

The first practical idea was that bettors might overreact to a dominant-looking
result without considering how likely that result already was. Oklahoma City's
series against Phoenix is a useful example. The Thunder began with a 97.45%
probability of winning the series, so advancing was already almost fully
expected. After Oklahoma City won, however, its implied championship
probability still increased from 47.5% to 51.5%.

The trigger price implied a post-series championship probability of only about
48.7% (`47.5% / 97.45%`). The market instead moved to 51.5%, meaning the
championship price increased more than this simple conditional relationship
predicted. That is unfavorable for the championship-loss side of the hedge and
illustrates why overwhelming favorites can be poor candidates. Very weak teams
can create the opposite problem through enormous surprise-driven adjustments,
thin championship markets, and unstable probability ratios. We therefore
focused on teams in the middle of both probability ranges.

[`middle_teams_strategy.py`](backtesting/middle_teams_strategy.py) therefore
uses a fixed probability window:

- Trigger-event win probability between 30% and 80%.
- Championship-win probability between 10% and 20%.

Across the available datasets, this filter selected 34 team-side hedges. At
\$100 per hedge and zero fees, it produced **\$50.81 P&L**, or a **1.49% gross
return on deployed stake**. This was the strongest simple strategy result, but
34 observations are far too few to establish that the edge will persist.

The broader threshold sweep also tested every whole-percent lower trigger
threshold from 0% through 100%. The best pooled in-sample threshold was 23%,
which selected 258 hedges and produced **\$124.80 P&L on \$25,800 deployed
stake**, a **0.48% gross return**. Because the same data was used to choose and
evaluate that threshold, this is an optimized in-sample result.

### 2. FIFA-only regression models

The next step was to determine whether we could train a model using our
original FIFA dataset and then generalize that model to other sports. The FIFA
experiment used 64 team-side rows from 32 matches and compared six feature
equations against four prediction targets, for 24 ridge-regression models in
total.

The tested features were combinations of:

- `p`: starting trigger-event win probability.
- `c`: starting championship-win probability.
- `c/p` or `p/c`: the relationship between the two markets.
- `log(p/c)`: a less skewed version of that relationship.
- `p²`: a nonlinear term allowing middle probabilities to behave differently
  from probabilities near 0% or 100%.

The targets included engine P&L per \$100, two strategy-EV definitions, and
`strategy_ev_relative`, which measures the championship repricing error
relative to the movement predicted by the trigger market.

The default FIFA equation was:

```text
prediction = beta_0 + beta_1 p + beta_2 c + beta_3(c/p)
             + beta_4 log(p/c) + beta_5 p²
```

It achieved an in-sample FIFA R² of approximately **0.344**, but its combined
external R² on the other sports was **-0.136**. It selected 212 of 234 external
team-side hedges and produced **\$60.37 P&L**, or **\$0.285 per selected hedge**.
Simply taking all 234 external hedges produced **\$69.25**, or **\$0.296 per
hedge**. Every tested FIFA-trained model had negative external R², so FIFA by
itself did not provide a reliable cross-sport prediction model.

Possible explanations include the small FIFA sample, dependence between the
two team rows from each matchup, sport-specific market behavior, and FIFA being
an unusual tournament rather than a representative training universe.

The FIFA model files and results are under
[`backtesting/experiments/fifa_model/`](backtesting/experiments/fifa_model/).

### 3. Multi-sport regression model

The final experiment increased the diversity of the training data. It trained
on:

- UCL 2026.
- Men's Wimbledon 2026.
- NHL 2026.
- NHL 2025.

This produced 124 training rows from 62 matchups. The fixed model uses `p` and
`p²` to predict `strategy_ev_relative`:

```text
prediction = beta_0 + beta_1 p + beta_2 p²
```

It was then evaluated, without refitting, on FIFA, LoL Worlds 2025, MLB, NBA
2026, NBA 2025, and NFL. The evaluation set contained 174 team-side rows from
87 matchups.

The model selected 89 of those 174 rows and produced **\$57.28 P&L on \$8,900
deployed stake**, or **\$0.644 per selected hedge** and a **0.64% gross return**.
Taking all 174 evaluation rows produced **\$25.83 P&L**, or **\$0.148 per hedge**.

This economic selection result was better than the all-hedge baseline, but the
model's external R² was **-2.159**. In other words, the selected subset made
more money in this sample even though the model was poor at predicting the
exact target values. The relative-EV target is also sensitive to observations
whose predicted championship movement is close to zero. The result is
promising enough to investigate, but it is not yet statistically robust.

The fixed runner and output are under
[`backtesting/experiments/multi_sport_model/`](backtesting/experiments/multi_sport_model/).

## Results summary

All values below assume \$100 per selected hedge and zero fees.

| Experiment | Selected rows | Deployed stake | Total P&L | P&L per hedge | Gross return |
|---|---:|---:|---:|---:|---:|
| Middle teams: 30%-80% trigger, 10%-20% title | 34 | \$3,400 | +\$50.81 | +\$1.49 | +1.49% |
| Best pooled threshold: 23% | 258 | \$25,800 | +\$124.80 | +\$0.48 | +0.48% |
| FIFA default model on other sports | 212 | \$21,200 | +\$60.37 | +\$0.285 | +0.28% |
| FIFA external all-hedge baseline | 234 | \$23,400 | +\$69.25 | +\$0.296 | +0.30% |
| Multi-sport `p + p²` model | 89 | \$8,900 | +\$57.28 | +\$0.644 | +0.64% |
| Multi-sport evaluation all-hedge baseline | 174 | \$17,400 | +\$25.83 | +\$0.148 | +0.15% |

These results should not be compared as independent trials. The experiments
reuse markets, team rows within a matchup are dependent, and several rules were
chosen after observing the available data.

## Conclusions

The current evidence supports four conclusions:

1. The mismatch between trigger-event and championship probabilities is a
   measurable research signal and can be expressed as a defined paired hedge.
2. A simple middle-probability filter performed better than trading every
   available team, but its sample contains only 34 observations.
3. Models trained only on FIFA did not generalize successfully to the other
   sports. Their external R² values were negative, and the default model did
   not outperform the all-hedge average P&L.
4. Training the `p + p²` model on UCL, Wimbledon, and two NHL seasons produced
   a better held-out economic selection result, but the negative external R²,
   limited data, and target instability prevent a strong profitability claim.

The project therefore demonstrates a complete research workflow and a
promising hypothesis, not a proven production strategy. The most important
next step is collecting a larger chronological dataset and reserving a final
period that is never used for strategy or model selection.

## Limitations

- Historical order-book depth is not reconstructed, so the backtest cannot
  determine how much size was available at the sampled price.
- Bid/ask spreads, slippage, partial fills, rejected orders, and fill
  probability are not modeled. A real order might not fill or might require
  paying through the spread.
- The reported results use zero fees. Real fees and execution costs could
  eliminate an edge measured in fractions of a percent.
- The stored price point may be stale relative to the intended entry or exit
  time, particularly in thin championship markets.
- Some championship-market exits use the latest CLOB observation at or before
  the configured cutoff rather than a guaranteed immediately executable quote.

Before live or paper trading, the strategy needs historical spreads and depth,
timestamped executable quotes, realistic order simulation, position-size and
risk limits, a chronological bankroll, and a genuinely untouched test set.

## Running the project

Python 3.10 or newer is required. No third-party Python packages are currently
needed.

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Run the middle-teams strategy:

```powershell
python -m backtesting.middle_teams_strategy nba_2025 `
  --stake 100 `
  --initial-cash 1000 `
  --fee-rate 0
```

Run the configurable paired hedge:

```powershell
python -m backtesting.paired_hedge_strategy nba_2025 `
  --trigger-min 0.30 `
  --trigger-max 0.80 `
  --championship-win-min 0.10 `
  --championship-win-max 0.20 `
  --stake 100 `
  --initial-cash 1000 `
  --fee-rate 0
```

Train one FIFA model and export row-level predictions:

```powershell
python -m backtesting.experiments.fifa_model.train_hedge_model `
  --feature-set p_c_c_over_p_log_p_over_c_p2 `
  --target strategy_ev_relative `
  --out backtesting/experiments/fifa_model/fifa_ridge_model_predictions.csv
```

Compare all FIFA-trained feature and target combinations:

```powershell
python -m backtesting.experiments.fifa_model.compare_hedge_models
```

Run the fixed UCL/Wimbledon/NHL model:

```powershell
python -m backtesting.experiments.multi_sport_model.train_multi_sport_model
```

Run a threshold sweep:

```powershell
python -m backtesting.threshold_comparison nba_2025 `
  --stake 100 `
  --fee-rate 0 `
  --out data/analysis/nba_2025_threshold_comparison.csv
```

## Repository layout

```text
README.md                          Project documentation
data/raw/                          Fixture schedules
data/match_data/                   Generated historical market CSVs
data/analysis/                     Threshold and exploratory outputs
data_ingestion/                    Shared Polymarket ingestion and aliases
backtesting/engine.py              Event-driven portfolio and execution engine
backtesting/paired_hedge_strategy.py  Shared hedge selection and sizing
backtesting/middle_teams_strategy.py  Fixed middle-probability strategy
backtesting/experiments/fifa_model/   FIFA training and comparisons
backtesting/experiments/multi_sport_model/  UCL/Wimbledon/NHL model
analysis/                           Analysis utilities
tests/                              Automated test suite
```

## Testing

The repository contains 79 tests covering engine accounting, CSV parsing,
ingestion and aliases, market resolution, sport configuration, strategy
selection and sizing, threshold sweeps, feature construction, model fitting,
and comparison outputs.

```powershell
python -m unittest discover -s tests -v
```

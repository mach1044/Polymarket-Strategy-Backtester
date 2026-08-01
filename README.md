# Polymarket Sports Research and Backtesting

A configuration-driven Python project for collecting historical Polymarket
sports prices, normalizing team and event names, and backtesting related
binary-contract strategies across multiple competitions. The repository
currently contains 10 sport-season configurations, 149 historical matchups,
and 298 team-side observations.

This is an exploratory research system, not a live trading system. Reported
results are in-sample and do not yet model historical order-book depth,
bid/ask spreads, slippage, fill probability, or position-size capacity.

## What the project does

```text
Fixture schedules
       |
       v
Shared Polymarket ingestion + aliases
       |
       v
Normalized match-price CSVs
       |
       v
Shared strategies -> BacktestEngine
       |
       v
P&L, risk metrics, threshold sweeps, and analysis CSVs
```

The main components are:

- A shared ingestion program using Polymarket's Gamma and CLOB APIs.
- Centralized aliases and market definitions instead of sport-specific
  ingestion programs.
- An event-driven backtesting engine that owns cash, positions, orders, fees,
  realized P&L, equity, and drawdown accounting.
- Shared sport configuration, so one strategy implementation works with every
  supported dataset.
- Automated threshold analysis and pooled multi-sport reporting.
- A standard-library-only test suite with 71 tests.

## Repository layout

```text
README.md              Main project documentation
data/raw/              Fixture schedules used as ingestion inputs
data/match_data/       Generated historical Polymarket price CSVs
data/analysis/         Generated backtest and exploration outputs
data_ingestion/        Shared ingestion program and alias configuration
backtesting/           Engine, strategies, sport config, and CSV adapter
analysis/              Exploratory analysis and result-combining utilities
tests/                 Automated unit and integration-style tests
```

The main README belongs here at the repository root. The
[backtesting README](backtesting/README.md) provides additional implementation
and dataset details.

## Requirements

- Python 3.10 or newer
- Internet access only when regenerating data from Polymarket
- No third-party Python packages are currently required

Run all commands from the repository root. Creating a virtual environment is
recommended:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

## Quick start

Run the full test suite:

```powershell
python -m unittest discover -s tests -v
```

Run the dedicated middle-teams strategy on NBA 2025:

```powershell
python -m backtesting.middle_teams_strategy nba_2025 `
  --stake 100 `
  --initial-cash 1000 `
  --fee-rate 0
```

Run the configurable paired-hedge strategy:

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

## Strategies

### Middle teams

[middle_teams_strategy.py](backtesting/middle_teams_strategy.py) is a named,
shared strategy with fixed selection rules:

- The team's match, series, or advancement token starts between 30% and 80%.
- Its implied championship-win price starts between 10% and 20%.
- Both bounds are inclusive.

The input CSV stores the complementary championship-loss token, so the implied
championship-win price is calculated as:

```text
championship win = 1 - championship loss
```

For each qualifying team, the requested stake is divided between its trigger
token and championship-loss token. The loss leg is sized to recover the stake
if the team fails in the triggering event; the remaining budget purchases the
trigger leg.

### Configurable paired hedge

[paired_hedge_strategy.py](backtesting/paired_hedge_strategy.py) contains the
shared selection, sizing, and execution implementation. It supports a lower
trigger threshold, an optional trigger maximum, an implied championship-win
range, stake size, starting cash, and proportional fees.

The older `--threshold` option remains an alias for `--trigger-min`, so existing
commands and the threshold sweep remain compatible.

### Threshold comparison

[threshold_comparison.py](backtesting/threshold_comparison.py) runs the paired
hedge at every whole-percent lower trigger threshold from 0% through 100%:

```powershell
python -m backtesting.threshold_comparison nba_2025 `
  --stake 100 `
  --fee-rate 0 `
  --out data/analysis/nba_2025_threshold_comparison.csv
```

It reports qualifying hedges, trades, total P&L, P&L per hedge, return on
deployed stake, and maximum drawdown. The PowerShell utility
[combine_threshold_results.ps1](analysis/combine_threshold_results.ps1)
combines the ten individual sweeps into long-form and pooled analysis files.

## Current datasets

The shared strategy configuration accepts these keys:

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

Together, the current CSVs contain:

- 149 matchups
- 298 team-side observations
- FIFA World Cup, NBA, NHL, MLB, NFL, League of Legends Worlds, men's
  Wimbledon, and men's UEFA Champions League data

Several datasets are availability-screened pilots rather than complete
historical universes. See [backtesting/README.md](backtesting/README.md) for
specific exclusions and fixture notes.

## Current results

The following results use `$100` per qualifying hedge and a zero fee rate:

| Experiment | Hedges | Deployed stake | Total P&L | Gross stake return |
|---|---:|---:|---:|---:|
| Middle teams: 30%-80% trigger, 10%-20% title | 34 | $3,400 | +$50.81 | +1.49% |
| Best pooled threshold by in-sample total P&L: 23% | 258 | $25,800 | +$124.80 | +0.48% |

These are descriptive backtest results, not evidence of a tradeable edge. The
23% threshold was selected from the same 101 thresholds being evaluated. The
middle-teams result contains only 34 qualifying observations. Team rows from
the same matchup, repeated teams, playoff rounds, and sport seasons are also
correlated rather than independent samples.

Generated analysis files include:

- [Combined threshold sweep](data/analysis/combined_threshold_comparison.csv)
- [All individual threshold sweeps](data/analysis/all_sports_threshold_comparison.csv)
- [Best threshold by sport](data/analysis/threshold_comparison_summary.csv)

## Data ingestion

Fixture files under `data/raw/` define the events and timestamps to collect.
Sport and naming differences live in
[aliases.py](data_ingestion/aliases.py), while
[polymarket.py](data_ingestion/polymarket.py) contains the shared ingestion
logic.

Example:

```powershell
python -m data_ingestion data/raw/NBA_2025.txt `
  --event-tag "NBA Playoffs" `
  --out data/match_data/nba_2025_match_data.csv
```

The workflow for adding data is:

1. Add or update a fixture schedule in `data/raw/`.
2. Add genuinely necessary naming aliases or market metadata in
   `data_ingestion/aliases.py`.
3. Run the shared ingestion package with the appropriate Polymarket event tag.
4. Add one entry to `backtesting/sport_strategy_config.py` if the dataset is a
   new backtesting configuration.
5. Run an existing shared strategy; no sport-specific strategy copy is needed.

## Testing

The 71 automated tests cover:

- Engine cash, inventory, fee, trade, liquidation, and P&L accounting
- CSV parsing and complementary-token accounting
- Alias construction and file-driven ingestion
- Polymarket event and token resolution behavior
- Shared sport configuration
- Paired-hedge selection and sizing
- Middle-teams range boundaries and CLI behavior
- Threshold sweep calculations and CSV output

Run them with:

```powershell
python -m unittest discover -s tests -v
```

## Important limitations

- Historical bid/ask spreads and order-book depth are not reconstructed.
- Slippage, partial fills, fill probability, and market capacity are not
  modeled.
- `fee_rate` is a generic proportional fee, not a reconstruction of every
  market's historical fee schedule.
- The stored price history does not preserve the exact source timestamp or
  quote age for every sampled point.
- Championship-loss exits use the latest available CLOB history point at or
  before the configured post-result cutoff and may be stale.
- Result-token end values use official binary resolution, while a real trader
  may have faced settlement delays or different exit liquidity.
- Dataset availability screening can introduce selection bias.
- Threshold selection and the reported results are in-sample; there is no
  locked walk-forward or untouched holdout test yet.
- The pooled report adds independently run sport results. It is not a single
  shared-bankroll portfolio and does not report a valid combined drawdown.

Before treating the strategy as executable, the project needs timestamped
quotes, historical spread/depth or trade-size evidence, a realistic execution
model, one chronological bankroll, and out-of-sample validation.

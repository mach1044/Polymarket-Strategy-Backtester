# Backtesting

This package separates three responsibilities:

1. `data_ingestion/` obtains historical market prices.
2. A strategy decides which orders to submit.
3. `BacktestEngine` executes those orders and owns portfolio accounting.

The engine currently supports long-only binary-token positions, cash and
starting inventory, chronological price updates, buy/sell orders, configurable
proportional fees, average-cost accounting, liquidation, and portfolio stats.
It intentionally does not contain a strategy.

## CSV accounting check

Run the engine against the current ingestion output:

```powershell
.\.venv\Scripts\python.exe -m backtesting.smoke_test
```

The check buys one share of both game-winner outcomes at kickoff and sells both
at the recorded end time. This is not a trading strategy. The two complementary
tokens should cost about `$1` and return about `$1`, so a zero-fee run should
finish close to flat with no remaining inventory.

Future strategy files can consume the same timestamped price events and submit
`Order` objects to the engine. Order-book fills, bid/ask spreads, slippage, and
Polymarket's market-specific fee formula should be added before treating a
simulation as executable P&L.

## Paired hedge strategy

`paired_hedge_strategy.py` contains the shared calculation and execution code.
Every supported sport uses that same strategy. The small differences between
sports—the input CSV, market column names, instrument namespace, and display
labels—live in `sport_strategy_config.py`.

At the default 70% threshold, each qualifying team gets a `$100` position split
between its series-winner token and championship-loss token. The quantities are
chosen so the championship-loss payout recovers the full stake if the team
loses its series. Both legs are sold at the recorded series end.

Choose the sport with one command:

```powershell
.\.venv\Scripts\python.exe -m backtesting.paired_hedge_strategy nhl
```

Available sport keys are `fifa`, `nba`, `nba_2025`, `nhl`, `nhl_2025`, `mlb`,
`nfl`, `lol_worlds_2025`, `wimbledon_2026`, and `ucl_2026`. You can optionally pass a
CSV path after the sport key:

```powershell
.\.venv\Scripts\python.exe -m backtesting.paired_hedge_strategy nba custom.csv
```

The runner also accepts `--threshold`, `--stake`, `--initial-cash`, and
`--fee-rate`. To add another sport that uses this strategy, add one entry to
`sport_strategy_config.py`; no new strategy module is needed.

The shared strategy can also select an inclusive probability window. For
example, this selects teams priced at 30%-50% to win their match or series and
10%-15% to win the championship:

```powershell
.\.venv\Scripts\python.exe -m backtesting.paired_hedge_strategy nba_2025 `
  --trigger-min 0.30 `
  --trigger-max 0.50 `
  --championship-win-min 0.10 `
  --championship-win-max 0.15 `
  --stake 100
```

The CSV stores the complementary championship-loss price, so championship win
probability is calculated as `1 - championship_loss_start`. Omitting the new
maximum and championship-range options preserves the original threshold-only
behavior.

## Middle teams strategy

`middle_teams_strategy.py` is the dedicated shared strategy for the selected
30%-80% match/series-win and 10%-20% championship-win window. Choose only the
sport and execution settings; the probability ranges are fixed in the file:

```powershell
.\.venv\Scripts\python.exe -m backtesting.middle_teams_strategy nba_2025 `
  --stake 100 `
  --initial-cash 1000 `
  --fee-rate 0
```

It calls the same centralized paired-hedge implementation and sport
configuration as the other runner, so it does not duplicate execution or
sport-specific logic.

## Added historical datasets

The additional price-complete datasets use pre-final elimination events only:

- NBA 2025: 14 series / 28 team rows.
- NHL 2025: 14 series / 28 team rows.
- Men's Wimbledon 2026: 21 matches / 42 player rows.
- LoL Worlds 2025: 6 knockout series / 12 team rows.
- Men's UEFA Champions League 2025-26: 13 ties / 26 team rows.

The Wimbledon file is an availability-screened pilot, not the complete draw.
Dimitrov–Fery was excluded because one outright hedge token had no trade until
after the match. Galatasaray–Liverpool was similarly excluded from the
Champions League file because one advancement token had no kickoff trade.

Regenerate the CSVs with the shared ingestion program:

```powershell
.\.venv\Scripts\python.exe -m data_ingestion data/raw/NBA_2025.txt --event-tag "NBA Playoffs" --out data/match_data/nba_2025_match_data.csv
.\.venv\Scripts\python.exe -m data_ingestion data/raw/NHL_2025.txt --event-tag NHL --out data/match_data/nhl_2025_match_data.csv
.\.venv\Scripts\python.exe -m data_ingestion data/raw/Wimbledon_2026_Men.txt --event-tag Wimbledon --out data/match_data/wimbledon_2026_men_match_data.csv
.\.venv\Scripts\python.exe -m data_ingestion data/raw/LoL_Worlds_2025.txt --event-tag "league of legends" --out data/match_data/lol_worlds_2025_match_data.csv
.\.venv\Scripts\python.exe -m data_ingestion data/raw/UCL_2026.txt --event-tag "Champions League" --out data/match_data/ucl_2026_match_data.csv
```

Result-market end columns (`game_winner_end` and `series_winner_end`) use the
official resolved 0/1 payout. Other end columns use the latest CLOB trade at or
before 15 minutes after the recorded fixture result, and `end_edt` records that
post-result exit time. The CSV does not preserve the source trade's exact
timestamp or include volume, order-book depth, bid/ask spread, or slippage.
Treat the resulting P&L as exploratory until quote age and execution liquidity
are modeled.

The 2025 Winnipeg Jets-Dallas Stars fixture uses its scheduled 9:30 PM entry
time instead of the 9:53 PM puck-drop time. A five-share trade briefly
distorted the puck-drop price to about 0.76 / 0.24.

## Threshold comparison

`threshold_comparison.py` runs the same paired-hedge strategy at every
whole-percent threshold from 0% through 100%:

```powershell
.\.venv\Scripts\python.exe -m backtesting.threshold_comparison nba `
  --stake 100 `
  --fee-rate 0 `
  --out data/analysis/nba_threshold_comparison.csv
```

The comparison reports the qualifying hedge count, total P&L, P&L per hedge,
return on deployed stake, and maximum drawdown for all 101 thresholds. If
`--initial-cash` is omitted, the runner allocates enough comparison cash to
avoid rejecting low-threshold runs simply because they select more teams.

The fixture selection caveats remain:

- `data/raw/MLB_2025.txt` excludes the Blue Jays-Mariners ALCS because its series market
  opened after Game 1.

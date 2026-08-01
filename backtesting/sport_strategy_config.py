from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MATCH_DATA_DIR = PROJECT_ROOT / "data" / "match_data"


@dataclass(frozen=True)
class SportStrategyConfig:
    display_name: str
    csv_path: Path
    trigger_prefix: str
    loss_prefix: str
    namespace: str
    trigger_label: str
    loss_label: str


# Every sport below uses the same paired-hedge strategy. Only its data columns,
# instrument namespace, and display labels differ.
SPORTS = {
    "fifa": SportStrategyConfig(
        "FIFA World Cup 2026",
        MATCH_DATA_DIR / "polymarket_match_data.csv",
        "game_winner",
        "tournament_loss",
        "fifa",
        "match",
        "World Cup loss",
    ),
    "nba": SportStrategyConfig(
        "NBA",
        MATCH_DATA_DIR / "nba_match_data.csv",
        "series_winner",
        "championship_loss",
        "nba",
        "series",
        "championship loss",
    ),
    "nba_2025": SportStrategyConfig(
        "NBA 2025",
        MATCH_DATA_DIR / "nba_2025_match_data.csv",
        "series_winner",
        "championship_loss",
        "nba_2025",
        "series",
        "championship loss",
    ),
    "nhl": SportStrategyConfig(
        "NHL",
        MATCH_DATA_DIR / "nhl_match_data.csv",
        "series_winner",
        "championship_loss",
        "nhl",
        "series",
        "Stanley Cup loss",
    ),
    "nhl_2025": SportStrategyConfig(
        "NHL 2025",
        MATCH_DATA_DIR / "nhl_2025_match_data.csv",
        "series_winner",
        "championship_loss",
        "nhl_2025",
        "series",
        "Stanley Cup loss",
    ),
    "lol_worlds_2025": SportStrategyConfig(
        "LoL Worlds 2025",
        MATCH_DATA_DIR / "lol_worlds_2025_match_data.csv",
        "series_winner",
        "championship_loss",
        "lol_worlds_2025",
        "series",
        "Worlds loss",
    ),
    "wimbledon_2026": SportStrategyConfig(
        "Men's Wimbledon 2026",
        MATCH_DATA_DIR / "wimbledon_2026_men_match_data.csv",
        "game_winner",
        "championship_loss",
        "wimbledon_2026_men",
        "match",
        "Wimbledon title loss",
    ),
    "ucl_2026": SportStrategyConfig(
        "Men's UEFA Champions League 2025-26",
        MATCH_DATA_DIR / "ucl_2026_match_data.csv",
        "series_winner",
        "championship_loss",
        "ucl_2026",
        "tie",
        "Champions League title loss",
    ),
    "mlb": SportStrategyConfig(
        "MLB",
        MATCH_DATA_DIR / "mlb_match_data.csv",
        "series_winner",
        "championship_loss",
        "mlb",
        "series",
        "World Series loss",
    ),
    "nfl": SportStrategyConfig(
        "NFL",
        MATCH_DATA_DIR / "nfl_match_data.csv",
        "game_winner",
        "championship_loss",
        "nfl",
        "game",
        "Super Bowl loss",
    ),
}


def get_sport_config(sport: str) -> SportStrategyConfig:
    try:
        return SPORTS[sport.casefold()]
    except KeyError as exc:
        available = ", ".join(sorted(SPORTS))
        raise ValueError(
            f'Unknown sport "{sport}". Available sports: {available}'
        ) from exc

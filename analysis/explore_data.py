from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MATCH_DATA_DIR = PROJECT_ROOT / "data" / "match_data"
ANALYSIS_DATA_DIR = PROJECT_ROOT / "data" / "analysis"

DEFAULT_INPUT = MATCH_DATA_DIR / "polymarket_match_data.csv"
DEFAULT_DATABASE = ANALYSIS_DATA_DIR / "explore_data.db"
DEFAULT_OUTPUT = ANALYSIS_DATA_DIR / "explore_data_table_1.csv"
DEFAULT_COUNTRY_OUTPUT = ANALYSIS_DATA_DIR / "explore_data_table_2.csv"
DEFAULT_TIER_OUTPUT = ANALYSIS_DATA_DIR / "explore_data_table_3.csv"

RAW_TABLE = "raw_data"
OUTPUT_TABLE = "explore_data_table_1"
COUNTRY_OUTPUT_TABLE = "explore_data_table_2"
TIER_OUTPUT_TABLE = "explore_data_table_3"
STRATEGY_COLUMNS = (
    "team_advance",
    "strategy_ev_relative",
    "strategy_ev",
    "profit_per_100",
)
PRICE_COLUMNS = (
    "game_winner_start",
    "game_winner_end",
    "tournament_loss_start",
    "tournament_loss_end",
)
REQUIRED_COLUMNS = (
    "country",
    "opponent",
    "match",
    "kickoff_edt",
    "end_edt",
    *PRICE_COLUMNS,
)


def quote_identifier(value: str) -> str:
    """Quote a SQLite identifier supplied by a CSV header."""
    return f'"{value.replace(chr(34), chr(34) * 2)}"'


def read_raw_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        columns = reader.fieldnames
        if not columns:
            raise ValueError(f"{path} has no header row")
        if len(columns) != len(set(columns)) or any(not column for column in columns):
            raise ValueError(f"{path} contains blank or duplicate column names")

        missing = [column for column in REQUIRED_COLUMNS if column not in columns]
        if missing:
            raise ValueError(f"{path} is missing columns: {', '.join(missing)}")
        conflicts = [column for column in STRATEGY_COLUMNS if column in columns]
        if conflicts:
            raise ValueError(
                f"{path} already contains derived columns: {', '.join(conflicts)}"
            )

        rows = list(reader)

    for row_number, row in enumerate(rows, start=2):
        for column in PRICE_COLUMNS:
            try:
                value = float(row[column])
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f'{path} row {row_number} has an invalid {column}: {row[column]!r}'
                ) from exc
            if not 0.0 <= value <= 1.0:
                raise ValueError(
                    f"{path} row {row_number} has {column} outside [0, 1]: {value}"
                )
    return columns, rows


def replace_raw_table(
    connection: sqlite3.Connection,
    columns: list[str],
    rows: Iterable[dict[str, str]],
) -> None:
    for table in (TIER_OUTPUT_TABLE, COUNTRY_OUTPUT_TABLE, OUTPUT_TABLE):
        connection.execute(f"DROP TABLE IF EXISTS {quote_identifier(table)}")
    connection.execute(f"DROP TABLE IF EXISTS {quote_identifier(RAW_TABLE)}")

    definitions = [
        f"{quote_identifier(column)} {'REAL' if column in PRICE_COLUMNS else 'TEXT'}"
        for column in columns
    ]
    connection.execute(
        f"CREATE TABLE {quote_identifier(RAW_TABLE)} ({', '.join(definitions)})"
    )

    column_sql = ", ".join(quote_identifier(column) for column in columns)
    placeholders = ", ".join("?" for _ in columns)
    connection.executemany(
        f"INSERT INTO {quote_identifier(RAW_TABLE)} ({column_sql}) "
        f"VALUES ({placeholders})",
        ([row[column] for column in columns] for row in rows),
    )


def create_first_output_table(
    connection: sqlite3.Connection, raw_columns: list[str]
) -> None:
    """Create the first derived table; all strategy arithmetic is done in SQL."""
    original_columns = ",\n            ".join(
        f"strategy_inputs.{quote_identifier(column)}" for column in raw_columns
    )
    connection.execute(
        f"""
        CREATE TABLE {quote_identifier(OUTPUT_TABLE)} AS
        WITH strategy_inputs AS (
            SELECT
                {quote_identifier(RAW_TABLE)}.*,
                CASE
                    WHEN game_winner_end > 0.5 THEN 'yes'
                    ELSE 'no'
                END AS team_advance,
                (1.0 - tournament_loss_start)
                    * (game_winner_end / NULLIF(game_winner_start, 0.0))
                    AS expected_tournament_win_price,
                1.0 - tournament_loss_start AS tournament_win_start,
                1.0 - tournament_loss_end AS tournament_win_final
            FROM {quote_identifier(RAW_TABLE)}
        ),
        strategy_values AS (
            SELECT
                strategy_inputs.*,
                expected_tournament_win_price - tournament_win_final
                    AS winner_strategy_ev,
                expected_tournament_win_price - tournament_win_start
                    AS expected_price_movement
            FROM strategy_inputs
        )
        SELECT
            {original_columns},
            team_advance,
            CASE
                WHEN team_advance = 'no' THEN 0.0
                ELSE winner_strategy_ev / NULLIF(expected_price_movement, 0.0)
            END AS strategy_ev_relative,
            CASE
                WHEN team_advance = 'no' THEN 0.0
                ELSE winner_strategy_ev
            END AS strategy_ev,
            CASE
                WHEN team_advance = 'no' THEN 0.0
                ELSE (100.0 / NULLIF(tournament_loss_start, 0.0))
                    * winner_strategy_ev
            END AS profit_per_100
        FROM strategy_values AS strategy_inputs
        """
    )


def create_country_output_table(connection: sqlite3.Connection) -> None:
    """Summarize match counts and winner-only average profit by country."""
    connection.execute(
        f"""
        CREATE TABLE {quote_identifier(COUNTRY_OUTPUT_TABLE)} AS
        SELECT
            country,
            COUNT(*) AS matches_played,
            SUM(CASE WHEN team_advance = 'yes' THEN 1 ELSE 0 END) AS matches_won,
            AVG(
                CASE
                    WHEN team_advance = 'yes' THEN profit_per_100
                END
            ) AS avg_profit_per_100
        FROM {quote_identifier(OUTPUT_TABLE)}
        GROUP BY country
        ORDER BY country COLLATE NOCASE
        """
    )


def create_tier_output_table(connection: sqlite3.Connection) -> None:
    """Summarize winner-only average profit by pre-match win-probability tier."""
    connection.execute(
        f"""
        CREATE TABLE {quote_identifier(TIER_OUTPUT_TABLE)} AS
        WITH probability_tiers(
            tier_order,
            favourite_tier,
            win_probability_range
        ) AS (
            VALUES
                (1, 'big favourite', '80%-100%'),
                (2, 'large favourite', '60%-<80%'),
                (3, 'middle', '40%-<60%'),
                (4, 'large underdog', '20%-<40%'),
                (5, 'big underdog', '0%-<20%')
        ),
        classified AS (
            SELECT
                country,
                team_advance,
                profit_per_100,
                CASE
                    WHEN game_winner_start >= 0.8 THEN 1
                    WHEN game_winner_start >= 0.6 THEN 2
                    WHEN game_winner_start >= 0.4 THEN 3
                    WHEN game_winner_start >= 0.2 THEN 4
                    ELSE 5
                END AS tier_order
            FROM {quote_identifier(OUTPUT_TABLE)}
        )
        SELECT
            probability_tiers.favourite_tier,
            probability_tiers.win_probability_range,
            COUNT(classified.country) AS matches_played,
            SUM(
                CASE
                    WHEN classified.team_advance = 'yes' THEN 1
                    ELSE 0
                END
            ) AS matches_won,
            AVG(
                CASE
                    WHEN classified.team_advance = 'yes'
                        THEN classified.profit_per_100
                END
            ) AS avg_profit_per_100
        FROM probability_tiers
        LEFT JOIN classified
            ON classified.tier_order = probability_tiers.tier_order
        GROUP BY
            probability_tiers.tier_order,
            probability_tiers.favourite_tier,
            probability_tiers.win_probability_range
        ORDER BY probability_tiers.tier_order
        """
    )


def export_table_to_csv(
    connection: sqlite3.Connection, table: str, path: Path
) -> int:
    cursor = connection.execute(f"SELECT * FROM {quote_identifier(table)}")
    columns = [description[0] for description in cursor.description]
    rows = cursor.fetchall()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(columns)
        writer.writerows(rows)
    return len(rows)


def build_first_table(input_path: Path, database_path: Path, output_path: Path) -> int:
    columns, rows = read_raw_csv(input_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database_path)) as connection:
        with connection:
            replace_raw_table(connection, columns, rows)
            create_first_output_table(connection, columns)
        return export_table_to_csv(connection, OUTPUT_TABLE, output_path)


def build_exploration_tables(
    input_path: Path,
    database_path: Path,
    output_path: Path,
    country_output_path: Path,
    tier_output_path: Path,
) -> tuple[int, int, int]:
    columns, rows = read_raw_csv(input_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database_path)) as connection:
        with connection:
            replace_raw_table(connection, columns, rows)
            create_first_output_table(connection, columns)
            create_country_output_table(connection)
            create_tier_output_table(connection)
        return (
            export_table_to_csv(connection, OUTPUT_TABLE, output_path),
            export_table_to_csv(
                connection, COUNTRY_OUTPUT_TABLE, country_output_path
            ),
            export_table_to_csv(connection, TIER_OUTPUT_TABLE, tier_output_path),
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build SQL exploration tables from raw Polymarket match data."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--country-out", type=Path, default=DEFAULT_COUNTRY_OUTPUT
    )
    parser.add_argument("--tier-out", type=Path, default=DEFAULT_TIER_OUTPUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        row_counts = build_exploration_tables(
            args.input,
            args.database,
            args.out,
            args.country_out,
            args.tier_out,
        )
    except (OSError, sqlite3.Error, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(
        f"Created {OUTPUT_TABLE} ({row_counts[0]} rows), "
        f"{COUNTRY_OUTPUT_TABLE} ({row_counts[1]} rows), and "
        f"{TIER_OUTPUT_TABLE} ({row_counts[2]} rows) in {args.database}; "
        f"exported them to {args.out}, {args.country_out}, and {args.tier_out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

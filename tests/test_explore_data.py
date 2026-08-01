from __future__ import annotations

import csv
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from analysis import explore_data


HEADERS = [
    "country",
    "opponent",
    "match",
    "kickoff_edt",
    "end_edt",
    "game_winner_start",
    "game_winner_end",
    "tournament_loss_start",
    "tournament_loss_end",
]


class ExploreDataTest(unittest.TestCase):
    def write_source(self, path: Path, rows: list[list[str]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(HEADERS)
            writer.writerows(rows)

    def test_builds_sql_table_and_exports_winner_and_loser(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "raw.csv"
            database = root / "explore.db"
            output = root / "table_1.csv"
            self.write_source(
                source,
                [
                    [
                        "Canada", "South Africa", "south-africa-canada",
                        "2026-06-28 03:00 PM EDT", "2026-06-28 07:00 PM EDT",
                        "0.715", "0.9995", "0.9985", "0.9975",
                    ],
                    [
                        "South Africa", "Canada", "south-africa-canada",
                        "2026-06-28 03:00 PM EDT", "2026-06-28 07:00 PM EDT",
                        "0.285", "0.0005", "0.9995", "0.9995",
                    ],
                ],
            )

            count = explore_data.build_first_table(source, database, output)

            with closing(sqlite3.connect(database)) as connection:
                canada = connection.execute(
                    "SELECT team_advance, strategy_ev_relative, strategy_ev, "
                    "profit_per_100 FROM explore_data_table_1 WHERE country = ?",
                    ("Canada",),
                ).fetchone()
                south_africa = connection.execute(
                    "SELECT team_advance, strategy_ev_relative, strategy_ev, "
                    "profit_per_100 FROM explore_data_table_1 WHERE country = ?",
                    ("South Africa",),
                ).fetchone()
                raw_count = connection.execute("SELECT COUNT(*) FROM raw_data").fetchone()[0]
            with output.open(encoding="utf-8", newline="") as saved_file:
                saved = list(csv.DictReader(saved_file))

        self.assertEqual(count, 2)
        self.assertEqual(raw_count, 2)
        self.assertEqual(canada[0], "yes")
        self.assertAlmostEqual(canada[1], -0.6754540128881078)
        self.assertAlmostEqual(canada[2], -0.00040314685314685315)
        self.assertAlmostEqual(canada[3], -0.04037524818796727)
        self.assertEqual(south_africa, ("no", 0.0, 0.0, 0.0))
        self.assertEqual(len(saved), 2)
        self.assertEqual(
            list(saved[0])[-4:],
            ["team_advance", "strategy_ev_relative", "strategy_ev", "profit_per_100"],
        )

    def test_relative_ev_is_null_when_expected_movement_is_zero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "raw.csv"
            database = root / "explore.db"
            output = root / "table_1.csv"
            self.write_source(
                source,
                [[
                    "Example", "Opponent", "example-opponent", "start", "end",
                    "0.8", "0.8", "0.9", "0.9",
                ]],
            )

            explore_data.build_first_table(source, database, output)

            with closing(sqlite3.connect(database)) as connection:
                relative_ev = connection.execute(
                    "SELECT strategy_ev_relative FROM explore_data_table_1"
                ).fetchone()[0]

        self.assertIsNone(relative_ev)

    def test_builds_country_and_probability_tier_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "raw.csv"
            database = root / "explore.db"
            output_1 = root / "table_1.csv"
            output_2 = root / "table_2.csv"
            output_3 = root / "table_3.csv"
            self.write_source(
                source,
                [
                    [
                        "Alpha", "Beta", "alpha-beta", "start", "end",
                        "0.85", "0.9995", "0.8", "0.75",
                    ],
                    [
                        "Beta", "Alpha", "alpha-beta", "start", "end",
                        "0.15", "0.0005", "0.99", "0.9995",
                    ],
                    [
                        "Alpha", "Gamma", "alpha-gamma", "start", "end",
                        "0.65", "0.0005", "0.8", "0.9995",
                    ],
                    [
                        "Gamma", "Alpha", "alpha-gamma", "start", "end",
                        "0.35", "0.9995", "0.95", "0.9",
                    ],
                ],
            )

            counts = explore_data.build_exploration_tables(
                source, database, output_1, output_2, output_3
            )

            with closing(sqlite3.connect(database)) as connection:
                alpha = connection.execute(
                    "SELECT matches_played, matches_won, avg_profit_per_100 "
                    "FROM explore_data_table_2 WHERE country = 'Alpha'"
                ).fetchone()
                beta = connection.execute(
                    "SELECT matches_played, matches_won, avg_profit_per_100 "
                    "FROM explore_data_table_2 WHERE country = 'Beta'"
                ).fetchone()
                alpha_win_profit = connection.execute(
                    "SELECT profit_per_100 FROM explore_data_table_1 "
                    "WHERE country = 'Alpha' AND team_advance = 'yes'"
                ).fetchone()[0]
                tier_rows = connection.execute(
                    "SELECT favourite_tier, matches_played, matches_won, "
                    "avg_profit_per_100 FROM explore_data_table_3"
                ).fetchall()
            with output_2.open(encoding="utf-8", newline="") as saved_file:
                country_csv = list(csv.DictReader(saved_file))
            with output_3.open(encoding="utf-8", newline="") as saved_file:
                tier_csv = list(csv.DictReader(saved_file))

        self.assertEqual(counts, (4, 3, 5))
        self.assertEqual(alpha[:2], (2, 1))
        self.assertAlmostEqual(alpha[2], alpha_win_profit)
        self.assertEqual(beta, (1, 0, None))
        self.assertEqual(
            [row[0] for row in tier_rows],
            [
                "big favourite",
                "large favourite",
                "middle",
                "large underdog",
                "big underdog",
            ],
        )
        self.assertEqual(
            [(row[1], row[2]) for row in tier_rows],
            [(1, 1), (1, 0), (0, 0), (1, 1), (1, 0)],
        )
        self.assertEqual(len(country_csv), 3)
        self.assertEqual(len(tier_csv), 5)


if __name__ == "__main__":
    unittest.main()

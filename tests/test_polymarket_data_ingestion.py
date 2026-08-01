from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from data_ingestion import polymarket as ingestion


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"

DRAW = ingestion.MarketConfig(
    "draw",
    "match",
    "Draw",
    "Will {team_1} vs. {team_2} end in a draw?",
    "{team_1} vs {team_2}",
    "Will {team_1} vs. {team_2} end in a draw?",
    "YES",
)
TOURNAMENT = ingestion.MarketConfig(
    "tournament_winner",
    "team",
    "{team}",
    "Will {team} win the 2026 FIFA World Cup?",
    "World Cup Winner",
    "Will {team} win the 2026 FIFA World Cup?",
    "NO",
)
GAME_WINNER = ingestion.MarketConfig(
    "game_winner",
    "team",
    "{team}",
    "{team_1} vs. {team_2}: Team to Advance",
    "{team_1} vs {team_2}",
    "{team_1} vs. {team_2}: Team to Advance",
    "{team}",
    "-more-markets",
)
NBA_SERIES = ingestion.MarketConfig(
    "series_winner",
    "team",
    "{team}",
    "NBA Playoffs: Who Will Win Series? - {team_1} vs. {team_2}",
    "NBA Playoffs: Who Will Win Series? - {team_1} vs. {team_2}",
    "NBA Playoffs: Who Will Win Series? - {team_1} vs. {team_2}",
    "{team_token}",
)
NBA_ADVANCE = ingestion.MarketConfig(
    "advance_to_finals",
    "team",
    "{team}",
    "Will {team} advance to the 2026 NBA Finals?",
    "NBA Playoffs: Team to advance to NBA Finals",
    "Will {team} advance to the 2026 NBA Finals?",
    "YES",
    output_name="series_winner",
)


class FileDrivenIngestionTest(unittest.TestCase):
    def test_parses_match_time_as_edt(self) -> None:
        matches = ingestion.parse_matches(
            "FIFA World Cup 2026\n"
            "2026-06-28 3:00 PM | 2026-06-28 8:00 PM | South Africa vs Canada "
            "| game_winner, tournament_loss\n"
            "2026-06-29 9:00 PM | 2026-06-30 2:00 AM | Brazil vs Japan\n"
        )
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].team_1, "South Africa")
        self.assertEqual(matches[0].start_utc.isoformat(), "2026-06-28T19:00:00+00:00")
        self.assertEqual(matches[0].end_utc.isoformat(), "2026-06-29T00:00:00+00:00")
        self.assertEqual(
            matches[0].markets,
            frozenset({"game_winner", "tournament_loss"}),
        )
        self.assertIsNone(matches[1].markets)

    def test_parses_match_time_as_est_from_file_header(self) -> None:
        matches = ingestion.parse_matches(
            "Times shown in Eastern Standard Time (EST)\n"
            "2026-01-10 8:00 PM | 2026-01-11 1:00 AM | "
            "Alpha vs Beta | game_winner, championship_loss\n"
        )

        self.assertEqual(
            matches[0].start_utc.isoformat(), "2026-01-11T01:00:00+00:00"
        )
        self.assertEqual(
            matches[0].end_utc.isoformat(), "2026-01-11T06:00:00+00:00"
        )
        self.assertEqual(matches[0].market_timezone.tzname(None), "EST")

    def test_loads_mens_only_wimbledon_configuration(self) -> None:
        markets = ingestion.configured_markets("Wimbledon")

        self.assertEqual(
            [market.name for market in markets],
            ["mens_game_winner", "mens_championship_loss"],
        )
        self.assertEqual(
            [market.output_name for market in markets],
            ["game_winner", "championship_loss"],
        )

    def test_parses_all_mens_wimbledon_fixtures(self) -> None:
        file_path = (
            RAW_DATA_DIR / "Wimbledon_2026_Men.txt"
        )

        matches = ingestion.parse_matches(file_path.read_text(encoding="utf-8"))

        self.assertEqual(len(matches), 21)
        self.assertEqual(matches[0].team_1, "Casper Ruud")
        self.assertEqual(matches[-1].team_2, "Novak Djokovic")
        self.assertEqual(
            matches[15].end_utc.isoformat(),
            "2026-07-07T16:47:00+00:00",
        )
        self.assertTrue(
            all(
                match.markets
                == frozenset({
                    "mens_game_winner",
                    "mens_championship_loss",
                })
                for match in matches
            )
        )

    def test_resolves_draw_token(self) -> None:
        payload = {
            "events": [{
                "title": "South Africa vs. Canada",
                "markets": [{
                    "question": "Will South Africa vs. Canada end in a draw?",
                    "outcomes": '["Yes", "No"]',
                    "clobTokenIds": '["draw-yes", "draw-no"]',
                }]
            }]
        }
        values = {"team_1": "South Africa", "team_2": "Canada"}
        tokens = ingestion.tokens_in_payload(payload, DRAW, values)
        self.assertEqual(tokens, {"draw-yes"})

    def test_resolves_tournament_no_token(self) -> None:
        payload = {
            "events": [{
                "title": "World Cup Winner",
                "markets": [{
                    "question": "Will Canada win the 2026 FIFA World Cup?",
                    "outcomes": '["Yes", "No"]',
                    "clobTokenIds": '["canada-yes", "canada-no"]',
                }]
            }]
        }
        values = {
            "team_1": "South Africa",
            "team_2": "Canada",
            "team": "Canada",
            "opponent": "South Africa",
        }
        tokens = ingestion.tokens_in_payload(payload, TOURNAMENT, values)
        self.assertEqual(tokens, {"canada-no"})

    def test_selects_reused_market_title_from_fixture_year(self) -> None:
        markets = {
            "old-token": {"startDate": "2024-10-04T15:28:21Z"},
            "new-token": {"startDate": "2025-09-29T01:24:31Z"},
        }

        selected = ingestion.markets_from_fixture_year(markets, "2025-09-30")

        self.assertEqual(selected, {"new-token": markets["new-token"]})

    def test_reads_market_configuration_from_arguments(self) -> None:
        (
            file_path,
            markets,
            event_tag,
            output_path,
            aliases,
            token_aliases,
        ) = ingestion.parse_args([
            "data/raw/World_Cup_2026.txt",
            "--event-tag", "World Cup",
            "--out", "prices.csv",
            "--team-alias", "game_winner:Ivory Coast=Cote d'Ivoire",
            "--token-alias", "series_winner:Cleveland Cavaliers=Cavs",
            "--market", "draw", "match", "Draw",
            "Will {team_1} vs. {team_2} end in a draw?",
            "{team_1} vs {team_2}",
            "Will {team_1} vs. {team_2} end in a draw?", "YES",
        ])
        self.assertEqual(file_path.name, "World_Cup_2026.txt")
        self.assertEqual(markets, [DRAW])
        self.assertEqual(event_tag, "World Cup")
        self.assertEqual(output_path.name, "prices.csv")
        self.assertEqual(aliases, {"game_winner:Ivory Coast": "Cote d'Ivoire"})
        self.assertEqual(
            token_aliases,
            {"series_winner:Cleveland Cavaliers": "Cavs"},
        )

    def test_loads_market_configuration_from_event_tag(self) -> None:
        (
            file_path,
            markets,
            event_tag,
            output_path,
            aliases,
            token_aliases,
        ) = ingestion.parse_args([
            "data/raw/NBA_2026.txt",
            "--event-tag", "2026 NBA Playoffs",
            "--out", "data/match_data/nba_match_data.csv",
        ])

        self.assertEqual(file_path.name, "NBA_2026.txt")
        self.assertEqual(event_tag, "2026 NBA Playoffs")
        self.assertEqual(output_path.name, "nba_match_data.csv")
        self.assertEqual(
            [market.name for market in markets],
            ["series_winner", "advance_to_finals", "championship_loss"],
        )
        self.assertEqual(markets[1].output_name, "series_winner")
        self.assertEqual(aliases, {})
        self.assertEqual(token_aliases, {})

    def test_loads_2025_nba_markets_from_event_tag(self) -> None:
        markets = ingestion.configured_markets("NBA Playoffs")

        self.assertEqual(
            [market.name for market in markets],
            ["series_winner", "championship_loss"],
        )
        self.assertEqual(
            markets[0].event,
            "NBA Playoffs: {team_1} vs. {team_2} (To Advance)",
        )
        self.assertEqual(markets[1].event, "NBA Champion")
        self.assertEqual(markets[1].event_slug, "nba-champion-2024-2025")

    def test_2025_nba_accepts_round_specific_minnesota_tokens(self) -> None:
        market = ingestion.configured_markets("NBA Playoffs")[0]
        values = {
            "team_1": "Timberwolves",
            "team_2": "Warriors",
            "team": "Timberwolves",
            "team_token": "Wolves || Timberwolves || Twolves || T-Wolves",
        }

        for outcome in ("Timberwolves", "Twolves", "T-Wolves"):
            with self.subTest(outcome=outcome):
                payload = {
                    "events": [{
                        "title": (
                            "NBA Playoffs: Timberwolves vs. Warriors "
                            "(To Advance)"
                        ),
                        "tags": [{"label": "NBA Playoffs"}],
                        "markets": [{
                            "question": (
                                "NBA Playoffs: Timberwolves vs. Warriors "
                                "(To Advance)"
                            ),
                            "outcomes": f'["{outcome}", "Warriors"]',
                            "clobTokenIds": '["minnesota", "warriors"]',
                        }],
                    }]
                }

                self.assertEqual(
                    ingestion.tokens_in_payload(
                        payload, market, values, "NBA Playoffs"
                    ),
                    {"minnesota"},
                )

    def test_parses_all_2025_nba_fixtures_and_midnight_end_times(self) -> None:
        file_path = RAW_DATA_DIR / "NBA_2025.txt"

        matches = ingestion.parse_matches(file_path.read_text(encoding="utf-8"))
        by_match = {
            (match.team_1, match.team_2): match
            for match in matches
        }

        self.assertEqual(len(matches), 14)
        self.assertEqual(
            by_match[("Los Angeles Lakers", "Minnesota Timberwolves")]
            .end_utc.isoformat(),
            "2025-05-01T04:53:00+00:00",
        )
        self.assertEqual(
            by_match[("Oklahoma City Thunder", "Minnesota Timberwolves")]
            .markets,
            frozenset({"series_winner", "championship_loss"}),
        )

    def test_loads_2025_nhl_markets_from_nhl_tag(self) -> None:
        markets = ingestion.configured_markets("NHL")

        self.assertEqual(
            [market.name for market in markets],
            [
                "to_advance",
                "east_champion",
                "west_champion",
                "championship_loss",
            ],
        )
        self.assertEqual(markets[0].event, "NHL Playoffs")
        self.assertIn("{team_1_token}", markets[0].market)
        self.assertEqual(markets[0].output_name, "series_winner")
        self.assertEqual(markets[1].output_name, "series_winner")
        self.assertEqual(markets[2].output_name, "series_winner")
        self.assertEqual(
            markets[2].event_slug,
            "nhl-western-conference-champion",
        )
        self.assertEqual(markets[3].event, "Stanley Cup Champion 2025")

    def test_exact_event_slug_disambiguates_reused_event_title(self) -> None:
        market = ingestion.configured_markets("NHL")[2]
        question = "Will the Dallas Stars win the Western Conference?"
        payload = {
            "events": [
                {
                    "title": "NHL: Western Conference Champion",
                    "slug": "nhl-western-conference-champion-865",
                    "tags": [{"label": "NHL"}],
                    "markets": [{
                        "question": question,
                        "outcomes": '["Yes", "No"]',
                        "clobTokenIds": '["wrong-year", "wrong-no"]',
                    }],
                },
                {
                    "title": "NHL Western Conference Champion",
                    "slug": "nhl-western-conference-champion",
                    "tags": [{"label": "NHL"}],
                    "markets": [{
                        "question": question,
                        "outcomes": '["Yes", "No"]',
                        "clobTokenIds": '["right-year", "right-no"]',
                    }],
                },
            ]
        }
        values = {"team": "Dallas Stars"}

        self.assertEqual(
            ingestion.tokens_in_payload(payload, market, values, "NHL"),
            {"right-year"},
        )

    def test_parses_all_2025_nhl_fixtures_and_midnight_end_times(self) -> None:
        file_path = RAW_DATA_DIR / "NHL_2025.txt"

        matches = ingestion.parse_matches(file_path.read_text(encoding="utf-8"))
        by_match = {
            (match.team_1, match.team_2): match
            for match in matches
        }

        self.assertEqual(len(matches), 14)
        self.assertEqual(
            by_match[("Edmonton Oilers", "Los Angeles Kings")]
            .end_utc.isoformat(),
            "2025-05-02T04:55:00+00:00",
        )
        self.assertEqual(
            by_match[("Vegas Golden Knights", "Edmonton Oilers")]
            .end_utc.isoformat(),
            "2025-05-15T04:41:00+00:00",
        )
        self.assertEqual(
            by_match[("Carolina Hurricanes", "Florida Panthers")].markets,
            frozenset({"east_champion", "championship_loss"}),
        )
        self.assertEqual(
            by_match[("Dallas Stars", "Edmonton Oilers")].markets,
            frozenset({"west_champion", "championship_loss"}),
        )

    def test_loads_2025_26_ucl_markets_from_champions_league_tag(self) -> None:
        markets = ingestion.configured_markets("Champions League")

        self.assertEqual(
            [market.name for market in markets],
            [
                "reach_quarter_finals",
                "reach_semifinal",
                "reach_final",
                "championship_loss",
            ],
        )
        self.assertEqual(
            [market.output_name for market in markets[:3]],
            ["series_winner", "series_winner", "series_winner"],
        )
        self.assertEqual(
            [market.event_slug for market in markets],
            [
                "ucl-team-to-reach-quarter-finals",
                "uefa-champions-league-team-to-advance-to-semis",
                "uefa-champions-league-team-to-reach-final",
                "uefa-champions-league-winner",
            ],
        )
        self.assertEqual(
            markets[3].market,
            "Will {team} win the 2025–26 Champions League?",
        )

    def test_parses_price_complete_2025_26_mens_ucl_ties(self) -> None:
        file_path = RAW_DATA_DIR / "UCL_2026.txt"

        matches = ingestion.parse_matches(file_path.read_text(encoding="utf-8"))
        by_match = {
            (match.team_1, match.team_2): match
            for match in matches
        }

        self.assertEqual(len(matches), 13)
        self.assertEqual(
            by_match[("Bodø/Glimt", "Sporting CP")].end_utc.isoformat(),
            "2026-03-17T20:23:00+00:00",
        )
        self.assertEqual(
            by_match[("Sporting CP", "Arsenal")].markets,
            frozenset({"reach_semifinal", "championship_loss"}),
        )
        self.assertEqual(
            by_match[("Paris Saint-Germain (PSG)", "Bayern München")]
            .markets,
            frozenset({"reach_final", "championship_loss"}),
        )

    def test_builds_ucl_winner_name_aliases(self) -> None:
        file_path = RAW_DATA_DIR / "UCL_2026.txt"

        aliases = ingestion.team_aliases_for_file(file_path)

        self.assertEqual(
            aliases["championship_loss:Atlético Madrid"],
            "Atletico Madrid",
        )
        self.assertEqual(
            aliases["championship_loss:Bayern München"],
            "Bayern Munich",
        )
        self.assertEqual(
            aliases["championship_loss:Bodø/Glimt"],
            "Bodo Glimt",
        )
        self.assertEqual(
            aliases["championship_loss:Paris Saint-Germain (PSG)"],
            "PSG",
        )
        self.assertEqual(
            aliases["championship_loss:Sporting CP"],
            "Sporting",
        )

    def test_loads_lol_worlds_2025_markets_from_lol_tag(self) -> None:
        markets = ingestion.configured_markets("league of legends")

        self.assertEqual(
            [market.name for market in markets],
            ["series_winner", "championship_loss"],
        )
        self.assertEqual(
            markets[0].event_slug,
            "lol-{team_1_token}-{team_2_token}-{date}",
        )
        self.assertEqual(markets[1].event, "LoL Worlds 2025 Winner")
        self.assertEqual(markets[1].event_slug, "lol-worlds-2025-winner")

    def test_parses_all_lol_worlds_2025_pre_final_fixtures(self) -> None:
        file_path = (
            RAW_DATA_DIR / "LoL_Worlds_2025.txt"
        )

        matches = ingestion.parse_matches(file_path.read_text(encoding="utf-8"))
        aliases = ingestion.team_aliases_for_file(file_path)
        token_aliases = ingestion.token_aliases_for_file(file_path)

        self.assertEqual(len(matches), 6)
        self.assertEqual(
            matches[0].start_utc.isoformat(),
            "2025-10-28T07:00:00+00:00",
        )
        self.assertEqual(
            matches[-1].end_utc.isoformat(),
            "2025-11-02T12:28:00+00:00",
        )
        self.assertEqual(
            aliases["championship_loss:Anyone's Legend"],
            "Anyone’s Legend",
        )
        self.assertEqual(token_aliases["series_winner:Gen.G"], "gen")
        self.assertEqual(token_aliases["series_winner:T1"], "t1")

    def test_lol_event_slug_disambiguates_reused_bo5_title(self) -> None:
        market = ingestion.configured_markets("league of legends")[0]
        question = "LoL: Gen.G vs KT Rolster (BO5)"
        payload = {
            "events": [
                {
                    "title": question,
                    "slug": "lol-gen-kt-2025-09-27",
                    "tags": [{"label": "league of legends"}],
                    "markets": [{
                        "question": question,
                        "outcomes": '["Gen.G", "KT Rolster"]',
                        "clobTokenIds": '["wrong-gen", "wrong-kt"]',
                    }],
                },
                {
                    "title": question,
                    "slug": "lol-gen-kt-2025-11-01",
                    "tags": [{"label": "league of legends"}],
                    "markets": [{
                        "question": question,
                        "outcomes": '["Gen.G", "KT Rolster"]',
                        "clobTokenIds": '["right-gen", "right-kt"]',
                    }],
                },
            ]
        }
        values = {
            "team_1": "Gen.G",
            "team_2": "KT Rolster",
            "team_1_token": "gen",
            "team_2_token": "kt",
            "team": "Gen.G",
            "date": "2025-11-01",
        }

        self.assertEqual(
            ingestion.tokens_in_payload(
                payload, market, values, "league of legends"
            ),
            {"right-gen"},
        )

    def test_builds_2025_nba_championship_alias(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "NBA_2025.txt"
            source.write_text(
                "2025-04-19 3:30 PM | 2025-05-03 10:00 PM | "
                "Denver Nuggets vs Los Angeles Clippers | "
                "series_winner, championship_loss\n",
                encoding="utf-8",
            )

            aliases = ingestion.team_aliases_for_file(source)

        self.assertEqual(
            aliases["championship_loss:Los Angeles Clippers"],
            "LA Clippers",
        )

    def test_builds_needed_team_aliases_from_world_cup_file(self) -> None:
        file_path = RAW_DATA_DIR / "World_Cup_2026.txt"

        aliases = ingestion.team_aliases_for_file(file_path)

        self.assertEqual(aliases, {
            "game_winner:Ivory Coast": "Cote d'Ivoire",
            "game_winner:Congo DR": "DR Congo",
            "game_winner:Bosnia-Herzegovina": "Bosnia and Herzegovina",
            "game_winner:Cape Verde": "Cabo Verde",
            "tournament_loss:United States": "USA",
        })

    def test_builds_needed_aliases_from_nba_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "NBA_2026.txt"
            source.write_text(
                "2026-04-18 7:30 PM | 2026-05-03 10:30 PM | "
                "Cleveland Cavaliers vs Minnesota Timberwolves\n"
                "2026-04-19 8:00 PM | 2026-04-29 3:00 AM | "
                "San Antonio Spurs vs Portland Trail Blazers\n",
                encoding="utf-8",
            )
            team_aliases = ingestion.team_aliases_for_file(source)
            token_aliases = ingestion.token_aliases_for_file(source)

        self.assertEqual(team_aliases, {
            "series_winner:Cleveland Cavaliers": "Cavaliers",
            "series_winner:Minnesota Timberwolves": "Timberwolves",
            "series_winner:San Antonio Spurs": "Spurs",
            "series_winner:Portland Trail Blazers": "Trail Blazers",
        })
        self.assertEqual(token_aliases, {
            "series_winner:Cleveland Cavaliers": "Cavs",
            "series_winner:Minnesota Timberwolves": (
                "Wolves || Timberwolves || Twolves || T-Wolves"
            ),
            "series_winner:San Antonio Spurs": "Spurs",
            "series_winner:Portland Trail Blazers": "Blazers",
        })

    def test_builds_needed_aliases_from_nhl_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "NHL_2026.txt"
            source.write_text(
                "2026-04-18 7:30 PM | 2026-05-03 10:30 PM | "
                "Carolina Hurricanes vs Montreal Canadiens\n"
                "2026-04-19 8:00 PM | 2026-04-29 3:00 AM | "
                "Vegas Golden Knights vs Colorado Avalanche\n",
                encoding="utf-8",
            )
            team_aliases = ingestion.team_aliases_for_file(source)
            token_aliases = ingestion.token_aliases_for_file(source)

        series_token_aliases = {
            key: value
            for key, value in token_aliases.items()
            if key.startswith("series_winner:")
        }

        self.assertEqual(team_aliases, {
            "series_winner:Carolina Hurricanes": "Hurricanes",
            "series_winner:Montreal Canadiens": "Canadiens",
            "series_winner:Vegas Golden Knights": "Golden Knights",
            "series_winner:Colorado Avalanche": "Avalanche",
        })
        self.assertEqual(series_token_aliases, {
            "series_winner:Carolina Hurricanes": "Canes",
            "series_winner:Montreal Canadiens": "Habs",
            "series_winner:Vegas Golden Knights": "Knights",
            "series_winner:Colorado Avalanche": "Avalanche",
        })

    def test_builds_2025_nhl_to_advance_token_aliases(self) -> None:
        file_path = RAW_DATA_DIR / "NHL_2025.txt"

        aliases = ingestion.token_aliases_for_file(file_path)
        to_advance = {
            key: value
            for key, value in aliases.items()
            if key.startswith("to_advance:")
        }

        self.assertEqual(len(to_advance), 16)
        self.assertEqual(
            to_advance["to_advance:Carolina Hurricanes"], "Hurricanes"
        )
        self.assertEqual(
            to_advance["to_advance:Montreal Canadiens"], "Canadiens"
        )
        self.assertEqual(
            to_advance["to_advance:Vegas Golden Knights"],
            "Golden Knights",
        )
        self.assertEqual(to_advance["to_advance:Winnipeg Jets"], "Jets")

    def test_2025_nhl_to_advance_accepts_short_and_full_market_titles(self) -> None:
        market = ingestion.configured_markets("NHL")[0]
        short_payload = {
            "events": [{
                "title": "NHL Playoffs: Stars vs. Avalanche (To Advance)",
                "tags": [{"label": "NHL", "slug": "nhl"}],
                "markets": [{
                    "question": (
                        "NHL Playoffs: Stars vs. Avalanche (To Advance)"
                    ),
                    "outcomes": '["Stars", "Avalanche"]',
                    "clobTokenIds": '["stars", "avalanche"]',
                }],
            }],
        }
        full_payload = {
            "events": [{
                "title": (
                    "NHL Playoffs: Winnipeg Jets vs. Dallas Stars "
                    "(To Advance)"
                ),
                "tags": [{"label": "NHL", "slug": "nhl"}],
                "markets": [{
                    "question": (
                        "NHL Playoffs: Winnipeg Jets vs. Dallas Stars "
                        "(To Advance)"
                    ),
                    "outcomes": '["Jets", "Stars"]',
                    "clobTokenIds": '["jets", "stars"]',
                }],
            }],
        }

        short_values = {
            "team_1": "Dallas Stars",
            "team_2": "Colorado Avalanche",
            "team_1_token": "Stars",
            "team_2_token": "Avalanche",
            "team_token": "Stars",
        }
        full_values = {
            "team_1": "Winnipeg Jets",
            "team_2": "Dallas Stars",
            "team_1_token": "Jets",
            "team_2_token": "Stars",
            "team_token": "Jets",
        }

        self.assertEqual(
            ingestion.tokens_in_payload(
                short_payload, market, short_values, "NHL"
            ),
            {"stars"},
        )
        self.assertEqual(
            ingestion.tokens_in_payload(
                full_payload, market, full_values, "NHL"
            ),
            {"jets"},
        )

    def test_builds_needed_aliases_from_mlb_and_nfl_files(self) -> None:
        mlb_path = RAW_DATA_DIR / "MLB_2025.txt"
        nfl_path = RAW_DATA_DIR / "NFL_2025.txt"

        mlb_aliases = ingestion.team_aliases_for_file(mlb_path)
        mlb_tokens = ingestion.token_aliases_for_file(mlb_path)
        nfl_aliases = ingestion.team_aliases_for_file(nfl_path)
        nfl_tokens = ingestion.token_aliases_for_file(nfl_path)

        self.assertEqual(
            mlb_aliases["series_winner:Toronto Blue Jays"], "Blue Jays"
        )
        self.assertEqual(
            mlb_tokens["series_winner:Los Angeles Dodgers"], "Dodgers"
        )
        self.assertEqual(
            nfl_aliases["game_winner:San Francisco 49ers"], "49ers"
        )
        self.assertEqual(
            nfl_tokens["game_winner:New England Patriots"], "Patriots"
        )

    def test_collect_matches_automatically_uses_file_team_aliases(self) -> None:
        tournament_loss = ingestion.MarketConfig(
            "tournament_loss",
            "team",
            "{team}",
            "Will {team} win?",
            "Winner",
            "Will {team} win?",
            "NO",
        )

        class FakeClient:
            def __init__(self):
                self.teams = []

            def resolve(self, config, values, event_tag):
                self.teams.append((config.name, values["team"]))
                return f"{config.name}:{values['team']}"

            def price_at_start(self, token_id, at):
                return 0.5

            def price_at_end(self, token_id, at):
                return 0.5

            def settlement_price(self, token_id):
                return 1.0

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "matches.txt"
            source.write_text(
                "2026-06-30 1:00 PM | 2026-06-30 6:00 PM | "
                "Ivory Coast vs United States\n",
                encoding="utf-8",
            )
            client = FakeClient()

            ingestion.collect_matches(
                source,
                client,
                [GAME_WINNER, tournament_loss],
                "World Cup",
            )

        self.assertIn(("game_winner", "Cote d'Ivoire"), client.teams)
        self.assertIn(("game_winner", "United States"), client.teams)
        self.assertIn(("tournament_loss", "Ivory Coast"), client.teams)
        self.assertIn(("tournament_loss", "USA"), client.teams)

    def test_uses_separate_nba_event_and_token_team_names(self) -> None:
        class FakeClient:
            def __init__(self):
                self.names = []

            def resolve(self, config, values, event_tag):
                self.names.append((values["team"], values["team_token"]))
                return values["team_token"]

            def price_at_start(self, token_id, at):
                return 0.5

            def price_at_end(self, token_id, at):
                return 0.5

            def settlement_price(self, token_id):
                return 1.0

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "nba.txt"
            source.write_text(
                "2026-04-18 7:30 PM | 2026-05-03 10:30 PM | "
                "Cleveland Cavaliers vs Minnesota Timberwolves | "
                "series_winner\n",
                encoding="utf-8",
            )
            client = FakeClient()

            ingestion.collect_matches(
                source,
                client,
                [NBA_SERIES, DRAW],
                "2026 NBA Playoffs",
            )

        self.assertEqual(
            client.names,
            [
                ("Cavaliers", "Cavs"),
                (
                    "Timberwolves",
                    "Wolves || Timberwolves || Twolves || T-Wolves",
                ),
            ],
        )

    def test_writes_advance_market_into_series_winner_columns(self) -> None:
        class FakeClient:
            def resolve(self, config, values, event_tag):
                return values["team"]

            def price_at_start(self, token_id, at):
                return 0.4

            def price_at_end(self, token_id, at):
                return 0.25

            def settlement_price(self, token_id):
                return 1.0

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "nba.txt"
            output = Path(directory) / "nba.csv"
            source.write_text(
                "2026-05-19 8:00 PM | 2026-05-26 1:00 AM | "
                "Cleveland Cavaliers vs New York Knicks | "
                "advance_to_finals\n",
                encoding="utf-8",
            )
            rows = ingestion.collect_matches(
                source,
                FakeClient(),
                [NBA_SERIES, NBA_ADVANCE],
                "2026 NBA Playoffs",
            )
            ingestion.write_csv(output, rows, [NBA_SERIES, NBA_ADVANCE])
            with output.open(encoding="utf-8", newline="") as saved_file:
                saved = list(csv.DictReader(saved_file))

        self.assertEqual(saved[0]["series_winner_start"], "0.400000")
        self.assertEqual(saved[0]["series_winner_end"], "1.000000")
        self.assertNotIn("advance_to_finals_start", saved[0])

    def test_skips_unrelated_event_without_more_markets(self) -> None:
        search_payload = {
            "events": [
                {
                    "title": "Brazil vs. Japan",
                    "slug": "volleyball-brazil-japan",
                    "tags": [{"label": "Volleyball", "slug": "volleyball"}],
                },
                {
                    "title": "Brazil vs. Japan",
                    "slug": "fifwc-bra-jpn-2026-06-29",
                    "tags": [{"label": "World Cup", "slug": "world-cup"}],
                },
            ]
        }
        related_payload = {
            "title": "Brazil vs. Japan - More Markets",
            "tags": [{"label": "World Cup", "slug": "world-cup"}],
            "markets": [{
                "question": "Brazil vs. Japan: Team to Advance",
                "outcomes": '["Brazil", "Japan"]',
                "clobTokenIds": '["brazil-advance", "japan-advance"]',
            }],
        }

        def fetcher(url: str) -> dict:
            if "public-search" in url:
                return search_payload
            if "volleyball-brazil-japan-more-markets" in url:
                raise AssertionError("volleyball must be rejected by its event tag")
            return related_payload

        values = {
            "team_1": "Brazil",
            "team_2": "Japan",
            "team": "Brazil",
            "opponent": "Japan",
        }
        token = ingestion.PolymarketClient(fetcher).resolve(
            GAME_WINNER, values, "World Cup"
        )
        self.assertEqual(token, "brazil-advance")

    def test_resolve_fetches_exact_configured_event_slug_directly(self) -> None:
        config = ingestion.configured_markets("league of legends")[0]
        requested_urls = []
        event = {
            "title": "LoL: Gen.G vs KT Rolster (BO5)",
            "slug": "lol-gen-kt-2025-11-01",
            "tags": [{"label": "league of legends"}],
            "markets": [{
                "question": "LoL: Gen.G vs KT Rolster (BO5)",
                "endDate": "2025-11-01T12:00:00Z",
                "outcomes": '["Gen.G", "KT Rolster"]',
                "clobTokenIds": '["gen-token", "kt-token"]',
            }],
        }

        def fetcher(url: str) -> dict:
            requested_urls.append(url)
            if url.endswith("/lol-gen-kt-2025-11-01"):
                return event
            raise AssertionError(f"unexpected fallback request: {url}")

        values = {
            "team_1": "Gen.G",
            "team_2": "KT Rolster",
            "team": "Gen.G",
            "team_1_token": "gen",
            "team_2_token": "kt",
            "date": "2025-11-01",
        }

        token = ingestion.PolymarketClient(fetcher).resolve(
            config, values, "league of legends"
        )

        self.assertEqual(token, "gen-token")
        self.assertEqual(
            requested_urls,
            [f"{ingestion.GAMMA_EVENT}/lol-gen-kt-2025-11-01"],
        )

    def test_resolve_rejects_single_wrong_year_candidate(self) -> None:
        config = ingestion.MarketConfig(
            "winner",
            "team",
            "{team}",
            "Winner",
            "Winner",
            "Will {team} win?",
            "YES",
            event_slug="winner-event",
        )
        event = {
            "title": "Winner",
            "slug": "winner-event",
            "tags": [{"label": "Test"}],
            "markets": [{
                "question": "Will Alpha win?",
                "endDate": "2024-12-31T23:00:00Z",
                "outcomes": '["Yes", "No"]',
                "clobTokenIds": '["old-yes", "old-no"]',
            }],
        }
        values = {"team": "Alpha", "date": "2025-01-01"}

        with self.assertRaisesRegex(RuntimeError, "found 0"):
            ingestion.PolymarketClient(lambda _: event).resolve(
                config, values, "Test"
            )

    def test_rejects_multiple_active_markets_for_one_output_column(self) -> None:
        first = ingestion.MarketConfig(
            "first_phase", "team", "{team}", "x", "x", "x", "YES",
            output_name="series_winner",
        )
        second = ingestion.MarketConfig(
            "second_phase", "team", "{team}", "x", "x", "x", "YES",
            output_name="series_winner",
        )

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "fixtures.txt"
            source.write_text(
                "2025-01-01 1:00 PM | 2025-01-01 4:00 PM | "
                "Alpha vs Beta\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "series_winner"):
                ingestion.collect_matches(
                    source,
                    object(),
                    [first, second],
                    "Test",
                )

    def test_price_uses_latest_point_not_after_kickoff(self) -> None:
        kickoff = datetime(2026, 6, 28, 19, 0, tzinfo=timezone.utc)
        timestamp = int(kickoff.timestamp())
        client = ingestion.PolymarketClient(lambda _: {
            "history": [
                {"t": timestamp - 60, "p": 0.41},
                {"t": timestamp, "p": 0.43},
                {"t": timestamp + 60, "p": 0.99},
            ]
        })
        self.assertEqual(client.price_at_start("token", kickoff), 0.43)

    def test_price_retries_coarser_history_after_http_500(self) -> None:
        calls = []

        def fetcher(url):
            calls.append(url)
            if "fidelity=1" in url or "fidelity=5" in url:
                raise RuntimeError("HTTP 500 from price history")
            return {"history": [{"t": 1_700_000_000, "p": 0.6}]}

        client = ingestion.PolymarketClient(fetcher)
        at = datetime.fromtimestamp(1_700_000_001, tz=timezone.utc)

        self.assertAlmostEqual(client.price_at_start("token", at), 0.6)
        self.assertEqual(len(calls), 3)
        self.assertIn("fidelity=1", calls[0])
        self.assertIn("fidelity=5", calls[1])
        self.assertIn("fidelity=30", calls[2])

    def test_price_retries_coarser_history_after_timeout(self) -> None:
        calls = []

        def fetcher(url):
            calls.append(url)
            if "fidelity=1" in url:
                raise RuntimeError("Could not reach Polymarket: timed out")
            return {"history": [{"t": 1_700_000_000, "p": 0.6}]}

        client = ingestion.PolymarketClient(fetcher)
        at = datetime.fromtimestamp(1_700_000_001, tz=timezone.utc)

        self.assertAlmostEqual(client.price_at_start("token", at), 0.6)
        self.assertEqual(len(calls), 2)
        self.assertIn("fidelity=5", calls[1])

    def test_end_price_uses_resolution_completed_by_end_time(self) -> None:
        end = datetime(2026, 6, 28, 23, 0, tzinfo=timezone.utc)
        client = ingestion.PolymarketClient(lambda _: {
            "history": [{"t": int(end.timestamp()) - 60, "p": 0.9985}]
        })
        client.resolutions["winner"] = ingestion.MarketResolution(
            1.0,
            datetime(2026, 6, 28, 22, 30, tzinfo=timezone.utc),
        )

        self.assertEqual(client.price_at_end("winner", end), 1.0)

    def test_end_price_keeps_history_if_resolution_happened_later(self) -> None:
        end = datetime(2026, 6, 28, 23, 0, tzinfo=timezone.utc)
        client = ingestion.PolymarketClient(lambda _: {
            "history": [{"t": int(end.timestamp()) - 60, "p": 0.9985}]
        })
        client.resolutions["winner"] = ingestion.MarketResolution(
            1.0,
            datetime(2026, 7, 19, 23, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(client.price_at_end("winner", end), 0.9985)

    def test_settlement_price_uses_official_binary_resolution(self) -> None:
        client = ingestion.PolymarketClient(lambda _: {})
        client.resolutions["winner"] = ingestion.MarketResolution(
            1.0,
            datetime(2026, 7, 19, 23, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(client.settlement_price("winner"), 1.0)

    def test_settlement_price_rejects_missing_or_non_binary_resolution(self) -> None:
        client = ingestion.PolymarketClient(lambda _: {})

        with self.assertRaisesRegex(RuntimeError, "No conclusive resolution"):
            client.settlement_price("missing")

        client.resolutions["invalid"] = ingestion.MarketResolution(
            0.5,
            datetime(2026, 7, 19, 23, 0, tzinfo=timezone.utc),
        )
        with self.assertRaisesRegex(RuntimeError, "non-binary payout"):
            client.settlement_price("invalid")

    def test_only_records_conclusively_resolved_market_prices(self) -> None:
        market = {
            "closed": True,
            "umaResolutionStatus": "resolved",
            "closedTime": "2026-06-28T22:30:00Z",
            "clobTokenIds": '["winner", "loser"]',
            "outcomePrices": '["1", "0"]',
        }
        resolution = ingestion.market_resolution(market, "winner")
        self.assertEqual(resolution, ingestion.MarketResolution(
            1.0,
            datetime(2026, 6, 28, 22, 30, tzinfo=timezone.utc),
        ))

        self.assertIsNone(ingestion.market_resolution(
            market | {"closed": False}, "winner"
        ))
        self.assertIsNone(ingestion.market_resolution(
            market | {"umaResolutionStatus": "proposed"}, "winner"
        ))
        self.assertIsNone(ingestion.market_resolution(
            market | {"closedTime": ""}, "winner"
        ))

    def test_collects_every_match_and_writes_csv(self) -> None:
        class FakeClient:
            def resolve(self, config, values, event_tag):
                return f"{config.name}:{values.get('team', 'match')}"

            def price_at_start(self, token_id, at):
                return at.timestamp()

            def price_at_end(self, token_id, at):
                return at.timestamp()

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "matches.txt"
            output = Path(directory) / "prices.csv"
            source.write_text(
                "2026-06-28 3:00 PM | 2026-06-28 8:00 PM | "
                "South Africa vs Canada\n"
                "2026-06-29 1:00 PM | 2026-06-29 6:00 PM | "
                "Brazil vs Japan\n",
                encoding="utf-8",
            )
            rows = ingestion.collect_matches(
                source, FakeClient(), [DRAW, TOURNAMENT], "World Cup"
            )
            ingestion.write_csv(output, rows, [DRAW, TOURNAMENT])

            with output.open(encoding="utf-8", newline="") as file:
                saved = list(csv.DictReader(file))

        self.assertEqual(len(saved), 4)
        self.assertEqual(saved[0]["country"], "South Africa")
        self.assertEqual(saved[0]["match"], "south-africa-canada")
        self.assertIn("draw_start", saved[0])
        self.assertIn("draw_end", saved[0])
        self.assertIn("tournament_winner_start", saved[0])
        self.assertNotEqual(saved[0]["draw_start"], saved[0]["draw_end"])
        self.assertEqual(saved[0]["end_edt"], "2026-06-28 08:15 PM EDT")


if __name__ == "__main__":
    unittest.main()

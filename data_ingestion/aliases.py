"""Polymarket naming differences, kept separate from ingestion logic.

Add future team-name exceptions here. The outer key is the logical market
name because Polymarket can use a different spelling for the same team in
different markets.
"""

TEAM_ALIASES = {
    "game_winner": {
        "Ivory Coast": "Cote d'Ivoire",
        "Congo DR": "DR Congo",
        "Bosnia-Herzegovina": "Bosnia and Herzegovina",
        "Cape Verde": "Cabo Verde",
        "Los Angeles Rams": "Rams",
        "Carolina Panthers": "Panthers",
        "Green Bay Packers": "Packers",
        "Chicago Bears": "Bears",
        "Buffalo Bills": "Bills",
        "Jacksonville Jaguars": "Jaguars",
        "San Francisco 49ers": "49ers",
        "Philadelphia Eagles": "Eagles",
        "Los Angeles Chargers": "Chargers",
        "New England Patriots": "Patriots",
        "Houston Texans": "Texans",
        "Pittsburgh Steelers": "Steelers",
        "Denver Broncos": "Broncos",
        "Seattle Seahawks": "Seahawks",
    },
    "tournament_loss": {
        "United States": "USA",
    },
    "championship_loss": {
        # The archived 2025 NBA outright uses "LA", while the fixture and
        # series markets use the franchise's full city name.
        "Los Angeles Clippers": "LA Clippers",
        # The Worlds match event uses a straight apostrophe, while its
        # archived outright question uses a curly apostrophe.
        "Anyone's Legend": "Anyone’s Legend",
        # The 2025-26 UCL outright abbreviates or anglicizes several names
        # used by the round-advancement markets.
        "Atlético Madrid": "Atletico Madrid",
        "Bayern München": "Bayern Munich",
        "Bodø/Glimt": "Bodo Glimt",
        "Manchester City": "Man City",
        "Paris Saint-Germain (PSG)": "PSG",
        "Sporting CP": "Sporting",
        "Tottenham Hotspur": "Tottenham",
    },
    "series_winner": {
        "Philadelphia 76ers": "76ers",
        "Boston Celtics": "Celtics",
        "Los Angeles Lakers": "Lakers",
        "Houston Rockets": "Rockets",
        "Minnesota Timberwolves": "Timberwolves",
        "Denver Nuggets": "Nuggets",
        "New York Knicks": "Knicks",
        "Atlanta Hawks": "Hawks",
        "Toronto Raptors": "Raptors",
        "Cleveland Cavaliers": "Cavaliers",
        "Detroit Pistons": "Pistons",
        "Orlando Magic": "Magic",
        "Phoenix Suns": "Suns",
        "Oklahoma City Thunder": "Thunder",
        "San Antonio Spurs": "Spurs",
        "Portland Trail Blazers": "Trail Blazers",
        "Miami Heat": "Heat",
        "Milwaukee Bucks": "Bucks",
        "Golden State Warriors": "Warriors",
        "Los Angeles Clippers": "Clippers",
        "Memphis Grizzlies": "Grizzlies",
        "Indiana Pacers": "Pacers",
        "Pittsburgh Penguins": "Penguins",
        "Philadelphia Flyers": "Flyers",
        "Buffalo Sabres": "Sabres",
        "Boston Bruins": "Bruins",
        "Minnesota Wild": "Wild",
        "Dallas Stars": "Stars",
        "Carolina Hurricanes": "Hurricanes",
        "Ottawa Senators": "Senators",
        "Montreal Canadiens": "Canadiens",
        "Tampa Bay Lightning": "Lightning",
        "Utah Mammoth": "Mammoth",
        "Vegas Golden Knights": "Golden Knights",
        "Anaheim Ducks": "Ducks",
        "Edmonton Oilers": "Oilers",
        "Colorado Avalanche": "Avalanche",
        "Los Angeles Kings": "Kings",
        "Cleveland Guardians": "Guardians",
        "Detroit Tigers": "Tigers",
        "Chicago Cubs": "Cubs",
        "San Diego Padres": "Padres",
        "New York Yankees": "Yankees",
        "Boston Red Sox": "Red Sox",
        "Los Angeles Dodgers": "Dodgers",
        "Cincinnati Reds": "Reds",
        "Seattle Mariners": "Mariners",
        "Toronto Blue Jays": "Blue Jays",
        "Milwaukee Brewers": "Brewers",
        "Philadelphia Phillies": "Phillies",
    },
}


TOKEN_ALIASES = {
    "game_winner": {
        "Los Angeles Rams": "Rams",
        "Carolina Panthers": "Panthers",
        "Green Bay Packers": "Packers",
        "Chicago Bears": "Bears",
        "Buffalo Bills": "Bills",
        "Jacksonville Jaguars": "Jaguars",
        "San Francisco 49ers": "49ers",
        "Philadelphia Eagles": "Eagles",
        "Los Angeles Chargers": "Chargers",
        "New England Patriots": "Patriots",
        "Houston Texans": "Texans",
        "Pittsburgh Steelers": "Steelers",
        "Denver Broncos": "Broncos",
        "Seattle Seahawks": "Seahawks",
    },
    "to_advance": {
        "Carolina Hurricanes": "Hurricanes",
        "Colorado Avalanche": "Avalanche",
        "Dallas Stars": "Stars",
        "Edmonton Oilers": "Oilers",
        "Florida Panthers": "Panthers",
        "Los Angeles Kings": "Kings",
        "Minnesota Wild": "Wild",
        "Montreal Canadiens": "Canadiens",
        "New Jersey Devils": "Devils",
        "Ottawa Senators": "Senators",
        "St. Louis Blues": "Blues",
        "Tampa Bay Lightning": "Lightning",
        "Toronto Maple Leafs": "Maple Leafs",
        "Vegas Golden Knights": "Golden Knights",
        "Washington Capitals": "Capitals",
        "Winnipeg Jets": "Jets",
    },
    "series_winner": {
        "Philadelphia 76ers": "76ers",
        "Boston Celtics": "Celtics",
        "Los Angeles Lakers": "Lakers",
        "Houston Rockets": "Rockets",
        # This outcome changed across archived seasons/rounds.
        "Minnesota Timberwolves": (
            "Wolves || Timberwolves || Twolves || T-Wolves"
        ),
        "Denver Nuggets": "Nuggets",
        "New York Knicks": "Knicks",
        "Atlanta Hawks": "Hawks",
        "Toronto Raptors": "Raptors",
        "Cleveland Cavaliers": "Cavs",
        "Detroit Pistons": "Pistons",
        "Orlando Magic": "Magic",
        "Phoenix Suns": "Suns",
        "Oklahoma City Thunder": "Thunder",
        "San Antonio Spurs": "Spurs",
        "Portland Trail Blazers": "Blazers",
        "Miami Heat": "Heat",
        "Milwaukee Bucks": "Bucks",
        "Golden State Warriors": "Warriors",
        "Los Angeles Clippers": "Clippers",
        "Memphis Grizzlies": "Grizzlies",
        "Indiana Pacers": "Pacers",
        # These short names are used only to build the archived Worlds event
        # slugs; the moneyline outcomes themselves use the full team names.
        "Gen.G": "gen",
        "Hanwha Life Esports": "hle1",
        "KT Rolster": "kt",
        "CTBC Flying Oyster": "cfo",
        "G2 Esports": "g2",
        "Top Esports": "tes",
        "Anyone's Legend": "al",
        "T1": "t1",
        "Pittsburgh Penguins": "Penguins",
        "Philadelphia Flyers": "Flyers",
        "Buffalo Sabres": "Sabres",
        "Boston Bruins": "Bruins",
        "Minnesota Wild": "Wild",
        "Dallas Stars": "Stars",
        "Carolina Hurricanes": "Canes",
        "Ottawa Senators": "Senators",
        "Montreal Canadiens": "Habs",
        "Tampa Bay Lightning": "Lightning",
        "Utah Mammoth": "Mammoth",
        "Vegas Golden Knights": "Knights",
        "Anaheim Ducks": "Ducks",
        "Edmonton Oilers": "Oilers",
        "Colorado Avalanche": "Avalanche",
        "Los Angeles Kings": "Kings",
        "Cleveland Guardians": "Guardians",
        "Detroit Tigers": "Tigers",
        "Chicago Cubs": "Cubs",
        "San Diego Padres": "Padres",
        "New York Yankees": "Yankees",
        "Boston Red Sox": "Red Sox",
        "Los Angeles Dodgers": "Dodgers",
        "Cincinnati Reds": "Reds",
        "Seattle Mariners": "Mariners",
        "Toronto Blue Jays": "Blue Jays",
        "Milwaukee Brewers": "Brewers",
        "Philadelphia Phillies": "Phillies",
    },
}


# Generic ingestion reads these definitions by event tag. Add a new sport or
# season here; the ingestion logic in polymarket.py should not need to change.
MARKETS_BY_EVENT_TAG = {
    "Wimbledon": (
        {
            "name": "mens_game_winner",
            "scope": "team",
            "label": "{team}",
            "search": "Wimbledon ATP: {team_1} vs {team_2}",
            "event": "Wimbledon ATP: {team_1} vs {team_2}",
            "market": "Wimbledon ATP: {team_1} vs {team_2}",
            "token": "{team_token}",
            "output_name": "game_winner",
        },
        {
            "name": "mens_championship_loss",
            "scope": "team",
            "label": "{team}",
            "search": "Will {team} be the 2026 Men’s Wimbledon winner?",
            "event": "2026 Men’s Wimbledon Winner",
            "market": "Will {team} be the 2026 Men’s Wimbledon winner?",
            "token": "NO",
            "output_name": "championship_loss",
            "event_slug": "2026-mens-wimbledon-winner",
        },
    ),
    "FIFA World Cup": (
        {
            "name": "game_winner",
            "scope": "team",
            "label": "{team}",
            "search": (
                "{team_1} vs. {team_2}: Team to Advance || "
                "{team_1} vs. {team_2}: Team to Win"
            ),
            "event": "{team_1} vs {team_2}",
            "market": (
                "{team_1} vs. {team_2}: Team to Advance || "
                "{team_1} vs. {team_2}: Team to Win"
            ),
            "token": "{team}",
            "event_suffix": "-more-markets",
        },
        {
            "name": "tournament_loss",
            "scope": "team",
            "label": "{team}",
            "search": "Will {team} win the 2026 FIFA World Cup?",
            "event": "World Cup Winner",
            "market": "Will {team} win the 2026 FIFA World Cup?",
            "token": "NO",
        },
    ),
    "2026 NBA Playoffs": (
        {
            "name": "series_winner",
            "scope": "team",
            "label": "{team}",
            "search": (
                "NBA Playoffs: Who Will Win Series? - "
                "{team_1} vs. {team_2}"
            ),
            "event": (
                "NBA Playoffs: Who Will Win Series? - "
                "{team_1} vs. {team_2}"
            ),
            "market": (
                "NBA Playoffs: Who Will Win Series? - "
                "{team_1} vs. {team_2}"
            ),
            "token": "{team_token} || {team}",
        },
        {
            "name": "advance_to_finals",
            "scope": "team",
            "label": "{team}",
            "search": "Will {team} advance to the 2026 NBA Finals?",
            "event": "NBA Playoffs: Team to advance to NBA Finals",
            "market": "Will {team} advance to the 2026 NBA Finals?",
            "token": "YES",
            "output_name": "series_winner",
        },
        {
            "name": "championship_loss",
            "scope": "team",
            "label": "{team}",
            "search": "Will the {team} win the 2026 NBA Finals?",
            "event": "2026 NBA Champion",
            "market": "Will the {team} win the 2026 NBA Finals?",
            "token": "NO",
        },
    ),
    "NBA Playoffs": (
        {
            "name": "series_winner",
            "scope": "team",
            "label": "{team}",
            "search": (
                "NBA Playoffs: {team_1} vs. {team_2} (To Advance)"
            ),
            "event": (
                "NBA Playoffs: {team_1} vs. {team_2} (To Advance)"
            ),
            "market": (
                "NBA Playoffs: {team_1} vs. {team_2} (To Advance)"
            ),
            "token": "{team_token} || {team}",
        },
        {
            "name": "championship_loss",
            "scope": "team",
            "label": "{team}",
            "search": "Will the {team} win the 2025 NBA Finals?",
            "event": "NBA Champion",
            "market": "Will the {team} win the 2025 NBA Finals?",
            "token": "NO",
            "event_slug": "nba-champion-2024-2025",
        },
    ),
    "NHL": (
        {
            "name": "to_advance",
            "scope": "team",
            "label": "{team}",
            "search": (
                "NHL Playoffs: {team_1} vs. {team_2} (To Advance) || "
                "NHL Playoffs: {team_1_token} vs. {team_2_token} "
                "(To Advance)"
            ),
            # The 2025 event titles inconsistently use full team names and
            # short outcome names. Match the common event prefix, then use
            # the exact full/short market-title alternatives above.
            "event": "NHL Playoffs",
            "market": (
                "NHL Playoffs: {team_1} vs. {team_2} (To Advance) || "
                "NHL Playoffs: {team_1_token} vs. {team_2_token} "
                "(To Advance)"
            ),
            "token": "{team_token}",
            "output_name": "series_winner",
        },
        {
            "name": "east_champion",
            "scope": "team",
            "label": "{team}",
            "search": "Will the {team} be Eastern Conference champions?",
            "event": "NHL Eastern Conference Champion",
            "market": "Will the {team} be Eastern Conference champions?",
            "token": "YES",
            "output_name": "series_winner",
            "event_slug": "nhl-eastern-conference-champion",
        },
        {
            "name": "west_champion",
            "scope": "team",
            "label": "{team}",
            "search": "Will the {team} win the Western Conference?",
            "event": "NHL Western Conference Champion",
            "market": "Will the {team} win the Western Conference?",
            "token": "YES",
            "output_name": "series_winner",
            "event_slug": "nhl-western-conference-champion",
        },
        {
            "name": "championship_loss",
            "scope": "team",
            "label": "{team}",
            "search": "Will the {team} win the 2025 Stanley Cup?",
            "event": "Stanley Cup Champion 2025",
            "market": "Will the {team} win the 2025 Stanley Cup?",
            "token": "NO",
        },
    ),
    "2026 NHL Playoffs": (
        {
            "name": "series_winner",
            "scope": "team",
            "label": "{team}",
            "search": (
                "NHL Playoffs: Who Will Win Series? - "
                "{team_1} vs. {team_2}"
            ),
            "event": (
                "NHL Playoffs: Who Will Win Series? - "
                "{team_1} vs. {team_2}"
            ),
            "market": (
                "NHL Playoffs: Who Will Win Series? - "
                "{team_1} vs. {team_2}"
            ),
            "token": "{team_token}",
        },
        {
            "name": "east_champion",
            "scope": "team",
            "label": "{team}",
            "search": "Will the {team} win the Eastern Conference?",
            "event": "NHL: Eastern Conference Champion",
            "market": "Will the {team} win the Eastern Conference?",
            "token": "YES",
            "output_name": "series_winner",
        },
        {
            "name": "west_champion",
            "scope": "team",
            "label": "{team}",
            "search": "Will the {team} win the Western Conference?",
            "event": "NHL: Western Conference Champion",
            "market": "Will the {team} win the Western Conference?",
            "token": "YES",
            "output_name": "series_winner",
        },
        {
            "name": "championship_loss",
            "scope": "team",
            "label": "{team}",
            "search": "Will the {team} win the 2026 NHL Stanley Cup?",
            "event": "2026 NHL Stanley Cup Champion",
            "market": "Will the {team} win the 2026 NHL Stanley Cup?",
            "token": "NO",
        },
    ),
    "league of legends": (
        {
            "name": "series_winner",
            "scope": "team",
            "label": "{team}",
            "search": "LoL: {team_1} vs {team_2} (BO5)",
            "event": "LoL: {team_1} vs {team_2} (BO5)",
            "market": "LoL: {team_1} vs {team_2} (BO5)",
            "token": "{team}",
            "event_slug": "lol-{team_1_token}-{team_2_token}-{date}",
        },
        {
            "name": "championship_loss",
            "scope": "team",
            "label": "{team}",
            "search": "Will {team} win LoL Worlds 2025?",
            "event": "LoL Worlds 2025 Winner",
            "market": "Will {team} win LoL Worlds 2025?",
            "token": "NO",
            "event_slug": "lol-worlds-2025-winner",
        },
    ),
    "Champions League": (
        {
            "name": "reach_quarter_finals",
            "scope": "team",
            "label": "{team}",
            "search": (
                "Will {team} reach the UEFA Champions League "
                "quarter-finals?"
            ),
            "event": (
                "UEFA Champions League: Team to reach quarter-finals"
            ),
            "market": (
                "Will {team} reach the UEFA Champions League "
                "quarter-finals?"
            ),
            "token": "YES",
            "output_name": "series_winner",
            "event_slug": "ucl-team-to-reach-quarter-finals",
        },
        {
            "name": "reach_semifinal",
            "scope": "team",
            "label": "{team}",
            "search": (
                "Will {team} reach the UEFA Champions League semifinal?"
            ),
            "event": "UEFA Champions League: Team to advance to semis",
            "market": (
                "Will {team} reach the UEFA Champions League semifinal?"
            ),
            "token": "YES",
            "output_name": "series_winner",
            "event_slug": (
                "uefa-champions-league-team-to-advance-to-semis"
            ),
        },
        {
            "name": "reach_final",
            "scope": "team",
            "label": "{team}",
            "search": "Will {team} reach the UEFA Champions League final?",
            "event": "UEFA Champions League: Team to reach final",
            "market": "Will {team} reach the UEFA Champions League final?",
            "token": "YES",
            "output_name": "series_winner",
            "event_slug": "uefa-champions-league-team-to-reach-final",
        },
        {
            "name": "championship_loss",
            "scope": "team",
            "label": "{team}",
            "search": "Will {team} win the 2025–26 Champions League?",
            "event": "UEFA Champions League Winner",
            "market": "Will {team} win the 2025–26 Champions League?",
            "token": "NO",
            "event_slug": "uefa-champions-league-winner",
        },
    ),
    "MLB Playoffs": (
        {
            "name": "series_winner",
            "scope": "team",
            "label": "{team}",
            "search": "{team_1} vs. {team_2} Series Winner",
            "event": "{team_1} vs. {team_2} Series Winner",
            "market": "{team_1} vs. {team_2} Series Winner",
            "token": "{team_token}",
        },
        {
            "name": "championship_loss",
            "scope": "team",
            "label": "{team}",
            "search": "Will the {team} win the 2025 World Series?",
            "event": "World Series Champion 2025",
            "market": "Will the {team} win the 2025 World Series?",
            "token": "NO",
        },
    ),
    "NFL": (
        {
            "name": "game_winner",
            "scope": "team",
            "label": "{team}",
            "search": "{team_1} vs. {team_2}",
            "event": "{team_1} vs. {team_2}",
            "market": "{team_1} vs. {team_2}",
            "token": "{team_token}",
        },
        {
            "name": "championship_loss",
            "scope": "team",
            "label": "{team}",
            "search": "Will the {team} win Super Bowl 2026?",
            "event": "Big Game Champion 2026",
            "market": "Will the {team} win Super Bowl 2026?",
            "token": "NO",
        },
    ),
}


def markets_for_event_tag(event_tag: str) -> tuple[dict[str, str], ...]:
    """Return configured markets for an event tag, case-insensitively."""
    wanted = event_tag.casefold()
    for configured_tag, markets in MARKETS_BY_EVENT_TAG.items():
        if configured_tag.casefold() == wanted:
            return markets
    available = ", ".join(sorted(MARKETS_BY_EVENT_TAG))
    raise KeyError(
        f'No market configuration for event tag "{event_tag}". '
        f"Available tags: {available}"
    )

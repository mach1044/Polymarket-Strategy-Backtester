from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen

if __package__:
    from .aliases import TEAM_ALIASES, TOKEN_ALIASES, markets_for_event_tag
else:
    # Keep direct script execution working in addition to ``python -m``.
    from aliases import TEAM_ALIASES, TOKEN_ALIASES, markets_for_event_tag


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MATCH_DATA_DIR = PROJECT_ROOT / "data" / "match_data"

GAMMA_SEARCH = "https://gamma-api.polymarket.com/public-search"
GAMMA_EVENT = "https://gamma-api.polymarket.com/events/slug"
GAMMA_EVENTS = "https://gamma-api.polymarket.com/events"
GAMMA_TAG = "https://gamma-api.polymarket.com/tags/slug"
CLOB_HISTORY = "https://clob.polymarket.com/prices-history"
CLOB_BATCH_HISTORY = "https://clob.polymarket.com/batch-prices-history"
EDT = timezone(timedelta(hours=-4), name="EDT")
EST = timezone(timedelta(hours=-5), name="EST")
MARKET_TIMEZONES = {"EDT": EDT, "EST": EST}
POST_RESULT_EXIT_DELAY = timedelta(minutes=15)
RESOLVED_RESULT_OUTPUTS = frozenset({"game_winner", "series_winner"})


@dataclass(frozen=True)
class MarketConfig:
    name: str
    scope: str
    label: str
    search: str
    event: str
    market: str
    token: str
    event_suffix: str = ""
    output_name: str = ""
    event_slug: str = ""


@dataclass(frozen=True)
class Match:
    date: str
    time: str
    team_1: str
    team_2: str
    start_utc: datetime
    end_utc: datetime
    market_timezone: timezone
    markets: frozenset[str] | None = None


@dataclass(frozen=True)
class MarketResolution:
    price: float
    resolved_at: datetime


MATCH_LINE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2}\s+[AP]M)\s*\|\s*"
    r"(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2}\s+[AP]M)\s*\|\s*"
    r"(.+?)\s+vs\.?\s+([^|]+?)"
    r"(?:\s*\|\s*([A-Za-z0-9_, ]+))?$",
    re.IGNORECASE,
)
DataRow = dict[str, str]


class NotFoundError(RuntimeError):
    pass


def normalize(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return " ".join(re.findall(r"[a-z0-9]+", ascii_value.lower()))


def render(template: str, values: dict[str, str]) -> str:
    return template.format(**values)


def render_options(template: str, values: dict[str, str]) -> list[str]:
    return [render(option.strip(), values) for option in template.split("||")]


def parse_matches(text: str) -> list[Match]:
    matches = []
    timezone_match = re.search(
        r"Times shown[^\n]*\b(EDT|EST)\b", text, re.IGNORECASE
    )
    market_timezone = MARKET_TIMEZONES[
        timezone_match.group(1).upper() if timezone_match else "EDT"
    ]
    for line in text.splitlines():
        found = MATCH_LINE.fullmatch(line.strip())
        if not found:
            continue
        (
            start_date,
            start_time,
            end_date,
            end_time,
            team_1,
            team_2,
            market_names,
        ) = found.groups()
        start_local = datetime.strptime(
            f"{start_date} {start_time.upper()}", "%Y-%m-%d %I:%M %p"
        ).replace(tzinfo=market_timezone)
        end_local = datetime.strptime(
            f"{end_date} {end_time.upper()}", "%Y-%m-%d %I:%M %p"
        ).replace(tzinfo=market_timezone)
        if end_local < start_local:
            raise ValueError(f"Match ends before it starts: {line.strip()}")
        matches.append(
            Match(
                start_date,
                start_time.upper(),
                team_1.strip(),
                team_2.strip(),
                start_local.astimezone(timezone.utc),
                end_local.astimezone(timezone.utc),
                market_timezone,
                (
                    frozenset(
                        name.strip() for name in market_names.split(",")
                    )
                    if market_names
                    else None
                ),
            )
        )
    return matches


def aliases_for_file(
    file_path: Path, known_aliases: dict[str, dict[str, str]]
) -> dict[str, str]:
    matches = parse_matches(file_path.read_text(encoding="utf-8"))
    teams = {
        team
        for match in matches
        for team in (match.team_1, match.team_2)
    }
    return {
        f"{market}:{team}": polymarket_name
        for market, market_aliases in known_aliases.items()
        for team, polymarket_name in market_aliases.items()
        if team in teams
    }


def team_aliases_for_file(file_path: Path) -> dict[str, str]:
    """Return event-name aliases needed by a fixture file."""
    return aliases_for_file(file_path, TEAM_ALIASES)


def token_aliases_for_file(file_path: Path) -> dict[str, str]:
    """Return outcome-token aliases needed by a fixture file."""
    return aliases_for_file(file_path, TOKEN_ALIASES)


def json_list(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    return [str(item) for item in value] if isinstance(value, list) else []


def token_in_market(market: dict[str, Any], wanted: str) -> str | None:
    outcomes = json_list(market.get("outcomes"))
    token_ids = json_list(market.get("clobTokenIds"))
    for outcome, token_id in zip(outcomes, token_ids):
        if normalize(outcome) == normalize(wanted):
            return token_id
    return None


def market_resolution(
    market: dict[str, Any], token_id: str
) -> MarketResolution | None:
    """Return a token's final price only when the market is conclusively resolved."""
    if market.get("closed") is not True:
        return None
    if normalize(str(market.get("umaResolutionStatus") or "")) != "resolved":
        return None

    token_ids = json_list(market.get("clobTokenIds"))
    outcome_prices = json_list(market.get("outcomePrices"))
    if len(token_ids) != len(outcome_prices):
        return None
    try:
        price = float(outcome_prices[token_ids.index(token_id)])
    except (ValueError, IndexError):
        return None
    if not 0.0 <= price <= 1.0:
        return None

    closed_time = str(market.get("closedTime") or "")
    try:
        resolved_at = datetime.fromisoformat(closed_time.replace("Z", "+00:00"))
    except ValueError:
        return None
    if resolved_at.tzinfo is None or resolved_at.utcoffset() is None:
        return None
    return MarketResolution(price, resolved_at.astimezone(timezone.utc))


def event_has_tag(event: dict[str, Any], wanted: str) -> bool:
    wanted = normalize(wanted)
    return any(
        wanted in {
            normalize(str(tag.get("label") or "")),
            normalize(str(tag.get("slug") or "")),
        }
        for tag in event.get("tags", [])
        if isinstance(tag, dict)
    )


def token_markets_in_payload(
    payload: Any,
    config: MarketConfig,
    values: dict[str, str],
    event_tag: str = "",
) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        return {}
    event_title = normalize(render(config.event, values))
    titles = {normalize(title) for title in render_options(config.market, values)}
    wanted_outcomes = [
        outcome.strip()
        for rendered in render_options(config.token, values)
        for outcome in rendered.split("||")
    ]
    wanted_event_slug = (
        render(config.event_slug, values).casefold() if config.event_slug else ""
    )
    found = {}
    for event in payload.get("events", []):
        if event_tag and not event_has_tag(event, event_tag):
            continue
        if (
            wanted_event_slug
            and str(event.get("slug") or "").casefold() != wanted_event_slug
        ):
            continue
        actual_event = normalize(str(event.get("title") or ""))
        if actual_event != event_title and not actual_event.startswith(f"{event_title} "):
            continue
        for market in event.get("markets", []):
            if normalize(str(market.get("question") or "")) not in titles:
                continue
            token_id = None
            for wanted in wanted_outcomes:
                token_id = token_in_market(market, wanted)
                if token_id:
                    break
            if token_id:
                found[token_id] = market
    return found


def tokens_in_payload(
    payload: Any,
    config: MarketConfig,
    values: dict[str, str],
    event_tag: str = "",
) -> set[str]:
    return set(token_markets_in_payload(payload, config, values, event_tag))


def markets_from_fixture_year(
    markets: dict[str, dict[str, Any]], fixture_date: str
) -> dict[str, dict[str, Any]]:
    """Disambiguate reused market titles without guessing between same-year markets."""
    year = fixture_date[:4]
    if not re.fullmatch(r"\d{4}", year):
        return {}
    return {
        token_id: market
        for token_id, market in markets.items()
        if any(
            str(market.get(field) or "").startswith(year)
            for field in ("startDate", "endDate", "closedTime")
        )
    }


def fetch_json(url: str) -> Any:
    headers = {
        "User-Agent": "polymarket-data-ingestion/1.0",
        "Accept": "application/json",
    }
    history_token = ""
    if url.startswith(f"{CLOB_HISTORY}?"):
        params = parse_qs(urlsplit(url).query)
        history_token = params["market"][0]
        body = json.dumps({
            "markets": [history_token],
            "start_ts": int(params["startTs"][0]),
            "end_ts": int(params["endTs"][0]),
            "fidelity": int(params["fidelity"][0]),
        }).encode()
        request = Request(
            CLOB_BATCH_HISTORY,
            data=body,
            headers=headers | {"Content-Type": "application/json"},
            method="POST",
        )
    else:
        request = Request(url, headers=headers)
    attempts = 1 if url.startswith(CLOB_HISTORY) else 3
    for attempt in range(attempts):
        try:
            with urlopen(request, timeout=25) as response:
                payload = json.load(response)
                if history_token:
                    histories = payload.get("history", {})
                    return {"history": histories.get(history_token, [])}
                return payload
        except HTTPError as exc:
            if exc.code == 404:
                raise NotFoundError(
                    f"No Polymarket resource at {url.split('?')[0]}"
                ) from exc
            if 500 <= exc.code < 600 and attempt < attempts - 1:
                time.sleep(0.25 * (2**attempt))
                continue
            raise RuntimeError(f"HTTP {exc.code} from {url}") from exc
        except (URLError, TimeoutError) as exc:
            if attempt < attempts - 1:
                time.sleep(0.25 * (2**attempt))
                continue
            raise RuntimeError(
                f"Could not reach Polymarket at {url}: {exc}"
            ) from exc
    raise AssertionError("unreachable")


class PolymarketClient:
    def __init__(self, fetcher: Callable[[str], Any] = fetch_json) -> None:
        self.fetcher = fetcher
        self.cache: dict[str, Any] = {}
        self.resolutions: dict[str, MarketResolution] = {}

    def get(self, url: str) -> Any:
        if url not in self.cache:
            self.cache[url] = self.fetcher(url)
        return self.cache[url]

    def search(self, query: str) -> Any:
        params = urlencode(
            {
                "q": query,
                "limit_per_type": 50,
                "keep_closed_markets": 1,
                "search_profiles": "false",
            }
        )
        return self.get(f"{GAMMA_SEARCH}?{params}")

    def tagged_events(self, event_tag: str, date: str) -> dict[str, Any]:
        tag = self.get(f"{GAMMA_TAG}/{slug(event_tag)}")
        if not isinstance(tag, dict) or not tag.get("id"):
            raise RuntimeError(f'Polymarket tag "{event_tag}" was not found')
        day = datetime.strptime(date, "%Y-%m-%d")
        params = urlencode(
            {
                "tag_id": tag["id"],
                "limit": 100,
                "offset": 0,
                "end_date_min": (day - timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z"),
                "end_date_max": (day + timedelta(days=2)).strftime("%Y-%m-%dT23:59:59Z"),
                "order": "endDate",
                "ascending": "true",
            }
        )
        events = self.get(f"{GAMMA_EVENTS}?{params}")
        return {"events": events if isinstance(events, list) else []}

    def resolve(
        self, config: MarketConfig, values: dict[str, str], event_tag: str
    ) -> str:
        payloads = []
        if config.event_slug:
            exact_slug = render(config.event_slug, values)
            exact_event = self.get(f"{GAMMA_EVENT}/{exact_slug}")
            payloads.append({"events": [exact_event]})
        else:
            for query in render_options(config.search, values):
                payloads.append(self.search(query))
        if config.event_suffix:
            expected_event = normalize(render(config.event, values))
            base_events = [
                event
                for payload in payloads if isinstance(payload, dict)
                for event in payload.get("events", [])
                if isinstance(event, dict)
                and normalize(str(event.get("title") or "")) == expected_event
                and event_has_tag(event, event_tag)
            ]
            if not base_events and values.get("date"):
                dated_payload = self.tagged_events(event_tag, values["date"])
                payloads.append(dated_payload)
                base_events = [
                    event
                    for event in dated_payload["events"]
                    if isinstance(event, dict)
                    and normalize(str(event.get("title") or "")) == expected_event
                    and event_has_tag(event, event_tag)
                ]
            related_slugs = {
                str(event.get("slug"))
                for event in base_events
                if event.get("slug")
            }
            for event_slug in related_slugs:
                if event_slug:
                    try:
                        related = self.get(
                            f"{GAMMA_EVENT}/{event_slug}{config.event_suffix}"
                        )
                    except NotFoundError:
                        continue
                    payloads.append({"events": [related]})
        if values.get("date") and not config.event_slug:
            payloads.append(self.tagged_events(event_tag, values["date"]))

        token_markets = {}
        for payload in payloads:
            token_markets.update(
                token_markets_in_payload(payload, config, values, event_tag)
            )
        if token_markets and values.get("date"):
            token_markets = markets_from_fixture_year(
                token_markets, values["date"]
            )
        found = set(token_markets)
        if len(found) != 1:
            market = render(config.market, values)
            token = render(config.token, values)
            available_tags = sorted({
                str(tag.get("label") or tag.get("slug") or "")
                for payload in payloads if isinstance(payload, dict)
                for event in payload.get("events", []) if isinstance(event, dict)
                for tag in event.get("tags", []) if isinstance(tag, dict)
                if tag.get("label") or tag.get("slug")
            })
            available_events = sorted({
                f'{event.get("title")} [{event.get("slug")}]'
                for payload in payloads if isinstance(payload, dict)
                for event in payload.get("events", []) if isinstance(event, dict)
                if event_has_tag(event, event_tag)
            })
            available_markets = [
                f'{market.get("question")} -> {", ".join(json_list(market.get("outcomes")))}'
                for payload in payloads if isinstance(payload, dict)
                for event in payload.get("events", []) if isinstance(event, dict)
                if event_has_tag(event, event_tag)
                for market in event.get("markets", []) if isinstance(market, dict)
            ]
            available_markets.sort(
                key=lambda item: (
                    not any(word in normalize(item) for word in ("advance", "winner", " win ")),
                    item,
                )
            )
            raise RuntimeError(
                f'Expected one token for market "{market}", token "{token}", '
                f'event tag "{event_tag}"; found {len(found)}. '
                f"Candidate events: {'; '.join(available_events[:25]) or 'none'}. "
                f"Available event tags: {', '.join(available_tags) or 'none'}. "
                f"Candidate markets: {'; '.join(available_markets[:25]) or 'none'}"
            )
        token_id = found.pop()
        resolution = market_resolution(token_markets[token_id], token_id)
        if resolution is not None:
            self.resolutions[token_id] = resolution
        return token_id

    def price_at_start(self, token_id: str, at: datetime) -> float:
        end = int(at.timestamp())
        payload = None
        last_error = None
        for lookback_days in (2, 7):
            for fidelity in (1, 5, 30):
                params = urlencode(
                    {
                        "market": token_id,
                        "startTs": end - lookback_days * 24 * 60 * 60,
                        "endTs": end,
                        "fidelity": fidelity,
                    }
                )
                try:
                    candidate = self.get(f"{CLOB_HISTORY}?{params}")
                except RuntimeError as exc:
                    last_error = exc
                    continue
                if isinstance(candidate, dict) and candidate.get("history"):
                    payload = candidate
                    break
            if payload is not None:
                break
        if payload is None and last_error is not None:
            raise last_error
        points = []
        for item in payload.get("history", []) if isinstance(payload, dict) else []:
            try:
                timestamp, price = int(item["t"]), float(item["p"])
            except (KeyError, TypeError, ValueError):
                continue
            if timestamp <= end:
                points.append((timestamp, price))
        if not points:
            raise RuntimeError(f"No price found at or before {at.isoformat()} for token {token_id}")
        return max(points)[1]

    def price_at_end(self, token_id: str, at: datetime) -> float:
        """Use settlement only if the market had resolved by this end time."""
        resolution = self.resolutions.get(token_id)
        if resolution is not None and resolution.resolved_at <= at:
            return resolution.price
        return self.price_at_start(token_id, at)

    def settlement_price(self, token_id: str) -> float:
        """Return the official binary payout for a resolved result market."""
        resolution = self.resolutions.get(token_id)
        if resolution is None:
            raise RuntimeError(
                f"No conclusive resolution found for result token {token_id}"
            )
        if resolution.price not in (0.0, 1.0):
            raise RuntimeError(
                f"Result token {token_id} resolved to non-binary payout "
                f"{resolution.price}"
            )
        return resolution.price


def slug(value: str) -> str:
    return normalize(value).replace(" ", "-")


def format_market_time(value: datetime, market_timezone: timezone) -> str:
    abbreviation = market_timezone.tzname(None)
    return value.astimezone(market_timezone).strftime(
        f"%Y-%m-%d %I:%M %p {abbreviation}"
    )


def market_team(aliases: dict[str, str], market: str, team: str) -> str:
    return aliases.get(f"{market}:{team}", aliases.get(team, team))


def collect_matches(
    file_path: Path,
    client: PolymarketClient,
    markets: list[MarketConfig],
    event_tag: str,
    aliases: dict[str, str] | None = None,
    token_aliases: dict[str, str] | None = None,
) -> list[DataRow]:
    matches = parse_matches(file_path.read_text(encoding="utf-8"))
    if not matches:
        raise ValueError(f"No match lines found in {file_path}")
    configured_markets = {market.name for market in markets}
    fixture_markets = {
        market_name
        for match in matches
        for market_name in (match.markets or ())
    }
    unknown_markets = sorted(fixture_markets - configured_markets)
    if unknown_markets:
        raise ValueError(
            f"{file_path} references market(s) not defined by the active "
            f"configuration: {', '.join(unknown_markets)}"
        )
    rows = []
    aliases = team_aliases_for_file(file_path) | (aliases or {})
    token_aliases = token_aliases_for_file(file_path) | (token_aliases or {})
    for match in matches:
        exit_utc = match.end_utc + POST_RESULT_EXIT_DELAY
        active_markets = [
            config
            for config in markets
            if match.markets is None or config.name in match.markets
        ]
        output_names = [
            config.output_name or config.name for config in active_markets
        ]
        duplicate_outputs = sorted({
            output_name
            for output_name in output_names
            if output_names.count(output_name) > 1
        })
        if duplicate_outputs:
            raise ValueError(
                f'Fixture "{match.team_1} vs {match.team_2}" selects '
                "multiple markets for output column(s): "
                + ", ".join(duplicate_outputs)
            )
        match_name = f"{slug(match.team_1)}-{slug(match.team_2)}"
        rows_by_team = {
            match.team_1: {
                "country": match.team_1,
                "opponent": match.team_2,
                "match": match_name,
                "kickoff_edt": format_market_time(
                    match.start_utc, match.market_timezone
                ),
                "end_edt": format_market_time(
                    exit_utc, match.market_timezone
                ),
            },
            match.team_2: {
                "country": match.team_2,
                "opponent": match.team_1,
                "match": match_name,
                "kickoff_edt": format_market_time(
                    match.start_utc, match.market_timezone
                ),
                "end_edt": format_market_time(
                    exit_utc, match.market_timezone
                ),
            },
        }
        for config in active_markets:
            output_name = config.output_name or config.name
            market_team_1 = market_team(aliases, config.name, match.team_1)
            market_team_2 = market_team(aliases, config.name, match.team_2)
            token_team_1 = market_team(
                token_aliases, config.name, match.team_1
            )
            token_team_2 = market_team(
                token_aliases, config.name, match.team_2
            )
            base = {
                "team_1": market_team_1,
                "team_2": market_team_2,
                "team_1_token": token_team_1,
                "team_2_token": token_team_2,
                "date": match.date,
            }
            targets = [(base, [match.team_1, match.team_2])]
            if config.scope == "team":
                targets = [
                    (
                        base | {
                            "team": market_team_1,
                            "opponent": market_team_2,
                            "team_token": token_team_1,
                            "opponent_token": token_team_2,
                        },
                        [match.team_1],
                    ),
                    (
                        base | {
                            "team": market_team_2,
                            "opponent": market_team_1,
                            "team_token": token_team_2,
                            "opponent_token": token_team_1,
                        },
                        [match.team_2],
                    ),
                ]
            for values, teams in targets:
                token_id = client.resolve(config, values, event_tag)
                start_price = client.price_at_start(token_id, match.start_utc)
                if output_name in RESOLVED_RESULT_OUTPUTS:
                    end_price = client.settlement_price(token_id)
                else:
                    end_price = client.price_at_end(token_id, exit_utc)
                for team in teams:
                    rows_by_team[team][f"{output_name}_start"] = f"{start_price:.6f}"
                    rows_by_team[team][f"{output_name}_end"] = f"{end_price:.6f}"
        rows.extend(rows_by_team.values())
    return rows


def write_csv(path: Path, rows: list[DataRow], markets: list[MarketConfig]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["country", "opponent", "match", "kickoff_edt", "end_edt"]
    output_names = dict.fromkeys(
        market.output_name or market.name for market in markets
    )
    fields += [
        column
        for name in output_names
        for column in (f"{name}_start", f"{name}_end")
    ]
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def configured_markets(event_tag: str) -> list[MarketConfig]:
    """Load generic market definitions for an event tag from the helper."""
    return [
        MarketConfig(**definition)
        for definition in markets_for_event_tag(event_tag)
    ]


def parse_args(
    argv: list[str] | None = None,
) -> tuple[
    Path,
    list[MarketConfig],
    str,
    Path,
    dict[str, str],
    dict[str, str],
]:
    parser = argparse.ArgumentParser(
        description=(
            "Collect historical Polymarket prices using the market and alias "
            "definitions registered for an event tag."
        )
    )
    parser.add_argument("file", type=Path)
    parser.add_argument("--event-tag", required=True)
    parser.add_argument(
        "--out",
        type=Path,
        default=MATCH_DATA_DIR / "polymarket_match_data.csv",
    )
    parser.add_argument(
        "--team-alias",
        action="append",
        default=[],
        metavar="[MARKET:]FILE_NAME=POLYMARKET_NAME",
    )
    parser.add_argument(
        "--token-alias",
        action="append",
        default=[],
        metavar="[MARKET:]FILE_NAME=POLYMARKET_TOKEN_NAME",
    )
    parser.add_argument(
        "--market",
        action="append",
        nargs=7,
        default=[],
        metavar=("NAME", "SCOPE", "LABEL", "SEARCH", "EVENT", "TITLE", "TOKEN"),
    )
    parser.add_argument(
        "--event-suffix",
        action="append",
        default=[],
        metavar="NAME=SUFFIX",
    )
    parser.add_argument(
        "--output-alias",
        action="append",
        default=[],
        metavar="NAME=OUTPUT_NAME",
    )
    args = parser.parse_args(argv)

    suffixes = {}
    for item in args.event_suffix:
        if "=" not in item:
            parser.error("--event-suffix must use NAME=SUFFIX")
        name, suffix = item.split("=", 1)
        suffixes[name] = suffix if suffix.startswith("-") else f"-{suffix}"

    output_names = {}
    for item in args.output_alias:
        if "=" not in item:
            parser.error("--output-alias must use NAME=OUTPUT_NAME")
        name, output_name = item.split("=", 1)
        if not re.fullmatch(r"[A-Za-z0-9_]+", output_name):
            parser.error(
                "--output-alias OUTPUT_NAME may contain only letters, "
                "numbers, and underscores"
            )
        output_names[name] = output_name

    try:
        markets = configured_markets(args.event_tag)
    except KeyError as exc:
        if not args.market:
            parser.error(str(exc.args[0]))
        markets = []
    if args.market:
        markets = []
        for name, scope, label, search, event, title, token in args.market:
            if not re.fullmatch(r"[A-Za-z0-9_]+", name):
                parser.error(
                    f'market name "{name}" may contain only letters, '
                    "numbers, and underscores"
                )
            if scope not in {"match", "team"}:
                parser.error(
                    f'market "{name}" scope must be "match" or "team"'
                )
            markets.append(
                MarketConfig(
                    name,
                    scope,
                    label,
                    search,
                    event,
                    title,
                    token,
                )
            )
    if len({market.name for market in markets}) != len(markets):
        parser.error("market names must be unique")

    market_names = {market.name for market in markets}
    unknown_suffixes = sorted(set(suffixes) - market_names)
    if unknown_suffixes:
        parser.error(
            "--event-suffix references unknown market(s): "
            + ", ".join(unknown_suffixes)
        )
    unknown_outputs = sorted(set(output_names) - market_names)
    if unknown_outputs:
        parser.error(
            "--output-alias references unknown market(s): "
            + ", ".join(unknown_outputs)
        )
    markets = [
        MarketConfig(
            market.name,
            market.scope,
            market.label,
            market.search,
            market.event,
            market.market,
            market.token,
            suffixes.get(market.name, market.event_suffix),
            output_names.get(market.name, market.output_name),
            market.event_slug,
        )
        for market in markets
    ]

    aliases_by_option = {}
    for option, items in (
        ("--team-alias", args.team_alias),
        ("--token-alias", args.token_alias),
    ):
        parsed = {}
        for item in items:
            if "=" not in item:
                parser.error(
                    f"{option} must use [MARKET:]FILE_NAME=POLYMARKET_NAME"
                )
            file_name, polymarket_name = item.split("=", 1)
            parsed[file_name] = polymarket_name
        aliases_by_option[option] = parsed
    return (
        args.file,
        markets,
        args.event_tag,
        args.out,
        aliases_by_option["--team-alias"],
        aliases_by_option["--token-alias"],
    )


def main(argv: list[str] | None = None) -> int:
    (
        file_path,
        markets,
        event_tag,
        output_path,
        aliases,
        token_aliases,
    ) = parse_args(argv)
    try:
        rows = collect_matches(
            file_path,
            PolymarketClient(),
            markets,
            event_tag,
            aliases,
            token_aliases,
        )
        write_csv(output_path, rows, markets)
        print(f"Saved {len(rows)} country-match rows to {output_path}")
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

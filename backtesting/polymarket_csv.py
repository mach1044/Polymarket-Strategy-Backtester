from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .engine import BacktestEngine, BacktestStats, Order, Side


MARKET_TIMEZONES = {
    "EDT": timezone(timedelta(hours=-4), name="EDT"),
    "EST": timezone(timedelta(hours=-5), name="EST"),
}
REQUIRED_COLUMNS = {
    "country",
    "match",
    "kickoff_edt",
    "end_edt",
    "game_winner_start",
    "game_winner_end",
}


@dataclass(frozen=True)
class GameWinnerRoundTrip:
    instrument: str
    match: str
    country: str
    start_time: datetime
    end_time: datetime
    start_price: float
    end_price: float


@dataclass(frozen=True)
class CsvSmokeTestResult:
    source_rows: int
    matches: int
    stats: BacktestStats


@dataclass(frozen=True)
class _ScheduledAction:
    action: str
    quote: GameWinnerRoundTrip
    price: float


def parse_market_timestamp(value: str) -> datetime:
    try:
        timestamp_text, abbreviation = value.rsplit(" ", 1)
        parsed = datetime.strptime(timestamp_text, "%Y-%m-%d %I:%M %p")
        market_timezone = MARKET_TIMEZONES[abbreviation]
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Invalid market timestamp: {value!r}") from exc
    return parsed.replace(tzinfo=market_timezone)


def game_winner_instrument(match: str, country: str) -> str:
    return f"game_winner::{match}::{country}"


def _parse_price(row_number: int, column: str, value: str) -> float:
    try:
        price = float(value)
    except ValueError as exc:
        raise ValueError(
            f"CSV row {row_number} has invalid {column}: {value!r}"
        ) from exc
    if not 0.0 <= price <= 1.0:
        raise ValueError(
            f"CSV row {row_number} has {column} outside [0, 1]: {price}"
        )
    return price


def load_game_winner_round_trips(path: Path) -> list[GameWinnerRoundTrip]:
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        columns = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            raise ValueError(f"{path} is missing columns: {', '.join(missing)}")

        quotes = []
        instruments = set()
        for row_number, row in enumerate(reader, start=2):
            instrument = game_winner_instrument(row["match"], row["country"])
            if instrument in instruments:
                raise ValueError(
                    f'{path} contains duplicate instrument "{instrument}"'
                )
            instruments.add(instrument)
            start_time = parse_market_timestamp(row["kickoff_edt"])
            end_time = parse_market_timestamp(row["end_edt"])
            if end_time < start_time:
                raise ValueError(
                    f"CSV row {row_number} ends before it starts"
                )
            quotes.append(
                GameWinnerRoundTrip(
                    instrument=instrument,
                    match=row["match"],
                    country=row["country"],
                    start_time=start_time,
                    end_time=end_time,
                    start_price=_parse_price(
                        row_number, "game_winner_start", row["game_winner_start"]
                    ),
                    end_price=_parse_price(
                        row_number, "game_winner_end", row["game_winner_end"]
                    ),
                )
            )
    return quotes


def run_csv_accounting_smoke_test(
    path: Path,
    initial_cash: float = 1_000.0,
    quantity_per_outcome: float = 1.0,
    fee_rate: float = 0.0,
) -> CsvSmokeTestResult:
    """Buy every match outcome at kickoff and close it at the end.

    Buying one share of both complementary match outcomes is deliberately not a
    strategy. With no fees, each match should cost and return approximately
    one dollar, making this a useful end-to-end accounting check.
    """
    quotes = load_game_winner_round_trips(path)
    schedule: dict[datetime, list[_ScheduledAction]] = defaultdict(list)
    for quote in quotes:
        schedule[quote.start_time].append(
            _ScheduledAction("open", quote, quote.start_price)
        )
        schedule[quote.end_time].append(
            _ScheduledAction("close", quote, quote.end_price)
        )

    engine = BacktestEngine(initial_cash=initial_cash, fee_rate=fee_rate)
    for timestamp in sorted(schedule):
        actions = schedule[timestamp]
        engine.update_prices(
            timestamp,
            {action.quote.instrument: action.price for action in actions},
        )
        for action in sorted(actions, key=lambda item: item.action):
            side = Side.SELL if action.action == "close" else Side.BUY
            engine.execute(
                Order(action.quote.instrument, side, quantity_per_outcome)
            )

    return CsvSmokeTestResult(
        source_rows=len(quotes),
        matches=len({quote.match for quote in quotes}),
        stats=engine.stats(),
    )

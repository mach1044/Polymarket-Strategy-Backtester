from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable, Mapping


EPSILON = 1e-12


class BacktestError(RuntimeError):
    """Base class for backtest execution failures."""


class InvalidOrderError(BacktestError):
    pass


class InsufficientCashError(BacktestError):
    pass


class InsufficientInventoryError(BacktestError):
    pass


class MissingPriceError(BacktestError):
    pass


class ChronologyError(BacktestError):
    pass


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class Order:
    instrument: str
    side: Side
    quantity: float


@dataclass
class Position:
    quantity: float = 0.0
    average_cost: float = 0.0


@dataclass(frozen=True)
class Trade:
    timestamp: datetime
    instrument: str
    side: Side
    quantity: float
    price: float
    notional: float
    fee: float
    realized_pnl: float
    cash_after: float
    position_after: float


@dataclass(frozen=True)
class PortfolioSnapshot:
    timestamp: datetime | None
    cash: float
    market_value: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float


@dataclass(frozen=True)
class BacktestStats:
    starting_equity: float
    ending_cash: float
    ending_market_value: float
    ending_equity: float
    total_pnl: float
    total_return: float | None
    realized_pnl: float
    unrealized_pnl: float
    max_drawdown: float
    trade_count: int
    buy_count: int
    sell_count: int
    winning_sells: int
    losing_sells: int
    breakeven_sells: int
    win_rate: float | None
    turnover: float
    fees_paid: float
    open_positions: int


def _validate_finite(name: str, value: float) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _validate_timestamp(timestamp: datetime) -> None:
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Backtest timestamps must be timezone-aware")


class BacktestEngine:
    """Execute long-only prediction-market orders against marked prices.

    The engine owns accounting and execution only. Data ingestion and strategy
    decisions intentionally live outside this class.
    """

    def __init__(
        self,
        initial_cash: float,
        initial_positions: Mapping[str, Position] | None = None,
        fee_rate: float = 0.0,
    ) -> None:
        self._cash = _validate_finite("initial_cash", initial_cash)
        if self._cash < 0.0:
            raise ValueError("initial_cash cannot be negative")
        self._fee_rate = _validate_finite("fee_rate", fee_rate)
        if not 0.0 <= self._fee_rate < 1.0:
            raise ValueError("fee_rate must be in [0, 1)")

        self._positions: dict[str, Position] = {}
        for instrument, position in (initial_positions or {}).items():
            if not instrument:
                raise ValueError("Position instruments cannot be blank")
            quantity = _validate_finite("position quantity", position.quantity)
            average_cost = _validate_finite(
                "position average_cost", position.average_cost
            )
            if quantity < 0.0:
                raise ValueError("Position quantities cannot be negative")
            if not 0.0 <= average_cost <= 1.0:
                raise ValueError("Position average_cost must be in [0, 1]")
            if quantity > EPSILON:
                self._positions[instrument] = Position(quantity, average_cost)

        self._prices: dict[str, float] = {}
        self._current_time: datetime | None = None
        self._trades: list[Trade] = []
        self._snapshots: list[PortfolioSnapshot] = []
        self._realized_pnl = 0.0
        self._fees_paid = 0.0
        self._turnover = 0.0
        self._starting_equity = self._cash + sum(
            position.quantity * position.average_cost
            for position in self._positions.values()
        )

    @property
    def cash(self) -> float:
        return self._cash

    @property
    def current_time(self) -> datetime | None:
        return self._current_time

    @property
    def trades(self) -> tuple[Trade, ...]:
        return tuple(self._trades)

    @property
    def snapshots(self) -> tuple[PortfolioSnapshot, ...]:
        return tuple(self._snapshots)

    @property
    def positions(self) -> dict[str, Position]:
        return {
            instrument: Position(position.quantity, position.average_cost)
            for instrument, position in self._positions.items()
            if position.quantity > EPSILON
        }

    def position(self, instrument: str) -> Position:
        position = self._positions.get(instrument, Position())
        return Position(position.quantity, position.average_cost)

    def price(self, instrument: str) -> float:
        try:
            return self._prices[instrument]
        except KeyError as exc:
            raise MissingPriceError(f'No marked price for "{instrument}"') from exc

    def update_prices(
        self, timestamp: datetime, prices: Mapping[str, float]
    ) -> PortfolioSnapshot:
        _validate_timestamp(timestamp)
        if self._current_time is not None and timestamp < self._current_time:
            raise ChronologyError(
                f"Cannot move from {self._current_time.isoformat()} "
                f"back to {timestamp.isoformat()}"
            )
        if not prices:
            raise ValueError("At least one price is required")

        checked: dict[str, float] = {}
        for instrument, raw_price in prices.items():
            if not instrument:
                raise ValueError("Price instruments cannot be blank")
            price = _validate_finite("price", raw_price)
            if not 0.0 <= price <= 1.0:
                raise ValueError(
                    f'Price for "{instrument}" must be in [0, 1]: {price}'
                )
            checked[instrument] = price

        self._current_time = timestamp
        self._prices.update(checked)
        return self._record_snapshot()

    def execute(self, order: Order) -> Trade:
        if self._current_time is None:
            raise BacktestError("Set market prices before executing an order")
        instrument = order.instrument.strip()
        if not instrument:
            raise InvalidOrderError("Order instrument cannot be blank")
        try:
            side = order.side if isinstance(order.side, Side) else Side(order.side)
        except ValueError as exc:
            raise InvalidOrderError(f"Unknown order side: {order.side!r}") from exc
        quantity = _validate_finite("order quantity", order.quantity)
        if quantity <= EPSILON:
            raise InvalidOrderError("Order quantity must be positive")

        price = self.price(instrument)
        notional = quantity * price
        fee = notional * self._fee_rate
        realized_pnl = 0.0
        position = self._positions.setdefault(instrument, Position())

        if side is Side.BUY:
            cash_required = notional + fee
            if cash_required > self._cash + EPSILON:
                raise InsufficientCashError(
                    f'Buying {quantity:g} shares of "{instrument}" requires '
                    f"{cash_required:.6f}, but only {self._cash:.6f} is available"
                )
            previous_cost = position.quantity * position.average_cost
            position.quantity += quantity
            position.average_cost = (
                previous_cost + notional + fee
            ) / position.quantity
            self._cash -= cash_required
        else:
            if quantity > position.quantity + EPSILON:
                raise InsufficientInventoryError(
                    f'Selling {quantity:g} shares of "{instrument}" exceeds '
                    f"the {position.quantity:g}-share inventory"
                )
            self._cash += notional - fee
            realized_pnl = quantity * (price - position.average_cost) - fee
            position.quantity -= quantity
            if position.quantity <= EPSILON:
                position.quantity = 0.0
                position.average_cost = 0.0

        self._realized_pnl += realized_pnl
        self._fees_paid += fee
        self._turnover += notional
        trade = Trade(
            timestamp=self._current_time,
            instrument=instrument,
            side=side,
            quantity=quantity,
            price=price,
            notional=notional,
            fee=fee,
            realized_pnl=realized_pnl,
            cash_after=self._cash,
            position_after=position.quantity,
        )
        self._trades.append(trade)
        self._record_snapshot()
        return trade

    def execute_many(self, orders: Iterable[Order]) -> tuple[Trade, ...]:
        return tuple(self.execute(order) for order in orders)

    def buy_for_cash(self, instrument: str, cash_amount: float) -> Trade:
        budget = _validate_finite("cash_amount", cash_amount)
        if budget <= EPSILON:
            raise InvalidOrderError("cash_amount must be positive")
        if budget > self._cash + EPSILON:
            raise InsufficientCashError(
                f"Buy budget {budget:.6f} exceeds available cash {self._cash:.6f}"
            )
        price = self.price(instrument)
        cost_per_share = price * (1.0 + self._fee_rate)
        if cost_per_share <= EPSILON:
            raise InvalidOrderError("Cannot size a cash order at a zero price")
        return self.execute(
            Order(instrument, Side.BUY, budget / cost_per_share)
        )

    def liquidate(self) -> tuple[Trade, ...]:
        orders = [
            Order(instrument, Side.SELL, position.quantity)
            for instrument, position in sorted(self._positions.items())
            if position.quantity > EPSILON
        ]
        return self.execute_many(orders)

    def portfolio_snapshot(self) -> PortfolioSnapshot:
        market_value = 0.0
        unrealized_pnl = 0.0
        for instrument, position in self._positions.items():
            if position.quantity <= EPSILON:
                continue
            mark = self._prices.get(instrument, position.average_cost)
            market_value += position.quantity * mark
            unrealized_pnl += position.quantity * (
                mark - position.average_cost
            )
        return PortfolioSnapshot(
            timestamp=self._current_time,
            cash=self._cash,
            market_value=market_value,
            equity=self._cash + market_value,
            realized_pnl=self._realized_pnl,
            unrealized_pnl=unrealized_pnl,
        )

    def stats(self) -> BacktestStats:
        ending = self.portfolio_snapshot()
        equities = [self._starting_equity]
        equities.extend(snapshot.equity for snapshot in self._snapshots)
        peak = equities[0]
        max_drawdown = 0.0
        for equity in equities:
            peak = max(peak, equity)
            if peak > EPSILON:
                max_drawdown = max(max_drawdown, (peak - equity) / peak)

        sells = [trade for trade in self._trades if trade.side is Side.SELL]
        winning_sells = sum(trade.realized_pnl > EPSILON for trade in sells)
        losing_sells = sum(trade.realized_pnl < -EPSILON for trade in sells)
        breakeven_sells = len(sells) - winning_sells - losing_sells
        decisive_sells = winning_sells + losing_sells
        total_pnl = ending.equity - self._starting_equity
        total_return = (
            total_pnl / self._starting_equity
            if self._starting_equity > EPSILON
            else None
        )

        return BacktestStats(
            starting_equity=self._starting_equity,
            ending_cash=ending.cash,
            ending_market_value=ending.market_value,
            ending_equity=ending.equity,
            total_pnl=total_pnl,
            total_return=total_return,
            realized_pnl=ending.realized_pnl,
            unrealized_pnl=ending.unrealized_pnl,
            max_drawdown=max_drawdown,
            trade_count=len(self._trades),
            buy_count=sum(
                trade.side is Side.BUY for trade in self._trades
            ),
            sell_count=len(sells),
            winning_sells=winning_sells,
            losing_sells=losing_sells,
            breakeven_sells=breakeven_sells,
            win_rate=winning_sells / decisive_sells if decisive_sells else None,
            turnover=self._turnover,
            fees_paid=self._fees_paid,
            open_positions=sum(
                position.quantity > EPSILON
                for position in self._positions.values()
            ),
        )

    def _record_snapshot(self) -> PortfolioSnapshot:
        snapshot = self.portfolio_snapshot()
        self._snapshots.append(snapshot)
        return snapshot

# Training data: UCL 2026, Wimbledon 2026, NHL 2026, and NHL 2025.
# Model features: p + p^2, where p is the starting match-win probability.
# Prediction target: strategy_ev_relative.
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

if __package__:
    from ..fifa_model.compare_hedge_models import (
        ComparisonRow,
        compare_model_grid,
        print_comparison,
        write_comparison_csv,
    )
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(PROJECT_ROOT))
    from backtesting.experiments.fifa_model.compare_hedge_models import (
        ComparisonRow,
        compare_model_grid,
        print_comparison,
        write_comparison_csv,
    )


TRAINING_SPORTS = (
    "ucl_2026",
    "wimbledon_2026",
    "nhl",
    "nhl_2025",
)
EVALUATION_SPORTS = (
    "fifa",
    "lol_worlds_2025",
    "mlb",
    "nba",
    "nba_2025",
    "nfl",
)
FEATURE_SETS = (
    "p_p2",
)
TARGETS = (
    "strategy_ev_relative",
)
ALPHA = 1.0
PREDICTION_THRESHOLD = 0.0
BENCHMARK_FEATURE_SET = "p_p2"
BENCHMARK_TARGET = "strategy_ev_relative"
BENCHMARK_SELECTED = 89
BENCHMARK_ENGINE_PNL = 57.28378222
DEFAULT_OUTPUT = Path(__file__).with_name("ucl_wimbledon_nhl_results.csv")


def run_experiment() -> tuple[ComparisonRow, ...]:
    """Run the frozen multi-sport train/test split and model grid."""
    return compare_model_grid(
        training_sports=TRAINING_SPORTS,
        evaluation_sports=EVALUATION_SPORTS,
        feature_sets=FEATURE_SETS,
        targets=TARGETS,
        alpha=ALPHA,
        prediction_threshold=PREDICTION_THRESHOLD,
    )


def benchmark_row(rows: tuple[ComparisonRow, ...]) -> ComparisonRow:
    matches = tuple(
        row
        for row in rows
        if row.feature_set == BENCHMARK_FEATURE_SET
        and row.target == BENCHMARK_TARGET
    )
    if len(matches) != 1:
        raise RuntimeError("The frozen benchmark model is missing or duplicated")
    return matches[0]


def verify_benchmark(row: ComparisonRow) -> None:
    """Fail clearly if data or model behavior no longer reproduces the case."""
    if row.training_rows != 124 or row.external_rows != 174:
        raise RuntimeError(
            "The pooled experiment data changed: expected 124 training and "
            f"174 evaluation rows, received {row.training_rows} and "
            f"{row.external_rows}"
        )
    if row.external_selected != BENCHMARK_SELECTED or not math.isclose(
        row.selected_engine_pnl,
        BENCHMARK_ENGINE_PNL,
        rel_tol=0.0,
        abs_tol=1e-8,
    ):
        raise RuntimeError(
            "The pooled benchmark drifted: expected 89 selected rows and "
            f"$57.28378222 P&L, received {row.external_selected} and "
            f"${row.selected_engine_pnl:.8f}"
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the fixed multi-sport hedge-model experiment."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"summary CSV path (default: {DEFAULT_OUTPUT})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        rows = run_experiment()
        reference = benchmark_row(rows)
        verify_benchmark(reference)
        write_comparison_csv(args.out, rows)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print_comparison(rows)
    print(
        "Reproduced benchmark: "
        f"{reference.external_selected}/{reference.external_rows} selected | "
        f"engine P&L ${reference.selected_engine_pnl:.2f}"
    )
    print(f"Saved summary to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

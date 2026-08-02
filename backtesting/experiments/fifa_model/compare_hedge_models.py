# Training data: FIFA's 64 team rows from 32 matches.
# Compares six feature formulas against four prediction targets.
# Evaluates each FIFA-trained model on the configured non-FIFA datasets.
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import median

if __package__:
    from .train_hedge_model import (
        FEATURE_SETS,
        DEFAULT_FEATURE_SET,
        TARGETS,
        evaluate_model,
        fit_ridge_model,
        load_sport_samples,
    )
    from ...sport_strategy_config import SPORTS, get_sport_config
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(PROJECT_ROOT))
    from backtesting.experiments.fifa_model.train_hedge_model import (
        DEFAULT_FEATURE_SET,
        FEATURE_SETS,
        TARGETS,
        evaluate_model,
        fit_ridge_model,
        load_sport_samples,
    )
    from backtesting.sport_strategy_config import SPORTS, get_sport_config


FIFA_TRAINING_SPORTS = ("fifa",)
DEFAULT_OUTPUT = Path(__file__).with_name("fifa_model_comparison.csv")


@dataclass(frozen=True)
class ComparisonRow:
    training_sports: tuple[str, ...]
    evaluation_sports: tuple[str, ...]
    feature_set: str
    target: str
    training_rows: int
    training_r_squared: float | None
    external_rows: int
    external_selected: int
    external_selected_average_target: float | None
    external_mae: float
    external_median_absolute_error: float
    external_rmse: float
    external_r_squared: float | None
    selected_engine_pnl: float
    selected_average_engine_pnl: float | None
    all_engine_pnl: float
    all_average_engine_pnl: float


def _engine_pnl_for_sports(
    sports: tuple[str, ...],
) -> dict[tuple[str, str, str], float]:
    values = {}
    for sport in sports:
        for sample in load_sport_samples(
            sport,
            get_sport_config(sport).csv_path,
            feature_set=DEFAULT_FEATURE_SET,
            target="engine_pnl_per_100",
        ):
            values[(sample.sport, sample.match, sample.team)] = sample.target_value
    return values


def compare_model_grid(
    *,
    training_sports: tuple[str, ...],
    evaluation_sports: tuple[str, ...] | None = None,
    feature_sets: tuple[str, ...] | None = None,
    targets: tuple[str, ...] | None = None,
    alpha: float = 1.0,
    prediction_threshold: float = 0.0,
) -> tuple[ComparisonRow, ...]:
    """Fit every feature/target pair on one sport split."""
    training_sports = tuple(sport.casefold() for sport in training_sports)
    if not training_sports:
        raise ValueError("At least one training sport is required")
    if len(set(training_sports)) != len(training_sports):
        raise ValueError("Training sports cannot contain duplicates")
    invalid_training = sorted(set(training_sports) - SPORTS.keys())
    if invalid_training:
        raise ValueError("Invalid training sports: " + ", ".join(invalid_training))

    if evaluation_sports is None:
        evaluation_sports = tuple(sorted(SPORTS.keys() - set(training_sports)))
    else:
        evaluation_sports = tuple(sport.casefold() for sport in evaluation_sports)
    if not evaluation_sports:
        raise ValueError("At least one evaluation sport is required")
    if len(set(evaluation_sports)) != len(evaluation_sports):
        raise ValueError("Evaluation sports cannot contain duplicates")
    invalid_evaluation = sorted(set(evaluation_sports) - SPORTS.keys())
    if invalid_evaluation:
        raise ValueError(
            "Invalid evaluation sports: " + ", ".join(invalid_evaluation)
        )
    overlap = sorted(set(training_sports) & set(evaluation_sports))
    if overlap:
        raise ValueError(
            "Sports cannot be in both training and evaluation: "
            + ", ".join(overlap)
        )

    feature_sets = tuple(FEATURE_SETS) if feature_sets is None else feature_sets
    targets = tuple(TARGETS) if targets is None else targets
    invalid_feature_sets = sorted(set(feature_sets) - FEATURE_SETS.keys())
    if invalid_feature_sets:
        raise ValueError("Invalid feature sets: " + ", ".join(invalid_feature_sets))
    invalid_targets = sorted(set(targets) - set(TARGETS))
    if invalid_targets:
        raise ValueError("Invalid targets: " + ", ".join(invalid_targets))

    rows = []
    engine_pnl = _engine_pnl_for_sports(evaluation_sports)
    all_engine_pnl = sum(engine_pnl.values())
    all_average_engine_pnl = all_engine_pnl / len(engine_pnl)
    for feature_set in feature_sets:
        for target in targets:
            training_samples = tuple(
                sample
                for sport in training_sports
                for sample in load_sport_samples(
                    sport,
                    (
                        None
                        if training_sports == ("fifa",)
                        else get_sport_config(sport).csv_path
                    ),
                    feature_set=feature_set,
                    target=target,
                )
            )
            model = fit_ridge_model(training_samples, alpha=alpha)
            training = evaluate_model(
                model,
                training_samples,
                sport="training",
                prediction_threshold=prediction_threshold,
            )
            evaluation_samples = tuple(
                sample
                for sport in evaluation_sports
                for sample in load_sport_samples(
                    sport,
                    get_sport_config(sport).csv_path,
                    feature_set=feature_set,
                    target=target,
                )
            )
            external = evaluate_model(
                model,
                evaluation_samples,
                sport="evaluation",
                prediction_threshold=prediction_threshold,
            )
            predictions = [
                model.predict(sample) for sample in evaluation_samples
            ]
            selected_samples = [
                sample
                for sample, prediction in zip(
                    evaluation_samples,
                    predictions,
                    strict=True,
                )
                if prediction > prediction_threshold
            ]
            selected_engine_pnl = sum(
                engine_pnl[(sample.sport, sample.match, sample.team)]
                for sample in selected_samples
            )
            absolute_errors = [
                abs(prediction - sample.target_value)
                for sample, prediction in zip(
                    evaluation_samples,
                    predictions,
                    strict=True,
                )
            ]
            rows.append(
                ComparisonRow(
                    training_sports=training_sports,
                    evaluation_sports=evaluation_sports,
                    feature_set=feature_set,
                    target=target,
                    training_rows=training.observations,
                    training_r_squared=training.r_squared,
                    external_rows=external.observations,
                    external_selected=external.selected,
                    external_selected_average_target=(
                        external.selected_average_target
                    ),
                    external_mae=external.mae,
                    external_median_absolute_error=median(absolute_errors),
                    external_rmse=external.rmse,
                    external_r_squared=external.r_squared,
                    selected_engine_pnl=selected_engine_pnl,
                    selected_average_engine_pnl=(
                        selected_engine_pnl / len(selected_samples)
                        if selected_samples
                        else None
                    ),
                    all_engine_pnl=all_engine_pnl,
                    all_average_engine_pnl=all_average_engine_pnl,
                )
            )
    return tuple(rows)


def compare_models(
    *,
    alpha: float = 1.0,
    prediction_threshold: float = 0.0,
    evaluation_sports: tuple[str, ...] | None = None,
) -> tuple[ComparisonRow, ...]:
    """Compare every feature/target pairing using FIFA for training."""
    return compare_model_grid(
        training_sports=FIFA_TRAINING_SPORTS,
        evaluation_sports=evaluation_sports,
        alpha=alpha,
        prediction_threshold=prediction_threshold,
    )


def _number(value: float | None) -> str:
    return "" if value is None else f"{value:.10g}"


def write_comparison_csv(path: Path, rows: tuple[ComparisonRow, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(
            (
                "training_sports",
                "evaluation_sports",
                "feature_set",
                "target",
                "training_rows",
                "training_r_squared",
                "external_rows",
                "external_selected",
                "external_selected_average_target",
                "external_mae",
                "external_median_absolute_error",
                "external_rmse",
                "external_r_squared",
                "selected_engine_pnl",
                "selected_average_engine_pnl",
                "all_engine_pnl",
                "all_average_engine_pnl",
            )
        )
        for row in rows:
            writer.writerow(
                (
                    ";".join(row.training_sports),
                    ";".join(row.evaluation_sports),
                    row.feature_set,
                    row.target,
                    row.training_rows,
                    _number(row.training_r_squared),
                    row.external_rows,
                    row.external_selected,
                    _number(row.external_selected_average_target),
                    _number(row.external_mae),
                    _number(row.external_median_absolute_error),
                    _number(row.external_rmse),
                    _number(row.external_r_squared),
                    _number(row.selected_engine_pnl),
                    _number(row.selected_average_engine_pnl),
                    _number(row.all_engine_pnl),
                    _number(row.all_average_engine_pnl),
                )
            )


def _metric(value: float | None) -> str:
    return "-" if value is None else f"{value:.4f}"


def print_comparison(rows: tuple[ComparisonRow, ...]) -> None:
    print("Hedge model comparison")
    if rows:
        print("Training: " + ", ".join(rows[0].training_sports))
        print("Evaluation: " + ", ".join(rows[0].evaluation_sports))
    print(
        "Feature set                 Target                 Train R^2  "
        "Ext R^2  Selected  Target avg  Engine P&L  Engine avg"
    )
    for row in rows:
        print(
            f"{row.feature_set:<27} "
            f"{row.target:<23} "
            f"{_metric(row.training_r_squared):>9}  "
            f"{_metric(row.external_r_squared):>7}  "
            f"{row.external_selected:>8}  "
            f"{_metric(row.external_selected_average_target):>10}  "
            f"${row.selected_engine_pnl:>9.2f}  "
            f"${_metric(row.selected_average_engine_pnl):>9}"
        )
    if rows:
        print(
            "All-hedge engine baseline: "
            f"{rows[0].external_rows} rows | "
            f"P&L ${rows[0].all_engine_pnl:.2f} | "
            f"average ${rows[0].all_average_engine_pnl:.4f}"
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fit every hedge-model feature set and target on FIFA, then "
            "compare performance on every other configured sport."
        )
    )
    parser.add_argument("--alpha", type=float, default=1.0)
    parser.add_argument("--prediction-threshold", type=float, default=0.0)
    parser.add_argument(
        "--test-sports",
        nargs="+",
        choices=sorted(SPORTS.keys() - set(FIFA_TRAINING_SPORTS)),
        help="optional non-FIFA evaluation configs",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"summary CSV path (default: {DEFAULT_OUTPUT})",
    )
    return parser


def comparison_cli(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        rows = compare_models(
            alpha=args.alpha,
            prediction_threshold=args.prediction_threshold,
            evaluation_sports=(
                tuple(args.test_sports) if args.test_sports else None
            ),
        )
        write_comparison_csv(args.out, rows)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print_comparison(rows)
    print(f"Saved summary to {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return comparison_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

if __package__:
    from ...paired_hedge_strategy import (
        HedgeQuote,
        load_hedge_quotes,
    )
    from ...sport_strategy_config import SPORTS, get_sport_config
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(PROJECT_ROOT))
    from backtesting.paired_hedge_strategy import (
        HedgeQuote,
        load_hedge_quotes,
    )
    from backtesting.sport_strategy_config import SPORTS, get_sport_config


TRAINING_SPORT = "fifa"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TRAINING_CSV = (
    PROJECT_ROOT / "data" / "analysis" / "explore_data_table_1.csv"
)
FEATURE_SETS = {
    "p_c_c_over_p_log_p_over_c_p2": (
        "trigger_win_start",
        "championship_win_start",
        "championship_to_game_ratio",
        "log_game_to_championship_ratio",
        "trigger_win_start_squared",
    ),
    "p_c_c_over_p_p2": (
        "trigger_win_start",
        "championship_win_start",
        "championship_to_game_ratio",
        "trigger_win_start_squared",
    ),
    "p_p_over_c_p2": (
        "trigger_win_start",
        "game_to_championship_ratio",
        "trigger_win_start_squared",
    ),
    "p_log_p_over_c_p2": (
        "trigger_win_start",
        "log_game_to_championship_ratio",
        "trigger_win_start_squared",
    ),
    "log_p_over_c_only": ("log_game_to_championship_ratio",),
    "p_p2": (
        "trigger_win_start",
        "trigger_win_start_squared",
    ),
}
TARGETS = (
    "engine_pnl_per_100",
    "profit_per_100",
    "strategy_ev",
    "strategy_ev_relative",
)
DEFAULT_FEATURE_SET = "p_c_c_over_p_log_p_over_c_p2"
DEFAULT_TARGET = "strategy_ev_relative"
EPSILON = 1e-12


@dataclass(frozen=True)
class HedgeSample:
    sport: str
    team: str
    match: str
    kickoff: datetime
    features: tuple[float, ...]
    target_value: float


@dataclass(frozen=True)
class RidgeModel:
    alpha: float
    means: tuple[float, ...]
    scales: tuple[float, ...]
    intercept: float
    coefficients: tuple[float, ...]

    def predict_features(self, features: Sequence[float]) -> float:
        if len(features) != len(self.coefficients):
            raise ValueError(
                f"Expected {len(self.coefficients)} features, "
                f"received {len(features)}"
            )
        standardized = (
            (value - mean) / scale
            for value, mean, scale in zip(
                features,
                self.means,
                self.scales,
                strict=True,
            )
        )
        return self.intercept + sum(
            coefficient * value
            for coefficient, value in zip(
                self.coefficients,
                standardized,
                strict=True,
            )
        )

    def predict(self, sample: HedgeSample) -> float:
        return self.predict_features(sample.features)


@dataclass(frozen=True)
class ModelEvaluation:
    sport: str
    observations: int
    matches: int
    selected: int
    selected_total_target: float
    selected_average_target: float | None
    selected_positive_rate: float | None
    all_total_target: float
    mae: float
    rmse: float
    r_squared: float | None


@dataclass(frozen=True)
class ModelReport:
    feature_set: str
    target: str
    model: RidgeModel
    training_samples: tuple[HedgeSample, ...]
    training_evaluation: ModelEvaluation
    evaluation_samples: tuple[HedgeSample, ...]
    evaluations: tuple[ModelEvaluation, ...]
    combined_evaluation: ModelEvaluation
    prediction_threshold: float


def quote_features(
    quote: HedgeQuote,
    feature_set: str = DEFAULT_FEATURE_SET,
) -> tuple[float, ...]:
    """Build entry-only model features for one paired hedge quote."""
    if feature_set not in FEATURE_SETS:
        raise ValueError(f'Unknown feature set "{feature_set}"')
    trigger_win = quote.trigger_start_price
    if trigger_win <= EPSILON:
        raise ValueError(
            f'Cannot build model features for "{quote.team}" with a '
            "zero trigger-win price"
        )
    championship_win = 1.0 - quote.loss_start_price
    if championship_win <= EPSILON:
        raise ValueError(
            f'Cannot build model features for "{quote.team}" with a '
            "zero championship-win price"
        )
    ratio = trigger_win / championship_win
    feature_values = {
        "trigger_win_start": trigger_win,
        "championship_win_start": championship_win,
        "championship_to_game_ratio": championship_win / trigger_win,
        "game_to_championship_ratio": ratio,
        "log_game_to_championship_ratio": math.log(ratio),
        "trigger_win_start_squared": trigger_win * trigger_win,
    }
    return tuple(feature_values[name] for name in FEATURE_SETS[feature_set])


def quote_target_value(quote: HedgeQuote, target: str) -> float | None:
    """Calculate one discussed output target from a quote row."""
    if target not in TARGETS:
        raise ValueError(f'Unknown target "{target}"')
    if quote.trigger_start_price <= EPSILON:
        raise ValueError(
            f'Cannot calculate {target} for "{quote.team}" with a '
            "zero trigger-win price"
        )

    championship_win_start = 1.0 - quote.loss_start_price
    if target == "engine_pnl_per_100":
        trigger_quantity = 100.0 * championship_win_start / quote.trigger_start_price
        return (
            trigger_quantity
            * (quote.trigger_end_price - quote.trigger_start_price)
            + 100.0 * (quote.loss_end_price - quote.loss_start_price)
        )

    if quote.trigger_end_price <= 0.5:
        return 0.0
    if target == "profit_per_100" and quote.loss_start_price <= EPSILON:
        raise ValueError(
            f'Cannot calculate profit_per_100 for "{quote.team}" with a '
            "zero championship-loss price"
        )

    championship_win_end = 1.0 - quote.loss_end_price
    expected_championship_win = (
        championship_win_start
        * quote.trigger_end_price
        / quote.trigger_start_price
    )
    strategy_ev = expected_championship_win - championship_win_end
    if target == "strategy_ev":
        return strategy_ev
    if target == "profit_per_100":
        return 100.0 * strategy_ev / quote.loss_start_price

    expected_movement = expected_championship_win - championship_win_start
    if abs(expected_movement) <= EPSILON:
        return None
    return strategy_ev / expected_movement


def _explicit_target_labels(
    path: Path,
    target: str,
) -> tuple[float | None, ...] | None:
    """Read a target directly when the source CSV already provides it."""
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        if target not in (reader.fieldnames or ()):
            return None
        labels = []
        for row_number, row in enumerate(reader, start=2):
            raw_value = row[target].strip()
            if not raw_value:
                labels.append(None)
                continue
            try:
                value = float(raw_value)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"CSV row {row_number} has an invalid {target}"
                ) from exc
            if not math.isfinite(value):
                raise ValueError(
                    f"CSV row {row_number} has a non-finite {target}"
                )
            labels.append(value)
    return tuple(labels)


def load_sport_samples(
    sport: str,
    csv_path: Path | None = None,
    *,
    feature_set: str = DEFAULT_FEATURE_SET,
    target: str = DEFAULT_TARGET,
) -> tuple[HedgeSample, ...]:
    """Generate one feature/target sample set for a configured dataset."""
    config = get_sport_config(sport)
    path = csv_path or (
        DEFAULT_TRAINING_CSV
        if sport.casefold() == TRAINING_SPORT
        else config.csv_path
    )
    quotes = load_hedge_quotes(
        path,
        config.trigger_prefix,
        config.loss_prefix,
        config.namespace,
    )
    if not quotes:
        raise ValueError(f"{path} contains no hedge quotes")
    explicit_labels = _explicit_target_labels(path, target)
    if explicit_labels is not None and len(explicit_labels) != len(quotes):
        raise ValueError(
            f"{path} has {len(quotes)} quotes but "
            f"{len(explicit_labels)} {target} labels"
        )

    samples = []
    for index, quote in enumerate(quotes):
        target_value = (
            explicit_labels[index]
            if explicit_labels is not None
            else quote_target_value(quote, target)
        )
        if target_value is None:
            continue
        samples.append(
            HedgeSample(
                sport=sport.casefold(),
                team=quote.team,
                match=quote.match,
                kickoff=quote.start_time,
                features=quote_features(quote, feature_set),
                target_value=target_value,
            )
        )
    return tuple(samples)


def _solve_linear_system(
    matrix: Sequence[Sequence[float]],
    values: Sequence[float],
) -> tuple[float, ...]:
    """Solve a small dense system using pivoted Gauss-Jordan elimination."""
    size = len(values)
    augmented = [
        [float(value) for value in row] + [float(values[index])]
        for index, row in enumerate(matrix)
    ]
    for column in range(size):
        pivot = max(
            range(column, size),
            key=lambda row: abs(augmented[row][column]),
        )
        if abs(augmented[pivot][column]) <= EPSILON:
            raise ValueError("Ridge regression system is singular")
        augmented[column], augmented[pivot] = (
            augmented[pivot],
            augmented[column],
        )

        pivot_value = augmented[column][column]
        augmented[column] = [
            value / pivot_value for value in augmented[column]
        ]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            if abs(factor) <= EPSILON:
                continue
            augmented[row] = [
                current - factor * pivot_entry
                for current, pivot_entry in zip(
                    augmented[row],
                    augmented[column],
                    strict=True,
                )
            ]
    return tuple(row[-1] for row in augmented)


def fit_ridge_model(
    samples: Sequence[HedgeSample],
    *,
    alpha: float = 1.0,
) -> RidgeModel:
    """Fit a transparent standardized ridge regression without dependencies."""
    if not samples:
        raise ValueError("At least one training sample is required")
    if not math.isfinite(alpha) or alpha < 0.0:
        raise ValueError("alpha must be a finite non-negative number")

    feature_count = len(samples[0].features)
    if any(len(sample.features) != feature_count for sample in samples):
        raise ValueError(f"Every sample must have {feature_count} features")

    count = len(samples)
    means = tuple(
        sum(sample.features[index] for sample in samples) / count
        for index in range(feature_count)
    )
    scales = []
    for index, mean in enumerate(means):
        variance = sum(
            (sample.features[index] - mean) ** 2 for sample in samples
        ) / count
        scale = math.sqrt(variance)
        scales.append(scale if scale > EPSILON else 1.0)
    scale_tuple = tuple(scales)

    design = []
    targets = []
    for sample in samples:
        standardized = [
            (value - mean) / scale
            for value, mean, scale in zip(
                sample.features,
                means,
                scale_tuple,
                strict=True,
            )
        ]
        design.append([1.0, *standardized])
        targets.append(sample.target_value)

    dimension = feature_count + 1
    gram = [[0.0] * dimension for _ in range(dimension)]
    response = [0.0] * dimension
    for row, target in zip(design, targets, strict=True):
        for left in range(dimension):
            response[left] += row[left] * target
            for right in range(dimension):
                gram[left][right] += row[left] * row[right]
    for index in range(1, dimension):
        gram[index][index] += alpha

    fitted = _solve_linear_system(gram, response)
    return RidgeModel(
        alpha=alpha,
        means=means,
        scales=scale_tuple,
        intercept=fitted[0],
        coefficients=fitted[1:],
    )


def evaluate_model(
    model: RidgeModel,
    samples: Sequence[HedgeSample],
    *,
    sport: str,
    prediction_threshold: float = 0.0,
) -> ModelEvaluation:
    if not samples:
        raise ValueError("At least one evaluation sample is required")
    if not math.isfinite(prediction_threshold):
        raise ValueError("prediction_threshold must be finite")

    predictions = [model.predict(sample) for sample in samples]
    errors = [
        prediction - sample.target_value
        for prediction, sample in zip(predictions, samples, strict=True)
    ]
    selected_samples = [
        sample
        for prediction, sample in zip(predictions, samples, strict=True)
        if prediction > prediction_threshold
    ]
    selected_total = sum(sample.target_value for sample in selected_samples)
    actual_values = [sample.target_value for sample in samples]
    actual_mean = sum(actual_values) / len(actual_values)
    residual_sum = sum(error * error for error in errors)
    total_sum = sum((value - actual_mean) ** 2 for value in actual_values)

    return ModelEvaluation(
        sport=sport,
        observations=len(samples),
        matches=len({(sample.sport, sample.match) for sample in samples}),
        selected=len(selected_samples),
        selected_total_target=selected_total,
        selected_average_target=(
            selected_total / len(selected_samples)
            if selected_samples
            else None
        ),
        selected_positive_rate=(
            sum(sample.target_value > EPSILON for sample in selected_samples)
            / len(selected_samples)
            if selected_samples
            else None
        ),
        all_total_target=sum(actual_values),
        mae=sum(abs(error) for error in errors) / len(errors),
        rmse=math.sqrt(residual_sum / len(errors)),
        r_squared=(1.0 - residual_sum / total_sum if total_sum > EPSILON else None),
    )


def run_cross_sport_model(
    evaluation_sports: Iterable[str] | None = None,
    *,
    alpha: float = 1.0,
    prediction_threshold: float = 0.0,
    training_csv: Path | None = None,
    feature_set: str = DEFAULT_FEATURE_SET,
    target: str = DEFAULT_TARGET,
) -> ModelReport:
    if feature_set not in FEATURE_SETS:
        raise ValueError(f'Unknown feature set "{feature_set}"')
    if target not in TARGETS:
        raise ValueError(f'Unknown target "{target}"')
    sports = (
        tuple(sorted(SPORTS.keys() - {TRAINING_SPORT}))
        if evaluation_sports is None
        else tuple(sport.casefold() for sport in evaluation_sports)
    )
    if not sports:
        raise ValueError("At least one evaluation sport is required")
    duplicates = sorted(
        sport for sport in set(sports) if sports.count(sport) > 1
    )
    if duplicates:
        raise ValueError(
            "Duplicate evaluation sports: " + ", ".join(duplicates)
        )
    invalid = sorted(set(sports) - (SPORTS.keys() - {TRAINING_SPORT}))
    if invalid:
        raise ValueError(
            "Invalid evaluation sports: " + ", ".join(invalid)
        )

    training_samples = load_sport_samples(
        TRAINING_SPORT,
        training_csv,
        feature_set=feature_set,
        target=target,
    )
    model = fit_ridge_model(training_samples, alpha=alpha)
    training_evaluation = evaluate_model(
        model,
        training_samples,
        sport=TRAINING_SPORT,
        prediction_threshold=prediction_threshold,
    )

    evaluation_samples = []
    evaluations = []
    for sport in sports:
        samples = load_sport_samples(
            sport,
            feature_set=feature_set,
            target=target,
        )
        evaluation_samples.extend(samples)
        evaluations.append(
            evaluate_model(
                model,
                samples,
                sport=sport,
                prediction_threshold=prediction_threshold,
            )
        )
    combined = evaluate_model(
        model,
        evaluation_samples,
        sport="combined",
        prediction_threshold=prediction_threshold,
    )
    return ModelReport(
        feature_set=feature_set,
        target=target,
        model=model,
        training_samples=training_samples,
        training_evaluation=training_evaluation,
        evaluation_samples=tuple(evaluation_samples),
        evaluations=tuple(evaluations),
        combined_evaluation=combined,
        prediction_threshold=prediction_threshold,
    )


def _format_optional(value: float | None, format_spec: str) -> str:
    return format(value, format_spec) if value is not None else "-"


def print_report(report: ModelReport) -> None:
    print("FIFA-trained ridge hedge model")
    print(
        f"Training: {len(report.training_samples)} team rows / "
        f"{report.training_evaluation.matches} matches | "
        f"features: {report.feature_set} | target: {report.target} | "
        f"alpha: {report.model.alpha:g}"
    )
    print("Standardized coefficients:")
    for name, coefficient in zip(
        FEATURE_SETS[report.feature_set],
        report.model.coefficients,
        strict=True,
    ):
        print(f"  {name}: {coefficient:+.6f}")
    print(f"  intercept: {report.model.intercept:+.6f}")
    training = report.training_evaluation
    print(
        "FIFA in-sample fit: "
        f"MAE {training.mae:.4f} | RMSE {training.rmse:.4f} | "
        f"R^2 {_format_optional(training.r_squared, '.3f')}"
    )
    print(
        "Sport              Rows  Matches  Selected  Selected Avg  "
        "All Avg  Positive      MAE     R^2"
    )
    for evaluation in (*report.evaluations, report.combined_evaluation):
        average = (
            f"{evaluation.selected_average_target:>12.4f}"
            if evaluation.selected_average_target is not None
            else "           -"
        )
        positive_rate = (
            f"{evaluation.selected_positive_rate:>8.1%}"
            if evaluation.selected_positive_rate is not None
            else "       -"
        )
        all_average = evaluation.all_total_target / evaluation.observations
        r_squared = _format_optional(evaluation.r_squared, ".3f")
        print(
            f"{evaluation.sport:<18}"
            f"{evaluation.observations:>5}  "
            f"{evaluation.matches:>7}  "
            f"{evaluation.selected:>8}  "
            f"{average}  "
            f"{all_average:>7.4f}  "
            f"{positive_rate}  "
            f"{evaluation.mae:>7.4f}  {r_squared:>6}"
        )


def write_predictions_csv(path: Path, report: ModelReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(
            (
                "dataset_role",
                "sport",
                "team",
                "match",
                "kickoff",
                *FEATURE_SETS[report.feature_set],
                f"actual_{report.target}",
                f"predicted_{report.target}",
                "selected",
            )
        )
        for role, samples in (
            ("training", report.training_samples),
            ("evaluation", report.evaluation_samples),
        ):
            for sample in samples:
                prediction = report.model.predict(sample)
                writer.writerow(
                    (
                        role,
                        sample.sport,
                        sample.team,
                        sample.match,
                        sample.kickoff.isoformat(),
                        *(f"{value:.8f}" for value in sample.features),
                        f"{sample.target_value:.8f}",
                        f"{prediction:.8f}",
                        prediction > report.prediction_threshold,
                    )
                )


def _parser() -> argparse.ArgumentParser:
    evaluation_choices = sorted(SPORTS.keys() - {TRAINING_SPORT})
    parser = argparse.ArgumentParser(
        description=(
            "Fit a one-feature ridge model on FIFA only, then evaluate it "
            "without refitting on other sport datasets."
        )
    )
    parser.add_argument(
        "sport",
        nargs="?",
        default="all",
        choices=("all", *evaluation_choices),
        help="evaluation dataset; defaults to all non-FIFA datasets",
    )
    parser.add_argument("--alpha", type=float, default=1.0)
    parser.add_argument(
        "--feature-set",
        choices=tuple(FEATURE_SETS),
        default=DEFAULT_FEATURE_SET,
    )
    parser.add_argument(
        "--target",
        choices=TARGETS,
        default=DEFAULT_TARGET,
    )
    parser.add_argument(
        "--prediction-threshold",
        type=float,
        default=0.0,
        help="select rows whose predicted target exceeds this value",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="optional CSV path for all training and evaluation predictions",
    )
    return parser


def model_cli(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    evaluation_sports = None if args.sport == "all" else (args.sport,)
    try:
        report = run_cross_sport_model(
            evaluation_sports,
            alpha=args.alpha,
            prediction_threshold=args.prediction_threshold,
            feature_set=args.feature_set,
            target=args.target,
        )
        if args.out is not None:
            write_predictions_csv(args.out, report)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print_report(report)
    if args.out is not None:
        print(f"Saved predictions to {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return model_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())

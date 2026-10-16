"""Monthly sales forecasting with chronological evaluation and honest uncertainty bands."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ForecastResult:
    """Forecast output and the walk-forward score of the selected model."""

    forecast: pd.DataFrame
    model_name: str
    mae: float
    mape_pct: float
    backtest_points: int
    training_months: int
    training_start: pd.Timestamp
    training_end: pd.Timestamp


def _predict(model_name: str, x_train: np.ndarray, y_train: np.ndarray, x_future: np.ndarray) -> np.ndarray:
    if model_name == "Last-month baseline":
        return np.full(len(x_future), float(y_train[-1]))
    design = np.column_stack((np.ones(len(x_train)), x_train))
    coefficients, *_ = np.linalg.lstsq(design, y_train, rcond=None)
    return coefficients[0] + coefficients[1] * x_future


def forecast_monthly_sales(monthly: pd.DataFrame, horizon: int = 3) -> ForecastResult:
    """Forecast gross sales using reliable months and expanding-window evaluation.

    The returned 90% band is an empirical range based on one-step-ahead
    walk-forward absolute errors. It is not a formal statistical confidence interval.
    """
    if not 1 <= int(horizon) <= 12:
        raise ValueError("Forecast horizon must be between 1 and 12 months.")
    required = {"month", "gross_sales", "reliable"}
    missing = required.difference(monthly.columns)
    if missing:
        raise ValueError(f"Monthly sales data is missing columns: {', '.join(sorted(missing))}")

    data = monthly.loc[monthly["reliable"]].copy()
    data["month"] = pd.to_datetime(data["month"])
    data["gross_sales"] = pd.to_numeric(data["gross_sales"], errors="coerce")
    data = data.dropna(subset=["month", "gross_sales"]).sort_values("month").reset_index(drop=True)
    if len(data) < 8:
        raise ValueError("At least 8 reliable months are needed to evaluate a forecast.")

    y = data["gross_sales"].to_numpy(dtype=float)
    # Calendar positions preserve elapsed time if reliable months contain a gap.
    month_index = ((data["month"].dt.year - data["month"].dt.year.min()) * 12
                   + data["month"].dt.month - data["month"].dt.month.min()).to_numpy(dtype=float)
    # Expanding one-month-ahead windows keep each validation target strictly
    # in the future of its training slice (without adding a heavy dependency).
    first_test = max(3, len(data) - 5)
    errors: dict[str, list[float]] = {"Last-month baseline": [], "Linear trend": []}
    fold_actuals: list[float] = []

    for test_pos in range(first_test, len(data)):
        train_idx = np.arange(test_pos)
        test_idx = np.array([test_pos])
        actual = float(y[test_pos])
        fold_actuals.append(actual)
        for name in errors:
            predicted = float(_predict(name, month_index[train_idx], y[train_idx], month_index[test_idx])[0])
            errors[name].append(actual - predicted)

    mae_by_model = {
        name: float(np.mean(np.abs(values))) for name, values in errors.items()
    }
    selected = min(mae_by_model, key=mae_by_model.get)
    cv_errors = np.asarray(errors[selected], dtype=float)
    model_mae = mae_by_model[selected]
    actual_arr = np.asarray(fold_actuals, dtype=float)
    mape = float(np.mean(np.abs(cv_errors) / np.maximum(np.abs(actual_arr), 1.0)) * 100)

    source_max = pd.to_datetime(monthly["month"]).max().to_period("M")
    forecast_periods = pd.period_range(source_max + 1, periods=int(horizon), freq="M")
    future_idx = np.arange(month_index[-1] + 1, month_index[-1] + 1 + int(horizon), dtype=float)
    point = np.maximum(0.0, _predict(selected, month_index, y, future_idx))

    # Empirical one-step error quantile, widening with horizon as an approximate guide.
    error_quantile = float(np.quantile(np.abs(cv_errors), 0.90))
    widening = np.sqrt(np.arange(1, int(horizon) + 1, dtype=float))
    margin = error_quantile * widening
    result = pd.DataFrame({
        "month": forecast_periods.to_timestamp(),
        "forecast": point.round(2),
        "lower_90": np.maximum(0.0, point - margin).round(2),
        "upper_90": (point + margin).round(2),
    })

    return ForecastResult(
        forecast=result,
        model_name=selected,
        mae=round(model_mae, 2),
        mape_pct=round(mape, 2),
        backtest_points=len(cv_errors),
        training_months=len(data),
        training_start=pd.Timestamp(data["month"].min()),
        training_end=pd.Timestamp(data["month"].max()),
    )

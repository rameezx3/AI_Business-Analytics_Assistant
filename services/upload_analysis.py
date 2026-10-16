"""Schema-agnostic profiling and business summaries for uploaded spreadsheets."""

from __future__ import annotations

from io import BytesIO
import re

import pandas as pd


def read_table(name: str, payload: bytes, sheet_name: str | int = 0) -> pd.DataFrame:
    """Read CSV/XLSX bytes without persisting user data to the project database."""
    suffix = name.lower().rsplit(".", 1)[-1]
    stream = BytesIO(payload)
    if suffix == "csv":
        try:
            return pd.read_csv(stream, low_memory=False)
        except UnicodeDecodeError:
            stream.seek(0)
            return pd.read_csv(stream, encoding="latin-1", low_memory=False)
    if suffix in {"xlsx", "xlsm"}:
        return pd.read_excel(stream, sheet_name=sheet_name, engine="openpyxl")
    if suffix == "xls":
        raise ValueError("Legacy .xls files are not supported. Save the workbook as .xlsx and upload it again.")
    raise ValueError("Upload a CSV or Excel workbook (.csv, .xlsx, .xlsm).")


def _find_column(columns: list[str], patterns: tuple[str, ...]) -> str | None:
    normalized = {column: re.sub(r"[^a-z0-9]+", "_", column.lower()).strip("_") for column in columns}
    for column, value in normalized.items():
        if any(re.search(pattern, value) for pattern in patterns):
            return column
    return None


def profile_table(frame: pd.DataFrame) -> dict:
    """Summarize data quality and infer common business fields from column names."""
    if frame.empty or len(frame.columns) == 0:
        raise ValueError("This sheet has no data rows or columns.")
    df = frame.copy()
    df.columns = [str(c).strip() or f"column_{i + 1}" for i, c in enumerate(df.columns)]
    date_col = _find_column(list(df.columns), (r"(^|_)(date|day|time|timestamp)(_|$)", r"created_at", r"ordered_at"))
    sales_col = _find_column(list(df.columns), (r"(^|_)(revenue|sales|amount|total|price|value)(_|$)",))
    customer_col = _find_column(list(df.columns), (r"(^|_)(customer|client|buyer)(_|_id$|$)",))
    product_col = _find_column(list(df.columns), (r"(^|_)(product|item|sku|category)(_|_id$|$)",))
    if sales_col and not pd.api.types.is_numeric_dtype(df[sales_col]):
        parsed = pd.to_numeric(df[sales_col].astype(str).str.replace(r"[^0-9.\-]", "", regex=True), errors="coerce")
        if parsed.notna().sum() >= max(1, int(len(df) * 0.5)):
            df[sales_col] = parsed
        else:
            sales_col = None
    parsed_dates = None
    if date_col:
        parsed_dates = pd.to_datetime(df[date_col], errors="coerce")
        if parsed_dates.notna().sum() < max(1, int(len(df) * 0.5)):
            date_col, parsed_dates = None, None
    numeric = df.select_dtypes(include="number").columns.tolist()
    categorical = [c for c in df.columns if c not in numeric and c != date_col and df[c].nunique(dropna=True) <= 100]
    return {"frame": df, "date": date_col, "parsed_dates": parsed_dates, "sales": sales_col,
            "customer": customer_col, "product": product_col, "numeric": numeric,
            "categorical": categorical, "rows": len(df), "columns": len(df.columns),
            "missing": int(df.isna().sum().sum()), "duplicates": int(df.duplicated().sum())}


def time_series(profile: dict) -> pd.DataFrame:
    """Aggregate the inferred sales or row count by month."""
    date_col, dates = profile["date"], profile["parsed_dates"]
    if not date_col:
        return pd.DataFrame()
    data = profile["frame"].copy()
    data["_analysis_date"] = dates
    data = data.dropna(subset=["_analysis_date"])
    data["Period"] = data["_analysis_date"].dt.to_period("M").dt.to_timestamp()
    sales = profile["sales"]
    return data.groupby("Period", as_index=False)[sales].sum() if sales else data.groupby("Period", as_index=False).size().rename(columns={"size": "Records"})


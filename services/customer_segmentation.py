"""Interpretable RFM customer segments derived from the customer analytics snapshot."""

from __future__ import annotations

import numpy as np
import pandas as pd


SEGMENT_GUIDANCE = {
    "Champions": "Recent customers who score highly on order frequency and lifetime spend. Reward loyalty and invite feedback.",
    "Loyal customers": "Frequent, relatively recent customers. Encourage continued engagement with relevant offers.",
    "Potential loyalists": "Recent customers with above-middle order frequency. Help them build a lasting relationship.",
    "New customers": "Recent customers with lower order frequency. Focus on a good first-to-second-order experience.",
    "At risk": "Less-recent customers with high historical frequency or spend. Consider a targeted win-back message.",
    "Hibernating": "Less-recent customers with lower frequency and spend. Test low-cost re-engagement before investing heavily.",
    "Needs nurturing": "Paying customers who do not meet another rule. Use the profile table to tailor a measured next step.",
    "No item spend": "People with orders but no item-price spend in this dataset. Keep separate from paying-customer RFM groups.",
}

SEGMENT_ORDER = list(SEGMENT_GUIDANCE)


def _quintile_score(values: pd.Series) -> pd.Series:
    """Convert percentile ranks to stable 1–5 scores despite tied feature values."""
    # Rank ties from the bottom of their value block: e.g. a very large
    # one-order cohort should remain low-frequency instead of getting a
    # misleading middle score simply because many customers share value=1.
    score = np.ceil(values.rank(method="min", pct=True) * 5).clip(1, 5)
    return score.astype("int8")


def segment_customers(customers: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    """Return per-person RFM scores, segment-level profiles, and the data cutoff.

    RFM stands for recency, frequency, and monetary value. Score bands are
    relative quintiles in this dataset, then transparent rules assign names.
    It is a descriptive segmentation, not a predictive or causal model.
    """
    required = {"customer_unique_id", "orders", "last_order", "spend"}
    missing = required.difference(customers.columns)
    if missing:
        raise ValueError(f"Customer snapshot is missing columns: {', '.join(sorted(missing))}")
    if customers.empty:
        raise ValueError("No customer rows are available to segment.")

    data = customers.copy()
    data["last_order"] = pd.to_datetime(data["last_order"], errors="coerce")
    data["orders"] = pd.to_numeric(data["orders"], errors="coerce").fillna(0).clip(lower=0)
    data["spend"] = pd.to_numeric(data["spend"], errors="coerce").fillna(0).clip(lower=0)
    cutoff = data["last_order"].max()
    if pd.isna(cutoff):
        raise ValueError("Customer snapshot has no valid order dates.")

    data["recency_days"] = (cutoff - data["last_order"]).dt.total_seconds().div(86400).fillna(0).clip(lower=0)
    data["frequency"] = data["orders"].astype("int64")
    data["monetary"] = data["spend"].astype(float).round(2)

    # Recent is good, so reverse recency's ascending percentile rank.
    data["r_score"] = 6 - _quintile_score(data["recency_days"])
    data["f_score"] = _quintile_score(data["frequency"])
    data["m_score"] = 0
    paying = data["monetary"] > 0
    data.loc[paying, "m_score"] = _quintile_score(data.loc[paying, "monetary"])

    conditions = [
        ~paying,
        (data["r_score"] >= 4) & (data["f_score"] >= 4) & (data["m_score"] >= 4),
        (data["f_score"] >= 4) & (data["r_score"] >= 3),
        (data["r_score"] >= 4) & (data["f_score"] >= 3),
        (data["r_score"] >= 4) & (data["f_score"] <= 2),
        (data["r_score"] <= 2) & ((data["f_score"] >= 4) | (data["m_score"] >= 4)),
        (data["r_score"] <= 2) & (data["f_score"] <= 2) & (data["m_score"] <= 2),
    ]
    labels = ["No item spend", "Champions", "Loyal customers", "Potential loyalists",
              "New customers", "At risk", "Hibernating"]
    data["segment"] = np.select(conditions, labels, default="Needs nurturing")

    rows = []
    for name in SEGMENT_ORDER:
        group = data.loc[data["segment"] == name]
        n = len(group)
        rows.append({
            "segment": name,
            "customers": n,
            "customer_share_pct": round(100 * n / len(data), 2),
            "avg_recency_days": round(float(group["recency_days"].mean()), 1) if n else 0.0,
            "avg_orders": round(float(group["frequency"].mean()), 2) if n else 0.0,
            "avg_spend": round(float(group["monetary"].mean()), 2) if n else 0.0,
            "median_spend": round(float(group["monetary"].median()), 2) if n else 0.0,
            "revenue_share_pct": round(100 * float(group["monetary"].sum()) / max(float(data["monetary"].sum()), 1.0), 2),
            "guidance": SEGMENT_GUIDANCE[name],
        })
    profiles = pd.DataFrame(rows)
    return data, profiles, pd.Timestamp(cutoff)

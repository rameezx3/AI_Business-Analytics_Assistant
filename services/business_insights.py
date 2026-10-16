"""Generate deterministic, evidence-linked business insights from verified analytics."""

from __future__ import annotations

import pandas as pd

from services.kpi import KPISet


def generate_business_insights(
    kpis: KPISet,
    monthly: pd.DataFrame,
    segment_profiles: pd.DataFrame,
    categories: pd.DataFrame,
    regional: pd.DataFrame,
    data_cutoff: pd.Timestamp,
) -> list[dict[str, object]]:
    """Turn existing descriptive metrics into findings with actions and limitations.

    This rule engine is deterministic. It does not infer causality or estimate
    financial impact, and every generated finding includes its source evidence.
    """
    insights: list[dict[str, object]] = []
    cutoff_label = pd.Timestamp(data_cutoff).strftime("%d %b %Y")

    reliable = monthly.loc[monthly["reliable"]].copy().sort_values("month")
    if not reliable.empty:
        latest = reliable.iloc[-1]
        growth = latest.get("yoy_growth_pct")
        growth_value = None if pd.isna(growth) else float(growth)
        if growth_value is not None:
            if growth_value >= 10:
                interpretation = "Reliable monthly item sales are growing year over year."
                action = "Check stock availability and delivery capacity for the latest high-performing categories before increasing promotion spend."
                priority = "Positive signal"
            elif growth_value <= -10:
                interpretation = "Reliable monthly item sales are down year over year."
                action = "Check category and regional breakdowns, then validate seasonality and dataset coverage before changing pricing or marketing."
                priority = "Needs attention"
            else:
                interpretation = "Reliable monthly item sales are within 10% of the same month last year."
                action = "Monitor the next complete months and review category-level changes before making broad growth decisions."
                priority = "Monitor"
            insights.append({
                "id": "sales_momentum",
                "area": "Sales performance",
                "priority": priority,
                "title": "Year-over-year sales momentum",
                "summary": interpretation,
                "evidence": [
                    f"{pd.Timestamp(latest['month']):%B %Y}: R$ {float(latest['gross_sales']):,.2f} gross item sales across {int(latest['orders_placed']):,} orders.",
                    f"Change from the same month one year earlier: {growth_value:+.1f}%.",
                    f"Comparison uses months with at least 500 placed orders; data cutoff: {cutoff_label}.",
                ],
                "action": action,
                "limitation": "Historical item sales exclude freight and do not explain why sales changed. The dataset is not live.",
                "value": growth_value,
            })

    if not categories.empty:
        ranked = categories.sort_values("gross_sales", ascending=False).head(3)
        total_sales = float(categories["gross_sales"].sum())
        if total_sales > 0 and not ranked.empty:
            top_share = float(ranked["gross_sales"].sum()) / total_sales * 100
            category_list = ", ".join(str(name) for name in ranked["category"].tolist())
            insights.append({
                "id": "category_mix",
                "area": "Product mix",
                "priority": "Monitor" if top_share >= 35 else "Portfolio view",
                "title": f"Top three categories account for {top_share:.1f}% of item sales",
                "summary": f"The three highest-grossing categories account for {top_share:.1f}% of observed item sales.",
                "evidence": [
                    f"Leading categories: {category_list}.",
                    *[
                        f"{row.category}: R$ {float(row.gross_sales):,.2f} ({100 * float(row.gross_sales) / total_sales:.1f}% of category sales)."
                        for row in ranked.itertuples(index=False)
                    ],
                ],
                "action": "Review inventory and service readiness for the largest categories while checking whether smaller categories have room to grow.",
                "limitation": "Sales share is not profit share; margins, stock availability, advertising spend, and product returns are not included in this comparison.",
                "value": round(top_share, 1),
                "chart": ranked[["category", "gross_sales"]].to_dict(orient="records"),
            })

    if not segment_profiles.empty:
        at_risk = segment_profiles.loc[segment_profiles["segment"] == "At risk"]
        champions = segment_profiles.loc[segment_profiles["segment"] == "Champions"]
        if not at_risk.empty:
            row = at_risk.iloc[0]
            insights.append({
                "id": "customer_retention",
                "area": "Customer behavior",
                "priority": "Needs attention" if float(row["revenue_share_pct"]) >= 15 else "Monitor",
                "title": "Review the historical at-risk customer group",
                "summary": f"{int(row['customers']):,} customers ({float(row['customer_share_pct']):.1f}% of the base) fall into the relative RFM At risk segment and account for {float(row['revenue_share_pct']):.1f}% of observed item sales.",
                "evidence": [
                    f"All-time repeat-customer rate: {kpis.repeat_customer_rate_pct:.2f}% of unique customers with more than one order.",
                    f"At-risk segment mean item spend: R$ {float(row['avg_spend']):,.2f} per customer.",
                    f"Champions: {int(champions.iloc[0]['customers']):,} customers and {float(champions.iloc[0]['revenue_share_pct']):.1f}% of item sales." if not champions.empty else "No Champions segment was identified in this snapshot.",
                    f"RFM reference date: {cutoff_label}.",
                ],
                "action": "Use a small re-engagement experiment with a holdout group, then compare incremental repeat purchases and contribution margin before scaling.",
                "limitation": "RFM groups are relative to this historical dataset cutoff. They do not identify customers who are currently at risk or establish that a campaign will work.",
                "value": int(row["customers"]),
            })

    rated = categories.loc[categories["reviewed_orders"] > 0].copy() if not categories.empty else pd.DataFrame()
    if not rated.empty:
        baseline = float((rated["avg_review"] * rated["reviewed_orders"]).sum() / rated["reviewed_orders"].sum())
        sales_threshold = float(categories["gross_sales"].quantile(0.75))
        flagged = categories.loc[
            (categories["reviewed_orders"] >= 100)
            & (categories["gross_sales"] >= sales_threshold)
            & (categories["avg_review"] <= baseline - 0.25)
        ].sort_values("gross_sales", ascending=False)
        if not flagged.empty:
            rows = flagged.head(5)
            insights.append({
                "id": "review_opportunity",
                "area": "Product experience",
                "priority": "Needs attention",
                "title": "High-volume categories with weaker review scores",
                "summary": f"{len(flagged)} category/categories meet the review and sales screening rule; the weighted dataset baseline is {baseline:.2f}/5.",
                "evidence": [
                    f"{row.category}: {float(row.avg_review):.2f}/5 across {int(row.reviewed_orders):,} reviewed orders, with R$ {float(row.gross_sales):,.2f} in item sales."
                    for row in rows.itertuples(index=False)
                ],
                "action": "Read the underlying review comments and inspect products in these categories to identify recurring quality, listing, or fulfillment issues.",
                "limitation": "Reviews are order-level. In orders with multiple categories, a review cannot be attributed to a specific product.",
                "value": len(flagged),
            })

    delivered = regional.loc[regional["avg_delivery_days"].notna() & (regional["delivered_orders"] > 0)].copy()
    if not delivered.empty:
        baseline = float((delivered["avg_delivery_days"] * delivered["delivered_orders"]).sum() / delivered["delivered_orders"].sum())
        total_sales = max(float(regional["gross_sales"].sum()), 1.0)
        delivered["sales_share_pct"] = 100 * delivered["gross_sales"] / total_sales
        flagged = delivered.loc[
            (delivered["orders"] >= 1000)
            & (delivered["sales_share_pct"] >= 2)
            & (delivered["avg_delivery_days"] > baseline * 1.15)
        ].sort_values("avg_delivery_days", ascending=False)
        if not flagged.empty:
            insights.append({
                "id": "delivery_exceptions",
                "area": "Fulfillment",
                "priority": "Needs attention",
                "title": "High-volume markets with slower delivery",
                "summary": f"{len(flagged)} markets exceed the order-weighted delivery baseline by more than 15% while meeting the volume screening rule.",
                "evidence": [
                    f"Delivered-order weighted baseline: {baseline:.2f} days.",
                    *[
                        f"{row.state}: {float(row.avg_delivery_days):.2f} days across {int(row.delivered_orders):,} delivered orders; {float(row.sales_share_pct):.1f}% of item sales."
                        for row in flagged.head(5).itertuples(index=False)
                    ],
                ],
                "action": "Compare seller origin, route distance, and order hand-off timelines in these markets before changing carrier or service policies.",
                "limitation": "This historical association does not control for distance, product mix, or customer expectations and is not a current service-level measure.",
                "value": len(flagged),
            })

    return insights

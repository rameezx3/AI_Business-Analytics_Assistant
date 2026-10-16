"""Interactive monthly sales forecast and historical walk-forward evaluation."""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from services.charts import ChartBuilder
from services.forecasting import forecast_monthly_sales
from services.sales_analytics import SalesAnalytics


@st.cache_data(ttl="1h", max_entries=4)
def _load_monthly_sales() -> pd.DataFrame:
    """Load the source monthly series once per hour across Streamlit reruns."""
    return SalesAnalytics().monthly_sales()


st.title("📈 Sales Forecast")
st.caption("A transparent, historical forecast built from the reliable monthly sales record.")

with st.container(border=True):
    st.subheader("Forecast settings")
    horizon = st.select_slider("Months to forecast", options=[1, 2, 3, 4, 5, 6], value=3)

try:
    monthly = _load_monthly_sales()
    result = forecast_monthly_sales(monthly, horizon=horizon)
except Exception as exc:
    st.error(f"Forecast could not be generated: {exc}")
    st.stop()

source_end = pd.to_datetime(monthly["month"]).max()
st.info(
    f"This is a historical dataset ending **{source_end:%B %Y}**. "
    f"The model was trained on **{result.training_months} reliable months** "
    f"({result.training_start:%b %Y}–{result.training_end:%b %Y}); "
    "low-volume edge months were excluded from training. Forecast dates are therefore historical projections."
)

metric_cols = st.columns(4)
metric_cols[0].metric("Selected model", result.model_name)
metric_cols[1].metric("Walk-forward MAE", f"R$ {result.mae:,.0f}")
metric_cols[2].metric("Walk-forward MAPE", f"{result.mape_pct:.1f}%")
metric_cols[3].metric("Backtest months", result.backtest_points)

historical = monthly.loc[monthly["reliable"], ["month", "gross_sales"]].copy()
historical["month"] = pd.to_datetime(historical["month"])
fig = ChartBuilder.line(historical, "month", "gross_sales", "Reliable monthly sales and forecast", "Gross sales (R$)")
fig.data[0].name = "Actual sales"
fig.data[0].showlegend = True
fig.add_scatter(
    x=result.forecast["month"], y=result.forecast["upper_90"],
    mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip", name="Upper range",
)
fig.add_scatter(
    x=result.forecast["month"], y=result.forecast["lower_90"],
    mode="lines", line=dict(width=0), fill="tonexty", fillcolor="rgba(85,217,239,.16)",
    showlegend=True, name="Approx. 90% empirical range", hoverinfo="skip",
)
fig.add_scatter(
    x=result.forecast["month"], y=result.forecast["forecast"],
    mode="lines+markers", line=dict(color="#55d9ef", width=3, dash="dash"),
    marker=dict(size=9), name="Forecast",
)
fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0))
st.plotly_chart(fig, width="stretch", alt="Reliable historical monthly sales with forecast and an empirical uncertainty range")

st.subheader("Forecast values")
display = result.forecast.rename(columns={
    "month": "Month", "forecast": "Forecast sales (R$)",
    "lower_90": "Lower range (R$)", "upper_90": "Upper range (R$)",
})
display["Month"] = display["Month"].dt.strftime("%B %Y")
st.dataframe(
    display.style.format({
        "Forecast sales (R$)": "R$ {:,.2f}",
        "Lower range (R$)": "R$ {:,.2f}",
        "Upper range (R$)": "R$ {:,.2f}",
    }), hide_index=True, width="stretch", alt="Monthly forecast values with lower and upper empirical ranges",
)

with st.expander("How to interpret this forecast"):
    st.markdown(
        "- Two simple candidates are compared using expanding-window, one-month-ahead validation: "
        "a last-month baseline and a linear trend. The candidate with lower mean absolute error is selected.\n"
        "- MAE is the average absolute forecast error in Brazilian reais. MAPE is the average absolute "
        "error as a percentage of actual sales. Validation always trains on earlier months and predicts a later month.\n"
        "- The shaded range uses the 90th percentile of the selected model's historical absolute backtest errors "
        "and widens with the forecast horizon. It is a small-sample empirical guide, not a formal confidence interval.\n"
        "- The Olist history is short and ends in 2018. This forecast demonstrates the method; it should not be "
        "used as a current business plan or extrapolated as a reliable long-term prediction."
    )

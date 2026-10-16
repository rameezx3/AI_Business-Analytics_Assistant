"""
services/charts.py

WHY THIS FILE EXISTS:
    Module 9: a reusable, consistently-themed chart-building layer.
    Module 7's Home page built its Plotly figure inline (axis labels,
    layout, styling all hand-written in dashboard/home.py). That doesn't
    scale: Modules 10-14 will add ~10 more pages full of charts, and
    without a shared layer, every page would re-invent styling and
    likely drift into visually inconsistent results (different fonts,
    colors, margins page to page). ChartBuilder fixes the visual theme
    in ONE place, so every chart in the app looks like it belongs to
    the same product.

    This module builds generic, reusable CHART TYPES (line, bar, pie,
    funnel, heatmap, scatter, histogram) - not business-specific charts.
    A "revenue by category" chart is Module 11/12's job to build USING
    ChartBuilder.horizontal_bar(); this file doesn't know what a
    category or an order is.

WHERE THIS FILE BELONGS:
    AI_Business_Analytics_Assistant/services/charts.py
"""

from contextvars import ContextVar
from typing import List, Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Single source of truth for the dashboard's visual identity. Change
# these and every chart in the app updates consistently.
THEME = {
    "colorway": px.colors.qualitative.Set2,
    "font_family": "Manrope, DM Sans, sans-serif",
    "title_font_size": 18,
    "template": "plotly_dark",
}

_ACTIVE_THEME: ContextVar[str] = ContextVar("chart_theme", default="dark")


def set_chart_theme(theme: str) -> None:
    """Set the chart palette for the current Streamlit render context."""
    _ACTIVE_THEME.set("light" if theme == "light" else "dark")


def _apply_theme(fig: go.Figure, title: str) -> go.Figure:
    """Applies the shared visual theme to any figure. Internal helper - not part of the public API."""
    light = _ACTIVE_THEME.get() == "light"
    text_color = "#334155" if light else "#cbd8eb"
    title_color = "#172b4d" if light else "#eaf2ff"
    grid_color = "rgba(100,116,139,.16)" if light else "rgba(151,177,209,.12)"
    fig.update_layout(
        title=title,
        template="plotly_white" if light else THEME["template"],
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=THEME["font_family"], color=text_color),
        title_font=dict(size=THEME["title_font_size"], color=title_color),
        colorway=px.colors.qualitative.Dark2 if light else THEME["colorway"],
        margin=dict(l=40, r=20, t=60, b=40),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="#fff" if light else "#132238",
            bordercolor="#cbd5e1" if light else "#35516f",
            font_color="#172b4d" if light else "#eaf2ff",
        ),
    )
    fig.update_xaxes(gridcolor=grid_color, zerolinecolor=grid_color)
    fig.update_yaxes(gridcolor=grid_color, zerolinecolor=grid_color)
    return fig


def _label(column_name: str) -> str:
    """Turns a snake_case column name into a readable axis label: 'order_count' -> 'Order Count'."""
    return column_name.replace("_", " ").title()


class ChartBuilder:
    """
    Stateless chart factory. Every method takes a DataFrame plus column
    names and returns a themed go.Figure, ready for st.plotly_chart().
    No method queries a database or knows about business concepts -
    callers (dashboard pages, via services/ analytics modules) supply
    already-queried data.
    """

    @staticmethod
    def line(df: pd.DataFrame, x: str, y: str, title: str, y_label: Optional[str] = None) -> go.Figure:
        """A trend line over time or any ordered axis. Used by Home's monthly order volume."""
        fig = px.line(df, x=x, y=y, markers=True)
        fig.update_layout(xaxis_title=_label(x), yaxis_title=y_label or _label(y))
        return _apply_theme(fig, title)

    @staticmethod
    def multi_line(df: pd.DataFrame, x: str, y_columns: List[str], title: str) -> go.Figure:
        """Multiple series over the same x-axis (e.g. revenue AND order count by month)."""
        fig = go.Figure()
        for col in y_columns:
            fig.add_trace(go.Scatter(x=df[x], y=df[col], mode="lines+markers", name=_label(col)))
        fig.update_layout(xaxis_title=_label(x))
        return _apply_theme(fig, title)

    @staticmethod
    def bar(df: pd.DataFrame, x: str, y: str, title: str, color: Optional[str] = None) -> go.Figure:
        """Vertical bar chart - good for a moderate number of categories (e.g. order status counts)."""
        fig = px.bar(df, x=x, y=y, color=color)
        fig.update_layout(xaxis_title=_label(x), yaxis_title=_label(y))
        return _apply_theme(fig, title)

    @staticmethod
    def stacked_bar(df: pd.DataFrame, x: str, y_columns: List[str], title: str) -> go.Figure:
        """
        Stacked bars: how a total splits into parts over an ordered axis
        (e.g. each month's active customers split into new vs returning).
        One trace per column in y_columns, stacked in the order given.
        """
        fig = go.Figure()
        for col in y_columns:
            fig.add_trace(go.Bar(x=df[x], y=df[col], name=_label(col)))
        fig.update_layout(barmode="stack", xaxis_title=_label(x))
        return _apply_theme(fig, title)

    @staticmethod
    def horizontal_bar(df: pd.DataFrame, category: str, value: str, title: str, top_n: Optional[int] = None) -> go.Figure:
        """
        Horizontal bar - the right choice when category LABELS are long
        (product category names, state names) since they stay readable
        instead of being rotated/truncated on a vertical x-axis.
        """
        data = df.nlargest(top_n, value) if top_n else df
        data = data.sort_values(value)  # ascending, so the largest bar ends up on top visually
        fig = px.bar(data, x=value, y=category, orientation="h")
        fig.update_layout(xaxis_title=_label(value), yaxis_title=_label(category))
        return _apply_theme(fig, title)

    @staticmethod
    def pie(df: pd.DataFrame, names: str, values: str, title: str, donut: bool = True) -> go.Figure:
        """Pie/donut chart - for a SMALL number of categories only (payment type, order status mix)."""
        fig = px.pie(df, names=names, values=values, hole=0.4 if donut else 0.0)
        return _apply_theme(fig, title)

    @staticmethod
    def funnel(stage_labels: List[str], stage_values: List[int], title: str) -> go.Figure:
        """
        Funnel chart - for a sequential process with a natural order
        and decreasing counts (e.g. the order status pipeline: created
        -> approved -> shipped -> delivered). stage_labels and
        stage_values must be the same length and in pipeline order.
        """
        fig = go.Figure(go.Funnel(y=stage_labels, x=stage_values, textinfo="value+percent initial"))
        return _apply_theme(fig, title)

    @staticmethod
    def heatmap(
        matrix: pd.DataFrame, title: str,
        zmin: Optional[float] = -1, zmax: Optional[float] = 1,
        color_scale: str = "RdBu_r", show_values: bool = True,
    ) -> go.Figure:
        """
        Heatmap of a DataFrame (rows x columns).

        Defaults suit a CORRELATION matrix (diverging red-blue scale,
        fixed -1..1 range, value printed in every cell). For counts or
        other one-directional data pass e.g. zmin=None, zmax=None,
        color_scale="Blues", show_values=False - a diverging scale
        would wrongly imply a meaningful midpoint, and printing a
        number in each of 168 weekday-by-hour cells is unreadable.
        """
        fig = px.imshow(
            matrix, text_auto=".2f" if show_values else False,
            color_continuous_scale=color_scale, zmin=zmin, zmax=zmax, aspect="auto",
        )
        return _apply_theme(fig, title)

    @staticmethod
    def scatter(df: pd.DataFrame, x: str, y: str, title: str, color: Optional[str] = None,
                size: Optional[str] = None) -> go.Figure:
        """Scatter plot - for relationships between two numeric variables (e.g. price vs. review score)."""
        fig = px.scatter(df, x=x, y=y, color=color, size=size, opacity=0.6)
        fig.update_layout(xaxis_title=_label(x), yaxis_title=_label(y))
        return _apply_theme(fig, title)

    @staticmethod
    def histogram(df: pd.DataFrame, column: str, title: str, nbins: int = 50, log_x: bool = False) -> go.Figure:
        """
        Distribution of a single numeric column (e.g. order price distribution).

        WHY THIS BINS THE DATA ITSELF INSTEAD OF USING px.histogram:
            px.histogram embeds every raw row in the figure and lets the
            browser do the binning. Measured on the real order_items
            table: 112,650 prices produced a ~1.2 MB figure, sent to the
            browser on every Streamlit rerun, growing with the data. Here
            the bins are computed with numpy and only the bar heights are
            sent, so the payload is a few KB regardless of row count.
            With log_x=True the bin edges are log-spaced (values must be
            > 0; non-positive values are dropped), matching how a
            log-scale histogram is meant to look.
        """
        values = df[column].dropna()
        if log_x:
            values = values[values > 0]
        if values.empty:
            raise ValueError(f"No plottable values in column '{column}'.")

        if log_x:
            edges = np.logspace(np.log10(values.min()), np.log10(values.max()), nbins + 1)
        else:
            edges = np.linspace(values.min(), values.max(), nbins + 1)
        # Pin the outer edges to the exact data min/max. np.logspace goes
        # through log10/10**x, so floating-point error can nudge the first
        # edge slightly ABOVE the true minimum (found by a test: 5 became
        # 5.000000000000001), which silently drops the smallest row(s)
        # from every bin. Same risk, in reverse, at the top edge.
        edges[0], edges[-1] = values.min(), values.max()
        counts, edges = np.histogram(values, bins=edges)
        centers = np.sqrt(edges[:-1] * edges[1:]) if log_x else (edges[:-1] + edges[1:]) / 2

        fig = go.Figure(go.Bar(
            x=centers, y=counts, width=np.diff(edges),
            hovertemplate=f"{_label(column)}: %{{x:,.2f}}<br>Count: %{{y:,}}<extra></extra>",
        ))
        fig.update_layout(
            xaxis_title=_label(column), yaxis_title="Count",
            xaxis_type="log" if log_x else "linear", bargap=0.02, showlegend=False,
        )
        return _apply_theme(fig, title)

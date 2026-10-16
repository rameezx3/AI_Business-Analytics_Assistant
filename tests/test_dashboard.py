"""
tests/test_dashboard.py

WHY THIS FILE EXISTS:
    Confirms Module 7 works end-to-end using Streamlit's own AppTest
    framework: every page loads without an unhandled exception, the
    Home page's live metrics match the real database, navigation
    between pages works, and a down database is handled gracefully
    instead of crashing (a real gap found and fixed during development
    - see dashboard/home.py's render() docstring comment).

    Run manually:  python tests/test_dashboard.py
    Or via pytest: pytest tests/test_dashboard.py -v
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from streamlit.testing.v1 import AppTest  # noqa: E402

from database.connection import db  # noqa: E402
from utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)

# WHY THESE ARE ABSOLUTE PATHS:
# AppTest.from_file() resolves relative paths against the file that
# CALLS it (this test file, in tests/), not the current working
# directory - so a plain "dashboard/home.py" would incorrectly resolve
# to tests/dashboard/home.py and fail with FileNotFoundError (found by
# actually running this test). Anchoring to the project root fixes it.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALL_PAGES = [
    str(PROJECT_ROOT / "dashboard" / name) for name in [
        "home.py", "sales.py", "customers.py", "products.py", "orders.py",
        "data_lab.py", "geography.py", "sellers.py", "forecast.py", "ai_assistant.py", "reports.py", "admin_dashboard.py", "settings.py",
    ]
]
APP_ENTRY = str(PROJECT_ROOT / "app.py")


def test_every_page_loads_without_exception() -> None:
    """Every page file must run cleanly on its own via AppTest.from_file()."""
    for page in ALL_PAGES:
        at = AppTest.from_file(page)
        at.run(timeout=30)
        assert not at.exception, f"{page} raised an exception: {at.exception}"


def test_home_page_shows_real_metrics() -> None:
    """Home page's KPIs must reflect the actual database, not placeholders."""
    at = AppTest.from_file(ALL_PAGES[0])  # dashboard/home.py
    at.run(timeout=30)
    assert not at.exception
    # Home renders these headline KPIs as clickable buttons so selecting a
    # card opens its definition and recent trend; they are not st.metric widgets.
    labels = {button.label for button in at.button}
    assert all(any(label in button for button in labels) for label in (
        "Total Orders", "Total Revenue", "Unique Customers", "Avg Review Score"
    ))


def test_home_page_renders_themed_trend_chart() -> None:
    """
    Home must render exactly one Plotly chart, built through the shared
    ChartBuilder (Module 9) - checked by looking for its title and the
    shared theme font in the figure spec Streamlit actually sends to
    the browser, not just 'the page didn't crash'.
    """
    import json

    at = AppTest.from_file(ALL_PAGES[0])
    at.run(timeout=30)
    assert not at.exception

    charts = at.get("plotly_chart")
    assert len(charts) == 1, f"expected 1 chart on Home, found {len(charts)}"
    spec = json.loads(charts[0].proto.spec)
    assert spec["layout"]["title"]["text"] == "Monthly Order Volume"
    assert "Manrope" in spec["layout"]["font"]["family"]
    assert len(spec["data"][0]["x"]) > 12, "trend chart should have the full monthly series"


CUSTOMERS_PAGE = str(PROJECT_ROOT / "dashboard" / "customers.py")


def test_customers_page_shows_real_numbers_and_all_charts() -> None:
    """
    Module 10: the page must show the SAME numbers the service computes
    (not placeholders) and render all 5 charts.
    """
    import json

    from services.customer_analytics import CustomerAnalytics

    summary = CustomerAnalytics().summary()

    at = AppTest.from_file(CUSTOMERS_PAGE)
    at.run(timeout=60)
    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Unique Customers"] == f"{summary.unique_customers:,}"
    assert metrics["Repeat Rate (2+ orders)"] == f"{summary.repeat_rate_pct}%"
    assert metrics["Returned After 24h"] == f"{summary.returned_after_24h_rate_pct}%"

    titles = [json.loads(c.proto.spec)["layout"]["title"]["text"] for c in at.get("plotly_chart")]
    assert len(titles) == 5, f"expected 5 charts, found {titles}"
    assert any("New vs Returning" in t for t in titles)


def test_customers_page_handles_database_being_down() -> None:
    """If the DB is unreachable the page must show a friendly error, not a crash trace."""
    from unittest.mock import patch

    from database.connection import DatabaseConnection

    with patch.object(DatabaseConnection, "test_connection", return_value=False):
        at = AppTest.from_file(CUSTOMERS_PAGE)
        at.run(timeout=60)
    assert not at.exception
    assert any("Cannot connect to the database" in e.value for e in at.error)
    assert len(at.get("plotly_chart")) == 0


SALES_PAGE = str(PROJECT_ROOT / "dashboard" / "sales.py")


def _chart_specs(at) -> list:
    import json

    return [json.loads(c.proto.spec) for c in at.get("plotly_chart")]


def test_sales_page_shows_real_numbers_and_all_charts() -> None:
    """Module 11: metrics equal the service's numbers; all 10 charts render."""
    from services.sales_analytics import SalesAnalytics

    s = SalesAnalytics().summary()
    at = AppTest.from_file(SALES_PAGE)
    at.run(timeout=90)
    assert not at.exception
    m = {x.label: x.value for x in at.metric}
    assert m["Gross Sales"] == f"R$ {s.gross_sales:,.2f}"
    assert m["Avg Order Value"] == f"R$ {s.avg_order_value:,.2f}"
    assert m["Year-over-Year Growth"] == f"{s.yoy_growth_pct:+.1f}%"
    assert m["Best Month"] == s.best_month
    assert len(_chart_specs(at)) == 10


def test_sales_trend_chart_shows_the_empty_month_and_flags_unreliable_months() -> None:
    """The first chart must cover EVERY calendar month and split full vs ramp-up/cutoff months."""
    at = AppTest.from_file(SALES_PAGE)
    at.run(timeout=90)
    spec = _chart_specs(at)[0]
    assert spec["layout"]["title"]["text"] == "Gross Sales by Month"
    names = {t["name"] for t in spec["data"]}
    assert names == {"Full trading month", "Ramp-up / cutoff (few orders)"}
    months = sorted(x for t in spec["data"] for x in t["x"])
    assert len(months) == 26, "every calendar month, including the one with no orders, must be plotted"


def test_sales_daily_chart_responds_to_the_date_picker() -> None:
    """Interactivity: choosing Nov 2017 must redraw the daily chart with exactly 30 days."""
    from datetime import date

    at = AppTest.from_file(SALES_PAGE)
    at.run(timeout=90)
    at.date_input[0].set_value((date(2017, 11, 1), date(2017, 11, 30))).run(timeout=90)
    assert not at.exception
    daily = next(s for s in _chart_specs(at) if s["layout"]["title"]["text"].startswith("Daily Gross Sales"))
    assert "01 Nov 2017 to 30 Nov 2017" in daily["layout"]["title"]["text"]
    assert len(daily["data"][0]["x"]) == 30


def test_sales_page_survives_a_half_finished_date_selection() -> None:
    """While a user is still choosing, the picker returns ONE date; the page must not crash."""
    from datetime import date

    at = AppTest.from_file(SALES_PAGE)
    at.run(timeout=90)
    at.date_input[0].set_value((date(2017, 11, 1),)).run(timeout=90)
    assert not at.exception
    assert any("end date" in i.value for i in at.info)


def test_sales_page_handles_database_being_down() -> None:
    from unittest.mock import patch

    from database.connection import DatabaseConnection

    with patch.object(DatabaseConnection, "test_connection", return_value=False):
        at = AppTest.from_file(SALES_PAGE)
        at.run(timeout=60)
    assert not at.exception
    assert any("Cannot connect to the database" in e.value for e in at.error)
    assert len(at.get("plotly_chart")) == 0


def test_navigation_between_pages_works() -> None:
    """switch_page() must move between pages through the real app.py entry point."""
    at = AppTest.from_file(APP_ENTRY)
    at.run(timeout=30)
    assert not at.exception

    at.switch_page("dashboard/settings.py")
    at.run(timeout=30)
    assert not at.exception
    assert any("Settings" in t.value for t in at.title)


if __name__ == "__main__":
    logger.info("Running standalone dashboard check...")

    if not db.test_connection():
        print("WARNING: database not reachable - some checks may fail.")

    all_ok = True
    for page in ALL_PAGES:
        at = AppTest.from_file(page)
        at.run(timeout=30)
        if at.exception:
            all_ok = False
            print(f"[FAIL] {page}: {at.exception}")
        else:
            print(f"[OK]   {page}")

    print("\nSUCCESS: all pages loaded cleanly." if all_ok else "\nFAILED: see above.")
    sys.exit(0 if all_ok else 1)

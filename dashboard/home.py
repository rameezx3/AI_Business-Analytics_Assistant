"""
dashboard/home.py

The dashboard's landing page - fully functional (unlike most other
pages wired up in Module 7, which are placeholders for later modules).
Shows headline KPIs (via Module 8's KPICalculator), an interactive
order-volume trend, and the most recent data validation run (Module 5).

WHY THIS NOW IMPORTS services/kpi.py INSTEAD OF QUERYING DIRECTLY:
    The original version had its own inline SQL for "Total Customers"
    using COUNT(*) FROM customers - which counts customer_id (one row
    per ORDER), not real distinct people. That's exactly the mistake
    Module 8's KPICalculator was built to prevent (and has a dedicated
    regression test for). Routing through the shared service fixes this
    page's numbers AND means every future page gets the same, correct
    definitions for free instead of re-deriving them.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from sqlalchemy import text

from database.connection import db
from services.charts import ChartBuilder, set_chart_theme
from services.kpi import KPICalculator, KPISet


KPI_DETAILS = {
    "total_orders": {
        "title": "Total Orders", "field": "total_orders", "format": "count",
        "formula": "Count of distinct orders by `order_id`.",
        "definition": "Counts every order in the selected purchase-date window, including cancelled and in-progress orders.",
        "slice": "Orders are filtered by `order_purchase_timestamp`; customer, item, review, and delivery tables are joined only where each definition needs them.",
    },
    "total_revenue": {
        "title": "Total Revenue", "field": "total_revenue", "format": "money",
        "formula": "Sum of `order_items.price` for orders in the selected window.",
        "definition": "Product sales across all order statuses. Freight is excluded because it is a pass-through shipping charge.",
        "slice": "Order items are matched to orders by `order_id` and filtered by purchase timestamp.",
    },
    "unique_customers": {
        "title": "Unique Customers", "field": "unique_customers", "format": "count",
        "formula": "Count of distinct `customers.customer_unique_id`.",
        "definition": "Counts real people, rather than the order-level `customer_id`, which can differ for the same person.",
        "slice": "Customer records are joined to orders in the selected purchase-date window.",
    },
    "average_review_score": {
        "title": "Avg Review Score", "field": "average_review_score", "format": "score",
        "formula": "Average of `order_reviews.review_score`.",
        "definition": "Mean review score on the 1–5 scale for reviews linked to orders in the selected window.",
        "slice": "Review rows are joined to orders by `order_id`; orders without a review do not enter the average.",
    },
    "average_order_value": {
        "title": "Avg Order Value", "field": "average_order_value", "format": "money",
        "formula": "Product revenue ÷ distinct orders that contain at least one item.",
        "definition": "Average value of orders with purchased items. Cancelled or unavailable orders with no items do not dilute the average; freight is excluded.",
        "slice": "Order items and orders are filtered to the same purchase-date window.",
    },
    "fulfillment_rate_pct": {
        "title": "Fulfillment Rate", "field": "fulfillment_rate_pct", "format": "percent",
        "formula": "Delivered orders ÷ all orders × 100.",
        "definition": "Share of orders in the window whose status is `delivered`.",
        "slice": "All orders in the selected purchase-date window are the denominator; delivered orders form the numerator.",
    },
    "average_delivery_days": {
        "title": "Avg Delivery Time", "field": "average_delivery_days", "format": "days",
        "formula": "Average of (delivered timestamp − purchase timestamp), in days.",
        "definition": "Mean elapsed time for orders with a recorded customer delivery date.",
        "slice": "Orders are filtered by purchase timestamp. Undelivered orders without a delivery date are excluded.",
    },
    "repeat_customer_rate_pct": {
        "title": "Repeat Customer Rate", "field": "repeat_customer_rate_pct", "format": "percent",
        "formula": "Customers with more than one order ÷ distinct customers × 100.",
        "definition": "Share of distinct people who placed at least two orders inside the selected window.",
        "slice": "Orders are grouped by `customer_unique_id` after filtering by purchase timestamp.",
    },
}


MODULE_DETAILS = [
    (1, "Database Connection", "complete", "Creates the shared PostgreSQL engine and session factory used by application services.", "`.env` settings → SQLAlchemy engine → PostgreSQL; SQLAlchemy, pg8000, python-dotenv.", ["Environment-based credentials and validation", "Pooled connections and health check", "Shared session factory"]),
    (2, "Database Schema", "complete", "Defines the relational Olist schema, ORM models, primary keys, foreign keys, and useful indexes.", "SQLAlchemy ORM models → PostgreSQL tables; SQLAlchemy and PostgreSQL.", ["Core tables and relationships modeled", "Constraints and indexes declared", "Schema initialization available"]),
    (3, "CSV Import", "complete", "Loads the nine source CSVs in foreign-key-safe order with coercion, batching, duplicate handling, and row-count checks.", "Nine Olist CSV files → typed batches → PostgreSQL; Python csv, Pandas, NumPy, SQLAlchemy, pg8000.", ["Nine source tables imported", "Chunked inserts and type coercion", "Post-load row counts checked"]),
    (4, "Data Cleaning", "complete", "Applies documented fixes for source-data quality issues while recording what changed.", "PostgreSQL source tables → cleaning rules → cleaned tables and quality log; SQLAlchemy and PostgreSQL.", ["Known category and geolocation issues handled", "Cleaning is re-runnable", "Changes logged"]),
    (5, "Data Validation", "complete", "Runs data-health checks and records pass, warning, and failure results for each run.", "PostgreSQL tables → SQL validation checks → validation log; SQLAlchemy and PostgreSQL.", ["Row counts and relationships checked", "Business-value rules checked", "Run-level status history stored"]),
    (6, "Exploratory Data Analysis", "complete", "Profiles the dataset and produces a static EDA report with distributions and relationships.", "PostgreSQL → Pandas analysis → charts/reports; Pandas, Matplotlib, Seaborn.", ["Core distributions and trends analyzed", "EDA charts generated", "Report artifact written"]),
    (7, "Dashboard Shell", "complete", "Provides the Streamlit app entry point, page routing, shared presentation, and Home dashboard.", "Streamlit pages → shared services → PostgreSQL; Streamlit and Python.", ["File-based page navigation", "Home and settings views", "Shared responsive theme"]),
    (8, "KPI Engine", "complete", "Calculates the project’s reusable business KPIs with documented definitions and optional date-window comparisons.", "SQL aggregate queries → typed KPI results; SQLAlchemy and PostgreSQL.", ["Revenue and order metrics defined", "Customer and fulfillment metrics defined", "Period comparisons supported"]),
    (9, "Chart Library", "complete", "Builds consistent reusable chart types for the dashboard, including compact binned histograms.", "Pandas/NumPy data → Plotly figures; Plotly, Pandas, NumPy.", ["Reusable chart builders available", "Shared light/dark styling", "Large histograms binned before browser rendering"]),
    (10, "Customer Analytics", "complete", "Profiles distinct customers, repeat behavior, spend, state/city breakdowns, and follow-up ordering patterns.", "PostgreSQL CTEs → Pandas customer snapshot → Streamlit/Plotly views; SQLAlchemy, Pandas, Plotly.", ["Customer-level table and summary", "Geography and spend breakdowns", "Repeat and follow-up analysis"]),
    (11, "Sales Analytics", "complete", "Analyzes sales trends, order value, categories, regions, payment mix, and demand timing.", "PostgreSQL aggregates → Pandas summaries → Plotly charts; SQLAlchemy, Pandas, Plotly.", ["Sales and date-window views", "Product, state, and payment breakdowns", "Demand and order-value analysis"]),
    (12, "Product Analytics", "complete", "Analyzes product/category performance, order review quality, and product-content signals.", "PostgreSQL aggregates → Pandas summaries → shared Plotly charts; SQLAlchemy, Pandas, ChartBuilder.", ["Category sales and review breakdowns", "Top and low-volume product rankings", "Photo and description-length sales comparisons"]),
    (13, "Geographical Analytics", "complete", "Compares Brazilian buyer-state sales and delivery time, and estimates seller-to-customer distance using ZIP-prefix centroids.", "PostgreSQL customer, seller, order, item, and geolocation tables → state summaries and great-circle distance estimates; SQLAlchemy, Pandas, Plotly.", ["Regional sales and delivery view", "Buyer-state coordinates and sales markers", "Seller–buyer distance and cross-state share"]),
    (14, "Seller Analytics", "complete", "Compares sellers by item sales, seller-order volume, review results, state, and delivery-time signals.", "PostgreSQL sellers, order items, orders, and reviews → seller-level summaries and monthly trends; SQLAlchemy, Pandas, Plotly.", ["Top sellers by gross item sales", "Review averages per distinct seller/order", "Monthly trend and state comparison"]),
    (15, "Forecasting", "complete", "Forecasts monthly gross sales from reliable history, compares a last-month baseline with a linear trend, and scores them by chronological walk-forward validation.", "PostgreSQL monthly sales → reliability filtering → walk-forward model comparison → forecast and empirical error range; NumPy, Pandas, Plotly.", ["Forecast sales for 1–6 months", "Show an empirical uncertainty range", "Track MAE and MAPE on held-out months"]),
    (16, "Customer Segmentation", "complete", "Groups people into explainable behavioral segments using relative Recency, Frequency, and Monetary-value scores.", "Customer-level purchase history → RFM quintile scores → transparent segment rules and profiles; SQLAlchemy, Pandas, Plotly.", ["Profile recency, order frequency, and item spend", "Compare segment size and sales contribution", "Explore state mix and export segment profiles"]),
    (17, "Recommendation Engine", "complete", "Builds transparent customer-retention, product-experience, and delivery recommendations from measured rules and supporting evidence.", "Existing RFM segments, category sales/reviews, and one-row-per-order delivery metrics → rule checks → actions with evidence and limitations; Pandas, SQLAlchemy, Streamlit.", ["Surface retention and review opportunities", "Flag slower high-volume markets", "Show evidence, thresholds, and caveats"]),
    (18, "Natural Language SQL", "complete", "Maps plain-English business questions into validated query plans, compiles only approved read-only SQL, and returns results with a chart.", "Question → local parser or optional Claude/OpenAI plan → whitelisted parameterized SQL → read-only PostgreSQL query → table/chart; Python, SQLAlchemy, Streamlit.", ["Ask supported sales/customer/product questions", "Inspect SQL and bound parameters", "Use a query timeout and database read-only transaction"]),
    (19, "LLM Chat", "complete", "Provides a session-based conversational assistant for safe, data-backed business questions and contextual year/state follow-ups.", "Chat turns → optional Claude/OpenAI interpretation and narrative → Module 18 validated plan → parameterized read-only SQL → result chart and table; Streamlit, Python, SQLAlchemy.", ["Maintain chat history for the browser session", "Answer supported data questions with verified database results", "Support optional Claude/OpenAI APIs and no-key local mode"]),
    (20, "Business Insight Generator", "complete", "Generates deterministic evidence-linked findings across sales momentum, product mix, customer behavior, review scores, and delivery performance.", "KPI, reliable monthly sales, RFM profiles, category reviews, and order-level regional delivery → transparent insight rules → evidence, thresholds, actions, limitations, and CSV; Pandas, SQLAlchemy, Streamlit.", ["Summarize measurable sales and customer patterns", "Flag category-review and delivery exceptions", "Show evidence, practical actions, assumptions, and limitations"]),
    (21, "PDF Report Generator", "complete", "Builds downloadable multi-page PDF reports from current verified analytics and provides the saved EDA report and charts in-app.", "KPI, reliable monthly sales, product categories, and evidence-linked findings → selected report template → ReportLab PDF with charts, page numbers, definitions, and limitations; saved Module 6 EDA markdown and figures → in-app viewer/download.", ["Generate executive, sales/product, and customer/fulfillment PDF templates", "Include KPI summaries, charts, evidence, actions, and data limitations", "View/download the saved EDA report and nine charts"]),
    (22, "System Health Dashboard", "complete", "Provides a read-only overview of database health, source-table row counts, data coverage, validation history, and cleaning audit records.", "Authenticated account → read-only dashboard → cached PostgreSQL system snapshot with a manual refresh control; infrastructure configuration stays admin-only.", ["Monitor database and business-table availability", "Review latest validation results and quality findings", "Inspect recent cleaning audit records without modifying data"]),
    (23, "Authentication", "complete", "Provides Admin/User sign-in, user registration, salted password hashing, temporary lockout after repeated failures, and role-based access.", "Admin accounts receive Olist database analytics and Settings; regular accounts receive session-only uploaded-data insights and the demo; passwords use salted hashes in PostgreSQL.", ["Provision the administrator privately", "Allow users to register without admin access", "Keep uploaded files separate from Olist database analytics"]),
    (24, "Deployment", "up_next", "Production hosting, managed secrets, and release checks remain to be completed.", "Streamlit hosting or another target → HTTPS, protected database/model secrets, and production environment; hosting target to be selected.", ["Choose hosting target", "Configure secrets and database", "Run production smoke checks"]),
]


def render_hero(light_theme: bool = False, is_admin: bool = False) -> None:
    """Small, dependency-free canvas hero with a pointer-reactive node field."""
    hero_html = """
    <div class="hero" aria-label="AI Business Analytics Assistant">
      <canvas id="field" aria-hidden="true"></canvas>
      <div class="hero-copy">
        <div class="eyebrow"><span class="pulse"></span> ANALYTICS, IN MOTION</div>
        <div class="hero-title">AI Business<br><span>Analytics Assistant</span></div>
        <div class="hero-sub">A clearer view of every signal in your business.</div>
        <div class="hero-meta"><span>OLIST COMMERCE DATA</span><i></i><span>LIVE INSIGHTS</span><i></i><span>23 / 24 MODULES ACTIVE</span></div>
      </div>
    </div>
    <style>
      *{box-sizing:border-box} body{margin:0;background:transparent;font-family:'DM Sans',Arial,sans-serif;color:#edf5ff}
      .hero{height:280px;position:relative;overflow:hidden;border:1px solid rgba(145,184,232,.17);border-radius:22px;background:radial-gradient(ellipse at 78% 50%,rgba(62,95,205,.2),transparent 35%),linear-gradient(115deg,rgba(13,24,42,.98),rgba(10,17,31,.88));box-shadow:0 22px 55px rgba(0,0,0,.27),inset 0 1px rgba(255,255,255,.05);isolation:isolate}
      .hero:after{content:'';position:absolute;inset:0;background:linear-gradient(90deg,rgba(12,21,36,.98) 5%,rgba(12,21,36,.85) 43%,rgba(12,21,36,.1) 100%);z-index:-1}
      #field{position:absolute;inset:0;width:100%;height:100%;z-index:-2}
      .hero-copy{position:relative;padding:38px 42px;pointer-events:none}
      .eyebrow{font-size:10px;letter-spacing:.2em;font-weight:700;color:#a5bed8;display:flex;align-items:center;gap:9px}
      .pulse{width:7px;height:7px;background:#57e2ef;border-radius:50%;box-shadow:0 0 13px #57e2ef;animation:pulse 2s ease-in-out infinite}
      .hero-title{font-family:'Manrope','DM Sans',Arial,sans-serif;font-size:38px;line-height:1.13;letter-spacing:-.045em;font-weight:800;margin-top:15px;animation:rise .8s ease both;color:#f5f8ff;transform-style:preserve-3d;transform:perspective(800px) rotateY(var(--tilt-x,0deg)) rotateX(var(--tilt-y,0deg)) translateZ(10px);transition:transform .16s ease-out}
      .hero-title span{background:linear-gradient(100deg,#f6f9ff 5%,#9deaf3 52%,#a7a0ff 100%);background-clip:text;-webkit-background-clip:text;color:transparent;text-shadow:0 8px 32px rgba(85,217,239,.14)}
      .hero-sub{font-size:14px;color:#a9bad0;margin-top:12px;animation:rise .9s .08s ease both}
      .hero-meta{position:absolute;top:220px;left:42px;display:flex;align-items:center;gap:12px;font-size:9px;font-weight:700;letter-spacing:.13em;color:#8fa6c2}
      .hero-meta i{height:3px;width:3px;border-radius:50%;background:#59dcea;box-shadow:0 0 8px #59dcea}
      .hero.light{background:radial-gradient(ellipse at 78% 50%,rgba(115,130,235,.13),transparent 37%),linear-gradient(115deg,#fff,#edf4fb);border-color:rgba(89,119,156,.2);box-shadow:0 18px 42px rgba(42,67,101,.12),inset 0 1px #fff}
      .hero.light:after{background:linear-gradient(90deg,rgba(255,255,255,.97) 5%,rgba(255,255,255,.88) 43%,rgba(255,255,255,.12) 100%)}
      .hero.light .eyebrow{color:#58708e}.hero.light .hero-title{color:#172b4d}.hero.light .hero-title span{background:linear-gradient(100deg,#234563 5%,#087e9c 52%,#6956cf 100%);background-clip:text;-webkit-background-clip:text;color:transparent;text-shadow:0 8px 28px rgba(8,126,156,.1)}
      .hero.light .hero-sub{color:#536984}.hero.light .hero-meta{color:#687f9b}
      @keyframes rise{from{opacity:0;transform:translateY(9px)}to{opacity:1;transform:translateY(0)}} @keyframes pulse{50%{opacity:.5;box-shadow:0 0 4px #57e2ef}}
      @media(max-width:650px){.hero{height:270px}.hero-copy{padding:31px 24px}.hero-title{font-size:30px}.hero-meta{left:24px;top:220px;gap:8px;font-size:8px}}
      @media(prefers-reduced-motion:reduce){*,*:before,*:after{animation:none!important;scroll-behavior:auto!important}}
    </style>
    <script>
      (()=>{const c=document.getElementById('field'),ctx=c.getContext('2d'),host=c.parentElement;let w=0,h=0,dpr=1,points=[],mx=.5,my=.5,raf=0;
      const resize=()=>{const r=host.getBoundingClientRect();dpr=Math.min(devicePixelRatio||1,1.5);w=r.width;h=r.height;c.width=w*dpr;c.height=h*dpr;c.style.width=w+'px';c.style.height=h+'px';ctx.setTransform(dpr,0,0,dpr,0,0);points=Array.from({length:48},(_,i)=>({x:w*(.48+Math.random()*.51),y:h*Math.random(),z:.35+Math.random()*.65,r:.7+Math.random()*1.25,p:Math.random()*6.28,s:.2+Math.random()*.45}));draw()};
      const draw=()=>{ctx.clearRect(0,0,w,h);const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;const title=host.querySelector('.hero-title');if(title&&!reduced){title.style.setProperty('--tilt-x',((mx-.5)*5)+'deg');title.style.setProperty('--tilt-y',((.5-my)*3)+'deg')}const pts=points.map(a=>({x:a.x+(mx-.5)*18*a.z,y:a.y+(my-.5)*12*a.z,a}));for(let i=0;i<pts.length;i++){for(let j=i+1;j<pts.length;j++){const A=pts[i],B=pts[j],dx=A.x-B.x,dy=A.y-B.y,dist=Math.hypot(dx,dy);if(dist<88){ctx.strokeStyle='rgba(99,187,226,'+((1-dist/88)*.18)+')';ctx.lineWidth=.6;ctx.beginPath();ctx.moveTo(A.x,A.y);ctx.lineTo(B.x,B.y);ctx.stroke()}}const {x,y,a}=pts[i],twinkle=reduced?1:.68+Math.sin(performance.now()*.001*a.s+a.p)*.25;ctx.fillStyle='rgba(135,224,245,'+(twinkle*a.z)+')';ctx.beginPath();ctx.arc(x,y,a.r,0,6.283);ctx.fill()}if(!reduced)raf=requestAnimationFrame(draw)};
      host.addEventListener('pointermove',e=>{const r=host.getBoundingClientRect();mx=(e.clientX-r.left)/r.width;my=(e.clientY-r.top)/r.height},{passive:true});host.addEventListener('pointerleave',()=>{mx=.5;my=.5},{passive:true});new ResizeObserver(resize).observe(host);resize()})();
    </script>
    """
    if not is_admin:
        hero_html = hero_html.replace(
            "<div class=\"hero-meta\"><span>OLIST COMMERCE DATA</span><i></i><span>LIVE INSIGHTS</span><i></i><span>23 / 24 MODULES ACTIVE</span></div>",
            "<div class=\"hero-meta\"><span>YOUR BUSINESS DATA</span><i></i><span>INSTANT INSIGHTS</span><i></i><span>PRIVATE SESSION ANALYSIS</span></div>",
        )
    if light_theme:
        hero_html = hero_html.replace('class="hero"', 'class="hero light"', 1)
    components.html(hero_html, height=282, scrolling=False)


def render_module_roadmap() -> None:
    """Render the roadmap footer as an accessible 6-by-4 button grid."""
    st.divider()
    title_col, count_col = st.columns([4, 1])
    title_col.markdown("### System Architecture & Build Roadmap")
    count_col.markdown("<div class='roadmap-progress'>23 complete&nbsp; · &nbsp;1 pending</div>", unsafe_allow_html=True)

    with st.container(key="module_roadmap"):
        for row_start in range(0, len(MODULE_DETAILS), 6):
            row = MODULE_DETAILS[row_start:row_start + 6]
            columns = st.columns(6, gap="small")
            for column, module in zip(columns, row):
                module_id, name, status, *_ = module
                status_text = {"complete": "✓ COMPLETE", "up_next": "◉ UP NEXT", "pending": "○ PENDING"}[status]
                label = f"{module_id:02d}  ·  {name}\n\n{status_text}\n\nView specs  ↗"
                with column:
                    with st.container(key=f"module_tile_{module_id:02d}"):
                        if st.button(
                            label,
                            key=f"module_{module_id:02d}",
                            type="secondary",
                            use_container_width=True,
                            help=f"Open Module {module_id:02d}: {name}",
                        ):
                            st.session_state["active_detail"] = ("module", module_id)


def _clear_active_detail() -> None:
    st.session_state.pop("active_detail", None)


def _format_kpi(key: str, value: float) -> str:
    format_kind = KPI_DETAILS[key]["format"]
    if format_kind == "money":
        return f"R$ {value:,.2f}"
    if format_kind == "percent":
        return f"{value:.2f}%"
    if format_kind == "score":
        return f"{value:.2f} / 5"
    if format_kind == "days":
        return f"{value:.2f} days"
    return f"{value:,.0f}"


@st.dialog(
    "Dashboard details",
    width="large",
    position="right",
    dismissible=True,
    on_dismiss=_clear_active_detail,
)
def show_detail_dialog(detail_type: str, detail_id: str | int) -> None:
    """Accessible Streamlit dialog for KPI definitions and module specs."""
    if detail_type == "kpi":
        detail = KPI_DETAILS[str(detail_id)]
        st.markdown(f"### {detail['title']}")
        st.caption("All-time headline · period comparison uses the latest 90 days in the dataset.")
        comparison = load_kpi_comparison()
        field = detail["field"]
        previous = getattr(comparison["previous"], field)
        current = getattr(comparison["current"], field)
        change = comparison["pct_change"][field]
        previous_col, current_col = st.columns(2)
        previous_col.metric("Previous 90 days", _format_kpi(str(detail_id), previous))
        current_col.metric(
            "Latest 90 days",
            _format_kpi(str(detail_id), current),
            delta=None if change is None else f"{change:+.1f}% vs previous",
        )
        if change is None:
            st.caption("Percentage change is unavailable because the previous period has no baseline value.")
        st.markdown("#### Formula & definition")
        st.write(detail["formula"])
        st.write(detail["definition"])
        st.markdown("#### Data slice")
        st.write(detail["slice"])
        st.caption("The comparison windows are based on the dataset’s latest available purchase date, not today’s date.")
    else:
        module = next(item for item in MODULE_DETAILS if item[0] == int(detail_id))
        module_id, name, status, scope, pipeline, checklist = module
        badge = {"complete": "✅ COMPLETE", "up_next": "✨ UP NEXT", "pending": "○ PENDING"}[status]
        st.markdown(f"### Module {module_id:02d} · {name}")
        st.markdown(f"<span class='detail-status {status}'>{badge}</span>", unsafe_allow_html=True)
        st.markdown("#### Scope & purpose")
        st.write(scope)
        st.markdown("#### Data pipeline & libraries")
        st.write(pipeline)
        st.markdown("#### Deliverables")
        for item in checklist:
            marker = "✅" if status == "complete" else "◯"
            st.markdown(f"{marker} {item}")

    if st.button("Close details", key="close_detail_dialog", type="secondary"):
        _clear_active_detail()
        st.rerun()


@st.cache_data(ttl=3600)
def load_kpis() -> KPISet:
    """All-time headline KPIs via Module 8's KPICalculator. Cached one hour."""
    return KPICalculator().calculate()


@st.cache_data(ttl=3600, show_spinner="Loading 90-day KPI comparison…")
def load_kpi_comparison() -> dict:
    """Lazy-load current-vs-previous 90-day comparison when a KPI is opened."""
    return KPICalculator().calculate_with_comparison(period_days=90)


@st.cache_data(ttl=3600)
def load_monthly_trend() -> pd.DataFrame:
    """Order volume by month, for the interactive trend chart."""
    return pd.read_sql(
        """
        SELECT DATE_TRUNC('month', order_purchase_timestamp) AS month, COUNT(*) AS orders
        FROM orders GROUP BY 1 ORDER BY 1
        """,
        db.engine,
    )


@st.cache_data(ttl=3600)
def load_latest_validation_summary() -> dict:
    """Most recent Module 5 validation run - surfaces data health right on the Home page."""
    with db.engine.connect() as conn:
        latest_run = conn.execute(
            text("SELECT run_id, MAX(checked_at) AS ts FROM validation_log GROUP BY run_id ORDER BY ts DESC LIMIT 1")
        ).fetchone()
        if latest_run is None:
            return {"available": False}

        counts = conn.execute(
            text("""
                SELECT status, COUNT(*) FROM validation_log
                WHERE run_id = :run_id GROUP BY status
            """),
            {"run_id": latest_run.run_id},
        ).fetchall()
    summary = {"available": True, "checked_at": latest_run.ts, "PASS": 0, "WARN": 0, "FAIL": 0}
    for status, count in counts:
        summary[status] = count
    return summary


def render_kpi_cards(kpis: KPISet) -> None:
    """Show polished, clickable KPI cards that open their definitions."""
    cards = [
        ("total_orders", "Total Orders", f"{kpis.total_orders:,}"),
        ("total_revenue", "Total Revenue (R$)", f"{kpis.total_revenue / 1_000_000:.2f}M"),
        ("unique_customers", "Unique Customers", f"{kpis.unique_customers:,}"),
        ("average_review_score", "Avg Review Score", f"{kpis.average_review_score:.2f} / 5"),
        ("average_order_value", "Avg Order Value", f"R$ {kpis.average_order_value:,.2f}"),
        ("fulfillment_rate_pct", "Fulfillment Rate", f"{kpis.fulfillment_rate_pct:.2f}%"),
        ("average_delivery_days", "Avg Delivery Time", f"{kpis.average_delivery_days:.2f} days"),
        ("repeat_customer_rate_pct", "Repeat Customer Rate", f"{kpis.repeat_customer_rate_pct:.2f}%"),
    ]
    with st.container(key="kpi_board"):
        for start in range(0, len(cards), 4):
            row = cards[start:start + 4]
            columns = st.columns(4, gap="small")
            for column, (key, title, value) in zip(columns, row):
                with column:
                    if st.button(
                        f"**{title}**  \n\n**{value}**",
                        key=f"kpi_{key}",
                        type="secondary",
                        width="stretch",
                        icon=":material/arrow_outward:",
                        help=(
                            f"Open the definition and recent trend for {title}"
                            + (f". Exact total: R$ {kpis.total_revenue:,.2f}." if key == "total_revenue" else ".")
                        ),
                    ):
                        st.session_state["active_detail"] = ("kpi", key)


def render() -> None:
    light_theme = st.session_state.get("light_theme", False)
    account = st.session_state.get("app_user", {})
    is_admin = account.get("role") == "admin"
    set_chart_theme("light" if light_theme else "dark")
    if not is_admin:
        render_hero(light_theme, is_admin=False)
        with st.container(border=True):
            st.markdown(
                "<div style='font-size:clamp(1.8rem,3.2vw,2.8rem);line-height:1.18;"
                "font-weight:800;letter-spacing:-.035em;color:#72d9e8;padding:.35rem 0 .8rem'>"
                "Upload your data in Data Lab and get all the insights in seconds</div>",
                unsafe_allow_html=True,
            )
            st.write("No database setup needed. Upload a CSV or Excel file to explore sales, customers, products, trends, and data quality.")
            st.page_link("dashboard/data_lab.py", label="Open Data Lab", icon=":material/upload_file:", width="content")
        st.subheader("Explore your insights")
        insight_links = st.columns(4)
        insight_links[0].page_link("dashboard/user_sales.py", label="Sales", icon=":material/bar_chart:")
        insight_links[1].page_link("dashboard/user_customers.py", label="Customers & products", icon=":material/groups:")
        insight_links[2].page_link("dashboard/user_geography.py", label="Geography", icon=":material/public:")
        insight_links[3].page_link("dashboard/user_insights.py", label="Business insights", icon=":material/query_stats:")
        return

    render_hero(light_theme, is_admin=True)
    st.markdown("### Business snapshot")
    st.caption("Brazilian E-Commerce (Olist) dataset · live from PostgreSQL")

    # Keep the architecture footer available even if PostgreSQL is down.
    if not db.test_connection():
        st.error(
            "⚠️ Cannot connect to the database. Check that PostgreSQL is "
            "running and your `.env` file has the correct credentials, "
            "then reload this page. (See the Settings page for details.)"
        )
    else:
        kpis = load_kpis()
        render_kpi_cards(kpis)

        st.subheader("Order volume & analytics")
        trend_df = load_monthly_trend()
        fig = ChartBuilder.line(trend_df, x="month", y="orders", title="Monthly Order Volume", y_label="Orders")
        st.plotly_chart(fig, width="stretch")

        st.subheader("Data health")
        validation = load_latest_validation_summary()
        if not validation["available"]:
            st.warning("No validation runs found yet. Run `services/data_validation.py` (Module 5).")
        else:
            vcol1, vcol2, vcol3 = st.columns(3)
            vcol1.metric("Checks Passed", validation["PASS"])
            vcol2.metric("Warnings", validation["WARN"])
            vcol3.metric("Failures", validation["FAIL"])
            st.caption(f"Last validated: {validation['checked_at']}")

    render_module_roadmap()
    active_detail = st.session_state.get("active_detail")
    if active_detail:
        show_detail_dialog(*active_detail)


render()

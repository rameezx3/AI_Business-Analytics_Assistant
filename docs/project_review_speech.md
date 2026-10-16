# AI Business Analytics Assistant — review and demo notes

For the full current-status review, module-by-module record, and 32 viva questions, see [project_review_qa.md](project_review_qa.md).

## Project goal

This project turns business data into understandable answers. Its current sample is the Brazilian Olist e-commerce dataset. It stores and checks the data, then presents sales, customer, and product performance through an interactive dashboard. The Data Lab also lets a user upload a CSV or Excel file and immediately inspect its quality and common business trends without writing code.

## Work completed

- PostgreSQL connection, relational schema, and CSV import for the nine Olist source tables.
- Re-runnable data cleaning and validation with recorded quality outcomes.
- Exploratory data analysis and reusable KPI/chart services.
- Interactive Home, Sales, Customers, and Products pages backed by database queries.
- Clickable Home KPI cards that open definitions and recent-period comparisons.
- Geographical Analytics for Brazilian buyer-state sales, delivery time, and estimated seller-to-customer distances.
- Seller Analytics for seller item sales, order volume, review results, state comparisons, and monthly trends.
- Data Lab for in-memory CSV/XLSX profiling, automatic sales/date/customer/product recognition, monthly trend and product ranking charts, quality profile, preview, and CSV export.
- Optional OIDC login with email-based user/admin page access. It must be configured with the organization’s identity provider before login is enabled.

The visible roadmap marks Modules 1–14 complete. Forecasting, segmentation, recommendations, AI Assistant, and other roadmap pages are not represented as completed functionality.

## Technologies

Python 3.11, Streamlit, PostgreSQL, SQLAlchemy, pg8000, Pandas, NumPy, Plotly, Matplotlib, Seaborn, OpenPyXL, and pytest. Streamlit’s optional built-in OpenID Connect support provides authentication without storing app passwords.

## Why a nontechnical user can use it

The dashboard presents named metrics and charts rather than requiring SQL or Python. The user can upload a familiar spreadsheet, and the Data Lab gives an immediate overview, flags missing or repeated rows, and visualizes trends when recognizable fields are available. The profile table and sample rows help explain what the file contains. Analysis is automatic, though descriptive: it summarizes the uploaded data and does not guarantee that a guessed column means exactly what its header suggests.

## Project introduction (spoken, about 2 minutes)

Good morning. My project is the AI Business Analytics Assistant. Its goal is to make business data easier to understand and use, even for someone who does not know programming, SQL, or machine learning.

For the current demonstration, I use the Brazilian Olist e-commerce dataset. The system loads the data into PostgreSQL, cleans common data-quality issues, and runs validation checks. It then displays important business measures in a Streamlit dashboard. A user can explore sales, customer behavior, and product performance using interactive charts and clearly labeled metrics. Selecting a Home-page metric opens its definition and a recent-period comparison, so the number has context instead of appearing as an unexplained figure.

I have also added a Data Lab for spreadsheet analysis. A user can upload a CSV or Excel file, and the app profiles its columns, reports missing and duplicate data, and identifies common sales, date, customer, and product fields. When those fields are available, it creates summaries and interactive charts automatically. The uploaded file is analyzed in the current session and does not get mixed into the project’s Olist database.

The project is built with Python, Streamlit, PostgreSQL, SQLAlchemy, Pandas, NumPy, and Plotly, with Matplotlib and Seaborn used for exploratory analysis. These technologies work together to store, check, analyze, and present the data through a browser-based interface.

The completed work currently covers the first fourteen modules, including product, geographical, and seller analytics. Forecasting, segmentation, recommendations, and the AI assistant are future work. The project therefore demonstrates a working foundation for business analytics, while leaving those planned capabilities clearly identified as future development.

Thank you. I would be happy to demonstrate the dashboard and show how a spreadsheet becomes a useful business summary.

## Demo order

1. Introduce the Home page and explain one KPI using its details panel.
2. Show the Sales, Customers, Products, Geography, and Sellers pages and their interactive charts.
3. Upload a small CSV/XLSX on Data Lab; point out missing data, detected fields, trend, and product chart.
4. Close with completed Modules 1–14 and explain which roadmap items remain planned.

# AI Business Analytics Assistant — review and demo notes

For the full 24-module status and viva Q&A, see [project_review_qa.md](project_review_qa.md). Vercel setup steps are in [deployment_vercel.md](deployment_vercel.md).

## Project goal

The AI Business Analytics Assistant helps business owners and nontechnical users turn sales data into clear metrics and useful findings. Its administrator dashboard analyzes the Brazilian Olist e-commerce dataset stored in PostgreSQL. Regular users can upload a spreadsheet to the Data Lab and explore their own data without programming.

## What the current application does

- Imports, cleans, and validates the nine related Olist tables.
- Presents interactive KPI, sales, customer, product, geography, and seller analytics.
- Forecasts monthly sales using a baseline/trend comparison and chronological evaluation.
- Groups customers using explainable RFM scores and produces rule-based recommendations.
- Supports safe natural-language data questions and optional Claude/OpenAI chat APIs.
- Generates evidence-linked business insights and downloadable PDF reports.
- Provides an admin health dashboard and separate Admin/User accounts.
- Analyzes uploaded CSV/Excel files in the current session; user uploads are not written to the Olist database.
- Includes Vercel Python/ASGI deployment configuration. A live deployment still needs the owner's Vercel account and hosted PostgreSQL settings.

## Technologies

Python, Streamlit, PostgreSQL, SQLAlchemy, pg8000, Pandas, NumPy, Plotly, Matplotlib, Seaborn, OpenPyXL, ReportLab, and pytest. Optional Claude/OpenAI features use provider APIs and separate API credentials.

## Why a nontechnical user can use it

The dashboard presents named measures, definitions, and interactive charts instead of requiring SQL or Python. A user can upload a familiar CSV or Excel workbook, see its quality profile, and explore generated sales, customer, product, and geographic summaries where the source columns support them. The analysis is descriptive and heuristic, so users should confirm that detected fields match their business meaning.

## Project introduction (spoken, about 2 minutes)

Good morning. My project is the AI Business Analytics Assistant. It helps people understand business data without needing to know programming or database queries.

The administrator demonstration uses the Brazilian Olist e-commerce dataset. The project imports related order, customer, product, payment, review, seller, and location records into PostgreSQL. It checks and cleans the data, then presents the results in a browser-based Streamlit dashboard. Users can explore sales, customer, product, geographic, and seller performance through interactive charts and clearly defined metrics.

The application also has a Data Lab for CSV and Excel files. A regular user uploads a spreadsheet and the system profiles its columns, reports missing and duplicate values, and detects common business fields such as dates, sales, customers, and products. It then creates relevant summaries and charts. These uploads are analyzed in the current session and remain separate from the administrator's Olist database.

The later modules add monthly sales forecasting, explainable RFM customer segments, evidence-based recommendations, natural-language data questions, optional Claude or OpenAI chat, business insights, PDF reports, an admin health dashboard, and separate user and administrator accounts. Model APIs are optional and need their own provider keys.

The project is built with Python, Streamlit, PostgreSQL, SQLAlchemy, Pandas, NumPy, and Plotly, with additional tools for reports and exploratory charts. All 24 roadmap modules now have implementations. Module 24 includes Vercel deployment files; publishing the live service still requires a managed PostgreSQL database and configuration in the project owner's Vercel account.

Thank you. I can now demonstrate how the application turns structured records or an uploaded spreadsheet into understandable business information.

## Demo order

1. Start at Home and explain one KPI using its definition/details interaction.
2. Show the sales, customer, product, geography, and seller pages.
3. Demonstrate Forecast, Segments, Recommendations, Ask Data/AI Assistant, Business Insights, and a PDF report.
4. Sign in as a regular user, upload a small CSV or Excel file in Data Lab, and explore its resulting insights.
5. Show the admin health dashboard and explain that Olist database pages are administrator-only.
6. Explain that Vercel deployment is configured; production activation needs the hosted database and account environment variables described in the deployment guide.

# Project Review: AI Business Analytics Assistant

Updated on 16 October 2026 from the current project files. Use the short answers for a review form and the longer answers for viva questions.

## 1. Project title

**AI Business Analytics Assistant: an interactive analytics platform for e-commerce data**

## 2. One-line introduction

My project converts raw e-commerce data into understandable business metrics, charts, and data-quality findings, and lets a user explore a spreadsheet without writing code.

## 3. Project overview

Businesses collect sales, customer, product, payment, and delivery records, but raw spreadsheets and database tables can be difficult to interpret. This project provides a browser-based interface that organizes those records, checks data quality, and presents useful business summaries. Its current demonstration uses the Brazilian E-Commerce Public Dataset by Olist. It also includes a Data Lab where a user uploads a CSV or Excel workbook for an automatic, exploratory analysis.

The current build includes database-backed analytics, spreadsheet analysis, forecasting, explainable customer segments, evidence-based recommendations and insights, safe natural-language data questions, optional Claude/OpenAI chat, PDF reporting, an admin health dashboard, and local Admin/User accounts. Claude and OpenAI calls require separately configured API keys; the built-in analytics path works without model keys. Vercel configuration is included, while the live production release still needs an account-connected deployment and a hosted PostgreSQL database.

## 4. Problem statement

Small businesses and nontechnical users may have useful sales data but lack the skills or time to clean it, query a database, and build charts. This project aims to make those first steps accessible through automatic quality checks, named business KPIs, and interactive visualizations. The current dashboard demonstrates these capabilities on Olist data; Data Lab extends the analysis to uploaded CSV and Excel files.

## 5. Objectives

1. Store related e-commerce records in a structured PostgreSQL database.
2. Import source CSV files reliably and handle data types and missing values.
3. Clean known quality issues and keep an audit trail.
4. Validate row counts, relationships, and business-value rules.
5. Calculate consistent sales, customer, product, and fulfillment measures.
6. Present those measures in a clear, interactive dashboard.
7. Let users profile common CSV/Excel datasets without programming.
8. Establish a secure optional login path for different user and admin roles.
9. Extend the foundation with forecasting and AI assistance in future modules.

## 6. Current implementation status

The project roadmap contains 24 modules. **All 24 modules now have an implementation in the project (24/24 = 100% of the roadmap implementation).** Module 24 includes Vercel configuration and an ASGI entry point; publishing a live production URL is an account and infrastructure setup step that is still pending. Data Lab is an additional feature outside the numbered roadmap.

| Module | Current status | What it provides |
|---|---|---|
| 1. Database Connection | Complete | Environment-based PostgreSQL connection and shared SQLAlchemy engine/session. |
| 2. Database Schema | Complete | ORM models, relationships, constraints, and indexes for nine source tables. |
| 3. CSV Import | Complete | Batched import with type coercion, load ordering, and row-count checks. |
| 4. Data Cleaning | Complete | Re-runnable fixes and an audit log. |
| 5. Data Validation | Complete | Thirty persisted checks for data health and integrity. |
| 6. Exploratory Data Analysis | Complete | Static EDA charts and a generated Markdown report. |
| 7. Dashboard Shell | Complete | Streamlit navigation, theme, Home, and Settings. |
| 8. KPI Engine | Complete | Shared KPI definitions and period comparisons. |
| 9. Chart Library | Complete | Reusable, themed Plotly chart builders. |
| 10. Customer Analytics | Complete | Customer counts, repeat behavior, spend, and geography summaries. |
| 11. Sales Analytics | Complete | Sales trends, categories, states, payment mix, and demand timing. |
| 12. Product Analytics | Complete | Category and product performance, review scores, and product-content signals. |
| 13. Geographical Analytics | Complete | State sales/delivery comparisons and ZIP-centroid-based seller/customer distance estimates. |
| 14. Seller Analytics | Complete | Seller revenue and volume, order-level review results, state comparison, and monthly trend. |
| 15. Forecasting | Implemented | Compares a last-month baseline with a linear trend using chronological walk-forward evaluation; shows empirical error ranges and MAE/MAPE. |
| 16. Customer Segmentation | Implemented | Explainable RFM quintile scores, customer segments, profiles, and exports. |
| 17. Recommendation Engine | Implemented | Transparent business rules create data-grounded delivery, retention, review, and product recommendations. |
| 18. Natural Language SQL | Implemented | Supported questions are translated to approved query plans and parameterized, read-only SQL; optional LLM planning is validated. |
| 19. LLM Chat | Implemented | Session-based business chat supports built-in answers and optional Claude/OpenAI API providers. |
| 20. Business Insight Generator | Implemented | Evidence-backed findings include supporting measures, practical actions, and limitations. |
| 21. PDF Report Generator | Implemented | Builds downloadable PDF reports from verified current analytics and provides saved EDA artifacts. |
| 22. Admin Dashboard | Implemented | Read-only health, table coverage, validation history, and cleaning audit overview. |
| 23. Authentication | Implemented | Admin/User sign-in and user registration; salted PBKDF2 password hashes, lockout after repeated failures, and role-based pages. |
| 24. Deployment | Prepared | Vercel Python/ASGI configuration and deployment guide are included. Live production release requires Vercel account setup and external PostgreSQL credentials. |

The **Data Lab** supports CSV, XLSX, and XLSM uploads up to 50 MB locally. It profiles missing and duplicate values, previews rows, and attempts to infer date, sales, customer, and product fields from column names. It generates summaries and charts when it can identify suitable fields. It analyzes uploads in memory and does not add them to the Olist PostgreSQL tables. The Vercel configuration limits uploads to 4 MB to stay under the function request-body cap.

The application uses its local account system, not OIDC. Admins are created privately through `scripts/create_admin.py`; regular users can register in the interface. Passwords are stored as salted PBKDF2 hashes in PostgreSQL. Admins have Olist analytics, system health, and settings access; regular users analyze their own session upload and use the corresponding insight pages. Production use requires HTTPS, a hosted PostgreSQL database, strong admin credentials, and secrets supplied through Vercel environment settings.

## 7. Technologies and why they are used

| Technology | Role in this project |
|---|---|
| Python 3.11 | Application logic and analytics. |
| Streamlit | Browser-based dashboard and file-upload user interface. |
| PostgreSQL | Relational storage for the Olist source tables. |
| SQLAlchemy | Database engine, ORM models, and reusable query access. |
| pg8000 | Pure-Python PostgreSQL driver that avoids a native compiler setup. |
| Pandas and NumPy | CSV/Excel handling, data profiling, and analysis. |
| Plotly | Interactive dashboard charts. |
| Matplotlib and Seaborn | Static charts used in the EDA report. |
| OpenPyXL | Reading Excel `.xlsx` and `.xlsm` workbooks. |
| pytest | Automated regression and page checks. |
| Python hashlib / PostgreSQL | Local account authentication with salted PBKDF2 password hashes and database-backed roles. |

Forecasting and segmentation are implemented with transparent statistical and rule-based methods; they do not require scikit-learn. Claude and OpenAI chat/planning integrations are optional API features and require provider keys, which may incur separate API charges.

## 8. Data and current results

The project uses the **Brazilian E-Commerce Public Dataset by Olist**, which has nine related CSV tables and about 1.55 million source rows in total, including one million geolocation records. The database has the cleaned data; for example, geolocation is reduced from 1,000,163 source records to 738,305 cleaned rows by deduplication. These counts refer to different stages and should not be mixed up.

Current sample-dataset headline results include:

- 99,441 orders.
- 96,096 unique customers.
- R$13,591,643.70 gross product sales (item prices; freight excluded).
- Average review score: 4.09 out of 5.
- Fulfillment rate: 97.02%.
- Average delivery time: 12.56 days.
- Repeat-customer rate: 3.12% under the project’s repeat-order definition.
- Geography analysis: 112,095 items had both ZIP-prefix centroids; estimated mean seller-to-customer great-circle distance is about 597 km.

The data-validation module records pass, warning, and failure results for its database checks. The repository includes regression tests for data access, analytics, authentication, charts, and page behavior. Earlier documented runs reported 78 tests passing before later modules were added; that count is not a current full-suite result and should not be quoted as one. The Vercel configuration is prepared, but a production deployment cannot be claimed until it has been deployed with a reachable hosted database and verified in the Vercel account.

The Olist data ends in 2018, and the dataset has sparse months at the beginning and end. Treat those values as a historical demonstration, not as current sales. Sales means item price and excludes freight unless a measure explicitly says otherwise. Geography distances are straight-line estimates from ZIP-prefix centroids, not actual delivery routes.

## 9. Two-minute introduction speech

Good morning. My project is called the AI Business Analytics Assistant. It is designed to make business data easier to understand, especially for users who do not know SQL, Python, or data science.

For the current working version, I use the Brazilian E-Commerce Public Dataset by Olist. It contains information about orders, products, customers, payments, reviews, sellers, and locations. The project first imports those related records into PostgreSQL. It then cleans known data issues, records the changes, and runs validation checks so that problems such as missing relationships or invalid values can be identified.

The dashboard turns the validated data into useful business views. The Home page shows key measures such as revenue, orders, unique customers, review score, fulfillment rate, delivery time, and repeat-customer rate. The Sales, Customers, Products, and Geography pages let the user explore trends and comparisons through interactive charts. A user can also select a Home metric to read its definition and compare recent periods.

I added a Data Lab to make spreadsheet analysis more accessible. A user can upload a CSV or Excel workbook. The system profiles the columns, reports missing and duplicate data, and tries to recognize common date, sales, customer, and product fields. When it finds suitable fields, it builds summaries and charts automatically. The uploaded file is analyzed in the current session and is not inserted into the Olist database.

The project uses Python, PostgreSQL, SQLAlchemy, Pandas, NumPy, Streamlit, Plotly, Matplotlib, and Seaborn. These tools support the data pipeline, calculations, and visual interface. The AI and machine-learning features are the next development stage; the current version is the tested analytics foundation for those features, rather than a finished AI chatbot or forecasting system.

The project implements all 24 roadmap modules, from importing and validating business data through analytics, AI-assisted questions, reporting, authentication, and Vercel deployment preparation. The live release still depends on Vercel account configuration and a hosted PostgreSQL database.

Thank you. I will now demonstrate the dashboard and show how the Olist data and an uploaded spreadsheet can be explored.

## 10. Review / viva questions and suggested answers

### Project basics

**1. What is the main purpose of your project?**
It helps users understand business data by checking its quality, calculating business measures, and displaying the results in interactive charts. The current version demonstrates that workflow on e-commerce data and offers spreadsheet profiling through Data Lab.

**2. What problem does it solve?**
Raw business data can be difficult to clean and interpret without programming or database skills. The project gives users a guided dashboard and automatic summaries so they can explore common sales, customer, product, and delivery questions more easily.

**3. What is Business Analytics?**
Business Analytics uses data, statistical methods, and visualizations to understand business performance and support informed decisions. This project demonstrates that process through data checks, KPIs, and interactive dashboards.

**4. Why is “AI” in the project name if the current version does not have an AI chatbot?**
The project’s intended final scope includes AI-assisted questions and business insights. The current completed version focuses on the dependable data and analytics foundation. The AI modules are on the roadmap and are not claimed as implemented yet.

**5. Who is the intended user?**
A business owner, analyst, student, or manager who needs to understand sales and customer data but may not know SQL or Python. The interface presents named metrics, charts, previews, and data-quality information.

**6. How is it useful to someone with no technical knowledge?**
They can use familiar pages and upload a spreadsheet. The app does calculations and charting in the background, while the user reads the results in plain labels. Users do not need to write queries or code for the supported analyses.

### Dataset and data pipeline

**7. Which dataset did you use, and why?**
The Brazilian E-Commerce Public Dataset by Olist. It is a realistic public dataset with related tables for orders, line items, customers, products, payments, reviews, sellers, and locations, so it supports several types of business analysis.

**8. What happens to the data from beginning to end?**
The CSV files are imported into PostgreSQL tables. Cleaning rules address known quality issues and record their actions. Validation checks row counts, relationships, and value rules. Analytics services query the stored data, calculate metrics, and provide results to Streamlit pages and charts.

**9. What is EDA?**
Exploratory Data Analysis is an early investigation of a dataset. It uses summaries, distributions, and charts to understand the data, notice trends, and find potential quality issues before drawing conclusions or building predictive models.

**10. What is data validation in this project?**
It is a set of checks that tests whether the expected tables and row counts exist, whether keys and relationships are consistent, and whether values such as review scores and prices are in reasonable ranges. The results are saved so runs can be reviewed later.

**11. Why use PostgreSQL instead of keeping everything in one spreadsheet?**
The source data is relational: an order can have several items or payments, and customers and products appear across many records. PostgreSQL supports those relationships, constraints, indexes, and queries more reliably than a collection of manually joined spreadsheets.

**12. Why use SQLAlchemy and pg8000?**
SQLAlchemy provides a shared database engine, schema models, and query access. pg8000 is a pure-Python PostgreSQL driver, which avoids requiring a C++ compiler to install the database dependency on Windows.

**13. Why does the geolocation count change after cleaning?**
The source file contains repeated ZIP-prefix locations. The cleaning step removes duplicate geolocation entries; therefore, the raw CSV has 1,000,163 rows while the cleaned database table currently has 738,305. Both counts are correct for their respective stages.

### Metrics and analysis

**14. What does total revenue mean here?**
The dashboard’s gross product sales are the sum of order-item prices. Freight is excluded because shipping is a separate charge. The measure includes orders with items across statuses unless a page or chart explicitly filters the order status.

**15. Why is average order value not revenue divided by all orders?**
Some orders contain no line items and therefore contribute no product sales. The project defines average order value using distinct orders that contain at least one item, so those zero-item orders do not pull the average down.

**16. How is a unique customer counted?**
The KPI uses `customer_unique_id`, which represents the same person across order-level customer records. Counting `customer_id` would treat repeat buyers as different people in some cases.

**17. What do the current headline values tell us?**
For this historical Olist sample, the app reports 99,441 orders, 96,096 unique customers, R$13.59 million in item sales, an average review of 4.09/5, a 97.02% fulfillment rate, 12.56 average delivery days, and a 3.12% repeat-customer rate. These describe this dataset, not a current live business.

**18. What is the difference between an order and an order item?**
An order is a customer purchase record. It can contain multiple order items, with each item representing a product line. Revenue is summed over items, while order counts must count distinct order IDs to avoid counting a multi-item order several times.

**19. What does the geographical distance measure mean?**
It estimates straight-line distance between average customer and seller ZIP-prefix coordinates using the great-circle formula. It is based on 112,095 items with both locations and is not a road, courier, or actual package route distance.

**20. What do the three validation warnings mean?**
They are known anomalies in the public dataset: two card/boleto payments have zero installments, eight active-status orders have no item rows, and one order has no payment record. The checks surface these for interpretation; they are warnings, not failed checks.

### User interface and functionality

**21. How does the user interact with the dashboard?**
The user navigates between Home, Sales, Customers, Products, Geography, Sellers, and Data Lab. They can inspect KPIs, use chart hover details, compare periods where supported, and open a KPI card’s definition from Home.

**22. What does Data Lab do with an uploaded spreadsheet?**
It reads CSV, XLSX, or XLSM files up to 50 MB, profiles column types and missing/duplicate values, previews the data, and looks for common date, sales, customer, and product fields. It then creates relevant summaries and charts where the data supports them.

**23. Does Data Lab automatically understand every possible spreadsheet?**
No. It uses column names and basic type checks to infer common fields. Clear headers improve results. The user should review the detected columns and results, because a column name can be ambiguous and automatic profiling is descriptive rather than guaranteed business interpretation.

**24. Is uploaded spreadsheet data saved to PostgreSQL?**
No. Data Lab analyzes the uploaded file in memory for the current Streamlit session. It does not merge it into the Olist database. On Vercel, the current request-size limit means uploads are restricted to 4 MB; locally they can be up to 50 MB.

**25. What do user/admin roles mean in this build?**
The app stores salted PBKDF2 password hashes in PostgreSQL. Admin accounts are provisioned from a private terminal command; users can register through the sign-in screen. Admin and user roles receive different pages and data access.

**26. How are passwords and roles handled?**
Passwords are converted to salted PBKDF2 hashes before storage in PostgreSQL; plain-text passwords are not stored. Admin accounts are created with the private setup script, while public registration only creates regular users. Repeated failed login attempts trigger a temporary lockout.

### Evaluation, limitations, and future work

**27. How did you test it?**
The project has pytest checks for service calculations, data quality, chart output, authentication, and Streamlit page rendering. Earlier recorded runs passed 78 tests before later modules were added, so that historical number is not the current full-suite result. Each analytics result should be interpreted with its stated definition and dataset limits.

**28. What are the current limitations?**
The Olist dataset is historical and ends in 2018. Data Lab’s field detection is heuristic, and geography distance is approximate. Optional LLM features need provider API keys. Vercel production needs external PostgreSQL, account environment variables, and Fluid Compute for Streamlit’s WebSocket connection. Vercel function request payload limits may constrain large spreadsheet uploads, so deployed upload size must be checked against platform limits. Function storage is temporary; persistent app data belongs in PostgreSQL or object storage.

**29. Does the current project predict future sales?**
Yes. Module 15 compares a last-month baseline with a linear trend, evaluates candidates through chronological walk-forward validation, and reports forecast errors. Its empirical uncertainty range is not a formal statistical confidence interval, and historical Olist forecasts should not be treated as current business predictions.

**30. Does it currently answer questions using ChatGPT or Claude?**
It can call Claude or OpenAI APIs for supported natural-language planning and chat when the corresponding provider key and model are configured. There is also a built-in mode that does not need a model key. Claude or ChatGPT subscriptions do not automatically provide API credits, and external API usage may be billed separately.

**31. What is the next development step?**
The numbered roadmap is implemented through Module 24. The next step is the account-specific production release: import the repository into Vercel, enable the required runtime support, configure a hosted PostgreSQL database and secrets, provision the admin account, then verify sign-in, database pages, uploads, and reports on the deployed URL.

**32. How much of the project is complete?**
All 24 roadmap modules have an implementation, so module implementation is 24/24. This does not mean a live production service is already running: the final release depends on configuring Vercel and a hosted PostgreSQL database in the owner’s accounts. Data Lab is an additional feature outside the numbered count.

**33. What did Module 24 add for Vercel?**
It adds a Streamlit ASGI entry point, Vercel routing and function configuration, exclusions for development files and the large admin-only source CSVs, and `/tmp` paths for generated logs/reports because Vercel function files are read-only. Live deployment still needs the account owner to connect Vercel, supply production database credentials, and run the release checks.

**34. Why can’t the project use the local PostgreSQL database after deployment?**
`localhost` on Vercel refers to the function container, not the developer’s computer. The deployed app needs an internet-reachable managed PostgreSQL database; the connection details must be set as Vercel environment variables and must never be committed to Git.

**35. What does the Vercel deployment still need?**
Import the GitHub repository into Vercel, enable Fluid Compute/WebSocket support for the Streamlit ASGI app, configure `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD` as environment variables, and load the schema and Olist data into the hosted database. Optional provider keys can be added only if Claude/OpenAI features are needed.

## 11. Suggested live demonstration

1. Open the Home page and introduce the Olist dataset and the headline figures.
2. Click a KPI card and explain its formula and time comparison.
3. Show Sales, Customers, Products, Geography, and Sellers to demonstrate the interactive analytics pages.
4. Open Geography and explain that the distance is a ZIP-centroid estimate, not delivery-route tracking.
5. Open Data Lab, upload a small sample spreadsheet, and show the data-quality profile, detected columns, and generated chart.
6. Show the forecasting, customer segments, recommendations, Ask Data/AI Assistant, generated insights, PDF report, and admin health pages.
7. Explain that Vercel configuration is ready and production publishing requires a hosted database and account environment settings.

## 12. Short closing statement

This project provides an end-to-end business analytics workflow: structured data, validation, interactive dashboards, spreadsheet analysis, forecasting, explainable customer groups, evidence-backed recommendations, optional AI assistance, reports, and role-based access. The deployment configuration is prepared for Vercel; the remaining release step is connecting the owner’s Vercel account and hosted PostgreSQL service, then checking the production URL.

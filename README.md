# AI Business Analytics Assistant

An AI-powered Business Analytics platform on the Brazilian E-Commerce (Olist)
dataset: PostgreSQL storage, automatic cleaning and validation, KPI dashboards,
plus product, geographical, and seller analytics, Data Lab for CSV/Excel analysis,
and a historical monthly sales forecast with walk-forward evaluation, plus
interpretable RFM customer segmentation, evidence-backed business
recommendations, natural-language data questions with safe SQL, conversational AI chat, and evidence-linked business insights.

**Built so far:** Modules 1-24 (database, import, cleaning, validation, EDA,
dashboard, KPIs, chart library, customer analytics, sales analytics, product
analytics, geography, seller analytics, forecasting, customer segmentation,
rule-based recommendations, natural-language SQL, conversational AI chat,
business insights, PDF reports, role-based accounts, an admin health dashboard,
and Vercel deployment configuration), plus the spreadsheet Data Lab. Live
production deployment still requires a Vercel account and hosted PostgreSQL
connection; see [Vercel deployment guide](docs/deployment_vercel.md).

For the current project-review overview, module status, presentation speech, and
viva questions, see [docs/project_review_qa.md](docs/project_review_qa.md).

---

## Setting up on a NEW computer (Windows)

Everything the project needs is inside this folder, **including the dataset**
(`data/`). You only need to install two programs and then run the commands below.

### 1. Install the two programs (one time)

| Program | Notes |
|---|---|
| **Python 3.11 or newer** (python.org) | Tick **"Add python.exe to PATH"** in the installer. Check with `python --version`. |
| **PostgreSQL 16** (postgresql.org/download/windows) | Remember the password you set for the `postgres` user. Keep port **5432**. |

### 2. Create a virtual environment and install packages

Open **Command Prompt** inside this project folder:

```cmd
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

You should see `(venv)` at the start of the prompt. Do the `activate` step again
every time you open a new Command Prompt.

### 3. Create the database

Either use pgAdmin (right-click Databases > Create > Database, name it
`bi_assistant_db`), or from Command Prompt:

```cmd
"C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -c "CREATE DATABASE bi_assistant_db;"
```

(Change `16` if you installed a different version.)

### 4. Create your `.env` file

```cmd
copy .env.example .env
notepad .env
```

Set `DB_PASSWORD` to **your** PostgreSQL password. `DB_HOST` must be just
`localhost` (never `user@localhost`); the username goes in `DB_USER`.

### 5. Check the connection

```cmd
python tests\test_connection.py
```

You should see `SUCCESS: Connected to PostgreSQL.`

### 6. Build the data (run in this order)

```cmd
python database\init_db.py
python database\import_csv.py
python services\data_cleaning.py
python services\data_validation.py
python services\eda.py
```

The import takes about a minute. Expected: 1,551,724 rows loaded; cleaning fixes
610 products and removes about 262k duplicate geolocation rows; validation reports
27 passed, 3 warnings, 0 failed.

### 7. Start the dashboard

In VS Code, run **Terminal → Run Task → Run Streamlit (project Python 3.11)**.
The workspace also includes a matching Run and Debug configuration. The first
launch can take a few seconds while PostgreSQL-backed dashboard queries finish.

From Command Prompt, activate the environment first and run:

```cmd
venv\Scripts\activate
streamlit run app.py
```

If Streamlit asks for an email, just press Enter. Your browser opens at
http://localhost:8501.

### 8. (Optional) Run the tests

```cmd
python -m pytest tests -q
```

The suite reloads the database as part of testing (about 2-3 minutes), so run
the data-building steps in section 6 again afterwards if you want the
cleaned data back.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `password authentication failed` | Wrong `DB_PASSWORD` in `.env`. |
| `connection refused` | PostgreSQL service is not running (Windows: Services > postgresql > Start). |
| `database "bi_assistant_db" does not exist` | Do step 3. |
| `DB_HOST looks malformed` | `.env` has `DB_HOST=user@localhost`; use `DB_HOST=localhost` and put the user in `DB_USER`. |
| `'python' is not recognized` | Reinstall Python and tick "Add to PATH". |
| `ModuleNotFoundError` (for example, `No module named 'plotly'`) | VS Code is likely using a different Python installation. In VS Code select **Python: Select Interpreter** → `.\venv\Scripts\python.exe`, then run **Terminal → Run Task → Run Streamlit (project Python 3.11)**. For Command Prompt, run `venv\Scripts\activate` and `python -m streamlit run app.py`, then re-run `python -m pip install -r requirements.txt` if a package is still missing. |

## Project layout

```
app.py              Streamlit entry point
config.py           Settings loaded from .env
database/           Connection, ORM models, schema, CSV import
services/           Business logic: cleaning, validation, EDA, KPIs, charts, customer + sales analytics
dashboard/          Streamlit pages (presentation only)
tests/              Automated tests
data/               The 9 Olist CSV files
sql/                Generated schema reference
```

## Natural-language data questions

The **Ask Data** page works in built-in mode without a model key. It translates supported questions into approved query plans and parameterized, read-only SQL. Claude and OpenAI API modes are optional and need provider API credentials; chat subscriptions do not supply those credentials automatically. API calls can be billed separately.

To enable one provider, add its key to the local `.env` file (do not commit or share that file), then restart Streamlit:

```dotenv
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your-key
ANTHROPIC_MODEL=claude-sonnet-4-6
```

Or use `LLM_PROVIDER=openai`, `OPENAI_API_KEY`, and `OPENAI_MODEL=gpt-4.1-mini`. Model names can be changed to any model available to your provider account. The app sends the question to the chosen provider to produce a validated query plan; SQL is still compiled locally from fixed templates.


## Uploading your own data

Open **Data Lab** and upload a `.csv`, `.xlsx`, or `.xlsm` file (up to 50 MB). The app profiles missing and duplicate values and tries to identify date, sales, customer, and product columns from their names. Clear headers such as `order_date`, `sales`, `customer_id`, and `product` improve automatic summaries. Uploads are analyzed in memory for the current session and are not imported into PostgreSQL.

## Admin and user accounts

The app requires sign-in. Choose **Admin** to use an administrator account, or **User** to sign in/create a regular account. Admins have access to the Brazilian Olist analytics, system-health overview, and Settings. Regular users get a focused Home page, Upload Data, Sales, Customers & Products, Geography, Business Insights, and Demo. User insight pages analyze only the current user's uploaded CSV/Excel file held in session memory; Olist data and database-backed analytics remain admin-only. Public sign-up can only create user accounts. Upload Data includes a downloadable 600-row sample file at `data/demo_ecommerce_sample.csv`; it is synthetic e-commerce data with sales, orders, customers, categories, dates, statuses, and payment methods. Upload analysis runs in memory and does not write the file to PostgreSQL. The sample is a subset of the MIT-licensed [Hugging Face E-commerce Customer Order Behavior Dataset](https://huggingface.co/datasets/millat/e-commerce-orders). Passwords must contain at least 12 characters and are stored as salted PBKDF2 hashes. Five consecutive incorrect attempts temporarily lock an account.

Create the first admin from the project root using the same Python environment as Streamlit. The command asks for the email and password privately in the terminal; the password is never written into the project or printed:

```powershell
.\venv\Scripts\python.exe scripts\create_admin.py
```

Start the app with `.\venv\Scripts\python.exe -m streamlit run app.py`, select **Admin**, and sign in with that account. Regular users can use **Create account** on the login screen. The `app_users` table is created automatically in the configured PostgreSQL database. Keep `.env` private because it contains the database connection credentials.


## AI assistant chat

Open **AI Assistant** to ask supported business questions in a session-based chat. Data answers use the same approved, parameterized, read-only query templates as **Ask Data** and include a chart/table for grouped results. Simple year or Brazilian-state follow-ups reuse the previous successful question. The built-in parser works without an API key; optional Claude/OpenAI provider keys and models use the same .env settings described under Natural-language data questions. Chat turns are kept only for the current browser session and are not saved permanently.


## Business insights

Open **Business Insights** for a refreshed, evidence-linked summary of reliable sales momentum, category mix, customer RFM behavior, weaker review categories, and slower high-volume delivery markets. Findings are deterministic, include actions and limitations, and can be downloaded as CSV. If configured, Claude or OpenAI can optionally write a short briefing after you click its button; opening the page does not call the model. API use may be billed separately. The page works without a model API key and does not present historical associations as causal or guaranteed returns.


## PDF reports

Open **Reports** and choose an executive overview, sales and product, or customers and fulfillment template. Generate the PDF and download it from the page. Reports contain current KPI summaries, historical sales and category charts where applicable, evidence-linked findings, suggested actions, definitions, data cutoffs, and limitations. The page also displays the saved Module 6 EDA report and its nine chart files, with a Markdown download. ReportLab is installed from `requirements.txt` with the rest of the project dependencies.

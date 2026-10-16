# Module 24: Vercel deployment

## What is prepared

- `api/index.py` exposes the Streamlit application as an ASGI app and provides `/healthz`.
- `vercel.json` routes app requests to the Python function, excludes development files and the large Olist source CSVs from the function bundle, and sets the function duration.
- `config.py` uses `/tmp` for generated files on Vercel and a small PostgreSQL connection pool suitable for serverless instances.
- `api/index.py` sets the Vercel upload cap to 4 MB to stay below the platform's 4.5 MB function request-body ceiling; local Streamlit runs keep the normal upload limit.
- `.vercelignore` keeps local secrets, virtual environments, test output, and the admin-only Olist CSVs out of deployment uploads. The small synthetic demo CSV and committed EDA artifacts remain available.

## Required account setup

The deployment is configured in the repository, but it is not live until these external services are connected:

1. In Vercel, choose **Add New → Project**, import `rameezx3/AI_Business-Analytics_Assistant`, and deploy the `main` branch from the repository root.
2. Enable Fluid Compute/WebSocket support for the deployment. Streamlit uses a persistent WebSocket session; the Vercel Python runtime supports ASGI, and WebSocket support on Functions requires Fluid Compute.
3. Provision an internet-reachable managed PostgreSQL database. `localhost` in a Vercel function is the function container, not the developer's computer.
4. Add these variables in **Vercel → Project → Settings → Environment Variables** for Production (and Preview if wanted):

   | Variable | Value |
   |---|---|
   | `DB_HOST` | Hosted database hostname |
   | `DB_PORT` | Hosted database port, usually `5432` |
   | `DB_NAME` | Database name |
   | `DB_USER` | Database username |
   | `DB_PASSWORD` | Database password; enter only in Vercel settings |
   | `DB_POOL_SIZE` | `1` |
   | `DB_MAX_OVERFLOW` | `0` |
   | `DB_ECHO` | `False` |
   | `APP_ENV` | `production` |
   | `APP_DEBUG` | `False` |
   | `LOG_LEVEL` | `INFO` |

   Optional AI variables are `LLM_PROVIDER`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `OPENAI_API_KEY`, and `OPENAI_MODEL`. They are only needed for the external Claude/OpenAI modes. The built-in analytics mode does not require a provider key.

5. Initialize and load the hosted database from a trusted local machine. Set the `DB_*` variables in that shell to the managed database credentials, then run:

   ```powershell
   .\venv\Scripts\python.exe database\init_db.py
   .\venv\Scripts\python.exe database\import_csv.py
   .\venv\Scripts\python.exe services\data_cleaning.py
   .\venv\Scripts\python.exe services\data_validation.py
   ```

   Do not put production credentials in Git or `vercel.json`. Keep these environment variables out of terminal recordings and screenshots.

6. Create the administrator against that same hosted database with `scripts/create_admin.py`. Enter the password in its private terminal prompt; do not add it to the repository or deployment configuration.
7. Redeploy after setting environment variables. On the production URL, check `/healthz`, Admin and User sign-in, database analytics, a small CSV/Excel upload, PDF download, and the Vercel function logs.

## Platform notes

- Vercel's Python runtime is currently documented as Beta. Streamlit's `st.App` ASGI interface is used so the app can run within a Python ASGI function rather than starting a long-running `streamlit run` process.
- The Vercel function filesystem is read-only except for temporary storage. Generated logs, charts, and reports therefore use `/tmp`; they do not persist between function instances. User uploads remain in Streamlit session memory. PostgreSQL is the persistent store for the Olist data and account records.
- The app allows uploads up to 50 MB locally. On Vercel, uploads are capped at 4 MB because Vercel Functions have a 4.5 MB HTTP request/response payload limit. Larger uploads need a direct-to-object-storage upload design or a host with a larger request-body limit.
- Vercel's WebSocket support for Functions requires Fluid Compute and is bounded by the function's maximum duration. A client may need to reconnect after a function instance ends.
- The large Olist CSV source files are excluded from the function bundle. They are needed for local database import, not for queries after the hosted database has been populated.

## Deployment status

Module 24 implementation is prepared in the repository. The live Vercel release remains pending because this workspace has no authenticated Vercel CLI session or hosted PostgreSQL credentials configured. No deployment URL exists until the project owner completes the account-specific steps above.

## References

- [Vercel Python runtime](https://vercel.com/docs/functions/runtimes/python)
- [Vercel project configuration](https://vercel.com/docs/project-configuration/vercel-json)
- [Vercel function limits](https://vercel.com/docs/functions/limitations)
- [Streamlit ASGI app](https://docs.streamlit.io/develop/api-reference/server/st.app)

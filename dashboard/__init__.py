"""
dashboard package

Streamlit page modules for the Interactive Dashboard (Module 7 - this
module - builds the shell/navigation; Modules 8-15 fill in most pages'
real content).

Each page module exposes exactly one function, render(), which app.py
wires up via st.Page(). A page module should:
    - Query data through services/ or database/connection.py, using
      @st.cache_data so Streamlit's rerun-on-every-interaction model
      doesn't re-hit PostgreSQL for unchanged data.
    - Never contain business logic itself - that belongs in services/.
      A page module is presentation only: layout, charts, widgets.
"""

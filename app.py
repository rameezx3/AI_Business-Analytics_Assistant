"""
app.py

WHY THIS FILE EXISTS:
    The single entry point for the Streamlit dashboard. Its only job is
    page configuration and navigation wiring - all actual page content
    lives in dashboard/*.py.

WHY PAGES ARE FILE PATHS, NOT CALLABLES:
    An earlier version used st.Page(module.render, ...) with each page
    exposing a render() function. That works for `streamlit run`, but
    breaks Streamlit's own AppTest.switch_page() - which requires
    file-based pages - making it impossible to automatically test
    navigation between pages. File-based pages are also Streamlit's
    more conventional pattern generally. Each dashboard/*.py file now
    runs top-to-bottom like a normal script (calling its own render()
    at the bottom) and can be tested directly with
    AppTest.from_file("dashboard/home.py") or navigated to with
    AppTest.from_file("app.py").switch_page("dashboard/home.py").

WHERE THIS FILE BELONGS:
    Project root: AI_Business_Analytics_Assistant/app.py

USAGE:
    streamlit run app.py
"""

import streamlit as st
from services.charts import set_chart_theme
from datetime import datetime, timezone

from services.local_auth import (
    authenticate_account,
    create_user_account,
    ensure_account_table,
)
from utils.access_control import current_account

st.set_page_config(
    page_title="AI Business Analytics Assistant",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

light_theme = st.sidebar.toggle(
    "Light theme",
    key="light_theme",
    value=False,
    help="Switch the full dashboard between light and dark appearance.",
)
set_chart_theme("light" if light_theme else "dark")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
:root { --ink:#eaf2ff; --muted:#9aabc4; --line:rgba(152,183,224,.16); --surface:rgba(16,27,46,.74); --canvas:#080d16; --blue:#55d9ef; --violet:#9b8cff; }
.stApp { background:radial-gradient(ellipse at 72% -10%,rgba(70,91,178,.19),transparent 42%),radial-gradient(ellipse at 3% 35%,rgba(0,190,210,.08),transparent 32%),var(--canvas); color:var(--ink); font-family:'DM Sans',sans-serif; }
[data-testid="stHeader"] { background:rgba(8,13,22,.72); }
[data-testid="stSidebar"] { background:rgba(8,14,25,.96); border-right:1px solid var(--line); }
[data-testid="stSidebar"] * { color:#dce8fb; }
[data-testid="stSidebar"] [data-testid="stSidebarNav"] { padding-top:1rem; }
[data-testid="stSidebar"] a { border:1px solid transparent; border-radius:11px; margin:4px 0; transition:background .2s ease,border-color .2s ease,transform .2s ease; }
[data-testid="stSidebar"] a:hover { background:rgba(85,217,239,.08); border-color:rgba(85,217,239,.2); transform:translateX(2px); }
h1,h2,h3 { font-family:'Manrope','DM Sans',sans-serif !important; color:var(--ink); letter-spacing:-.035em; }
h1 { font-size:2rem !important; font-weight:800 !important; }
h2 { font-size:1.35rem !important; font-weight:700 !important; margin-top:1.7rem !important; }
p, [data-testid="stCaptionContainer"] { color:#9aabc4; }
[data-testid="stMetric"] { background:linear-gradient(145deg,rgba(20,34,56,.88),rgba(12,21,36,.82)); border:1px solid var(--line); border-radius:16px; padding:18px 20px; box-shadow:0 12px 26px rgba(0,0,0,.2),inset 0 1px rgba(255,255,255,.045); min-height:112px; backdrop-filter:blur(14px); transition:transform .2s ease,border-color .2s ease,box-shadow .2s ease; }
[data-testid="stMetric"]:hover { transform:translateY(-3px); border-color:rgba(85,217,239,.32); box-shadow:0 18px 34px rgba(0,0,0,.28),0 0 24px rgba(85,217,239,.06),inset 0 1px rgba(255,255,255,.06); }
[data-testid="stMetricLabel"] { color:var(--muted); font-size:.83rem; font-weight:600; }
[data-testid="stMetricValue"] { color:#f2f7ff; font-family:'Manrope',sans-serif; font-weight:750; }
[data-testid="stPlotlyChart"] { background:rgba(12,21,36,.72); border:1px solid var(--line); border-radius:16px; padding:10px 12px; box-shadow:0 12px 28px rgba(0,0,0,.18); }
[data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:12px; }
[data-testid="stAlert"] { border-radius:12px; background:rgba(18,30,48,.85); }
button[kind="primary"],button[kind="secondary"] { border-radius:11px !important; transition:transform .16s ease,box-shadow .16s ease !important; }
button[kind="primary"] { background:linear-gradient(135deg,#26aeca,#6078e8) !important; border:1px solid rgba(143,231,255,.4) !important; box-shadow:0 5px 0 #16536e,0 10px 22px rgba(0,0,0,.28),inset 0 1px rgba(255,255,255,.32) !important; }
button[kind="primary"]:hover { transform:translateY(-2px); box-shadow:0 7px 0 #16536e,0 14px 26px rgba(25,170,206,.22),inset 0 1px rgba(255,255,255,.36) !important; }
button[kind="primary"]:active { transform:translateY(3px); box-shadow:0 1px 0 #16536e,0 4px 10px rgba(0,0,0,.22) !important; }
button[kind="secondary"] { background:rgba(19,31,50,.9) !important; border:1px solid var(--line) !important; box-shadow:0 4px 0 rgba(4,9,17,.8),0 8px 16px rgba(0,0,0,.16) !important; }
button[kind="secondary"]:hover { transform:translateY(-2px); border-color:rgba(85,217,239,.4) !important; box-shadow:0 6px 0 rgba(4,9,17,.8),0 12px 20px rgba(0,0,0,.2) !important; }
button[kind="secondary"]:active { transform:translateY(2px); box-shadow:0 1px 0 rgba(4,9,17,.8) !important; }
div[class*="st-key-kpi_board"] [data-testid="stButton"] button { min-height:148px; white-space:normal; text-align:left; justify-content:flex-start; padding:20px 20px; line-height:1.35; font-size:1rem; transform-style:preserve-3d; }
div[class*="st-key-kpi_board"] [data-testid="stButton"] button [data-testid="stMarkdownContainer"] { width:100%; }
div[class*="st-key-kpi_board"] [data-testid="stButton"] button [data-testid="stMarkdownContainer"] p { color:#d6e2f2 !important; font-size:1.08rem; font-weight:650; letter-spacing:-.01em; text-transform:none; white-space:pre-line !important; overflow-wrap:anywhere; line-height:1.5; }
div[class*="st-key-kpi_board"] [data-testid="stButton"] button [data-testid="stMarkdownContainer"] p:first-child strong { color:#9fb3cd !important; font-size:.9rem; font-weight:700; letter-spacing:.025em; }
div[class*="st-key-kpi_board"] [data-testid="stButton"] button [data-testid="stMarkdownContainer"] p:last-child strong { color:#f4f8ff !important; font-family:'Manrope','DM Sans',sans-serif; font-size:1.38rem; font-weight:800; letter-spacing:-.035em; }
div[class*="st-key-kpi_board"] [data-testid="stButton"] button svg { color:#55d9ef !important; width:1.15rem; height:1.15rem; }
div[class*="st-key-kpi_board"] [data-testid="stButton"] button:hover { transform:translateY(-4px) perspective(700px) rotateX(1deg); border-color:rgba(85,217,239,.48) !important; box-shadow:0 9px 0 #102b43,0 20px 34px rgba(0,0,0,.28),0 0 26px rgba(85,217,239,.12),inset 0 1px rgba(255,255,255,.16) !important; }
div[class*="st-key-kpi_board"] [data-testid="stButton"] button:active { transform:translateY(3px) translateZ(-3px); box-shadow:0 1px 0 #102b43,0 5px 10px rgba(0,0,0,.2) !important; }
div[class*="st-key-module_roadmap"] [data-testid="stHorizontalBlock"] { gap:.65rem; }
div[class*="st-key-module_roadmap"] div[class*="st-key-module_tile_"] [data-testid="stButton"] button { min-height:142px; white-space:pre-line; text-align:left; justify-content:flex-start; padding:12px; line-height:1.4; font-size:.77rem; transform-style:preserve-3d; }
div[class*="st-key-module_roadmap"] div[class*="st-key-module_tile_"] [data-testid="stButton"] button:hover { transform:translateY(-3px) perspective(600px) rotateX(1deg); border-color:rgba(85,217,239,.38) !important; box-shadow:0 7px 0 rgba(4,9,17,.72),0 15px 22px rgba(0,0,0,.23),0 0 17px rgba(85,217,239,.08) !important; }
div[class*="st-key-module_roadmap"] div[class*="st-key-module_tile_"] [data-testid="stButton"] button:active { transform:translateY(2px) translateZ(-3px); box-shadow:0 1px 0 rgba(4,9,17,.8),0 3px 7px rgba(0,0,0,.16) !important; }
:is([class*="st-key-module_tile_01"],[class*="st-key-module_tile_02"],[class*="st-key-module_tile_03"],[class*="st-key-module_tile_04"],[class*="st-key-module_tile_05"],[class*="st-key-module_tile_06"],[class*="st-key-module_tile_07"],[class*="st-key-module_tile_08"],[class*="st-key-module_tile_09"],[class*="st-key-module_tile_10"],[class*="st-key-module_tile_11"],[class*="st-key-module_tile_12"],[class*="st-key-module_tile_13"],[class*="st-key-module_tile_14"],[class*="st-key-module_tile_15"],[class*="st-key-module_tile_16"],[class*="st-key-module_tile_17"],[class*="st-key-module_tile_18"],[class*="st-key-module_tile_19"],[class*="st-key-module_tile_20"],[class*="st-key-module_tile_21"],[class*="st-key-module_tile_22"],[class*="st-key-module_tile_23"]) [data-testid="stButton"] button { border-color:rgba(73,207,178,.28) !important; box-shadow:0 5px 0 rgba(3,27,30,.78),0 10px 18px rgba(0,0,0,.15),0 0 14px rgba(73,207,178,.05),inset 0 1px rgba(255,255,255,.06) !important; }
div[class*="st-key-module_tile_24"] [data-testid="stButton"] button { border-color:rgba(85,217,239,.45) !important; animation:nextPulse 2.8s ease-in-out infinite; }
@keyframes nextPulse { 50% { box-shadow:0 5px 0 rgba(3,27,30,.7),0 10px 20px rgba(0,0,0,.15),0 0 18px rgba(85,217,239,.15),inset 0 1px rgba(255,255,255,.08); } }
.roadmap-progress { text-align:right; white-space:nowrap; margin-top:.65rem; padding:8px 12px; border-radius:999px; border:1px solid rgba(73,207,178,.25); background:rgba(73,207,178,.08); color:#8be5d0; font-size:.78rem; font-weight:700; }
.detail-status { display:inline-block; padding:5px 10px; border-radius:999px; font-size:.72rem; font-weight:750; letter-spacing:.08em; }
.detail-status.complete { background:rgba(73,207,178,.12); color:#38c9a5; border:1px solid rgba(73,207,178,.28); }
.detail-status.up_next { background:rgba(85,217,239,.12); color:#55d9ef; border:1px solid rgba(85,217,239,.3); }
.detail-status.pending { background:rgba(145,164,190,.1); color:#a3b1c5; border:1px solid rgba(145,164,190,.2); }
[data-testid="stDialog"] { backdrop-filter:blur(9px); background:rgba(2,8,18,.42) !important; }
[data-testid="stDialog"] > div { background:rgba(14,23,38,.97) !important; border:1px solid rgba(152,183,224,.2) !important; backdrop-filter:blur(22px); box-shadow:0 26px 90px rgba(0,0,0,.42) !important; }
div[data-testid="stVerticalBlock"] > div { gap:.8rem; }
@media(max-width:700px) { h1 { font-size:1.55rem !important; } [data-testid="stMetric"] { padding:12px; min-height:96px; } }
@media(max-width:1450px) { div[class*="st-key-kpi_board"] [data-testid="stHorizontalBlock"] { flex-wrap:wrap !important; } div[class*="st-key-kpi_board"] [data-testid="column"] { flex:1 1 calc(50% - .5rem) !important; min-width:calc(50% - .5rem) !important; } }
@media(max-width:900px) { div[class*="st-key-module_roadmap"] [data-testid="stHorizontalBlock"] { flex-wrap:wrap !important; } div[class*="st-key-module_roadmap"] [data-testid="column"] { flex:1 1 calc(33.333% - .65rem) !important; min-width:calc(33.333% - .65rem) !important; } }
@media(max-width:700px) { div[class*="st-key-kpi_board"] [data-testid="stHorizontalBlock"] { flex-wrap:wrap !important; } div[class*="st-key-kpi_board"] [data-testid="column"] { flex:1 1 calc(50% - .5rem) !important; min-width:calc(50% - .5rem) !important; } div[class*="st-key-module_roadmap"] [data-testid="column"] { flex:1 1 calc(50% - .5rem) !important; min-width:calc(50% - .5rem) !important; } }
@media(prefers-reduced-motion:reduce) { *,*::before,*::after { animation-duration:.01ms !important; transition-duration:.01ms !important; scroll-behavior:auto !important; } }
</style>
""", unsafe_allow_html=True)

if light_theme:
    st.markdown("""
    <style>
    :root { color-scheme:light; --ink:#172b4d; --muted:#64748b; --line:rgba(90,116,153,.18); --surface:rgba(255,255,255,.88); --canvas:#f3f6fb; --blue:#087e9c; --violet:#6854cc; }
    .stApp, [data-testid="stAppViewContainer"] { background:#f3f6fb !important; color:#172b4d !important; }
    [data-testid="stMain"], [data-testid="stMainBlockContainer"] { background:transparent !important; color:#172b4d !important; }
    [data-testid="stHeader"] { background:rgba(255,255,255,.88) !important; border-bottom:1px solid rgba(90,116,153,.12); }
    [data-testid="stSidebar"] { background:linear-gradient(180deg,#fff,#f4f7fc) !important; border-right:1px solid rgba(90,116,153,.18) !important; }
    [data-testid="stSidebar"] * { color:#263a56 !important; }
    [data-testid="stSidebar"] a:hover { background:#eaf5f8 !important; border-color:rgba(8,126,156,.2) !important; }
    h1,h2,h3,h4,h5,h6,[data-testid="stMarkdownContainer"] { color:#172b4d; }
    p, [data-testid="stCaptionContainer"], small { color:#64748b !important; }
    label, [data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] { color:#344963 !important; }
    [data-testid="stMetric"] { background:linear-gradient(145deg,rgba(255,255,255,.98),rgba(246,249,253,.96)) !important; border-color:rgba(90,116,153,.2) !important; box-shadow:0 8px 22px rgba(43,65,96,.08),inset 0 1px #fff !important; }
    [data-testid="stMetric"]:hover { border-color:rgba(8,126,156,.35) !important; box-shadow:0 13px 28px rgba(43,65,96,.12),0 0 20px rgba(8,126,156,.06) !important; }
    [data-testid="stMetricLabel"] { color:#64748b !important; }
    [data-testid="stMetricValue"] { color:#172b4d !important; }
    [data-testid="stPlotlyChart"] { background:rgba(255,255,255,.78) !important; border-color:rgba(90,116,153,.2) !important; box-shadow:0 8px 22px rgba(43,65,96,.07) !important; }
    [data-testid="stDataFrame"], [data-testid="stTable"] { background:#fff !important; border-color:rgba(90,116,153,.2) !important; }
    [data-testid="stDataFrame"] { --gdg-bg-cell:#fff; --gdg-bg-cell-medium:#f7f9fc; --gdg-bg-header:#f1f5f9; --gdg-text-dark:#172b4d; --gdg-text-medium:#475569; --gdg-border-color:rgba(90,116,153,.18); }
    [data-testid="stAlert"] { background:rgba(255,255,255,.92) !important; border:1px solid rgba(90,116,153,.16); color:#263a56 !important; }
    [data-testid="stExpander"] details, [data-testid="stForm"], [data-testid="stVerticalBlockBorderWrapper"] { background:rgba(255,255,255,.78) !important; border-color:rgba(90,116,153,.18) !important; }
    [data-baseweb="input"] > div, [data-baseweb="textarea"] > div, [data-baseweb="select"] > div, [data-testid="stDateInput"] input, [data-testid="stNumberInput"] input { background:#fff !important; color:#172b4d !important; border-color:rgba(90,116,153,.28) !important; }
    input, textarea { color:#172b4d !important; }
    [data-baseweb="popover"], [role="listbox"], [role="option"], [data-baseweb="menu"] { background:#fff !important; color:#172b4d !important; }
    [role="tab"] { color:#52657d !important; }
    [role="tab"][aria-selected="true"] { color:#087e9c !important; }
    button[kind="secondary"] { color:#243a56 !important; background:linear-gradient(145deg,#fff,#f4f7fb) !important; border-color:rgba(90,116,153,.22) !important; box-shadow:0 4px 0 rgba(74,97,129,.18),0 8px 16px rgba(43,65,96,.08) !important; }
    button[kind="secondary"]:hover { border-color:rgba(8,126,156,.38) !important; box-shadow:0 6px 0 rgba(74,97,129,.14),0 12px 20px rgba(43,65,96,.1) !important; }
    button[kind="secondary"]:active { box-shadow:0 1px 0 rgba(74,97,129,.14) !important; }
    button[kind="primary"] { color:#fff !important; }
    div[class*="st-key-kpi_board"] [data-testid="stButton"] button { color:#263a56 !important; background:linear-gradient(145deg,#fff,#f3f7fb) !important; border-color:rgba(90,116,153,.22) !important; box-shadow:0 6px 0 rgba(74,97,129,.14),0 13px 22px rgba(43,65,96,.08),inset 0 1px #fff !important; }
    div[class*="st-key-kpi_board"] [data-testid="stButton"] button [data-testid="stMarkdownContainer"] p { color:#475569 !important; }
    div[class*="st-key-kpi_board"] [data-testid="stButton"] button [data-testid="stMarkdownContainer"] p:first-child strong { color:#64748b !important; }
    div[class*="st-key-kpi_board"] [data-testid="stButton"] button [data-testid="stMarkdownContainer"] p:last-child strong { color:#15314c !important; }
    div[class*="st-key-kpi_board"] [data-testid="stButton"] button svg { color:#087e9c !important; }
    div[class*="st-key-kpi_board"] [data-testid="stButton"] button:hover { border-color:rgba(8,126,156,.4) !important; box-shadow:0 9px 0 rgba(74,97,129,.12),0 18px 28px rgba(43,65,96,.13),0 0 22px rgba(8,126,156,.08) !important; }
    div[class*="st-key-kpi_board"] [data-testid="stButton"] button:active { box-shadow:0 1px 0 rgba(74,97,129,.14),0 4px 8px rgba(43,65,96,.08) !important; }
    div[class*="st-key-module_roadmap"] div[class*="st-key-module_tile_"] [data-testid="stButton"] button { color:#344963 !important; background:linear-gradient(145deg,#fff,#f3f7fb) !important; border-color:rgba(90,116,153,.2) !important; box-shadow:0 5px 0 rgba(74,97,129,.12),0 10px 18px rgba(43,65,96,.07),inset 0 1px #fff !important; }
    div[class*="st-key-module_roadmap"] div[class*="st-key-module_tile_"] [data-testid="stButton"] button:hover { border-color:rgba(8,126,156,.38) !important; box-shadow:0 7px 0 rgba(74,97,129,.1),0 14px 22px rgba(43,65,96,.1),0 0 16px rgba(8,126,156,.07) !important; }
:is([class*="st-key-module_tile_01"],[class*="st-key-module_tile_02"],[class*="st-key-module_tile_03"],[class*="st-key-module_tile_04"],[class*="st-key-module_tile_05"],[class*="st-key-module_tile_06"],[class*="st-key-module_tile_07"],[class*="st-key-module_tile_08"],[class*="st-key-module_tile_09"],[class*="st-key-module_tile_10"],[class*="st-key-module_tile_11"],[class*="st-key-module_tile_12"],[class*="st-key-module_tile_13"],[class*="st-key-module_tile_14"],[class*="st-key-module_tile_15"],[class*="st-key-module_tile_16"],[class*="st-key-module_tile_17"],[class*="st-key-module_tile_18"],[class*="st-key-module_tile_19"],[class*="st-key-module_tile_20"],[class*="st-key-module_tile_21"],[class*="st-key-module_tile_22"],[class*="st-key-module_tile_23"]) [data-testid="stButton"] button { border-color:rgba(14,150,119,.32) !important; box-shadow:0 5px 0 rgba(34,100,83,.14),0 10px 18px rgba(43,65,96,.07),0 0 13px rgba(14,150,119,.05),inset 0 1px #fff !important; }
    div[class*="st-key-module_tile_24"] [data-testid="stButton"] button { border-color:rgba(8,126,156,.42) !important; }
    .roadmap-progress { background:#fff; color:#087e6a; border-color:rgba(14,150,119,.25); box-shadow:0 3px 10px rgba(43,65,96,.05); }
    .detail-status.complete { color:#078468; background:#eaf8f3; }.detail-status.up_next { color:#087e9c; background:#eaf7fa; }.detail-status.pending { color:#64748b; background:#f1f5f9; }
    [data-testid="stDialog"] { background:rgba(26,43,67,.2) !important; }
    [data-testid="stDialog"] > div { background:rgba(255,255,255,.98) !important; border-color:rgba(90,116,153,.2) !important; box-shadow:0 26px 80px rgba(43,65,96,.22) !important; }
    @media(max-width:900px) { .roadmap-progress { text-align:left; } }
    code, pre { background:#eaf0f7 !important; color:#28415f !important; }
    hr { border-color:rgba(90,116,153,.2) !important; }
    </style>
    """, unsafe_allow_html=True)

try:
    ensure_account_table()
except Exception as exc:
    st.error("The account database is unavailable. Start PostgreSQL and check the project .env settings.")
    st.caption(f"Diagnostic: {type(exc).__name__}")
    st.stop()

account = current_account()
if account is None:
    st.title("🔐 AI Business Analytics Assistant")
    st.write("Sign in to explore the business dashboard.")
    account_type = st.selectbox("Choose account type", ["User", "Admin"], key="login_account_type")
    if account_type == "Admin":
        with st.form("admin_sign_in"):
            email = st.text_input("Admin email", autocomplete="username")
            password = st.text_input("Password", type="password", autocomplete="current-password")
            submitted = st.form_submit_button("Sign in as admin", type="primary", width="stretch")
        if submitted:
            authenticated = authenticate_account(email, password, "admin")
            if authenticated:
                st.session_state["app_user"] = {
                    **authenticated,
                    "authenticated_at": datetime.now(timezone.utc).isoformat(),
                }
                st.rerun()
            st.error("Sign-in failed. Check your credentials or wait for the temporary lockout to expire.")
    else:
        access_mode = st.radio("User access", ["Sign in", "Create account"], horizontal=True, key="user_access_mode")
        if access_mode == "Sign in":
            with st.form("user_sign_in"):
                email = st.text_input("Email", autocomplete="username")
                password = st.text_input("Password", type="password", autocomplete="current-password")
                submitted = st.form_submit_button("Sign in", type="primary", width="stretch")
            if submitted:
                authenticated = authenticate_account(email, password, "user")
                if authenticated:
                    st.session_state["app_user"] = {
                        **authenticated,
                        "authenticated_at": datetime.now(timezone.utc).isoformat(),
                    }
                    st.rerun()
                st.error("Sign-in failed. Check your credentials or wait for the temporary lockout to expire.")
        else:
            st.caption("Create an account to view analytics. Passwords must be at least 12 characters.")
            with st.form("user_sign_up"):
                email = st.text_input("Email", autocomplete="email")
                password = st.text_input("Create password", type="password", autocomplete="new-password")
                confirm = st.text_input("Confirm password", type="password", autocomplete="new-password")
                submitted = st.form_submit_button("Create user account", type="primary", width="stretch")
            if submitted:
                if password != confirm:
                    st.error("The passwords do not match.")
                else:
                    created, message = create_user_account(email, password)
                    if created:
                        st.success(message + " Select Sign in to continue.")
                    else:
                        st.error(message)
    st.stop()

is_admin = account["role"] == "admin"
active_upload = st.session_state.get("user_upload")
if active_upload and active_upload.get("owner_email") != account["email"]:
    st.session_state.pop("user_upload", None)
st.sidebar.caption(f"Signed in as {account['email']} · {'Admin' if is_admin else 'User'}")
if not is_admin and st.session_state.get("user_upload"):
    active_upload = st.session_state["user_upload"]
    st.sidebar.caption(f"Current file: {active_upload.get('filename', 'Uploaded dataset')}")
    if st.sidebar.button("Clear uploaded data", key="clear_user_upload"):
        st.session_state.pop("user_upload", None)
        st.rerun()
if st.sidebar.button("Sign out", key="account_sign_out"):
    st.session_state.pop("app_user", None)
    st.session_state.pop("user_upload", None)
    st.rerun()

analytics_pages = [
    st.Page("dashboard/home.py", title="Home", icon="🏠", url_path="home", default=True),
    st.Page("dashboard/sales.py", title="Sales", icon="💰", url_path="sales"),
    st.Page("dashboard/customers.py", title="Customers", icon="👥", url_path="customers"),
    st.Page("dashboard/segmentation.py", title="Segments", icon="🧭", url_path="segments"),
    st.Page("dashboard/recommendations.py", title="Recommendations", icon="💡", url_path="recommendations"),
    st.Page("dashboard/business_insights.py", title="Business Insights", icon="✨", url_path="business-insights"),
    st.Page("dashboard/natural_language_sql.py", title="Ask Data", icon="💬", url_path="ask-data"),
    st.Page("dashboard/products.py", title="Products", icon="📦", url_path="products"),
    st.Page("dashboard/data_lab.py", title="Upload Data", icon="📤", url_path="upload-data"),
    st.Page("dashboard/orders.py", title="Orders", icon="🧾", url_path="orders"),
    st.Page("dashboard/geography.py", title="Geography", icon="🗺️", url_path="geography"),
    st.Page("dashboard/sellers.py", title="Sellers", icon="🏪", url_path="sellers"),
    st.Page("dashboard/forecast.py", title="Forecast", icon="📈", url_path="forecast"),
    st.Page("dashboard/ai_assistant.py", title="AI Assistant", icon="🤖", url_path="ai-assistant"),
    st.Page("dashboard/reports.py", title="Reports", icon="📄", url_path="reports"),
    st.Page("dashboard/admin_dashboard.py", title="System Health", icon=":material/monitor_heart:", url_path="system-health"),
    st.Page("dashboard/demo.py", title="Demo", icon="📊", url_path="demo"),
]
admin_pages = analytics_pages + [
    st.Page("dashboard/settings.py", title="Settings", icon="⚙️", url_path="settings"),
]
if is_admin:
    pages = admin_pages
else:
    # User analytics operate only on their current in-memory upload, never Olist tables.
    pages = {
        "Workspace": [
            st.Page("dashboard/home.py", title="Home", icon=":material/home:", url_path="home", default=True),
            st.Page("dashboard/data_lab.py", title="Upload Data", icon=":material/upload_file:", url_path="upload-data"),
        ],
        "Insights": [
            st.Page("dashboard/user_sales.py", title="Sales", icon=":material/bar_chart:", url_path="my-sales"),
            st.Page("dashboard/user_customers.py", title="Customers & Products", icon=":material/groups:", url_path="my-customers-products"),
            st.Page("dashboard/user_geography.py", title="Geography", icon=":material/public:", url_path="my-geography"),
            st.Page("dashboard/user_insights.py", title="Business Insights", icon=":material/query_stats:", url_path="my-insights"),
        ],
        "Preview": [
            st.Page("dashboard/demo.py", title="Demo", icon=":material/analytics:", url_path="demo"),
        ],
    }

navigation = st.navigation(pages)
navigation.run()

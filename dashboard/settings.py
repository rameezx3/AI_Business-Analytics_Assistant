"""
dashboard/settings.py

Unlike most other non-Home pages in Module 7, this one is real rather
than a placeholder - showing connection/environment status is cheap to
build now and immediately useful (e.g. confirming the dashboard is
actually talking to the database you think it is).
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st

from config import config
from database.connection import db
from utils.access_control import has_admin_access


def render() -> None:
    if not has_admin_access():
        st.error("This page is available to administrators only. Sign in with an admin account.")
        st.stop()

    st.title("⚙️ Settings")

    st.subheader("Database Connection")
    connected = db.test_connection()
    if connected:
        st.success("Connected")
    else:
        st.error("Not connected - check your .env file.")

    st.write(f"**Host:** {config.database.host}")
    st.write(f"**Port:** {config.database.port}")
    st.write(f"**Database:** {config.database.name}")
    st.write(f"**User:** {config.database.user}")

    st.subheader("Application")
    st.write(f"**Environment:** {config.app.environment}")
    st.write(f"**Debug mode:** {config.app.debug}")
    st.write(f"**Log level:** {config.app.log_level}")

    st.subheader("Paths")
    st.code(
        f"Data dir:    {config.app.data_dir}\n"
        f"Logs dir:    {config.app.logs_dir}\n"
        f"Reports dir: {config.app.reports_dir}\n"
        f"Charts dir:  {config.app.charts_dir}",
        language="text",
    )


render()

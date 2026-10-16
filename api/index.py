"""Vercel ASGI entry point for the Streamlit application."""

from pathlib import Path
import os

import streamlit as st
from streamlit import config as streamlit_config
from starlette.responses import JSONResponse
from starlette.routing import Route


PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Vercel Functions cap HTTP request bodies at 4.5 MB. Keep the Streamlit
# uploader slightly below that ceiling; local runs retain the normal limit.
if os.getenv("VERCEL", "").lower() == "1" or os.getenv("VERCEL_ENV"):
    streamlit_config.set_option("server.maxUploadSize", 4)


async def health_check(request):
    """Lightweight process health check; database readiness is configured separately."""
    return JSONResponse({"status": "ok", "application": "AI Business Analytics Assistant"})


app = st.App(
    str(PROJECT_ROOT / "app.py"),
    routes=[Route("/healthz", health_check, methods=["GET"])],
)

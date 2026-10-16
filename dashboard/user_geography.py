"""Country, state/province, and city analysis for the current upload."""

import plotly.express as px
import streamlit as st

from services.charts import ChartBuilder, set_chart_theme
from services.upload_workspace import find_column, measure_name, require_upload, sales_groups


set_chart_theme("light" if st.session_state.get("light_theme", False) else "dark")
upload = require_upload()
profile = upload["profile"]
frame, sales = profile["frame"], profile.get("sales")
st.title("Geography")
st.caption(f"Location performance in **{upload['filename']}** · grouped from the uploaded rows")

country = find_column(frame, "country", "country_region")
state = find_column(frame, "state", "state_province", "province")
city = find_column(frame, "city", "town")
measure = measure_name(sales)
geo_frame = frame.copy()
if not sales:
    geo_frame[measure] = 1

if country and sales:
    by_country = sales_groups(geo_frame, country, sales)
    map_figure = px.choropleth(
        by_country,
        locations=country,
        locationmode="country names",
        color=sales,
        hover_name=country,
        color_continuous_scale="Tealgrn",
        title="Sales by country",
    )
    map_figure.update_layout(margin=dict(l=0, r=0, t=50, b=0), height=450)
    st.plotly_chart(map_figure, width="stretch")

left, right = st.columns(2)
if country:
    country_groups = sales_groups(geo_frame, country, sales).sort_values(measure, ascending=False).head(12)
    with left:
        st.subheader("Top countries")
        st.plotly_chart(ChartBuilder.horizontal_bar(country_groups, country, measure, f"Top countries by {measure.lower()}"), width="stretch")
elif not state and not city:
    st.info("No country, state/province, or city column was detected. Try headers such as Country, State, Province, or City.")

if state:
    state_frame = geo_frame
    if country:
        countries = sorted(frame[country].dropna().astype(str).unique().tolist())
        if countries:
            selected_country = st.selectbox("Choose a country to compare its states / provinces", countries, key="user_geo_country")
            state_frame = geo_frame[geo_frame[country].astype(str) == selected_country]
    state_groups = sales_groups(state_frame, state, sales).sort_values(measure, ascending=False).head(12)
    with right:
        st.subheader("Top states / provinces")
        st.plotly_chart(ChartBuilder.horizontal_bar(state_groups, state, measure, f"Top states / provinces by {measure.lower()}"), width="stretch")

if city:
    st.subheader("Top cities")
    city_groups = sales_groups(geo_frame, city, sales).sort_values(measure, ascending=False).head(12)
    st.plotly_chart(ChartBuilder.horizontal_bar(city_groups, city, measure, f"Top cities by {measure.lower()}"), width="stretch")

st.caption("A choropleth uses recognized country names. The uploaded workbook has no latitude/longitude fields, so state and city results are shown as ranked charts rather than point maps.")

import streamlit as st

home_page = st.Page(
    "main_home.py",
    title="Home",
    icon="🏠",
    default=True,
)

change_ratio_page = st.Page(
    "change_ratio_page.py",
    title="Change Ratio Analysis",
    icon="📉",
    url_path="change-ratio-analysis",
)

verified_page = st.Page(
    "site_verified_page.py",
    title="Site Verified Lakes",
    icon="🖼️",
    url_path="site-verified-lakes",
)

pg = st.navigation(
    [home_page, change_ratio_page, verified_page],
    position="hidden",
)

pg.run()
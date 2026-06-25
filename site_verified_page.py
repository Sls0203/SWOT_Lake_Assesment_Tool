from __future__ import annotations

from pathlib import Path

import streamlit as st
from working_lake_ids import SITE_VERIFIED_LAKES

APP_DIR = Path(__file__).resolve().parent
SITE_IMG_DIR = APP_DIR / "site_verified_imgs"


def inject_css() -> None:
    st.markdown(
        """
        <style>
            .stApp {background: #06101d; color: #f8fafc;}
            [data-testid="stSidebar"] {display: none;}
            .block-container {padding-top: 1rem;}
            .page-title {font-size: 2rem; font-weight: 700; margin-bottom: 0.3rem;}
            .page-sub {color: #93c5fd; margin-bottom: 1rem;}
            .info-box {
                background: rgba(15, 23, 42, 0.65);
                border: 1px solid rgba(148,163,184,0.15);
                border-radius: 12px;
                padding: 12px 14px;
                margin-bottom: 12px;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main():
    inject_css()

    st.markdown('<div class="page-title">Site Verified Lakes</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="page-sub">Select one of the 5 site-verified lakes to view the uploaded comparison image.</div>',
        unsafe_allow_html=True,
    )

    st.link_button("← Back to Main Hydrocron Page", "/", type="secondary")

    st.markdown(
        '<div class="info-box">This page contains only the verified-lake image viewer.</div>',
        unsafe_allow_html=True,
    )

    lake_name = st.selectbox(
        "Select verified lake",
        list(SITE_VERIFIED_LAKES.keys()),
        index=0,
    )

    file_name = SITE_VERIFIED_LAKES[lake_name]
    img_path = SITE_IMG_DIR / file_name

    st.markdown(f"### {lake_name}")

    if img_path.exists():
        st.image(str(img_path), use_container_width=True)
    else:
        st.error(f"Missing image file: {img_path.name}")

st.link_button("← Back to Main Hydrocron Page", "/", type="secondary")

if __name__ == "__main__":
    main()
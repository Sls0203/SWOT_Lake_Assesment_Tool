India Lakes -> SWOT Hydrocron

Project structure:
- app.py                         Main Streamlit app
- hydrocron_client.py            Hydrocron API client
- working_lake_ids.py            Site-verified lake image mapping
- requirements.txt               Python packages to install
- data/india_lakes_points.geojson
- site_verified_imgs/img_1.png ... img_5.png

What this app does:
1. Left panel: select lake by ID, set date range, or choose one of the 5 site-verified lakes.
2. Middle panel: India map with clickable lake points.
3. Right panel:
   - Tab 1: Hydrocron API fetch with interactive elevation and storage time series.
   - Tab 2: Site-verified lake comparison images.

How to run:
1. Open terminal in this folder.
2. Create virtual environment:
   python -m venv .venv
3. Activate it:
   Windows: .venv\Scripts\activate
   Mac/Linux: source .venv/bin/activate
4. Install dependencies:
   pip install -r requirements.txt
5. Run the app:
   streamlit run app.py

Notes:
- Internet is required for Hydrocron API calls.
- Python 3.11 is the best version that can be used for accessing this tool.
- The 5 site-verified lake images are already bundled inside site_verified_imgs.

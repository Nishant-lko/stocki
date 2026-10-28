# Slotwise

Slotwise is a Streamlit warehouse-slotting dashboard. It includes a saved, reproducible warehouse run for the comparison and safety views, plus a small synthetic area map for exploring product-to-warehouse options.

## Run locally

```bash
python -m pip install -r requirements.txt
streamlit run frontend/app.py
```

To build a new run from an orders CSV, launch the app and use **New test run**. The saved default run is included so the dashboard opens without downloading the source retail archive.

## Deploy on Streamlit Community Cloud

1. Select this GitHub repository and the `main` branch.
2. Set the app file path to `frontend/app.py`.
3. Deploy. Dependencies are installed from `requirements.txt`; the checked-in default run supplies the dashboard's initial data.

The warehouse measurements and product physical attributes are modeled. The area-map product and warehouse choices are deterministic synthetic demo data.

# Slotwise

Run the baseline pipeline against the included UCI Online Retail II archive:

```bash
.venv/bin/warehouse-slotting --config configs/default.yaml
```

Launch the hackathon dashboard:

```bash
.venv/bin/streamlit run frontend/app.py
```

The dashboard reads immutable artifact bundles in `runs/`. The initial screen shows the completed feasible baseline; the optimizer, matched path comparison, and baseline-versus-optimized metrics are the next implementation slice.

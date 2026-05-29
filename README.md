# Vendor Report Dashboard — Flask Edition

A complete rewrite of the Dash dashboard using **Flask + Plotly JS + AG Grid**.

## Project Structure

```
vendor_dashboard/
├── app.py                   # Flask app — all routes & data logic
├── requirements.txt         # Python dependencies
├── dataset.xlsx             # ← Place your data file here
├── templates/
│   └── index.html           # Main HTML template (Jinja2)
└── static/
    ├── css/
    │   └── style.css        # All styles
    └── js/
        └── main.js          # All client-side logic (filters, charts, table)
```

## Setup & Run

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Place your Excel data file in the project root
cp /path/to/your/dataset.xlsx ./dataset.xlsx

# 3. Run the server
python app.py
# → Open http://localhost:8051
```

## Features

| Feature | Description |
|---|---|
| Cross-filtered dropdowns | Country / Vendor / Study Type / Project Nature |
| Range sliders | Desired IR, Actual IR, LOI |
| KPI cards | 7 live metrics |
| AG Grid table | Grouped/flat, sortable, filterable, paginated |
| Tracker chart | Bar + trend line, selectable PID |
| Vendor ranking | Horizontal bar, configurable metric & Top-N |
| Scatter plot | Any two metrics, color by category, trend line |
| World map | Choropleth, click-to-select countries |
| Region stats | Summary cards for selected regions |
| Export CSV | Exports current filtered/grouped view |
| Row modal | Click any table row to see full study details |

## Architecture

- **`app.py`** — All data preprocessing, filtering, and Plotly figure generation happens server-side. Each chart/feature is a separate `POST /api/...` endpoint that returns Plotly JSON.
- **`main.js`** — Pure vanilla JS. Manages filter state, calls APIs on change (debounced 200 ms), and renders results using `Plotly.react()` and AG Grid Community Edition.
- **`style.css`** — Full custom stylesheet using CSS variables. No Bootstrap dependency.

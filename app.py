import re
import time
import warnings
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file
import io
import json

warnings.filterwarnings("ignore", message=".*ChainedAssignmentError.*", category=FutureWarning)

app = Flask(__name__)

# ==================== CONSTANTS ====================

COLORS = {
    "primary":    "#1f77b4",
    "success":    "#2ca02c",
    "danger":     "#d62728",
    "warning":    "#ff7f0e",
    "purple":     "#9467bd",
    "border":     "#e2e8f0",
    "text":       "#333333",
    "text_light": "#666666",
    "bg_light":   "#f8fafc",
}

COUNTRY_ISO_MAP = {
    'AT': 'AUT', 'AU': 'AUS', 'BE': 'BEL', 'BR': 'BRA',
    'CA': 'CAN', 'CN': 'CHN', 'DE': 'DEU', 'ES': 'ESP',
    'FR': 'FRA', 'ID': 'IDN', 'IN': 'IND', 'IR': 'IRN',
    'IT': 'ITA', 'JP': 'JPN', 'KR': 'KOR', 'MX': 'MEX',
    'NL': 'NLD', 'PL': 'POL', 'SE': 'SWE', 'TH': 'THA',
    'TW': 'TWN', 'UK': 'GBR', 'US': 'USA', 'SP': 'ESP',
}

GROUP_COL_OPTIONS = [
    {'label': 'Country',  'value': 'country_clean'},
    {'label': 'Vendor',   'value': 'vendor'},
    {'label': 'PID',      'value': 'pid'},
    {'label': 'Study',    'value': 'study_name'},
]

# ==================== DATA HELPERS ====================

def safe_numeric_convert(val):
    if pd.isna(val):
        return 0
    if isinstance(val, (int, float)):
        return val if not np.isnan(val) else 0
    val_str = str(val).lower().strip()
    if val_str in ['na', 'n/a', 'nan', 'none', 'null', '']:
        return 0
    range_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:to|-)\s*(\d+(?:\.\d+)?)', val_str)
    if range_match:
        return (float(range_match.group(1)) + float(range_match.group(2))) / 2
    if '%' in val_str:
        val_str = val_str.replace('%', '')
    num_match = re.search(r'(\d+(?:\.\d+)?)', val_str)
    if num_match:
        return float(num_match.group(1))
    return 0


def parse_loi(loi_str):
    if pd.isna(loi_str):
        return 0
    loi_str = str(loi_str).lower().strip()
    if loi_str in ['na', 'n/a', 'nan', 'none', 'null', '']:
        return 0
    minutes = seconds = 0
    min_match = re.search(r'(\d+(?:\.\d+)?)\s*min', loi_str)
    if min_match:
        minutes = float(min_match.group(1))
    sec_match = re.search(r'(\d+(?:\.\d+)?)\s*sec', loi_str)
    if sec_match:
        seconds = float(sec_match.group(1))
    if not min_match and not sec_match:
        num_match = re.search(r'(\d+(?:\.\d+)?)', loi_str)
        if num_match:
            minutes = float(num_match.group(1))
    return minutes + (seconds / 60)


def preprocess_dataframe(df):
    df = df.copy()
    df.columns = (df.columns.str.strip().str.lower()
                  .str.replace(' ', '_').str.replace('(', '').str.replace(')', ''))
    str_cols = df.select_dtypes(include='object').columns
    df[str_cols] = df[str_cols].apply(
        lambda col: col.astype(str).str.replace(r'[\s\xa0]+', ' ', regex=True).str.strip()
    )
    col_map = {
        'field_in__': 'field_in',
        'scrubbing_removals_supplier': 'scrubbing_removals',
        'field_end_date': 'field_end_date',
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    df['allocated_completes'] = df['allocated_completes'].apply(safe_numeric_convert)
    df['achieved_completes']  = df['achieved_completes'].apply(safe_numeric_convert)
    df['desired_ir']          = df['desired_ir'].apply(safe_numeric_convert) * 100
    df['actual_ir']           = df['actual_ir'].apply(safe_numeric_convert) * 100

    df['scrubbing_removals'] = (df['scrubbing_removals'].apply(safe_numeric_convert)
                                if 'scrubbing_removals' in df.columns else 0)
    df['loi'] = df['loi'].apply(parse_loi) if 'loi' in df.columns else 0

    if 'field_end_date' in df.columns:
        df['field_end_date'] = pd.to_datetime(df['field_end_date'], errors='coerce')
        df['month']   = df['field_end_date'].dt.strftime('%Y-%m')
        df['quarter'] = df['field_end_date'].dt.to_period('Q').astype(str)
        df['year']    = df['field_end_date'].dt.year
    else:
        df['field_end_date'] = pd.NaT
        df['month'] = df['quarter'] = 'Unknown'
        df['year'] = 0

    if 'country' in df.columns:
        df['country_clean'] = df['country'].fillna('Unknown').astype(str).str.strip().str.upper()
        df['country_clean'] = df['country_clean'].replace({
            'US': 'US', 'USA': 'US', 'UNITED STATES': 'US',
            'UK': 'UK', 'UNITED KINGDOM': 'UK',
            'SOUTH KOREA': 'KOREA',
        })
    else:
        df['country_clean'] = 'Unknown'

    df['removal_pct'] = 0.0
    mask = df['achieved_completes'] > 0
    df.loc[mask, 'removal_pct'] = (
        df.loc[mask, 'scrubbing_removals'] / df.loc[mask, 'achieved_completes'] * 100
    ).round(1)
    df['removal_pct'] = df['removal_pct'].fillna(0.0).replace([np.inf, -np.inf], 0.0)

    for col in ['study_type', 'criteria', 'project_nature', 'vendor']:
        if col in df.columns:
            df[col] = df[col].fillna('Other').astype(str).str.strip()
            df[col] = df[col].replace(['', 'nan', 'None', 'NA', 'n/a'], 'Other')
        else:
            df[col] = 'Other'

    if 'vendor' in df.columns:
        popular = df.groupby(df['vendor'].str.lower())['vendor'].agg(
            lambda x: x.value_counts().index[0]
        )
        df['vendor'] = df['vendor'].str.lower().map(popular)

    df['pid'] = (df['pid'].apply(safe_numeric_convert).astype(int)
                 if 'pid' in df.columns else 0)
    df['study_name'] = (df['study_name'].fillna('Unknown Study').astype(str)
                        if 'study_name' in df.columns else 'Unknown Study')

    df = df[(df['allocated_completes'] > 0) | (df['achieved_completes'] > 0)]
    dedup_cols = [c for c in df.columns if c != 'sl']
    df = df.drop_duplicates(subset=dedup_cols, keep='first')
    return df


def load_excel_data():
    try:
        df = pd.read_excel('dataset.xlsx')
        df = preprocess_dataframe(df)
        print(f"Loaded {len(df)} records successfully")
        return df
    except FileNotFoundError:
        print("Excel file not found — using empty DataFrame.")
        return pd.DataFrame()


# Load data at startup
current_df = load_excel_data()

DESIRED_IR_MAX = float(current_df['desired_ir'].max()) if not current_df.empty else 100.0
ACTUAL_IR_MAX  = float(current_df['actual_ir'].max())  if not current_df.empty else 100.0
LOI_MAX        = float(current_df['loi'].max())         if not current_df.empty else 60.0


def apply_filters(df, country, vendor, study_type, project_nature,
                  desired_ir_min, desired_ir_max,
                  actual_ir_min, actual_ir_max,
                  loi_min, loi_max):
    if df.empty:
        return df
    if country and 'country_clean' in df.columns:
        df = df[df['country_clean'].isin(country)]
    if vendor and 'vendor' in df.columns:
        df = df[df['vendor'].isin(vendor)]
    if study_type and 'study_type' in df.columns:
        df = df[df['study_type'].isin(study_type)]
    if project_nature and 'project_nature' in df.columns:
        df = df[df['project_nature'].isin(project_nature)]
    if 'desired_ir' in df.columns:
        df = df[(df['desired_ir'] >= desired_ir_min) & (df['desired_ir'] <= desired_ir_max)]
    if 'actual_ir' in df.columns:
        df = df[(df['actual_ir']  >= actual_ir_min)  & (df['actual_ir']  <= actual_ir_max)]
    if 'loi' in df.columns:
        df = df[(df['loi'] >= loi_min) & (df['loi'] <= loi_max)]
    return df


def get_filter_params():
    """Parse filter params from request.json safely."""
    body = request.get_json(silent=True) or {}
    country        = body.get('country') or []
    vendor         = body.get('vendor') or []
    study_type     = body.get('study_type') or []
    project_nature = body.get('project_nature') or []
    desired_ir     = body.get('desired_ir', [0, DESIRED_IR_MAX])
    actual_ir      = body.get('actual_ir',  [0, ACTUAL_IR_MAX])
    loi            = body.get('loi',        [0, LOI_MAX])
    return (country, vendor, study_type, project_nature,
            desired_ir[0], desired_ir[1],
            actual_ir[0],  actual_ir[1],
            loi[0],        loi[1])


def filtered_df():
    params = get_filter_params()
    return apply_filters(current_df.copy(), *params)


# ==================== ROUTES ====================

@app.route('/')
def index():
    return render_template('index.html',
                           desired_ir_max=DESIRED_IR_MAX,
                           actual_ir_max=ACTUAL_IR_MAX,
                           loi_max=LOI_MAX,
                           group_col_options=GROUP_COL_OPTIONS)


# ---------- Filter options (cross-filtered) ----------
@app.route('/api/filter-options', methods=['POST'])
def filter_options():
    body = request.get_json(silent=True) or {}
    country        = body.get('country') or []
    vendor         = body.get('vendor') or []
    study_type     = body.get('study_type') or []
    project_nature = body.get('project_nature') or []
    desired_ir     = body.get('desired_ir', [0, DESIRED_IR_MAX])
    actual_ir      = body.get('actual_ir',  [0, ACTUAL_IR_MAX])
    loi            = body.get('loi',        [0, LOI_MAX])

    def _apply(df, skip):
        if df.empty:
            return df
        if skip != 'country'        and country and 'country_clean' in df.columns:        df = df[df['country_clean'].isin(country)]
        if skip != 'vendor'         and vendor and 'vendor' in df.columns:                df = df[df['vendor'].isin(vendor)]
        if skip != 'study_type'     and study_type and 'study_type' in df.columns:        df = df[df['study_type'].isin(study_type)]
        if skip != 'project_nature' and project_nature and 'project_nature' in df.columns: df = df[df['project_nature'].isin(project_nature)]
        if 'desired_ir' in df.columns:
            df = df[(df['desired_ir'] >= desired_ir[0]) & (df['desired_ir'] <= desired_ir[1])]
        if 'actual_ir' in df.columns:
            df = df[(df['actual_ir']  >= actual_ir[0])  & (df['actual_ir']  <= actual_ir[1])]
        if 'loi' in df.columns:
            df = df[(df['loi'] >= loi[0]) & (df['loi'] <= loi[1])]
        return df

    def _col(df, col):
        return sorted(df[col].unique().tolist()) if col in df.columns else []

    return jsonify({
        'countries':       _col(_apply(current_df.copy(), 'country'),        'country_clean'),
        'vendors':         _col(_apply(current_df.copy(), 'vendor'),         'vendor'),
        'study_types':     _col(_apply(current_df.copy(), 'study_type'),     'study_type'),
        'project_natures': _col(_apply(current_df.copy(), 'project_nature'), 'project_nature'),
    })


# ---------- KPIs ----------
@app.route('/api/kpis', methods=['POST'])
def kpis():
    df = filtered_df()
    if df.empty:
        return jsonify({})
    ta  = df['allocated_completes'].sum()
    tac = df['achieved_completes'].sum()
    ts  = df['scrubbing_removals'].sum()
    return jsonify({
        'total_allocated':   int(ta),
        'total_achieved':    int(tac),
        'avg_achieved_pct':  round((tac / ta * 100) if ta > 0 else 0, 1),
        'total_scrubbed':    int(ts),
        'avg_removal_pct':   round((ts / tac * 100) if tac > 0 else 0, 1),
        'avg_desired_ir':    round(float(df['desired_ir'].mean()), 1),
        'avg_actual_ir':     round(float(df['actual_ir'].mean()), 1),
    })


# ---------- Data Table ----------
@app.route('/api/table', methods=['POST'])
def table_data():
    body    = request.get_json(silent=True) or {}
    df      = filtered_df()
    enabled = body.get('group_enabled', True)
    gcols   = [c for c in (body.get('group_cols') or []) if c]

    ALL_COLS  = ['country_clean','vendor','pid','study_name','allocated_completes',
                 'achieved_completes','achieved_pct','desired_ir','actual_ir',
                 'scrubbing_removals','removal_pct','study_type','loi',
                 'field_in','field_end_date','project_nature']
    FLAT_COLS = ['country_clean','vendor','pid','study_name','allocated_completes',
                 'achieved_completes','achieved_pct','desired_ir','actual_ir',
                 'scrubbing_removals','removal_pct','study_type','loi','project_nature']

    def _achieved_pct(d):
        d = d.copy()
        if d.empty or 'achieved_completes' not in d.columns:
            d['achieved_pct'] = 0
            return d
        d['achieved_pct'] = (d['achieved_completes'] / d['allocated_completes'] * 100).round(1)
        d['achieved_pct'] = d['achieved_pct'].fillna(0).replace([np.inf, -np.inf], 0)
        return d

    if df.empty:
        return jsonify({'rows': [], 'columns': []})

    if not enabled:
        df = _achieved_pct(df)
        cols = [c for c in ALL_COLS if c in df.columns]
        df['field_end_date'] = df['field_end_date'].astype(str)
        rows = df[cols].to_dict('records')
    elif gcols:
        grouped = df.groupby(gcols).agg(
            allocated_completes=('allocated_completes','sum'),
            achieved_completes=('achieved_completes','sum'),
            scrubbing_removals=('scrubbing_removals','sum'),
            actual_ir=('actual_ir','mean'),
            loi=('loi','mean'),
            desired_ir=('desired_ir','mean'),
        ).reset_index()
        grouped['removal_pct']  = (grouped['scrubbing_removals'] / grouped['achieved_completes'] * 100).round(1).fillna(0)
        grouped['achieved_pct'] = (grouped['achieved_completes'] / grouped['allocated_completes'] * 100).round(1).fillna(0).replace([np.inf, -np.inf], 0)
        cols = [c for c in FLAT_COLS if c in grouped.columns]
        rows = grouped[cols].to_dict('records')
    else:
        df = _achieved_pct(df)
        cols = [c for c in FLAT_COLS if c in df.columns]
        rows = df[cols].to_dict('records')

    # Serialise non-JSON-safe types
    for row in rows:
        for k, v in row.items():
            if pd.isna(v) if not isinstance(v, (list, dict)) else False:
                row[k] = None
            elif isinstance(v, (np.integer,)):
                row[k] = int(v)
            elif isinstance(v, (np.floating,)):
                row[k] = float(v)
            elif isinstance(v, pd.Timestamp):
                row[k] = v.strftime('%Y-%m-%d') if not pd.isna(v) else None

    return jsonify({'rows': rows, 'columns': cols})


# ---------- Tracker Chart ----------
@app.route('/api/tracker-chart', methods=['POST'])
def tracker_chart():
    body       = request.get_json(silent=True) or {}
    df         = filtered_df()
    bar_metric = body.get('bar_metric', 'both')
    trend      = body.get('trend', 'actual_ir')
    pid        = body.get('pid')
    sort_order = body.get('sort_order', 'desc')

    if 'project_nature' not in df.columns:
        return jsonify(json.loads(go.Figure().to_json()))
    tracker = df[df['project_nature'].str.upper() == 'TRACKER']
    if tracker.empty:
        return jsonify(go.Figure().to_json())

    if not pid:
        x_grp = 'pid'
        agg = tracker.groupby(x_grp).agg(
            achieved_completes=('achieved_completes','sum'),
            scrubbing_removals=('scrubbing_removals','sum'),
            allocated_completes=('allocated_completes','sum'),
            actual_ir=('actual_ir','mean'),
            desired_ir=('desired_ir','mean'),
            removal_pct=('removal_pct','mean'),
            loi=('loi','mean'),
            count=('study_name','nunique'),
        ).reset_index()
        agg['label'] = agg['pid'].astype(str)
    else:
        x_grp = 'study_name'
        sub = tracker[tracker['pid'] == int(pid)]
        if sub.empty:
            return jsonify(go.Figure().to_json())
        agg = sub.groupby(x_grp).agg(
            achieved_completes=('achieved_completes','sum'),
            scrubbing_removals=('scrubbing_removals','sum'),
            allocated_completes=('allocated_completes','sum'),
            actual_ir=('actual_ir','mean'),
            desired_ir=('desired_ir','mean'),
            removal_pct=('removal_pct','mean'),
            loi=('loi','mean'),
            count=('study_name','nunique'),
        ).reset_index()
        agg['label'] = agg['study_name'].apply(lambda x: x if len(x) <= 25 else x[:22]+'...')

    sort_col_map = {'achieved':'achieved_completes','scrubbed':'scrubbing_removals',
                    'allocated':'allocated_completes','both':'achieved_completes',
                    'achieved_allocated':'achieved_completes','counts':'count'}
    agg = agg.sort_values(sort_col_map.get(bar_metric,'achieved_completes'),
                          ascending=(sort_order == 'asc')).reset_index(drop=True)

    fig = go.Figure()
    if bar_metric in ('achieved','both'):
        fig.add_trace(go.Bar(x=agg['label'], y=agg['achieved_completes'],
                             name='Achieved Completes', marker_color=COLORS['success'], opacity=0.85))
    if bar_metric in ('scrubbed','both'):
        fig.add_trace(go.Bar(x=agg['label'], y=agg['scrubbing_removals'],
                             name='Scrubbed Removals', marker_color=COLORS['danger'], opacity=0.85))
    if bar_metric in ('allocated','achieved_allocated'):
        fig.add_trace(go.Bar(x=agg['label'], y=agg['allocated_completes'],
                             name='Allocated Completes', marker_color=COLORS['primary'], opacity=0.85))
    if bar_metric == 'achieved_allocated':
        fig.add_trace(go.Bar(x=agg['label'], y=agg['achieved_completes'],
                             name='Achieved Completes', marker_color=COLORS['success'], opacity=0.85))
    if bar_metric == 'counts':
        fig.add_trace(go.Bar(x=agg['label'], y=agg['count'],
                             name='Project Counts', marker_color=COLORS['purple'], opacity=0.85))

    trend_labels = {'actual_ir':'Actual IR %','desired_ir':'Desired IR %',
                    'removal_pct':'Avg Removal %','loi':'LOI (min)'}
    if trend in trend_labels:
        fig.add_trace(go.Scatter(x=agg['label'], y=agg[trend], name=trend_labels[trend],
                                 line=dict(color=COLORS['primary'], width=3),
                                 marker=dict(size=8), yaxis='y2'))

    fig.update_layout(
        barmode='group', xaxis_tickangle=-45,
        yaxis=dict(showgrid=True, gridcolor='#f0f0f0', zeroline=False),
        yaxis2=dict(overlaying='y', side='right', showgrid=False, zeroline=False),
        hovermode='x unified', template='plotly_white', height=400,
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        margin=dict(l=10, r=50, t=10, b=80), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    return jsonify(json.loads(fig.to_json()))


# ---------- Vendor Ranking ----------
@app.route('/api/vendor-ranking', methods=['POST'])
def vendor_ranking():
    body   = request.get_json(silent=True) or {}
    df     = filtered_df()
    top_n  = int(body.get('top_n', 10))
    metric = body.get('metric', 'achieved_completes')

    if df.empty:
        return jsonify(go.Figure().to_json())

    if metric in ('achieved_completes','allocated_completes','scrubbing_removals'):
        ranking = df.groupby('vendor')[metric].sum().sort_values(ascending=False).head(top_n)
    else:
        ranking = df.groupby('vendor')[metric].mean().sort_values(ascending=False).head(top_n)

    labels  = {'achieved_completes':'Achieved Completes','allocated_completes':'Allocated Completes',
               'scrubbing_removals':'Scrubbed Removals','actual_ir':'Actual IR (%)','removal_pct':'Avg Removal (%)'}
    is_pct  = metric in ('actual_ir','removal_pct')
    fmt_fn  = (lambda v: f'{v:.1f}') if is_pct else (lambda v: f'{v:,.0f}')

    fig = go.Figure(go.Bar(
        x=ranking.values, y=ranking.index, orientation='h',
        marker=dict(color=ranking.values.tolist(), colorscale='Blues', showscale=False),
        text=[fmt_fn(v) for v in ranking.values],
        textposition='inside', textfont=dict(size=12, color='white'),
        hovertemplate='<b>%{y}</b><br>%{x}<extra></extra>'))
    fig.update_layout(
        title=dict(text=f"Top {top_n} Vendors — {labels.get(metric,metric)}", font=dict(size=14)),
        xaxis=dict(showgrid=True, gridcolor='#f0f0f0', zeroline=False),
        yaxis=dict(autorange='reversed', showgrid=False),
        template='plotly_white', height=400,
        margin=dict(l=10, r=40, t=40, b=10),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    return jsonify(json.loads(fig.to_json()))


# ---------- Scatter ----------
@app.route('/api/scatter', methods=['POST'])
def scatter():
    body     = request.get_json(silent=True) or {}
    df       = filtered_df()
    x_metric = body.get('x_metric', 'loi')
    y_metric = body.get('y_metric', 'actual_ir')
    color_by = body.get('color_by', 'study_type')

    if df.empty:
        return jsonify(go.Figure().to_json())

    df = df[df[x_metric].notna() & df[y_metric].notna() & (df[x_metric] >= 0) & (df[y_metric] >= 0)]
    m_labels = {'loi':'LOI (minutes)','actual_ir':'Actual IR (%)','desired_ir':'Desired IR (%)',
                'removal_pct':'Avg Removal (%)','achieved_completes':'Achieved Completes',
                'allocated_completes':'Allocated Completes'}
    smax = df['achieved_completes'].max() or 1

    fig = go.Figure()
    if color_by == 'none':
        sizes = (df['achieved_completes'] / smax * 40 + 8).clip(8, 48)
        fig.add_trace(go.Scatter(
            x=df[x_metric], y=df[y_metric], mode='markers',
            marker=dict(size=sizes.tolist(), color=COLORS['primary'], opacity=0.7,
                        line=dict(color='rgba(0,0,0,0.2)', width=1)),
            text=df['vendor'], showlegend=False,
            customdata=df[['study_name','country_clean','study_type']].values.tolist(),
            hovertemplate='<b>%{text}</b><br>'+
                          f'{m_labels.get(x_metric,x_metric)}: %{{x:,.1f}}<br>'+
                          f'{m_labels.get(y_metric,y_metric)}: %{{y:,.1f}}<br>'+
                          'Study: %{customdata[0]}<br>Country: %{customdata[1]}<br><extra></extra>'))
    else:
        cats   = df[color_by].unique()
        colors = px.colors.qualitative.Plotly
        for i, cat in enumerate(cats):
            sub = df[df[color_by] == cat]
            sz  = (sub['achieved_completes'] / smax * 40 + 8).clip(8, 48)
            fig.add_trace(go.Scatter(
                x=sub[x_metric], y=sub[y_metric], mode='markers', name=str(cat),
                marker=dict(size=sz.tolist(), color=colors[i % len(colors)], opacity=0.7,
                            line=dict(color='rgba(0,0,0,0.2)', width=1)),
                text=sub['vendor'],
                customdata=sub[['study_name','country_clean']].values.tolist(),
                hovertemplate='<b>%{text}</b><br>'+
                              f'{m_labels.get(x_metric,x_metric)}: %{{x:,.1f}}<br>'+
                              f'{m_labels.get(y_metric,y_metric)}: %{{y:,.1f}}<br>'+
                              'Study: %{customdata[0]}<br>Country: %{customdata[1]}<br><extra></extra>'))

    xv, yv = df[x_metric].values, df[y_metric].values
    if len(xv) > 2:
        try:
            coeffs = np.polyfit(xv, yv, 1)
            tx = np.linspace(xv.min(), xv.max(), 100)
            r2 = np.corrcoef(xv, yv)[0, 1] ** 2
            fig.add_trace(go.Scatter(x=tx.tolist(), y=(coeffs[0]*tx+coeffs[1]).tolist(),
                                     mode='lines', line=dict(color='red', width=2, dash='dash'),
                                     name=f'Trend (R²={r2:.3f})'))
        except np.linalg.LinAlgError:
            pass

    fig.update_layout(
        title=dict(text=f"{m_labels.get(y_metric,y_metric)} vs {m_labels.get(x_metric,x_metric)}", font=dict(size=14)),
        xaxis=dict(title=m_labels.get(x_metric,x_metric), showgrid=True, gridcolor='#f0f0f0', zeroline=False),
        yaxis=dict(title=m_labels.get(y_metric,y_metric), showgrid=True, gridcolor='#f0f0f0', zeroline=False),
        template='plotly_white', height=450, autosize = True,hovermode='closest',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        margin=dict(l=10, r=10, t=40, b=10),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    return jsonify(json.loads(fig.to_json()))


# ---------- World Map ----------
@app.route('/api/world-map', methods=['POST'])
def world_map():
    body          = request.get_json(silent=True) or {}
    df            = filtered_df()
    color_metric  = body.get('color_metric', 'count')
    sel_regions   = body.get('selected_regions') or []

    if df.empty:
        fig = go.Figure()
        fig.update_layout(height=600, template='plotly_white')
        return jsonify(json.loads(fig.to_json()))

    geo_data = df.groupby('country_clean').agg(
        count=('pid','count'),
        achieved_completes=('achieved_completes','sum'),
        actual_ir=('actual_ir','mean'),
        scrubbing_removals=('scrubbing_removals','sum'),
    ).reset_index()
    geo_data['removal_pct'] = (geo_data['scrubbing_removals'] / geo_data['achieved_completes'] * 100).round(1).fillna(0).replace([np.inf,-np.inf],0)
    geo_data['iso_alpha']   = geo_data['country_clean'].map(COUNTRY_ISO_MAP).fillna('')
    geo_data = geo_data[geo_data['iso_alpha'] != '']

    col_map    = {'count':'count','achieved_completes':'achieved_completes',
                  'removal_pct':'removal_pct','actual_ir':'actual_ir'}
    color_col  = col_map.get(color_metric, 'count')
    color_title= {'count':'Survey Count','achieved_completes':'Achieved Completes',
                  'removal_pct':'Avg Removal %','actual_ir':'Actual IR (%)'}[color_metric]

    selected_set = set(sel_regions)
    fig = go.Figure()
    last_iso = geo_data['iso_alpha'].iloc[-1] if not geo_data.empty else ''

    for _, row in geo_data.iterrows():
        is_sel = row['country_clean'] in selected_set
        fig.add_trace(go.Choropleth(
            locations=[row['iso_alpha']],
            z=[row[color_col]],
            text=[row['country_clean']],
            customdata=[[row['count'], row['achieved_completes'], row['actual_ir'], row['removal_pct']]],
            colorscale='Blues',
            zmin=float(geo_data[color_col].min()),
            zmax=float(geo_data[color_col].max()) or 1,
            colorbar=dict(title=dict(text=color_title, font=dict(size=11)),
                          thickness=15, len=0.5, x=1.02, y=0.5),
            marker=dict(line=dict(color='rgba(255,0,0,0.9)' if is_sel else 'rgba(0,0,0,0.4)',
                                  width=2.5 if is_sel else 0.8)),
            hovertemplate='<b>%{text}</b><br>Survey Count: %{customdata[0]:,d}<br>'
                          'Achieved: %{customdata[1]:,.0f}<br>Actual IR: %{customdata[2]:.1f}%<br>'
                          'Avg Removal: %{customdata[3]:.1f}%<br><extra></extra>',
            showscale=(row['iso_alpha'] == last_iso),
        ))

    fig.update_layout(
        geo=dict(showframe=True, framecolor='rgba(0,0,0,0.1)', showcoastlines=True,
                 coastlinecolor='rgba(0,0,0,0.3)', showland=True, landcolor='rgb(230,230,230)',
                 showocean=True, oceancolor='rgb(210,225,240)', projection_type='equirectangular',
                 lonaxis=dict(range=[-180,180]), lataxis=dict(range=[-60,85])),
        template='plotly_white', height=600,
        margin=dict(l=0, r=0, t=0, b=0), dragmode='zoom',
        paper_bgcolor='rgba(0,0,0,0)')
    return jsonify(json.loads(fig.to_json()))


# ---------- Tracker PIDs ----------
@app.route('/api/tracker-pids', methods=['POST'])
def tracker_pids():
    df      = filtered_df()
    if 'project_nature' not in df.columns or 'pid' not in df.columns:
        return jsonify({'pids': []})
    tracker = df[df['project_nature'].str.upper() == 'TRACKER']
    pids    = sorted(tracker['pid'].unique().tolist())
    return jsonify({'pids': [int(p) for p in pids]})


# ---------- Region Stats ----------
@app.route('/api/region-stats', methods=['POST'])
def region_stats():
    body     = request.get_json(silent=True) or {}
    df       = filtered_df()
    regions  = body.get('regions') or []
    if not regions:
        return jsonify(None)
    sub = df[df['country_clean'].isin(regions)]
    if sub.empty:
        return jsonify(None)
    ta  = float(sub['allocated_completes'].sum())
    tac = float(sub['achieved_completes'].sum())
    ts  = float(sub['scrubbing_removals'].sum())
    return jsonify({
        'allocated':    ta,
        'achieved':     tac,
        'removal_pct':  round((ts / tac * 100) if tac > 0 else 0, 1),
        'actual_ir':    round(float(sub['actual_ir'].mean()), 1),
        'desired_ir':   round(float(sub['desired_ir'].mean()), 1),
        'loi':          round(float(sub['loi'].mean()), 0),
    })


# ---------- Export CSV ----------
@app.route('/api/export', methods=['POST'])
def export_csv():
    body    = request.get_json(silent=True) or {}
    df      = filtered_df()
    enabled = body.get('group_enabled', True)
    gcols   = [c for c in (body.get('group_cols') or []) if c]

    FLAT_COLS = ['country_clean','vendor','pid','study_name','allocated_completes',
                 'achieved_completes','achieved_pct','desired_ir','actual_ir',
                 'scrubbing_removals','removal_pct','study_type','loi','project_nature']

    if not enabled:
        df['achieved_pct'] = (df['achieved_completes'] / df['allocated_completes'] * 100).round(1).fillna(0).replace([np.inf,-np.inf],0)
        out = df[[c for c in FLAT_COLS if c in df.columns]]
    elif gcols:
        grouped = df.groupby(gcols).agg(
            allocated_completes=('allocated_completes','sum'),
            achieved_completes=('achieved_completes','sum'),
            scrubbing_removals=('scrubbing_removals','sum'),
            actual_ir=('actual_ir','mean'),
            loi=('loi','mean'),
            desired_ir=('desired_ir','mean'),
        ).reset_index()
        grouped['removal_pct']  = (grouped['scrubbing_removals'] / grouped['achieved_completes'] * 100).round(1).fillna(0)
        grouped['achieved_pct'] = (grouped['achieved_completes'] / grouped['allocated_completes'] * 100).round(1).fillna(0).replace([np.inf,-np.inf],0)
        out = grouped[[c for c in FLAT_COLS if c in grouped.columns]]
    else:
        df['achieved_pct'] = (df['achieved_completes'] / df['allocated_completes'] * 100).round(1).fillna(0).replace([np.inf,-np.inf],0)
        out = df[[c for c in FLAT_COLS if c in df.columns]]

    buf = io.StringIO()
    out.to_csv(buf, index=False)
    buf.seek(0)
    return send_file(io.BytesIO(buf.getvalue().encode()),
                     mimetype='text/csv',
                     as_attachment=True,
                     download_name='vendor_report_export.csv')


if __name__ == '__main__':
    import os
    app.run(debug=True, port=int(os.environ.get('PORT', 8054)))

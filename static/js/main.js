/* ============================================================
   Vendor Report Dashboard — main.js
   ============================================================ */

'use strict';

// ─── Config injected from server ─────────────────────────────
const CFG = window.DASHBOARD_CONFIG || {};
const DESIRED_IR_MAX = CFG.desired_ir_max || 100;
const ACTUAL_IR_MAX = CFG.actual_ir_max || 100;
const LOI_MAX = CFG.loi_max || 60;

// ─── Debounce helper ─────────────────────────────────────────
function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

// ─── Filter state ────────────────────────────────────────────
const state = {
  country: [],
  vendor: [],
  study_type: [],
  project_nature: [],
  desired_ir: [0, DESIRED_IR_MAX],
  actual_ir: [0, ACTUAL_IR_MAX],
  loi: [0, LOI_MAX],
};

// ─── Tom-Select instances ────────────────────────────────────
let tsCountry, tsVendor, tsStudyType, tsProjectNature, tsGeoRegions;

function buildFilterPayload() {
  return {
    country: state.country,
    vendor: state.vendor,
    study_type: state.study_type,
    project_nature: state.project_nature,
    desired_ir: state.desired_ir,
    actual_ir: state.actual_ir,
    loi: state.loi,
  };
}

async function apiFetch(path, body = {}) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return res.json();
}

// active slider circle_________________________
setTimeout(() => {

  document.querySelectorAll('.noUi-handle').forEach(handle => {

    handle.addEventListener('mousedown', function () {

      // remove previous active
      document.querySelectorAll('.noUi-handle')
        .forEach(h => h.classList.remove('active-handle'));

      // add current active
      this.classList.add('active-handle');

    });

  });

  document.addEventListener('mouseup', function () {
    document.querySelectorAll('.noUi-handle')
      .forEach(h => h.classList.remove('active-handle'));
  });

}, 100);

// ─── Refresh all dashboard sections ─────────────────────────
const refreshAll = debounce(async () => {
  const payload = buildFilterPayload();
  await Promise.all([
    refreshFilterOptions(payload),
    refreshKPIs(payload),
    refreshTable(payload),
    refreshTrackerChart(payload),
    refreshRanking(payload),
    refreshScatter(payload),
    refreshWorldMap(payload),
  ]);
  updateResetBtnStyle();
}, 200);

// ─────────────────────────────────────────────────────────────
//  FILTER OPTIONS  (cross-filtered)
// ─────────────────────────────────────────────────────────────
async function refreshFilterOptions(payload) {
  const data = await apiFetch('/api/filter-options', payload);

  repopulateTomSelect(tsCountry, data.countries, state.country);
  repopulateTomSelect(tsVendor, data.vendors, state.vendor);
  repopulateTomSelect(tsStudyType, data.study_types, state.study_type);
  repopulateTomSelect(tsProjectNature, data.project_natures, state.project_nature);
}

function repopulateTomSelect(ts, items, selected) {
  if (!ts) return;
  const prev = selected.slice();
  ts.clearOptions();
  items.forEach(v => ts.addOption({ value: v, text: v }));
  // Re-select still-valid values
  const valid = prev.filter(v => items.includes(v));
  ts.setValue(valid, true);
}

// ─────────────────────────────────────────────────────────────
//  KPIs
// ─────────────────────────────────────────────────────────────
async function refreshKPIs(payload) {
  const d = await apiFetch('/api/kpis', payload);
  const row = document.getElementById('kpi-row');
  if (!d || !Object.keys(d).length) { row.innerHTML = '<div class="loading-msg">No data</div>'; return; }

  const fmt = (v, pct = false) => pct ? `${v.toFixed(1)}%` : Number(v).toLocaleString();

  const cards = [
    { label: 'TOTAL ALLOCATED', val: fmt(d.total_allocated), cls: 'text-primary' },
    { label: 'TOTAL ACHIEVED', val: fmt(d.total_achieved), cls: d.total_achieved < d.total_allocated ? 'text-danger' : 'text-success' },
    { label: 'AVG ACHIEVED %', val: fmt(d.avg_achieved_pct, true), cls: d.avg_achieved_pct < 100 ? 'text-danger' : 'text-purple' },
    { label: 'TOTAL SCRUBBED', val: fmt(d.total_scrubbed), cls: 'text-danger' },
    { label: 'AVG REMOVAL %', val: fmt(d.avg_removal_pct, true), cls: 'text-warning' },
    { label: 'AVG DESIRED IR', val: fmt(d.avg_desired_ir, true), cls: 'text-purple' },
    { label: 'AVG ACTUAL IR', val: fmt(d.avg_actual_ir, true), cls: d.avg_actual_ir < d.avg_desired_ir ? 'text-danger' : 'text-success' },
  ];

  row.innerHTML = cards.map(c =>
    `<div class="kpi-card">
       <div class="kpi-label">${c.label}</div>
       <div class="kpi-value ${c.cls}">${c.val}</div>
     </div>`
  ).join('');
}

// ─────────────────────────────────────────────────────────────
//  AG-GRID TABLE
// ─────────────────────────────────────────────────────────────
let gridApi = null;

const COL_DEFS_MAP = {
  country_clean: { field: 'country_clean', headerName: 'Country', width: 140, pinned: 'left', filter: 'agTextColumnFilter' },
  vendor: { field: 'vendor', headerName: 'Vendor', width: 180, pinned: 'left', filter: 'agTextColumnFilter' },
  pid: { field: 'pid', headerName: 'PID', width: 110, type: 'rightAligned', filter: 'agNumberColumnFilter' },
  study_name: { field: 'study_name', headerName: 'Study', width: 300, filter: 'agTextColumnFilter' },
  study_type: { field: 'study_type', headerName: 'Study Type', width: 150, filter: 'agTextColumnFilter' },
  allocated_completes: {
    field: 'allocated_completes', headerName: 'Allocated', width: 130, type: 'rightAligned', filter: 'agNumberColumnFilter',
    valueFormatter: p => p.value != null ? Number(p.value).toLocaleString() : '0'
  },
  achieved_completes: {
    field: 'achieved_completes', headerName: 'Achieved', width: 130, type: 'rightAligned', filter: 'agNumberColumnFilter',
    valueFormatter: p => p.value != null ? Number(p.value).toLocaleString() : '0',
    cellStyle: p => p.value != null && p.data.allocated_completes != null && p.value < p.data.allocated_completes
      ? { color: '#d62728', fontWeight: 'bold' } : { color: '#2ca02c', fontWeight: 'bold' }
  },
  achieved_pct: {
    field: 'achieved_pct', headerName: 'Achieved %', width: 130, type: 'rightAligned', filter: 'agNumberColumnFilter',
    valueFormatter: p => p.value != null ? p.value.toFixed(1) + '%' : '0.0%',
    cellStyle: p => p.value < 100 ? { color: '#d62728', fontWeight: 'bold' } : { color: '#2ca02c', fontWeight: 'bold' }
  },
  desired_ir: {
    field: 'desired_ir', headerName: 'Desired IR', width: 130, type: 'rightAligned', filter: 'agNumberColumnFilter',
    valueFormatter: p => p.value != null ? p.value.toFixed(1) + '%' : '0.0%'
  },
  actual_ir: {
    field: 'actual_ir', headerName: 'Actual IR', width: 130, type: 'rightAligned', filter: 'agNumberColumnFilter',
    valueFormatter: p => p.value != null ? p.value.toFixed(1) + '%' : '0.0%',
    cellStyle: p => p.value != null && p.data.desired_ir != null && p.value < p.data.desired_ir
      ? { color: '#d62728', fontWeight: 'bold' } : { color: '#2ca02c', fontWeight: 'bold' }
  },
  scrubbing_removals: {
    field: 'scrubbing_removals', headerName: 'Scrubbed', width: 130, type: 'rightAligned', filter: 'agNumberColumnFilter',
    valueFormatter: p => p.value != null ? Number(p.value).toLocaleString() : '0'
  },
  removal_pct: {
    field: 'removal_pct', headerName: 'Removal %', width: 130, type: 'rightAligned', filter: 'agNumberColumnFilter',
    valueFormatter: p => p.value != null ? p.value.toFixed(1) + '%' : '0.0%',
    cellStyle: p => {
      const v = p.value || 0;
      if (v <= 5) return { color: '#2ca02c', fontWeight: 'bold' };
      const r = Math.min(200, Math.round(100 + v * 4));
      return { color: `rgb(${r},0,0)`, fontWeight: 'bold' };
    }
  },
  loi: {
    field: 'loi', headerName: 'LOI (min)', width: 120, type: 'rightAligned', filter: 'agNumberColumnFilter',
    valueFormatter: p => p.value != null ? Math.round(p.value).toString() : '0'
  },
  field_in: { field: 'field_in', headerName: 'Field In', width: 130, filter: 'agTextColumnFilter' },
  field_end_date: {
    field: 'field_end_date', headerName: 'Field End Date', width: 150, filter: 'agTextColumnFilter',
    valueFormatter: p => p.value ? String(p.value).split(' ')[0] : ''
  },
  project_nature: { field: 'project_nature', headerName: 'Project Nature', width: 150, filter: 'agTextColumnFilter' },
};

function getGroupBySettings() {
  const enabled = document.getElementById('group-by-toggle').checked;
  const gcols = Array.from(document.querySelectorAll('.group-level-sel'))
    .map(s => s.value).filter(Boolean);
  return { group_enabled: enabled, group_cols: gcols };
}

async function refreshTable(payload) {
  const { group_enabled, group_cols } = getGroupBySettings();
  const body = { ...payload, group_enabled, group_cols };
  const data = await apiFetch('/api/table', body);

  const wrap = document.getElementById('grouped-table');
  if (!data || !data.rows || !data.rows.length) {
    wrap.innerHTML = '<div class="loading-msg">No data available</div>';
    gridApi = null;
    return;
  }

  const checkboxCol = {
    headerName: '', width: 50, pinned: 'left', lockPosition: true,
    checkboxSelection: true, headerCheckboxSelection: true,
    sortable: false, resizable: false, filter: false,
  };
  const columnDefs = [checkboxCol, ...data.columns.map(c => COL_DEFS_MAP[c] || { field: c, headerName: c, width: 140 })];

  if (gridApi) {
    gridApi.setGridOption('columnDefs', columnDefs);
    gridApi.setGridOption('rowData', data.rows);
    return;
  }

  wrap.innerHTML = '<div id="ag-grid-container" class="ag-theme-alpine" style="height:100%;width:100%;"></div>';
  const gridOptions = {
    columnDefs,
    rowData: data.rows,
    defaultColDef: { sortable: true, resizable: true, filter: true, menuTabs: ['filterMenuTab'] },
    pagination: true,
    paginationPageSize: 200,
    paginationPageSizeSelector: [200, 500, 1000],
    rowHeight: 40,
    headerHeight: 50,
    rowSelection: 'single',
    onRowClicked: e => showModal(e.data),
  };
  const gridDiv = document.getElementById('ag-grid-container');
  gridApi = agGrid.createGrid(gridDiv, gridOptions);
}

// ─────────────────────────────────────────────────────────────
//  CHARTS
// ─────────────────────────────────────────────────────────────
async function refreshTrackerChart(payload) {
  const body = {
    ...payload,
    bar_metric: document.getElementById('tracker-bar-metric').value,
    trend: document.getElementById('tracker-trend').value,
    pid: document.getElementById('tracker-pid').value || null,
    sort_order: document.querySelector('input[name="tracker-sort"]:checked').value,
  };
  const fig = await apiFetch('/api/tracker-chart', body);
  Plotly.react('chart-tracker', fig.data || [], fig.layout || {}, { responsive: true });
}

async function refreshRanking(payload) {
  const body = {
    ...payload,
    top_n: parseInt(document.getElementById('top-n').value),
    metric: document.getElementById('rank-metric').value,
  };
  const fig = await apiFetch('/api/vendor-ranking', body);
  Plotly.react('chart-ranking', fig.data || [], fig.layout || {}, { responsive: true });
}

async function refreshScatter(payload) {
  const body = {
    ...payload,
    x_metric: document.getElementById('scatter-x').value,
    y_metric: document.getElementById('scatter-y').value,
    color_by: document.getElementById('scatter-color').value,
  };
  const fig = await apiFetch('/api/scatter', body);
  Plotly.react('chart-scatter', fig.data || [], fig.layout || {}, { responsive: true });
}

// ─────────────────────────────────────────────────────────────
//  WORLD MAP
// ─────────────────────────────────────────────────────────────
let selectedRegions = [];

async function refreshWorldMap(payload) {
  const body = {
    ...payload,
    color_metric: document.getElementById('geo-color-metric').value,
    selected_regions: selectedRegions,
  };
  const fig = await apiFetch('/api/world-map', body);
  Plotly.react('chart-worldmap', fig.data || [], fig.layout || {}, { responsive: true, scrollZoom: true });

  // Click handler
  const el = document.getElementById('chart-worldmap');
  el.removeAllListeners && el.removeAllListeners('plotly_click');
  el.on('plotly_click', e => {
    if (!e.points || !e.points[0]) return;
    const region = e.points[0].text;
    if (!region) return;
    if (selectedRegions.includes(region)) {
      selectedRegions = selectedRegions.filter(r => r !== region);
    } else {
      selectedRegions.push(region);
    }
    syncGeoRegionsDropdown();
    refreshWorldMap(buildFilterPayload());
    refreshRegionStats();
  });
}

function syncGeoRegionsDropdown() {
  if (!tsGeoRegions) return;
  tsGeoRegions.setValue(selectedRegions, true);
}

async function refreshRegionStats() {
  if (!selectedRegions.length) {
    document.getElementById('region-stats').style.display = 'none';
    return;
  }
  const data = await apiFetch('/api/region-stats', { ...buildFilterPayload(), regions: selectedRegions });
  if (!data) { document.getElementById('region-stats').style.display = 'none'; return; }

  const regLabel = selectedRegions.length <= 3 ? selectedRegions.join(', ') : `${selectedRegions.length} regions`;
  const el = document.getElementById('region-stats');
  el.style.display = 'block';
  el.innerHTML = `
    <h5 style="margin-bottom:14px;font-size:15px;font-weight:700;">Selected: ${regLabel}</h5>
    <div class="region-stats-grid">
      <div class="region-stat-card"><div class="stat-label">Total Allocated</div><div class="stat-val text-primary">${Number(data.allocated).toLocaleString()}</div></div>
      <div class="region-stat-card"><div class="stat-label">Total Achieved</div><div class="stat-val text-success">${Number(data.achieved).toLocaleString()}</div></div>
      <div class="region-stat-card"><div class="stat-label">Removal %</div><div class="stat-val text-warning">${data.removal_pct.toFixed(1)}%</div></div>
      <div class="region-stat-card"><div class="stat-label">Avg Actual IR</div><div class="stat-val text-success">${data.actual_ir.toFixed(1)}%</div></div>
      <div class="region-stat-card"><div class="stat-label">Avg Desired IR</div><div class="stat-val text-purple">${data.desired_ir.toFixed(1)}%</div></div>
      <div class="region-stat-card"><div class="stat-label">Avg LOI</div><div class="stat-val text-purple">${Math.round(data.loi)} min</div></div>
    </div>`;
}

// ─────────────────────────────────────────────────────────────
//  MODAL
// ─────────────────────────────────────────────────────────────
function showModal(row) {
  if (!row) return;
  const fmt = v => (v != null && !isNaN(v)) ? Number(v).toLocaleString() : (v || '—');
  const fmtPct = v => (v != null && !isNaN(v)) ? `${parseFloat(v).toFixed(1)}%` : '—';
  const modal = document.getElementById('detail-modal');
  document.getElementById('modal-content').innerHTML = `
    <p class="modal-study-name">${row.study_name || '—'}</p>
    <div class="modal-row">
      <div class="modal-col"><div class="modal-field-label">Vendor</div><div class="modal-field-val">${row.vendor || '—'}</div></div>
      <div class="modal-col"><div class="modal-field-label">Country</div><div class="modal-field-val">${row.country_clean || '—'}</div></div>
      <div class="modal-col"><div class="modal-field-label">Study Type</div><div class="modal-field-val">${row.study_type || '—'}</div></div>
      <div class="modal-col"><div class="modal-field-label">Project Nature</div><div class="modal-field-val">${row.project_nature || '—'}</div></div>
    </div>
    <hr class="modal-hr" />
    <div class="modal-row">
      <div class="modal-col"><div class="modal-field-label">Allocated</div><div class="modal-big text-primary">${fmt(row.allocated_completes)}</div></div>
      <div class="modal-col"><div class="modal-field-label">Achieved</div><div class="modal-big text-success">${fmt(row.achieved_completes)}</div></div>
      <div class="modal-col"><div class="modal-field-label">Scrubbed</div><div class="modal-big text-danger">${fmt(row.scrubbing_removals)}</div></div>
      <div class="modal-col"><div class="modal-field-label">Actual IR</div><div class="modal-big">${fmtPct(row.actual_ir)}</div></div>
      <div class="modal-col"><div class="modal-field-label">LOI</div><div class="modal-big">${row.loi != null ? Math.round(row.loi) + ' min' : '—'}</div></div>
    </div>
    <hr class="modal-hr" />
    <div class="modal-row">
      <div class="modal-col"><div class="modal-field-label">PID</div><div class="modal-field-val">${row.pid || '—'}</div></div>
      <div class="modal-col"><div class="modal-field-label">Field End Date</div><div class="modal-field-val">${row.field_end_date || '—'}</div></div>
    </div>`;
  modal.style.display = 'flex';
}

// ─────────────────────────────────────────────────────────────
//  EXPORT
// ─────────────────────────────────────────────────────────────
async function exportCSV() {
  const { group_enabled, group_cols } = getGroupBySettings();
  const payload = { ...buildFilterPayload(), group_enabled, group_cols };
  const res = await fetch('/api/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'vendor_report_export.csv'; a.click();
  URL.revokeObjectURL(url);
}

// ─────────────────────────────────────────────────────────────
//  RESET BUTTON STYLE
// ─────────────────────────────────────────────────────────────
function updateResetBtnStyle() {
  const btn = document.getElementById('reset-btn');
  const isDefault =
    !state.country.length && !state.vendor.length &&
    !state.study_type.length && !state.project_nature.length &&
    state.desired_ir[0] === 0 && state.desired_ir[1] === DESIRED_IR_MAX &&
    state.actual_ir[0] === 0 && state.actual_ir[1] === ACTUAL_IR_MAX &&
    state.loi[0] === 0 && state.loi[1] === LOI_MAX;
  btn.classList.toggle('active', !isDefault);
}

// ─────────────────────────────────────────────────────────────
//  INIT
// ─────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {

  // ── Tabs ──────────────────────────────────────────────────
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(btn.dataset.tab).classList.add('active');
      // Lazy-render charts when switching tabs
      const tab = btn.dataset.tab;
      const p = buildFilterPayload();
      if (tab === 'tab-charts') { refreshTrackerChart(p); refreshRanking(p); refreshScatter(p); }
      if (tab === 'tab-regional') { refreshWorldMap(p); }
    });
  });


  // ________________________________________________dropdown__________________________________________________
  // ── Tom-Select filter dropdowns ───────────────────────────

  const tsOpts = {
    plugins: ['remove_button'],
    maxItems: null,
    closeAfterSelect: false,
  };
  
  function createMultiSelect(selector, stateKey) {
  
    const ts = new TomSelect(selector, {
  
      ...tsOpts,
  
      placeholder: 'All',
  
      hideSelected: false,
  
      closeAfterSelect: false,
  
      render: {
  
        option: function (data, escape) {
  
          const checked = this.items.includes(data.value)
            ? 'checked'
            : '';
  
          return `
            <div class="option custom-option">
              <label>
                <input type="checkbox" ${checked}>
                <span>${escape(data.text)}</span>
              </label>
            </div>
          `;
        }
  
      },
  
      onChange(values) {
  
        state[stateKey] = values;
  
        refreshAll();
  
        this.refreshOptions(false);
  
        updateSelectedCount();
  
      }
  
    });
  
    // ── Override TomSelect's internal placeholder method ──────
    ts.updatePlaceholder = function () {
  
      const input = ts.control_input;
  
      if (!input) return;
  
      if (ts.items.length > 0) {
  
        input.placeholder = '';
  
        input.setAttribute('size', '0');
  
        input.style.width = '0';
  
        input.style.minWidth = '0';
  
        input.style.opacity = '0';
  
      } else {
  
        input.placeholder = 'All';
  
        input.setAttribute('size', '1');
  
        input.style.width = '';
  
        input.style.minWidth = '';
  
        input.style.opacity = '1';
  
      }
  
    };
  
    // ── change event to hide/show placeholder ─────────────────
    ts.on('change', function () {
  
      const input = ts.wrapper.querySelector('input');
  
      if (!input) return;
  
      if (ts.items.length > 0) {
  
        input.placeholder = '';
  
        input.setAttribute('size', '0');
  
        input.style.width = '0';
  
        input.style.minWidth = '0';
  
        input.style.opacity = '0';
  
      } else {
  
        input.placeholder = 'All';
  
        input.setAttribute('size', '1');
  
        input.style.width = '';
  
        input.style.minWidth = '';
  
        input.style.opacity = '1';
  
      }
  
    });
  
    // ── selected count ─────────────────────────────────────────
  
    function updateSelectedCount() {
  
      const count = ts.items.length;
  
      const control = ts.wrapper.querySelector('.ts-control');
  
      const input = control.querySelector('input');
  
      // hide/show placeholder
      if (input) {
  
        if (count > 0) {
  
          input.placeholder = '';
  
          input.setAttribute('size', '0');
  
          input.style.width = '0';
  
          input.style.minWidth = '0';
  
          input.style.opacity = '0';
  
        } else {
  
          input.placeholder = 'All';
  
          input.setAttribute('size', '1');
  
          input.style.width = '';
  
          input.style.minWidth = '';
  
          input.style.opacity = '1';
  
        }
  
      }
  
      // remove old counter
      const oldCounter = control.querySelector('.selected-count');
  
      if (oldCounter) {
        oldCounter.remove();
      }
  
      // no selection
      if (count === 0) return;
  
      // create counter
      const counter = document.createElement('span');
  
      counter.className = 'selected-count';
  
      counter.innerText = `(${count} selected)`;
  
      control.appendChild(counter);
  
    }
  
    // ── dropdown ───────────────────────────────────────────────
  
    const dropdown = ts.dropdown;
  
    // check / uncheck option
    dropdown.addEventListener('click', function (e) {
  
      const option = e.target.closest('.option');
  
      if (!option) return;
  
      const value = option.dataset.value;
  
      // already selected → uncheck
      if (ts.items.includes(value)) {
  
        ts.removeItem(value);
  
      } else {
  
        // not selected → check
        ts.addItem(value);
  
      }
  
      // refresh UI
      ts.refreshOptions(false);
  
      updateSelectedCount();
  
      // keep dropdown open
      e.preventDefault();
  
      e.stopPropagation();
  
    }, true);
  
    // ── select all / deselect all ──────────────────────────────
  
    const actions = document.createElement('div');
  
    actions.className = 'dropdown-actions';
  
    actions.innerHTML = `
      <span class="select-all">Select All</span>
      <span class="deselect-all">Deselect All</span>
    `;
  
    dropdown.prepend(actions);
  
    // select all
    actions.querySelector('.select-all')
      .addEventListener('click', () => {
  
        const allValues = Object.keys(ts.options);
  
        ts.setValue(allValues);
  
        ts.refreshOptions(false);
  
        updateSelectedCount();
  
      });
  
    // deselect all
    actions.querySelector('.deselect-all')
      .addEventListener('click', () => {
  
        ts.clear();
  
        ts.refreshOptions(false);
  
        updateSelectedCount();
  
      });
  
    updateSelectedCount();
  
    return ts;
  }



// initialize dropdowns
tsCountry = createMultiSelect('#filter-country', 'country');

tsVendor = createMultiSelect('#filter-vendor', 'vendor');

tsStudyType = createMultiSelect('#filter-study-type', 'study_type');

tsProjectNature = createMultiSelect('#filter-project-nature', 'project_nature');

//   _____________________________________________________________________________________________________________


// ── Group-by default values ───────────────────────────────
const defaults = ['country_clean', 'vendor', 'pid', 'study_name'];
document.querySelectorAll('.group-level-sel').forEach((sel, i) => {
  sel.value = defaults[i] || '';
  sel.addEventListener('change', () => refreshAll());
});

// ── Group-by toggle ───────────────────────────────────────
document.getElementById('group-by-toggle').addEventListener('change', e => {
  const enabled = e.target.checked;
  document.querySelectorAll('.group-level-sel').forEach(s => s.disabled = !enabled);
  refreshAll();
});

// ── noUiSlider — Desired IR ───────────────────────────────
// ── noUiSlider — Desired IR ───────────────────────────────
const slDesiredIR = document.getElementById('slider-desired-ir');
noUiSlider.create(slDesiredIR, {
  start: [0, DESIRED_IR_MAX],
  connect: true,
  step: 0.5,
  range: { min: 0, max: DESIRED_IR_MAX || 100 },
  tooltips: [true, true],
  format: { to: v => v.toFixed(1), from: v => parseFloat(v) },
  pips: {
    mode: 'steps',
    density: 10,
    filter: (value) => {
      const max = DESIRED_IR_MAX || 100;
      const step = max / 5;
      if (value === 0 || value === max) return 1;
      return Math.round(value * 10) % Math.round(step * 10) === 0 ? 1 : 0;
    },
    format: { to: v => Math.round(v) },
  },
});
slDesiredIR.noUiSlider.on('update', (vals) => {
  document.getElementById('desired-ir-lo').textContent = vals[0];
  document.getElementById('desired-ir-hi').textContent = vals[1];
});
slDesiredIR.noUiSlider.on('change', (vals) => {
  state.desired_ir = [parseFloat(vals[0]), parseFloat(vals[1])];
  refreshAll();
});

// ── noUiSlider — Actual IR ────────────────────────────────
const slActualIR = document.getElementById('slider-actual-ir');
noUiSlider.create(slActualIR, {
  start: [0, ACTUAL_IR_MAX],
  connect: true,
  step: 0.5,
  range: { min: 0, max: ACTUAL_IR_MAX || 100 },
  tooltips: [true, true],
  format: { to: v => v.toFixed(1), from: v => parseFloat(v) },
  pips: {
    mode: 'steps',
    density: 10,
    filter: (value) => {
      const max = ACTUAL_IR_MAX || 100;
      const step = max / 5;
      if (value === 0 || value === max) return 1;
      return Math.round(value * 10) % Math.round(step * 10) === 0 ? 1 : 0;
    },
    format: { to: v => Math.round(v) },
  },
});
slActualIR.noUiSlider.on('update', (vals) => {
  document.getElementById('actual-ir-lo').textContent = vals[0];
  document.getElementById('actual-ir-hi').textContent = vals[1];
});
slActualIR.noUiSlider.on('change', (vals) => {
  state.actual_ir = [parseFloat(vals[0]), parseFloat(vals[1])];
  refreshAll();
});

// ── noUiSlider — LOI ──────────────────────────────────────
const slLOI = document.getElementById('slider-loi');
noUiSlider.create(slLOI, {
  start: [0, LOI_MAX],
  connect: true,
  step: 0.5,
  range: { min: 0, max: LOI_MAX || 60 },
  tooltips: [true, true],
  format: { to: v => v.toFixed(1), from: v => parseFloat(v) },
  pips: {
    mode: 'steps',
    density: 10,
    filter: (value) => {
      const max = LOI_MAX || 60;
      const step = max / 5;
      if (value === 0 || value === max) return 1;
      return Math.round(value * 10) % Math.round(step * 8) === 0 ? 1 : 0;
    },
    format: { to: v => Math.round(v) },
  },
});
slLOI.noUiSlider.on('update', (vals) => {
  document.getElementById('loi-lo').textContent = vals[0];
  document.getElementById('loi-hi').textContent = vals[1];
});
slLOI.noUiSlider.on('change', (vals) => {
  state.loi = [parseFloat(vals[0]), parseFloat(vals[1])];
  refreshAll();
});

// ── Reset filters ──────────────────────────────────────────
document.getElementById('reset-btn').addEventListener('click', () => {
  state.country = []; state.vendor = []; state.study_type = []; state.project_nature = [];
  state.desired_ir = [0, DESIRED_IR_MAX];
  state.actual_ir = [0, ACTUAL_IR_MAX];
  state.loi = [0, LOI_MAX];

  tsCountry.clear(true);
  tsVendor.clear(true);
  tsStudyType.clear(true);
  tsProjectNature.clear(true);

  slDesiredIR.noUiSlider.set([0, DESIRED_IR_MAX]);
  slActualIR.noUiSlider.set([0, ACTUAL_IR_MAX]);
  slLOI.noUiSlider.set([0, LOI_MAX]);

  refreshAll();
});

// ── Chart controls ─────────────────────────────────────────
['tracker-bar-metric', 'tracker-trend', 'tracker-pid'].forEach(id => {
  document.getElementById(id).addEventListener('change', () => refreshTrackerChart(buildFilterPayload()));
});
document.querySelectorAll('input[name="tracker-sort"]').forEach(r => {
  r.addEventListener('change', () => refreshTrackerChart(buildFilterPayload()));
});
['rank-metric', 'top-n'].forEach(id => {
  document.getElementById(id).addEventListener('change', () => refreshRanking(buildFilterPayload()));
});
['scatter-x', 'scatter-y', 'scatter-color'].forEach(id => {
  document.getElementById(id).addEventListener('change', () => refreshScatter(buildFilterPayload()));
});

// ── Regional ──────────────────────────────────────────────
tsGeoRegions = new TomSelect('#geo-regions', {
  plugins: ['remove_button'],
  maxItems: null,
  onChange(vals) {
    selectedRegions = vals;
    refreshWorldMap(buildFilterPayload());
    refreshRegionStats();
  }
});

document.getElementById('geo-color-metric').addEventListener('change', () => {
  refreshWorldMap(buildFilterPayload());
});

document.getElementById('apply-geo-filter').addEventListener('click', () => {
  if (!selectedRegions.length) return;
  state.country = selectedRegions.slice();
  // Switch to data table tab
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.querySelector('[data-tab="tab-data-table"]').classList.add('active');
  document.getElementById('tab-data-table').classList.add('active');
  // Sync dropdown
  tsCountry.setValue(state.country, true);
  refreshAll();
});

// ── Export ─────────────────────────────────────────────────
document.getElementById('export-btn').addEventListener('click', exportCSV);

// ── Modal close ────────────────────────────────────────────
document.getElementById('modal-close').addEventListener('click', () => {
  document.getElementById('detail-modal').style.display = 'none';
});
document.getElementById('detail-modal').addEventListener('click', e => {
  if (e.target.id === 'detail-modal') document.getElementById('detail-modal').style.display = 'none';
});

// ── Populate tracker PID dropdown ─────────────────────────
async function loadTrackerPIDs() {
  const data = await apiFetch('/api/tracker-pids', buildFilterPayload());
  const sel = document.getElementById('tracker-pid');
  sel.innerHTML = '<option value="">All PIDs</option>';
  (data.pids || []).forEach(p => {
    const opt = document.createElement('option');
    opt.value = p; opt.textContent = p;
    sel.appendChild(opt);
  });
}
loadTrackerPIDs();

// ── Initial data load ──────────────────────────────────────
refreshAll();
});

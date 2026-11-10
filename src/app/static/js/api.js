/**
 * Módulo de Comunicação com a API Backend e Estado Central do App.
 * Desafio UniSoma 2026 — Aloca ABC
 */

let table = null;
let tableReady = false;
let suppressCellEvents = false;
let pendingUpdates = new Map();
let syncTimer = null;
let searchTimer = null;
let toastTimer = null;
let flashTimer = null;
let saveWidthTimer = null;
let currentZoom = 1.0;

let state = {
  activeSheet: "Alunos",
  sheetNames: ["Alunos"],
  numCols: 3,
  page: 1,
  totalPages: 1,
  totalRows: 0,
  searchQuery: "",
  selectedMatIdx: 0,
  selectedExcelRow: 1,
  selectedCol: 0,
  flashExcelRow: null,
  dirty: false,
  colWidths: {}
};

async function apiPost(path, body = {}) {
  const resp = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  return await resp.json();
}

function showBusy(text) {
  const m = document.getElementById("busyMask");
  if (m) {
    m.textContent = text || "Processando...";
    m.classList.add("show");
  }
}

function hideBusy() {
  const m = document.getElementById("busyMask");
  if (m) {
    m.classList.remove("show");
  }
}

function showToast(msg) {
  const t = document.getElementById("toast");
  if (t) {
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove("show"), 3600);
  }
}

function queueCellSync(matIdx, colIdx, newVal) {
  if (suppressCellEvents || isNaN(matIdx) || isNaN(colIdx) || colIdx < 0) return;
  pendingUpdates.set(`${matIdx}:${colIdx}`, {
    mat_idx: matIdx,
    col: colIdx,
    value: newVal === null || newVal === undefined ? "" : String(newVal)
  });
  clearTimeout(syncTimer);
  syncTimer = setTimeout(flushPendingUpdates, 35);
}

async function flushPendingUpdates() {
  if (pendingUpdates.size === 0) return;
  const updatesList = Array.from(pendingUpdates.values());
  pendingUpdates.clear();

  const res = await apiPost("/api/update_cells", {
    sheet_name: state.activeSheet,
    updates: updatesList
  });
  if (res.success) {
    if (typeof updateDirtyIndicator === "function") updateDirtyIndicator(res.dirty);
    if (res.flagged_rows && typeof applyFlaggedRowsInPlace === "function") applyFlaggedRowsInPlace(res.flagged_rows);
    if (res.summary && typeof renderSummary === "function") renderSummary(res.summary);
  }
}

/**
 * Módulo de Grade de Planilha (Tabulator), Colunas, Células e Manipulações.
 * Desafio UniSoma 2026 — Aloca ABC
 */

function colLetter(idx) {
  let n = idx + 1, s = "";
  while (n > 0) {
    const rem = (n - 1) % 26;
    s = String.fromCharCode(65 + rem) + s;
    n = Math.floor((n - 1) / 26);
  }
  return s;
}

function normStr(val) {
  return (val || "")
    .toString()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function isRowEmpty(rowData) {
  for (let c = 0; c < state.numCols; c++) {
    if ((rowData["c" + c] || "").toString().trim() !== "") return false;
  }
  return true;
}

// Ordenação estilo Excel: preserva Linha 1 no topo e linhas vazias ao final (visualização apenas)
function excelColumnSorter(a, b, aRow, bRow, column, dir) {
  const origFirst = dir === "asc" ? aRow.getData() : bRow.getData();
  const origSecond = dir === "asc" ? bRow.getData() : aRow.getData();

  if (origFirst.excel_row === 1) return -1;
  if (origSecond.excel_row === 1) return 1;

  const emptyFirst = isRowEmpty(origFirst);
  const emptySecond = isRowEmpty(origSecond);
  if (emptyFirst && emptySecond) return origFirst.excel_row - origSecond.excel_row;
  if (emptyFirst) return 1;
  if (emptySecond) return -1;

  const valA = (a || "").toString().trim();
  const valB = (b || "").toString().trim();
  const numA = parseFloat(valA.replace(",", "."));
  const numB = parseFloat(valB.replace(",", "."));
  if (!isNaN(numA) && !isNaN(numB) && valA !== "" && valB !== "") {
    return numA - numB;
  }
  return valA.localeCompare(valB, "pt-BR", { sensitivity: "base" });
}

function getSavedColumnWidths(sheetName) {
  if (!sheetName) return {};
  const fromState = (state.colWidths && state.colWidths[sheetName]) ? state.colWidths[sheetName] : {};
  try {
    const raw = localStorage.getItem("unisoma_col_widths_" + sheetName);
    const fromLocal = raw ? JSON.parse(raw) : {};
    return Object.assign({}, fromLocal, fromState);
  } catch (_) {
    return Object.assign({}, fromState);
  }
}

function saveColumnWidth(sheetName, field, width) {
  if (!sheetName || !field || !width) return;
  const w = Math.round(width);
  if (!state.colWidths) state.colWidths = {};
  if (!state.colWidths[sheetName]) state.colWidths[sheetName] = {};
  state.colWidths[sheetName][field] = w;

  try {
    const current = getSavedColumnWidths(sheetName);
    current[field] = w;
    localStorage.setItem("unisoma_col_widths_" + sheetName, JSON.stringify(current));
  } catch (_) {}

  clearTimeout(saveWidthTimer);
  saveWidthTimer = setTimeout(() => {
    apiPost("/api/set_col_width", { sheet_name: sheetName, field: field, width: w });
  }, 150);
}

function calculateDefaultColumnWidth(colIdx, res) {
  const header = (res && res.header) ? res.header : [];
  const rows = (res && res.rows) ? res.rows : [];
  const sheetName = (res && res.active_sheet) ? res.active_sheet : (state.activeSheet || "");

  const hRaw = (header[colIdx] !== undefined && header[colIdx] !== null) ? String(header[colIdx]).trim() : "";
  const hLower = hRaw.toLowerCase();

  // Find max text length in this column among header and up to first 120 sample rows
  let maxChars = hRaw.length;
  const sampleLimit = Math.min(rows.length, 120);
  for (let i = 0; i < sampleLimit; i++) {
    const r = rows[i];
    if (r && r.cells && r.cells[colIdx] !== undefined && r.cells[colIdx] !== null) {
      const s = String(r.cells[colIdx]).trim();
      if (s.length > maxChars) {
        maxChars = s.length;
      }
    }
  }

  // Column character classification
  const isSexo = hLower === "sexo" || hLower === "gênero" || hLower === "genero" ||
                 (maxChars <= 2 && hRaw.length > 0 && hRaw.length <= 4);

  const isName = hLower.includes("nome") || hLower.includes("aluno") || hLower.includes("estudante") ||
                 hLower.includes("docente") || (colIdx === 0 && sheetName === "Alunos");

  const isLongText = hLower.includes("inconsist") || hLower.includes("erro") || hLower.includes("alerta") ||
                     hLower.includes("motivo") || hLower.includes("observa") || hLower.includes("descri") ||
                     hLower.includes("nomenclatura") || maxChars > 50;

  // 1. Column "Sexo": compact (80px), definitely smaller than Nome
  if (isSexo) {
    return 80;
  }

  // 2. Column "Inconsistências" / long text: capped at 250px so it does not blow up the layout
  if (isLongText) {
    return 250;
  }

  // 3. Column "Nome": comfortably fits full student names (250px - 360px), much bigger than Sexo
  if (isName) {
    const contentWidth = Math.round(maxChars * 8.2 + 38);
    return Math.max(250, Math.min(360, contentWidth));
  }

  // 4. Empty column (no header, no cell content)
  if (maxChars === 0) {
    return 95;
  }

  // 5. General column (Disponibilidade, Recursos, Quantidade, Turma, Turno, etc.)
  const generalWidth = Math.round(maxChars * 8.0 + 36);
  return Math.max(95, Math.min(290, generalWidth));
}

function buildTabulatorColumns(numCols, res) {
  const sheetName = (res && res.active_sheet) ? res.active_sheet : (state.activeSheet || "");
  const savedWidths = getSavedColumnWidths(sheetName);
  const cols = [];

  for (let c = 0; c < numCols; c++) {
    const field = "c" + c;
    let colWidth = savedWidths[field];
    if (typeof colWidth !== "number" || colWidth < 50) {
      colWidth = calculateDefaultColumnWidth(c, res);
    }

    const isSexo = c === 1 && sheetName === "Alunos";
    cols.push({
      title: colLetter(c),
      field: field,
      width: colWidth,
      minWidth: isSexo ? 65 : 80,
      resizable: true,
      headerSort: true,
      headerSortTristate: true,
      headerTooltip: "Clique/arraste para selecionar colunas • Clique na seta para ordenar (A-Z / Z-A / Original)",
      sorter: excelColumnSorter,
      editor: "input",
      editorParams: { selectContents: true }
    });
  }
  return cols;
}

function buildTabulatorData(res) {
  const numCols = res.num_cols || 3;
  const header = res.header || [];
  const data = [];

  const row1 = {
    excel_row: 1,
    mat_idx: 0,
    flag: res.header_flag || ""
  };
  for (let c = 0; c < numCols; c++) {
    row1["c" + c] = header[c] !== undefined ? String(header[c]) : "";
  }
  data.push(row1);

  (res.rows || []).forEach(rObj => {
    const item = {
      excel_row: rObj.excel_row,
      mat_idx: rObj.mat_idx,
      flag: rObj.flag || ""
    };
    for (let c = 0; c < numCols; c++) {
      item["c" + c] = (rObj.cells && rObj.cells[c] !== undefined) ? String(rObj.cells[c]) : "";
    }
    data.push(item);
  });

  return data;
}

function formatSheetRow(row) {
  const d = row.getData();
  const el = row.getElement();
  if (!el) return;
  el.classList.remove("sheet-header-row", "flag-impeditiva", "flag-alerta", "flag-tratada", "jump-highlight");

  if (d.excel_row === 1) {
    el.classList.add("sheet-header-row");
    if (d.flag === "IMPEDITIVA") {
      el.classList.add("flag-impeditiva");
    }
  } else if (d.flag === "IMPEDITIVA") {
    el.classList.add("flag-impeditiva");
  } else if (d.flag === "ALERTA") {
    el.classList.add("flag-alerta");
  } else if (d.flag === "TRATADA") {
    el.classList.add("flag-tratada");
  }

  if (state.flashExcelRow && d.excel_row === state.flashExcelRow) {
    el.classList.add("jump-highlight");
  }
}

function updateDirtyIndicator(isDirty) {
  state.dirty = !!isDirty;
  const pill = document.getElementById("savePill");
  if (!pill) return;
  if (state.dirty) {
    pill.textContent = "Modificado (não salvo)";
    pill.classList.add("dirty");
  } else {
    pill.textContent = "Salvo";
    pill.classList.remove("dirty");
  }
}

function updateSelectionBarFromRanges() {
  if (!table || !tableReady) return;
  const ranges = table.getRanges();
  if (!ranges || ranges.length === 0) return;

  const activeRange = ranges[ranges.length - 1];
  const rows = activeRange.getRows();
  const cols = activeRange.getColumns().filter(col => {
    const f = col.getField();
    return f && f.startsWith("c");
  });
  if (!rows.length || !cols.length) return;

  const firstRowData = rows[0].getData();
  const lastRowData = rows[rows.length - 1].getData();
  const firstColIdx = parseInt(cols[0].getField().slice(1), 10);
  const lastColIdx = parseInt(cols[cols.length - 1].getField().slice(1), 10);

  state.selectedExcelRow = lastRowData.excel_row;
  state.selectedMatIdx = lastRowData.mat_idx;
  state.selectedCol = lastColIdx;

  const startRef = `${colLetter(firstColIdx)}${firstRowData.excel_row}`;
  const endRef = `${colLetter(lastColIdx)}${lastRowData.excel_row}`;
  const refEl = document.getElementById("cellRef");
  if (refEl) {
    refEl.textContent = startRef === endRef ? startRef : `${startRef}:${endRef}`;
  }

  const formulaEl = document.getElementById("formulaInput");
  if (formulaEl && document.activeElement !== formulaEl) {
    formulaEl.value = firstRowData["c" + firstColIdx] || "";
  }
}

function applyFlaggedRowsInPlace(flaggedMap) {
  if (!table || !tableReady || (state.activeSheet !== "Alunos" && state.activeSheet !== "Turmas")) return;
  const map = flaggedMap || {};
  table.getRows().forEach(row => {
    const d = row.getData();
    const newFlag = map[String(d.excel_row)] || "";
    if (d.flag !== newFlag) {
      d.flag = newFlag;
      const el = row._row && row._row.element ? row._row.element : null;
      if (el && el.parentNode) {
        formatSheetRow(row);
      }
    }
  });
}

function clearJumpHighlights() {
  clearTimeout(flashTimer);
  const prevRow = state.flashExcelRow;
  state.flashExcelRow = null;
  if (prevRow && table && tableReady) {
    try {
      const oldComp = table.getRow(prevRow);
      if (oldComp) formatSheetRow(oldComp);
    } catch (_) {}
  }
  try {
    const els = document.querySelectorAll(".jump-highlight");
    els.forEach(el => el.classList.remove("jump-highlight"));
  } catch (_) {}
}

async function highlightAndScrollRow(excelRow, targetCol = 0) {
  if (!table || !tableReady || !excelRow) return;
  const rowComp = table.getRow(excelRow);
  if (!rowComp) return;

  clearJumpHighlights();

  state.flashExcelRow = excelRow;
  try {
    await table.scrollToRow(rowComp, "center", false);
  } catch (_) {}

  formatSheetRow(rowComp);
  state.selectedExcelRow = excelRow;
  state.selectedMatIdx = excelRow - 1;
  state.selectedCol = targetCol;
  const targetCell = rowComp.getCell("c" + targetCol) || rowComp.getCell("c0");
  if (targetCell) {
    table.getRanges().forEach(r => r.remove());
    table.addRange(targetCell, targetCell);
    const cellRefEl = document.getElementById("cellRef");
    if (cellRefEl) cellRefEl.textContent = `${colLetter(targetCol)}${excelRow}`;
    const formulaEl = document.getElementById("formulaInput");
    if (formulaEl && document.activeElement !== formulaEl) {
      formulaEl.value = rowComp.getData()["c" + targetCol] || "";
    }
  }

  flashTimer = setTimeout(() => {
    clearJumpHighlights();
  }, 1400);
}

async function pasteFromClipboard() {
  try {
    if (navigator.clipboard && navigator.clipboard.readText) {
      const text = await navigator.clipboard.readText();
      if (text && table && table.modules && table.modules.clipboard) {
        const clip = table.modules.clipboard;
        const parsed = clip.pasteParser.call(clip, text);
        if (parsed) {
          const rows = clip.pasteAction.call(clip, parsed);
          clip.dispatchExternal("clipboardPasted", text, parsed, rows);
          showToast("Conteúdo colado na seleção.");
          return;
        }
      }
    }
  } catch (_) {}
  showToast("Pressione Ctrl+V para colar na célula selecionada.");
}

function getContextMenuItems(e, row) {
  if (!row) return [];
  const d = row.getData();
  const isHeaderRow = d.excel_row === 1;

  state.selectedExcelRow = d.excel_row;
  state.selectedMatIdx = d.mat_idx;
  if (e && e.target && e.target.closest) {
    const cellEl = e.target.closest(".tabulator-cell");
    if (cellEl) {
      const f = cellEl.getAttribute("tabulator-field");
      if (f && f.startsWith("c")) {
        state.selectedCol = parseInt(f.slice(1), 10);
      }
    }
  }

  const svgIcon = (pathD) =>
    `<svg class="ui-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${pathD}</svg>`;

  const icCopy = svgIcon('<rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>');
  const icPaste = svgIcon('<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/>');
  const icClear = svgIcon('<path d="M21 4H8l-7 8 7 8h13a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2z"/><line x1="18" y1="9" x2="12" y2="15"/><line x1="12" y1="9" x2="18" y2="15"/>');
  const icRow = svgIcon('<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>');
  const icCol = svgIcon('<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>');
  const icDelete = svgIcon('<polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>');
  const icUndo = svgIcon('<polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>');
  const icRedo = svgIcon('<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>');

  return [
    {
      label: `<div class="ctx-item"><span class="ctx-label">${icCopy} Copiar</span><kbd>Ctrl+C</kbd></div>`,
      action: () => {
        if (table) table.copyToClipboard();
        showToast("Células copiadas para a área de transferência.");
      }
    },
    {
      label: `<div class="ctx-item"><span class="ctx-label">${icPaste} Colar</span><kbd>Ctrl+V</kbd></div>`,
      action: () => pasteFromClipboard()
    },
    {
      label: `<div class="ctx-item"><span class="ctx-label">${icClear} Limpar Conteúdo</span><kbd>Del</kbd></div>`,
      action: () => {
        clearSelectedRanges();
        showToast("Conteúdo da seleção apagado.");
      }
    },
    { separator: true },
    {
      label: `<div class="ctx-item"><span class="ctx-label">${icRow} Inserir Linha Abaixo</span></div>`,
      action: () => addRowBelow()
    },
    {
      label: `<div class="ctx-item"><span class="ctx-label">${icCol} Inserir Coluna à Direita</span></div>`,
      action: () => addColumnRight()
    },
    {
      label: `<div class="ctx-item" style="${isHeaderRow ? 'color:#94A3B8;' : 'color:#DC2626;'}"><span class="ctx-label">${icDelete} Excluir Linha</span></div>`,
      disabled: isHeaderRow,
      action: () => {
        if (isHeaderRow) {
          showToast("A linha 1 é o cabeçalho e não pode ser excluída.");
          return;
        }
        deleteSelectedRow();
      }
    },
    { separator: true },
    {
      label: `<div class="ctx-item"><span class="ctx-label">${icUndo} Desfazer</span><kbd>Ctrl+Z</kbd></div>`,
      action: () => handleUndo()
    },
    {
      label: `<div class="ctx-item"><span class="ctx-label">${icRedo} Refazer</span><kbd>Ctrl+Y</kbd></div>`,
      action: () => handleRedo()
    }
  ];
}

async function applyPagePayload(res) {
  if (res.filename) {
    const ft = document.getElementById("fileTitle");
    if (ft) ft.textContent = res.filename;
  }
  if (res.filepath) {
    const fp = document.getElementById("filePath");
    if (fp) fp.textContent = res.filepath;
  }

  const prevNumCols = state.numCols;
  const prevSheet = state.activeSheet;
  state.activeSheet = res.active_sheet;
  if (res.col_widths) {
    if (!state.colWidths) state.colWidths = {};
    state.colWidths[res.active_sheet] = Object.assign({}, res.col_widths, state.colWidths[res.active_sheet] || {});
  }
  state.sheetNames = res.sheet_names || state.sheetNames;
  state.numCols = res.num_cols || 3;
  state.page = res.page || 1;
  state.totalPages = res.total_pages || 1;
  state.totalRows = res.total_rows || 0;
  state.flashExcelRow = null;
  updateDirtyIndicator(res.dirty);

  const rstBtn = document.getElementById("btnResetSort");
  if (rstBtn) rstBtn.style.display = "none";

  if (typeof renderTabs === "function") renderTabs();
  if (typeof renderPager === "function") renderPager();

  const data = buildTabulatorData(res);
  const targetHighlight = res.highlight_excel_row || null;

  const savedRow = res.highlight_excel_row || state.selectedExcelRow || 1;
  const savedCol = (res.highlight_col !== undefined ? res.highlight_col : state.selectedCol) || 0;
  let savedScrollTop = 0;
  let savedScrollLeft = 0;
  if (table && table.rowManager && table.rowManager.element) {
    savedScrollTop = table.rowManager.element.scrollTop;
    savedScrollLeft = table.rowManager.element.scrollLeft;
  }

  if (!table) {
    table = new Tabulator("#sheetGrid", {
      index: "excel_row",
      data: data,
      columns: buildTabulatorColumns(state.numCols, res),
      height: "100%",
      layout: "fitDataFill",
      resizableRows: false,
      rowContextMenu: getContextMenuItems,
      selectableRange: true,
      selectableRangeColumns: true,
      selectableRangeRows: true,
      selectableRangeClearCells: false,
      selectableRangeAutoFocus: false,
      editTriggerEvent: "dblclick",
      headerSortClickElement: "icon",
      headerSortTristate: true,
      clipboard: true,
      clipboardCopyStyled: false,
      clipboardCopyRowRange: "range",
      clipboardCopyConfig: { columnHeaders: false, rowHeaders: false },
      clipboardPasteParser: "range",
      clipboardPasteAction: "range",
      rowHeader: {
        title: "",
        width: 50,
        minWidth: 44,
        hozAlign: "center",
        resizable: false,
        headerSort: false,
        editor: false,
        frozen: true,
        cssClass: "excel-row-num",
        formatter: (cell) => cell.getRow().getData().excel_row
      },
      rowFormatter: formatSheetRow
    });

    table.on("tableBuilt", () => {
      tableReady = true;
      if (targetHighlight) {
        highlightAndScrollRow(targetHighlight);
      } else {
        updateSelectionBarFromRanges();
      }
    });

    table.on("cellClick", (e, cell) => {
      if (state.flashExcelRow) clearJumpHighlights();
      const f = cell.getField();
      if (!f || !f.startsWith("c")) return;
      const colIdx = parseInt(f.slice(1), 10);
      const d = cell.getRow().getData();
      state.selectedExcelRow = d.excel_row;
      state.selectedMatIdx = d.mat_idx;
      state.selectedCol = colIdx;
      const refEl = document.getElementById("cellRef");
      if (refEl) refEl.textContent = `${colLetter(colIdx)}${d.excel_row}`;
      const formulaEl = document.getElementById("formulaInput");
      if (formulaEl && document.activeElement !== formulaEl) {
        formulaEl.value = d["c" + colIdx] || "";
      }
    });

    table.on("rangeChanged", () => {
      if (suppressCellEvents) return;
      updateSelectionBarFromRanges();
    });

    table.on("cellEdited", (cell) => {
      const f = cell.getField();
      if (!f || !f.startsWith("c")) return;
      const colIdx = parseInt(f.slice(1), 10);
      const d = cell.getRow().getData();
      queueCellSync(d.mat_idx, colIdx, cell.getValue());
    });

    table.on("clipboardPasted", (clipboardData, rowData, rows) => {
      if (!rows || !rows.length || !Array.isArray(rowData) || !rowData.length) return;
      rows.forEach((rObj, idx) => {
        const d = rObj.getData();
        const patch = rowData[idx % rowData.length] || {};
        Object.keys(patch).forEach(k => {
          if (k.startsWith("c")) {
            const colIdx = parseInt(k.slice(1), 10);
            queueCellSync(d.mat_idx, colIdx, patch[k]);
          }
        });
      });
    });

    table.on("dataSorted", (sorters) => {
      const btn = document.getElementById("btnResetSort");
      if (btn) btn.style.display = (sorters && sorters.length > 0) ? "inline-flex" : "none";
    });

    table.on("columnResized", (column) => {
      if (!column) return;
      const f = column.getField();
      const w = column.getWidth();
      if (f && w && state.activeSheet) {
        saveColumnWidth(state.activeSheet, f, w);
      }
    });
  } else {
    suppressCellEvents = true;
    try {
      table.clearSort();
      if (state.totalPages === 1 && !state.searchQuery) {
        table.clearFilter();
      }
      if (prevNumCols !== state.numCols || prevSheet !== state.activeSheet) {
        await table.setColumns(buildTabulatorColumns(state.numCols, res));
      }
      await table.replaceData(data);

      if (state.totalPages === 1 && state.searchQuery) {
        applyClientFilter(state.searchQuery);
      }

      const maxRow = data.length > 0 ? data[data.length - 1].excel_row : 1;
      const targetRow = Math.max(1, Math.min(savedRow, maxRow));
      const targetCol = Math.max(0, Math.min(savedCol, state.numCols - 1));

      state.selectedExcelRow = targetRow;
      state.selectedMatIdx = targetRow - 1;
      state.selectedCol = targetCol;

      if (targetHighlight) {
        await highlightAndScrollRow(targetHighlight, targetCol);
      } else {
        const rowComp = table.getRow(targetRow);
        if (rowComp) {
          const cellComp = rowComp.getCell("c" + targetCol) || rowComp.getCell("c0");
          if (cellComp) {
            table.getRanges().forEach(r => r.remove());
            table.addRange(cellComp, cellComp);
          }
          const refEl = document.getElementById("cellRef");
          if (refEl) refEl.textContent = `${colLetter(targetCol)}${targetRow}`;
          const formulaEl = document.getElementById("formulaInput");
          if (formulaEl && document.activeElement !== formulaEl) {
            formulaEl.value = rowComp.getData()["c" + targetCol] || "";
          }
        }
        if (table.rowManager && table.rowManager.element) {
          table.rowManager.element.scrollTop = savedScrollTop;
          table.rowManager.element.scrollLeft = savedScrollLeft;
        }
      }
    } finally {
      setTimeout(() => {
        suppressCellEvents = false;
      }, 80);
    }
  }
}

function resetSortOrder() {
  if (!table || !tableReady) return;
  table.clearSort();
  const rstBtn = document.getElementById("btnResetSort");
  if (rstBtn) rstBtn.style.display = "none";
  showToast("Ordem original da visualização restaurada.");
}

async function onFormulaKeyDown(ev) {
  if (ev.key === "Enter") {
    ev.preventDefault();
    const val = ev.target.value;
    if (table && tableReady) {
      const rowComp = table.getRow(state.selectedExcelRow);
      if (rowComp) {
        await rowComp.update({ ["c" + state.selectedCol]: val });
      }
    }
    queueCellSync(state.selectedMatIdx, state.selectedCol, val);
    showToast(`Célula ${colLetter(state.selectedCol)}${state.selectedExcelRow} atualizada.`);
  }
}

function applyClientFilter(rawQuery) {
  if (!table || !tableReady) return;
  const q = normStr(rawQuery);
  if (!q) {
    table.clearFilter();
    return;
  }
  table.setFilter((data) => {
    if (data.excel_row === 1) return true;
    if (String(data.excel_row) === q) return true;
    for (let c = 0; c < state.numCols; c++) {
      if (normStr(data["c" + c]).includes(q)) return true;
    }
    return false;
  });
}

function onSearchChange() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(async () => {
    const sb = document.getElementById("searchBox");
    state.searchQuery = sb ? sb.value : "";
    if (state.totalPages === 1 && table && tableReady) {
      applyClientFilter(state.searchQuery);
      return;
    }
    const res = await apiPost("/api/get_page", {
      sheet_name: state.activeSheet,
      page: 1,
      search_query: state.searchQuery
    });
    if (res.success) await applyPagePayload(res);
  }, 150);
}

async function addRowBelow() {
  await flushPendingUpdates();
  const targetAfter = state.selectedExcelRow || 1;
  const currentCol = state.selectedCol || 0;
  showBusy("Inserindo linha...");
  const res = await apiPost("/api/add_row", {
    sheet_name: state.activeSheet,
    after_row: targetAfter
  });
  hideBusy();
  if (res.success) {
    const sb = document.getElementById("searchBox");
    if (sb) sb.value = "";
    state.searchQuery = "";
    res.highlight_col = currentCol;
    await applyPagePayload(res);
    if (res.summary && typeof renderSummary === "function") renderSummary(res.summary);
    showToast(`Nova linha inserida abaixo da Linha ${targetAfter}.`);
  }
}

async function addColumnRight() {
  await flushPendingUpdates();
  const targetCol = state.selectedCol || 0;
  const currentRow = state.selectedExcelRow || 1;
  showBusy("Inserindo coluna...");
  const res = await apiPost("/api/add_column", {
    sheet_name: state.activeSheet,
    after_col: targetCol
  });
  hideBusy();
  if (res.success) {
    res.highlight_excel_row = currentRow;
    res.highlight_col = targetCol + 1;
    await applyPagePayload(res);
    if (res.summary && typeof renderSummary === "function") renderSummary(res.summary);
    showToast(`Nova coluna inserida à direita da Coluna ${colLetter(targetCol)}.`);
  }
}

async function deleteSelectedRow() {
  await flushPendingUpdates();
  const currentRow = state.selectedExcelRow;
  const currentCol = state.selectedCol;
  const rowSet = new Set();
  if (table && tableReady) {
    table.getRanges().forEach(rg => {
      rg.getRows().forEach(rw => {
        const er = rw.getData().excel_row;
        if (er > 1) rowSet.add(er);
      });
    });
  }
  if (rowSet.size === 0 && state.selectedExcelRow > 1) {
    rowSet.add(state.selectedExcelRow);
  }
  if (rowSet.size === 0) {
    showToast("Selecione uma ou mais linhas de dados (abaixo da linha 1) para excluir.");
    return;
  }

  const matIndices = Array.from(rowSet).map(r => r - 1);
  const res = await apiPost("/api/delete_row", {
    sheet_name: state.activeSheet,
    mat_idx: matIndices[0],
    mat_indices: matIndices,
    page: state.page,
    search_query: state.totalPages > 1 ? state.searchQuery : ""
  });
  if (res.success) {
    res.highlight_excel_row = Math.min(...rowSet);
    res.highlight_col = currentCol;
    await applyPagePayload(res);
    if (res.summary && typeof renderSummary === "function") renderSummary(res.summary);
    showToast(matIndices.length > 1 ? `${matIndices.length} linhas excluídas.` : "Linha excluída.");
  } else {
    const termoErr = matIndices.length > 1 ? "Não foi possível excluir as linhas." : "Não foi possível excluir a linha.";
    showToast(res.error || termoErr);
  }
}

async function handleUndo() {
  await flushPendingUpdates();
  showBusy("Desfazendo...");
  const res = await apiPost("/api/undo");
  hideBusy();
  if (res.success) {
    await applyPagePayload(res);
    if (res.summary && typeof renderSummary === "function") renderSummary(res.summary);
    showToast("Desfeito (Ctrl+Z)!");
  } else {
    showToast(res.error || "Nada para desfazer.");
  }
}

async function handleRedo() {
  await flushPendingUpdates();
  showBusy("Refazendo...");
  const res = await apiPost("/api/redo");
  hideBusy();
  if (res.success) {
    await applyPagePayload(res);
    if (res.summary && typeof renderSummary === "function") renderSummary(res.summary);
    showToast("Refeito (Ctrl+Y)!");
  } else {
    showToast(res.error || "Nada para refazer.");
  }
}

function clearSelectedRanges() {
  if (!table || !tableReady) return;
  const ranges = table.getRanges();
  if (!ranges || !ranges.length) return;
  table.blockRedraw();
  try {
    ranges.forEach(rg => {
      rg.getCells().flat().forEach(cell => {
        const f = cell.getField();
        if (f && f.startsWith("c")) {
          cell.setValue("");
        }
      });
    });
  } finally {
    table.restoreRedraw();
  }
}

// Atalhos Globais de Teclado (Delete/Backspace p/ limpar seleção, Ctrl+Z p/ Desfazer e Ctrl+Y / Ctrl+Shift+Z p/ Refazer)
window.addEventListener("keydown", (ev) => {
  const activeEl = document.activeElement;
  const isTextInput = activeEl && (
    activeEl.tagName === "INPUT" ||
    activeEl.tagName === "TEXTAREA"
  );
  if (isTextInput) return;

  const isCtrl = ev.ctrlKey || ev.metaKey;
  if (!isCtrl && !ev.altKey && (ev.key === "Delete" || ev.key === "Backspace")) {
    if (table && tableReady && table.getRanges().length > 0) {
      ev.preventDefault();
      clearSelectedRanges();
    }
    return;
  }

  if (!isCtrl) return;

  const key = ev.key.toLowerCase();
  if (key === "z") {
    ev.preventDefault();
    if (ev.shiftKey) {
      handleRedo();
    } else {
      handleUndo();
    }
  } else if (key === "y") {
    ev.preventDefault();
    handleRedo();
  }
});

/**
 * Módulo Principal da Aplicação: Inicialização, Abas, Arquivos e Otimização.
 * Desafio UniSoma 2026 — Aloca ABC
 */

function renderTabs() {
  const wrap = document.getElementById("sheetTabs");
  if (!wrap) return;
  wrap.innerHTML = "";
  state.sheetNames.forEach(name => {
    const div = document.createElement("div");
    div.className = "sheet-tab" + (name === state.activeSheet ? " active" : "");
    div.textContent = name;
    div.onclick = () => switchSheet(name);
    wrap.appendChild(div);
  });
}

function renderPager() {
  const box = document.getElementById("pagerBox");
  if (!box) return;
  if (state.totalPages <= 1) {
    const termoReg = state.totalRows === 1 ? "1 registro" : `${state.totalRows} registros`;
    box.innerHTML = `<span>${termoReg}</span>`;
    return;
  }
  box.innerHTML = `
    <span>${state.totalRows} registros • Pág. ${state.page}/${state.totalPages}</span>
    <button class="btn btn-sm" ${state.page <= 1 ? "disabled" : ""} onclick="changePage(${state.page - 1})">&#9664;</button>
    <button class="btn btn-sm" ${state.page >= state.totalPages ? "disabled" : ""} onclick="changePage(${state.page + 1})">&#9654;</button>
  `;
}

async function switchSheet(name) {
  await flushPendingUpdates();
  const sb = document.getElementById("searchBox");
  if (sb) sb.value = "";
  state.searchQuery = "";
  showBusy("Abrindo aba...");
  const res = await apiPost("/api/get_page", { sheet_name: name, page: 1, search_query: "" });
  hideBusy();
  if (res.success) await applyPagePayload(res);
}

async function changePage(p) {
  await flushPendingUpdates();
  showBusy("Carregando página...");
  const res = await apiPost("/api/get_page", {
    sheet_name: state.activeSheet,
    page: p,
    search_query: state.searchQuery
  });
  hideBusy();
  if (res.success) await applyPagePayload(res);
}

async function openExcel() {
  await flushPendingUpdates();
  const chkInt = document.getElementById("chkIntegral");
  const allowIntegral = chkInt ? chkInt.checked : false;
  showBusy("Selecionando planilha...");
  const res = await apiPost("/api/open_dialog", { allow_integral: allowIntegral });
  hideBusy();
  if (res.cancelled) return;
  if (res.success) {
    const sb = document.getElementById("searchBox");
    if (sb) sb.value = "";
    state.searchQuery = "";
    await applyPagePayload(res);
    if (res.summary) {
      renderSummary(res.summary);
    } else {
      resetSummaryCards();
    }
    if (res.column_errors && res.column_errors.length > 0) {
      if (typeof setSideTab === "function") setSideTab("report");
      showToast(res.column_errors[0].mensagem || "Atenção: coluna obrigatória ausente no cabeçalho.");
    } else {
      showToast(`Planilha '${res.filename}' carregada.`);
    }
  } else {
    showToast(res.error || "Erro ao abrir arquivo.");
  }
}

async function saveExcel(saveAs = false) {
  await flushPendingUpdates();
  showBusy("Salvando alterações no Excel...");
  const res = await apiPost("/api/save_excel", { save_as: saveAs });
  hideBusy();
  if (res.cancelled) return;
  if (res.success) {
    const ft = document.getElementById("fileTitle");
    if (ft) ft.textContent = res.filename;
    const fp = document.getElementById("filePath");
    if (fp) fp.textContent = res.filepath;
    updateDirtyIndicator(false);
    if (res.summary) renderSummary(res.summary);
    showToast(`Salvo com sucesso em ${res.filename}!`);
  } else {
    showToast(res.error || "Falha ao salvar Excel.");
  }
}

async function onOptionToggleChanged() {
  await flushPendingUpdates();
  const chkInt = document.getElementById("chkIntegral");
  const chkUna = document.getElementById("chkUnalloc");
  const allowIntegral = chkInt ? chkInt.checked : false;
  const allowUnallocated = chkUna ? chkUna.checked : false;
  const res = await apiPost("/api/set_options", {
    allow_integral: allowIntegral,
    allow_unallocated: allowUnallocated,
    sheet_name: state.activeSheet,
    page: state.page,
    search_query: state.searchQuery || ""
  });
  if (res && res.success) {
    await applyPagePayload(res);
    if (res.summary) {
      renderSummary(res.summary);
    }
    if (!allowIntegral) {
      showToast("Opção 'Aceitar Integral' desabilitada: alunos com disponibilidade integral verificados como erro impeditivo.");
    } else {
      showToast("Opção 'Aceitar Integral' habilitada: alunos integrais aceitos para distribuição.");
    }
  }
}

async function runOptimization() {
  await flushPendingUpdates();
  const chkInt = document.getElementById("chkIntegral");
  const chkUna = document.getElementById("chkUnalloc");
  const allowIntegral = chkInt ? chkInt.checked : false;
  const allowUnallocated = chkUna ? chkUna.checked : false;
  showBusy("Otimizando turmas matematicamente...");
  const res = await apiPost("/api/run_ensalamento", {
    allow_integral: allowIntegral,
    allow_unallocated: allowUnallocated
  });
  hideBusy();
  if (res.success) {
    const sb = document.getElementById("searchBox");
    if (sb) sb.value = "";
    state.searchQuery = "";
    await applyPagePayload(res);
    renderSummary(res.summary);
    if (res.summary && typeof renderDashboard === "function") renderDashboard(res.summary);
    if (typeof setSideTab === "function") setSideTab("report");
    showToast(
      res.summary.feasible
        ? `Ensalamento concluído em ${res.summary.tempo_ms} ms!`
        : "Atenção: verifique os impedimentos indicados no painel."
    );
  } else {
    if (res.summary) {
      renderSummary(res.summary);
      if (typeof setSideTab === "function") setSideTab("report");
    }
    showToast(res.error || "Erro na otimização.");
  }
}

async function exportStudentPdf() {
  await flushPendingUpdates();
  const chkUna = document.getElementById("chkUnalloc");
  const allowUnallocated = chkUna ? chkUna.checked : false;
  showBusy("Gerando PDF das turmas...");
  const res = await apiPost("/api/export_pdf_dialog", {
    allow_unallocated: allowUnallocated
  });
  hideBusy();
  if (res.cancelled) return;
  if (res.success) {
    showToast(`PDF das turmas salvo em: ${res.pdf_path}`);
  } else {
    showToast(res.error || "Erro ao gerar PDF.");
  }
}

function initResizer() {
  const resizer = document.getElementById("paneResizer");
  const sidePane = document.getElementById("sidePane");
  const workspace = document.querySelector(".workspace");
  if (!resizer || !sidePane || !workspace) return;

  let savedWidth = null;
  try {
    savedWidth = localStorage.getItem("unisoma_side_width");
  } catch (_) {}
  if (savedWidth) {
    const parsed = parseInt(savedWidth, 10);
    if (!isNaN(parsed) && parsed >= 360 && parsed <= 900) {
      sidePane.style.width = `${parsed}px`;
    }
  }

  let isDragging = false;
  let startX = 0;
  let startWidth = 0;

  resizer.addEventListener("mousedown", (e) => {
    isDragging = true;
    startX = e.clientX;
    startWidth = sidePane.getBoundingClientRect().width;
    resizer.classList.add("dragging");
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  });

  window.addEventListener("mousemove", (e) => {
    if (!isDragging) return;
    const delta = startX - e.clientX;
    const maxW = Math.max(360, workspace.clientWidth - 320);
    const newW = Math.min(Math.max(360, startWidth + delta), maxW);
    sidePane.style.width = `${newW}px`;
  });

  window.addEventListener("mouseup", () => {
    if (!isDragging) return;
    isDragging = false;
    resizer.classList.remove("dragging");
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
    try { localStorage.setItem("unisoma_side_width", parseInt(sidePane.style.width, 10)); } catch (_) {}
    if (table && tableReady) table.redraw();
  });

  resizer.addEventListener("dblclick", () => {
    sidePane.style.width = "520px";
    try { localStorage.setItem("unisoma_side_width", 520); } catch (_) {}
    if (table && tableReady) table.redraw();
    showToast("Proporção restaurada para o padrão (520px).");
  });
}

window.addEventListener("DOMContentLoaded", async () => {
  initResizer();
  const chkInt = document.getElementById("chkIntegral");
  const chkUna = document.getElementById("chkUnalloc");
  if (chkInt) chkInt.addEventListener("change", onOptionToggleChanged);
  if (chkUna) chkUna.addEventListener("change", onOptionToggleChanged);

  const res = await apiPost("/api/init", {
    allow_integral: chkInt ? chkInt.checked : false,
    allow_unallocated: chkUna ? chkUna.checked : false
  });
  if (res.success) {
    await applyPagePayload(res);
    if (res.summary) {
      renderSummary(res.summary);
      if (typeof renderDashboard === "function") renderDashboard(res.summary);
    }
  } else {
    const ft = document.getElementById("fileTitle");
    if (ft) ft.textContent = "Sem planilha aberta";
  }
  if (typeof checkTutorialFirstRun === "function") {
    checkTutorialFirstRun();
  }
});

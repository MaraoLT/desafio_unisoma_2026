/**
 * Módulo do Dashboard de Ensalamento, Lotação de Salas e Relatório de Distribuição.
 * Desafio UniSoma 2026 — Aloca ABC
 */

function setSideTab(which) {
  const isReport = which === "report";
  const isDashboard = which === "dashboard";

  const btnReport = document.getElementById("btnSideReport");
  const btnDash = document.getElementById("btnSideDashboard");
  const paneReport = document.getElementById("paneReport");
  const paneDash = document.getElementById("paneDashboard");

  if (btnReport) btnReport.classList.toggle("active", isReport);
  if (btnDash) btnDash.classList.toggle("active", isDashboard);

  if (paneReport) {
    paneReport.classList.toggle("active", isReport);
    paneReport.style.display = isReport ? "flex" : "none";
  }
  if (paneDash) {
    paneDash.classList.toggle("active", isDashboard);
    paneDash.style.display = isDashboard ? "flex" : "none";
  }
}

function createTurmaCardElement(t) {
  const cap = Math.max(0, Number(t.capacidade) || 0);
  const lot = Math.max(0, Number(t.lotacao) || 0);
  const masc = Math.max(0, Number(t.masculino) || 0);
  const fem = Math.max(0, Number(t.feminino) || 0);
  const livres = Math.max(0, cap - lot);
  const ocupPct = cap > 0 ? ((100.0 * lot) / cap).toFixed(1) : "0.0";

  const pctM = cap > 0 ? Math.min(100, (100.0 * masc) / cap) : 0;
  const pctF = cap > 0 ? Math.min(Math.max(0, 100 - pctM), (100.0 * fem) / cap) : 0;
  const pctVazio = Math.max(0, 100 - pctM - pctF);

  const isManha = (t.turno || "").toUpperCase().includes("MANH");
  const accentClass = isManha ? "turma-code-manha" : "turma-code-tarde";

  const card = document.createElement("div");
  card.className = "dash-turma-card";
  card.title = `Clique para filtrar os alunos da turma ${t.codigo} na planilha`;
  card.onclick = () => filterSheetByTurma(t.codigo);

  card.innerHTML = `
    <div class="dash-turma-top">
      <span class="dash-turma-code ${accentClass}">${t.codigo}</span>
      <span class="dash-turma-lot">Lotação: ${lot}/${cap} (${ocupPct}%) • ${livres} livres</span>
    </div>
    <div class="dash-gender-bar">
      <div class="dash-bar-seg-m" style="width: ${pctM.toFixed(2)}%;" title="Meninos (M): ${masc}"></div>
      <div class="dash-bar-seg-f" style="width: ${pctF.toFixed(2)}%;" title="Meninas (F): ${fem}"></div>
      <div class="dash-bar-seg-empty" style="width: ${pctVazio.toFixed(2)}%;" title="Vagas Vazias: ${livres}"></div>
    </div>
    <div class="dash-turma-legend">
      <span class="legend-m">■ Meninos (M): ${masc}</span>
      <span class="legend-f">■ Meninas (F): ${fem}</span>
      <span class="legend-empty">■ Vagas Vazias: ${livres}</span>
    </div>
  `;
  return card;
}

function createShiftRemovableWarnElement(shiftLabel, shiftTurmas) {
  if (!shiftTurmas || shiftTurmas.length === 0) return null;
  const nSalas = shiftTurmas.length;
  const capUnit = Math.max(0, Number(shiftTurmas[0].capacidade) || 0);
  if (capUnit <= 0) return null;
  const totAloc = shiftTurmas.reduce((acc, t) => acc + (Math.max(0, Number(t.lotacao) || 0)), 0);
  const minSalasNeeded = totAloc > 0 ? Math.ceil(totAloc / capUnit) : 0;
  const removiveis = Math.max(0, nSalas - minSalasNeeded);
  if (removiveis < 1) return null;

  const restantes = nSalas - removiveis;
  const vagasRestantes = restantes * capUnit;
  const warnDiv = document.createElement("div");
  warnDiv.className = "dash-shift-warn";
  const termo = removiveis === 1 ? "1 turma" : `${removiveis} turmas`;
  const termoRestantes = restantes === 1 ? "1 turma" : `${restantes} turmas`;
  const termoAlunos = totAloc === 1 ? "1 aluno cabe" : `${totAloc} alunos cabem`;
  warnDiv.innerHTML =
    `<b>⚠ Aviso:</b> É possível remover <b>${termo}</b> no turno da <b>${shiftLabel}</b> ` +
    `(${termoAlunos} em ${termoRestantes} de ${capUnit} vagas = ${vagasRestantes} vagas).`;
  return warnDiv;
}

function renderDashboard(s) {
  const container = document.getElementById("dashTurmasContainer");
  if (!container || !s || !s.stats_turnos) {
    return;
  }

  const stM = s.stats_turnos["MANHÃ"] || { salas: 0, capacidade_total: 0, alocados: 0, masculino: 0, feminino: 0, ocupacao_pct: 0 };
  const stT = s.stats_turnos["TARDE"] || { salas: 0, capacidade_total: 0, alocados: 0, masculino: 0, feminino: 0, ocupacao_pct: 0 };

  const capTotal = (stM.capacidade_total || 0) + (stT.capacidade_total || 0);
  const alocTotal = (stM.alocados || 0) + (stT.alocados || 0);
  const livresTotal = Math.max(0, capTotal - alocTotal);
  const ocupGlobal = capTotal > 0 ? ((100.0 * alocTotal) / capTotal).toFixed(1) : "0.0";

  const livresM = Math.max(0, (stM.capacidade_total || 0) - (stM.alocados || 0));
  const livresT = Math.max(0, (stT.capacidade_total || 0) - (stT.alocados || 0));

  const elTotalVal = document.getElementById("dashKpiTotalVal");
  const elTotalSub = document.getElementById("dashKpiTotalSub");
  const elManhaVal = document.getElementById("dashKpiManhaVal");
  const elManhaSub = document.getElementById("dashKpiManhaSub");
  const elTardeVal = document.getElementById("dashKpiTardeVal");
  const elTardeSub = document.getElementById("dashKpiTardeSub");

  if (elTotalVal) elTotalVal.textContent = `${alocTotal} / ${capTotal} (${ocupGlobal}%)`;
  if (elTotalSub) elTotalSub.textContent = `${s.total_salas || 0} turmas ativas • ${livresTotal} vagas livres`;

  if (elManhaVal) elManhaVal.textContent = `${stM.alocados}/${stM.capacidade_total} alunos (${stM.masculino}M / ${stM.feminino}F)`;
  const termoTurmasM = (stM.salas || 0) === 1 ? "1 turma" : `${stM.salas || 0} turmas`;
  const termoTurmasT = (stT.salas || 0) === 1 ? "1 turma" : `${stT.salas || 0} turmas`;
  if (elManhaSub) elManhaSub.textContent = `${termoTurmasM} • Ocupação: ${Number(stM.ocupacao_pct || 0).toFixed(1)}% (${livresM} livres)`;

  if (elTardeVal) elTardeVal.textContent = `${stT.alocados}/${stT.capacidade_total} alunos (${stT.masculino}M / ${stT.feminino}F)`;
  if (elTardeSub) elTardeSub.textContent = `${termoTurmasT} • Ocupação: ${Number(stT.ocupacao_pct || 0).toFixed(1)}% (${livresT} livres)`;

  const turmas = s.turmas || [];
  if (!turmas.length) {
    container.innerHTML = `
      <div class="dash-empty-state">
        Clique em <b>Organizar Turmas</b> na barra superior para visualizar os cartões de lotação e as barras de distribuição de meninos, meninas e vagas vazias por sala.
      </div>
    `;
    return;
  }

  const turmasManha = turmas.filter(t => (t.turno || "").toUpperCase().includes("MANH"));
  const turmasTarde = turmas.filter(t => !(t.turno || "").toUpperCase().includes("MANH"));

  container.innerHTML = "";
  const grid = document.createElement("div");
  grid.className = "dash-columns-grid";

  // Coluna Manhã
  const colM = document.createElement("div");
  colM.className = "dash-shift-col";
  const hdrM = document.createElement("div");
  hdrM.className = "dash-col-header header-manha";
  const termoSalasM = turmasManha.length === 1 ? "1 sala" : `${turmasManha.length} salas`;
  hdrM.textContent = `Turmas da Manhã (${termoSalasM})`;
  colM.appendChild(hdrM);

  const warnM = createShiftRemovableWarnElement("Manhã", turmasManha);
  if (warnM) colM.appendChild(warnM);

  if (turmasManha.length === 0) {
    const emptyM = document.createElement("div");
    emptyM.className = "dash-col-empty";
    emptyM.textContent = "Nenhuma turma configurada para a Manhã.";
    colM.appendChild(emptyM);
  } else {
    turmasManha.forEach(t => colM.appendChild(createTurmaCardElement(t)));
  }

  // Coluna Tarde
  const colT = document.createElement("div");
  colT.className = "dash-shift-col";
  const hdrT = document.createElement("div");
  hdrT.className = "dash-col-header header-tarde";
  const termoSalasT = turmasTarde.length === 1 ? "1 sala" : `${turmasTarde.length} salas`;
  hdrT.textContent = `Turmas da Tarde (${termoSalasT})`;
  colT.appendChild(hdrT);

  const warnT = createShiftRemovableWarnElement("Tarde", turmasTarde);
  if (warnT) colT.appendChild(warnT);

  if (turmasTarde.length === 0) {
    const emptyT = document.createElement("div");
    emptyT.className = "dash-col-empty";
    emptyT.textContent = "Nenhuma turma configurada para a Tarde.";
    colT.appendChild(emptyT);
  } else {
    turmasTarde.forEach(t => colT.appendChild(createTurmaCardElement(t)));
  }

  grid.appendChild(colM);
  grid.appendChild(colT);
  container.appendChild(grid);
}

async function filterSheetByTurma(turmaCodigo) {
  if (!state.sheetNames.includes("Ensalamento")) return;
  await flushPendingUpdates();
  const sb = document.getElementById("searchBox");
  if (sb) sb.value = turmaCodigo;
  state.searchQuery = turmaCodigo;

  if (state.activeSheet === "Ensalamento" && state.totalPages === 1 && table && tableReady) {
    applyClientFilter(turmaCodigo);
    showToast(`Exibindo alunos alocados em '${turmaCodigo}'.`);
    return;
  }

  showBusy(`Filtrando ${turmaCodigo}...`);
  const res = await apiPost("/api/get_page", {
    sheet_name: "Ensalamento",
    page: 1,
    search_query: ""
  });
  hideBusy();
  if (res.success) {
    state.searchQuery = turmaCodigo;
    await applyPagePayload(res);
    showToast(`Exibindo alunos alocados em '${turmaCodigo}'.`);
  }
}

async function exportDashboardReport() {
  await flushPendingUpdates();
  showBusy("Gerando relatório de distribuição das turmas...");
  const res = await apiPost("/api/export_dashboard_report_dialog");
  hideBusy();
  if (res.cancelled) return;
  if (res.success) {
    showToast(`Relatório de distribuição salvo em: ${res.pdf_path}`);
  } else {
    showToast(res.error || "Erro ao gerar relatório de distribuição.");
  }
}

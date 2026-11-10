/**
 * Módulo de Inconsistências, Diagnóstico e Ações Rápidas de Correção.
 * Desafio UniSoma 2026 — Aloca ABC
 */

const duplicateCycleIndices = {};

function resetSummaryCards() {
  const kpiAloc = document.getElementById("kpiAloc");
  if (kpiAloc) kpiAloc.textContent = "—";
  const kpiSalas = document.getElementById("kpiSalas");
  if (kpiSalas) kpiSalas.textContent = "—";
  const kpiEspera = document.getElementById("kpiEspera");
  if (kpiEspera) kpiEspera.textContent = "—";
  const kpiErros = document.getElementById("kpiErros");
  if (kpiErros) kpiErros.textContent = "—";
  const solverBadge = document.getElementById("solverBadge");
  if (solverBadge) solverBadge.textContent = "";
  const shiftsBox = document.getElementById("shiftsBox");
  if (shiftsBox) shiftsBox.innerHTML = "Pré-visualização da capacidade por período.";
  const issuesBox = document.getElementById("issuesBox");
  if (issuesBox) issuesBox.innerHTML = "<span style='font-size:12px; color:#64748B;'>Nenhum erro verificado ainda.</span>";
}

function renderSummary(s) {
  if (!s) return;
  const kpiAloc = document.getElementById("kpiAloc");
  if (kpiAloc) kpiAloc.textContent = `${s.total_alocados}/${s.total_validos}`;
  const kpiSalas = document.getElementById("kpiSalas");
  if (kpiSalas) kpiSalas.textContent = String(s.total_salas);
  const kpiEspera = document.getElementById("kpiEspera");
  if (kpiEspera) kpiEspera.textContent = String(s.total_espera);

  const errEl = document.getElementById("kpiErros");
  if (errEl) {
    errEl.textContent = String(s.incons_counts.total);
    errEl.className = "kpi-num " + (s.incons_counts.impeditivas > 0 ? "danger" : (s.incons_counts.total > 0 ? "warn" : "green"));
  }

  const badge = document.getElementById("solverBadge");
  if (badge) {
    if (s.tempo_ms > 0) {
      badge.textContent = s.feasible ? `Ótimo (${s.tempo_ms} ms)` : "Requer Correção";
      badge.style.color = s.feasible ? "#107C41" : "#DC2626";
    } else {
      badge.textContent = s.incons_counts.impeditivas === 0 ? "Cadastro Válido" : "Erros Detectados";
      badge.style.color = s.incons_counts.impeditivas === 0 ? "#107C41" : "#DC2626";
    }
  }

  // Turnos
  const sb = document.getElementById("shiftsBox");
  if (sb) {
    sb.innerHTML = "";
    ["MANHÃ", "TARDE"].forEach(tk => {
      const st = s.stats_turnos[tk];
      if (!st) return;
      const div = document.createElement("div");
      div.className = "shift-row";
      div.innerHTML = `
        <div>
          <b style="color:#0F172A;">${tk}</b>
          <div style="font-size:11px; color:#64748B;">${st.salas} salas • ${st.masculino} M / ${st.feminino} F</div>
        </div>
        <div style="text-align:right;">
          <b style="color:#0F172A;">${st.alocados} / ${st.capacidade_total}</b>
          <div style="font-size:11px; color:#107C41;">${st.ocupacao_pct}% ocup.</div>
        </div>
      `;
      sb.appendChild(div);
    });
  }

  // Atualiza também a aba Dashboard do Ensalamento
  if (typeof renderDashboard === "function") {
    renderDashboard(s);
  }

  // Alertas e Erros Clicáveis
  const ib = document.getElementById("issuesBox");
  if (!ib) return;
  ib.innerHTML = "";
  if (!s.inconsistencias || s.inconsistencias.length === 0) {
    ib.innerHTML = "<span style='font-size:12px; color:#107C41; font-weight:500;'>Nenhum erro ou inconsistência encontrado!</span>";
  } else {
    const hasSanitize = s.inconsistencias.some(i => i.can_review && i.review_type === "sanitize");
    if (hasSanitize) {
      const topBar = document.createElement("div");
      topBar.className = "issue-actions-bar";
      topBar.style.marginBottom = "8px";
      const btnAll = document.createElement("button");
      btnAll.className = "btn-action-fix btn-action-accept";
      btnAll.innerHTML = `<svg class="ui-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> <span>Aplicar Todas as Correções</span>`;
      btnAll.title = "Aplica todas as correções automáticas de grafia e padronização";
      btnAll.onclick = () => resolveIssue("accept_sanitize", "sanitize", []);
      topBar.appendChild(btnAll);
      ib.appendChild(topBar);
    }

    const sortedIncs = [...s.inconsistencias].sort((a, b) => {
      const aImp = a.severidade === "IMPEDITIVA" ? 0 : 1;
      const bImp = b.severidade === "IMPEDITIVA" ? 0 : 1;
      if (aImp !== bImp) return aImp - bImp;

      const aRow = (a.linhas && a.linhas.length > 0) ? a.linhas[0] : (a.linha || (a.target_row || 9999999));
      const bRow = (b.linhas && b.linhas.length > 0) ? b.linhas[0] : (b.linha || (b.target_row || 9999999));
      const aHasRow = (aRow && aRow !== 9999999) ? 0 : 1;
      const bHasRow = (bRow && bRow !== 9999999) ? 0 : 1;
      if (aHasRow !== bHasRow) return aHasRow - bHasRow;
      if (aRow !== bRow) return aRow - bRow;

      const aTie = a.severidade === "ALERTA" ? 0 : 1;
      const bTie = b.severidade === "ALERTA" ? 0 : 1;
      return aTie - bTie;
    });

    sortedIncs.forEach((inc) => {
      const card = document.createElement("div");
      card.className = `issue-item ${inc.severidade}`;

      const rowsList = inc.linhas && inc.linhas.length > 0 ? inc.linhas : (inc.linha ? [inc.linha] : []);
      const isMulti = rowsList.length > 1;

      const headDiv = document.createElement("div");
      headDiv.className = "issue-header-row";

      const tagSpan = document.createElement("span");
      tagSpan.className = "issue-badge-tag";
      tagSpan.textContent = `[${inc.severidade}] ${inc.categoria || "Cadastro"}`;
      headDiv.appendChild(tagSpan);

      if (isMulti) {
        const cyclePill = document.createElement("span");
        cyclePill.className = "issue-cycle-pill";
        cyclePill.title = "Clique para alternar entre as ocorrências duplicadas na planilha";
        cyclePill.innerHTML = `${rowsList.length} ocorrências <svg class="ui-icon" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>`;
        cyclePill.onclick = (ev) => {
          ev.stopPropagation();
          cycleDuplicateRow(inc.nome, rowsList);
        };
        headDiv.appendChild(cyclePill);
      } else if (inc.linha) {
        const singlePill = document.createElement("span");
        singlePill.className = "issue-cycle-pill";
        singlePill.textContent = `Linha ${inc.linha}`;
        headDiv.appendChild(singlePill);
      }

      const msgDiv = document.createElement("div");
      msgDiv.className = "issue-msg-text";
      msgDiv.innerHTML = `<b>${inc.nome}</b>: ${inc.mensagem}`;

      card.onclick = () => {
        if (inc.target_sheet === "Turmas" || inc.categoria === "Capacidade Insuficiente") {
          jumpToSheetAndRow("Turmas", inc.target_row || 2);
        } else if (inc.target_sheet && inc.categoria === "Coluna Obrigatória Ausente") {
          jumpToSheetAndRow(inc.target_sheet, inc.target_row || 1);
        } else if (isMulti) {
          cycleDuplicateRow(inc.nome, rowsList);
        } else if (inc.linha) {
          jumpToStudentRow(inc.linha);
        }
      };

      card.appendChild(headDiv);
      card.appendChild(msgDiv);

      if (inc.can_review && inc.review_type === "sanitize") {
        const bar = document.createElement("div");
        bar.className = "issue-actions-bar";
        bar.onclick = (e) => e.stopPropagation();

        const btnAccept = document.createElement("button");
        btnAccept.className = "btn-action-fix btn-action-accept";
        btnAccept.innerHTML = `<svg class="ui-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> <span>Aplicar Correção</span>`;
        btnAccept.title = "Aplica na planilha a grafia padronizada (ex.: acentos, espaços extras, turno)";
        btnAccept.onclick = () => resolveIssue("accept_sanitize", "sanitize", rowsList);
        bar.appendChild(btnAccept);

        card.appendChild(bar);
      } else if (inc.can_review && inc.review_type === "fix_header") {
        const bar = document.createElement("div");
        bar.className = "issue-actions-bar";
        bar.onclick = (e) => e.stopPropagation();

        const btnFixHdr = document.createElement("button");
        btnFixHdr.className = "btn-action-fix btn-action-accept";
        btnFixHdr.innerHTML = "✓ Corrigir Cabeçalho";
        btnFixHdr.title = "Restaura os nomes oficiais das colunas na Linha 1";
        btnFixHdr.onclick = () => resolveIssue("fix_header", "header", [1], { sheet: inc.target_sheet || "Alunos" });
        bar.appendChild(btnFixHdr);

        card.appendChild(bar);
      }

      ib.appendChild(card);
    });
  }
}

async function cycleDuplicateRow(studentName, rowsList) {
  if (!rowsList || rowsList.length === 0) return;
  const cur = duplicateCycleIndices[studentName] || 0;
  const targetRow = rowsList[cur % rowsList.length];
  duplicateCycleIndices[studentName] = (cur + 1) % rowsList.length;
  const stepMsg = `Ocorrência ${(cur % rowsList.length) + 1} de ${rowsList.length} (Linha ${targetRow})`;
  showToast(`Alternando '${studentName}': ${stepMsg}`);
  await jumpToStudentRow(targetRow);
}

async function resolveIssue(action, issueType, targetRows, extra = {}) {
  await flushPendingUpdates();
  showBusy("Processando revisão cadastral...");
  const res = await apiPost("/api/resolve_issue", {
    action: action,
    issue_type: issueType,
    target_rows: targetRows,
    extra: extra
  });
  hideBusy();
  if (res.success) {
    await applyPagePayload(res);
    if (res.summary) renderSummary(res.summary);
    showToast("Problema revisado e atualizado na planilha!");
  } else {
    showToast(res.error || "Não foi possível aplicar a ação.");
  }
}

async function jumpToSheetAndRow(sheetName, excelRow) {
  await flushPendingUpdates();
  const sb = document.getElementById("searchBox");
  if (sb) sb.value = "";
  state.searchQuery = "";

  if (state.activeSheet === sheetName && state.totalPages === 1 && table && tableReady) {
    table.clearFilter();
    await highlightAndScrollRow(excelRow);
    showToast(`Navegado para a Linha ${excelRow} da aba '${sheetName}'.`);
    return;
  }

  showBusy(`Abrindo aba ${sheetName}...`);
  const res = await apiPost("/api/jump_row", { sheet_name: sheetName, excel_row: excelRow });
  hideBusy();
  if (res.success) {
    await applyPagePayload(res);
    showToast(`Navegado para a aba '${sheetName}' (Linha ${excelRow}) para ajustar a capacidade.`);
  }
}

async function jumpToStudentRow(excelRow) {
  await flushPendingUpdates();
  const sb = document.getElementById("searchBox");
  if (sb) sb.value = "";
  state.searchQuery = "";

  if (state.activeSheet === "Alunos" && state.totalPages === 1 && table && tableReady) {
    table.clearFilter();
    await highlightAndScrollRow(excelRow);
    showToast(`Navegado para a Linha ${excelRow} da aba Alunos.`);
    return;
  }

  const res = await apiPost("/api/jump_row", { sheet_name: "Alunos", excel_row: excelRow });
  if (res.success) {
    await applyPagePayload(res);
    showToast(`Navegado para a Linha ${excelRow} da aba Alunos.`);
  }
}

/**
 * Módulo de Tutorial Interativo (Passo a Passo) e Boas-Vindas.
 * Desafio UniSoma 2026 — Aloca ABC
 */

const tutorialSteps = [
  {
    targetId: "brandBox",
    title: "Boas-vindas ao Aloca ABC!",
    text: "O Aloca ABC organiza e distribui alunos em turmas escolares com otimização matemática avançada e equilíbrio pedagógico.",
    placement: "bottom"
  },
  {
    targetId: "btnOpenSheet",
    title: "1. Abrir Planilha",
    text: "Carregue sua planilha Excel (.xlsx) contendo as abas de Alunos e Turmas para iniciar a alocação.",
    placement: "bottom"
  },
  {
    targetId: "btnSaveExcel",
    title: "2. Salvar Alterações",
    text: "Salve a planilha atualizada com os resultados do ensalamento, notas e correções diretamente em arquivo Excel.",
    placement: "bottom"
  },
  {
    targetId: "optToggles",
    title: "3. Opções Extras",
    text: "Configure opções de flexibilização: aceite alunos integrais em turnos parciais ou autorize lista de espera se as vagas forem insuficientes.",
    placement: "bottom"
  },
  {
    targetId: "btnRunOptimization",
    title: "4. Organizar Turmas",
    text: "Clique aqui para executar o algoritmo matemático de otimização (MILP) que distribui os alunos garantindo equilíbrio perfeito.",
    placement: "bottom"
  },
  {
    targetId: "sidePane",
    title: "5. Relatórios e Dashboard",
    text: "Acompanhe aqui o relatório de inconsistências cadastrais e o dashboard visual com gráficos de ocupação e proporção de gênero por turma.",
    placement: "left"
  },
  {
    targetId: "btnTutorial",
    title: "6. Acesso ao Tutorial",
    text: "Você pode rever este passo a passo interativo a qualquer momento clicando no botão 'Tutorial' na barra superior.",
    placement: "bottom"
  }
];

let currentTutorialStep = 0;
let tutorialActive = false;

function startTutorial(isFirstRun = false) {
  if (isFirstRun) {
    showTutorialWelcomeModal();
  } else {
    startTutorialSteps();
  }
}

function showTutorialWelcomeModal() {
  const modal = document.getElementById("tutorialWelcomeModal");
  const backdrop = document.getElementById("tutorialBackdrop");
  if (modal) modal.classList.add("active");
  if (backdrop) backdrop.classList.add("active");
}

function hideTutorialWelcomeModal() {
  const modal = document.getElementById("tutorialWelcomeModal");
  if (modal) modal.classList.remove("active");
}

function startTutorialSteps() {
  hideTutorialWelcomeModal();
  tutorialActive = true;
  currentTutorialStep = 0;
  const backdrop = document.getElementById("tutorialBackdrop");
  if (backdrop) backdrop.classList.add("active");
  showTutorialStep(0);
}

function showTutorialStep(index) {
  if (index < 0 || index >= tutorialSteps.length) return;
  currentTutorialStep = index;
  const step = tutorialSteps[index];

  // Remove destaque anterior
  document.querySelectorAll(".tutorial-highlight").forEach(el => el.classList.remove("tutorial-highlight"));

  const targetEl = document.getElementById(step.targetId);
  const card = document.getElementById("tutorialCard");
  const spotlight = document.getElementById("tutorialSpotlight");
  const arrow = document.getElementById("tutorialArrow");
  if (!card) return;

  if (targetEl) {
    targetEl.classList.add("tutorial-highlight");
    if (spotlight) {
      const rect = targetEl.getBoundingClientRect();
      const pad = 6;
      spotlight.style.top = `${Math.max(0, rect.top - pad)}px`;
      spotlight.style.left = `${Math.max(0, rect.left - pad)}px`;
      spotlight.style.width = `${rect.width + pad * 2}px`;
      spotlight.style.height = `${rect.height + pad * 2}px`;
      spotlight.classList.add("active");
    }
  } else if (spotlight) {
    spotlight.classList.remove("active");
  }

  // Preenche textos e contador
  const countEl = document.getElementById("tutorialStepCount");
  const titleEl = document.getElementById("tutorialTitle");
  const textEl = document.getElementById("tutorialText");
  if (countEl) countEl.textContent = `Passo ${index + 1} de ${tutorialSteps.length}`;
  if (titleEl) titleEl.textContent = step.title;
  if (textEl) textEl.textContent = step.text;

  // Botões de navegação
  const prevBtn = document.getElementById("btnTutorialPrev");
  const nextBtn = document.getElementById("btnTutorialNext");
  const finishBtn = document.getElementById("btnTutorialFinish");

  if (prevBtn) prevBtn.style.display = index === 0 ? "none" : "inline-block";
  if (index === tutorialSteps.length - 1) {
    if (nextBtn) nextBtn.style.display = "none";
    if (finishBtn) finishBtn.style.display = "inline-block";
  } else {
    if (nextBtn) nextBtn.style.display = "inline-block";
    if (finishBtn) finishBtn.style.display = "none";
  }

  card.classList.add("active");
  positionTutorialCard(targetEl, step.placement);
}

function positionTutorialCard(targetEl, placement) {
  const card = document.getElementById("tutorialCard");
  const arrow = document.getElementById("tutorialArrow");
  if (!card) return;

  const cardW = 340;
  const cardH = card.offsetHeight || 190;
  if (arrow) arrow.className = "tutorial-arrow";

  if (!targetEl) {
    card.style.top = "50%";
    card.style.left = "50%";
    card.style.transform = "translate(-50%, -50%)";
    return;
  }
  card.style.transform = "none";

  const rect = targetEl.getBoundingClientRect();
  const margin = 12;

  if (placement === "left" && rect.left - cardW - margin > 10) {
    card.style.left = `${Math.max(16, rect.left - cardW - margin)}px`;
    card.style.top = `${Math.min(Math.max(16, rect.top + 20), window.innerHeight - cardH - 16)}px`;
    if (arrow) {
      arrow.classList.add("arrow-right");
      arrow.style.top = "24px";
      arrow.style.left = "auto";
    }
  } else {
    // Padrão: bottom
    let top = rect.bottom + margin;
    if (top + cardH > window.innerHeight - 10) {
      top = Math.max(10, rect.top - cardH - margin);
      if (arrow) arrow.classList.add("arrow-bottom");
    } else {
      if (arrow) arrow.classList.add("arrow-top");
    }
    let left = rect.left + (rect.width / 2) - (cardW / 2);
    left = Math.max(16, Math.min(left, window.innerWidth - cardW - 16));
    card.style.top = `${top}px`;
    card.style.left = `${left}px`;
    if (arrow) {
      arrow.style.top = "";
      arrow.style.left = `${Math.min(Math.max(16, rect.left + rect.width / 2 - left - 8), cardW - 24)}px`;
    }
  }
}

function nextTutorialStep() {
  if (currentTutorialStep < tutorialSteps.length - 1) {
    showTutorialStep(currentTutorialStep + 1);
  }
}

function prevTutorialStep() {
  if (currentTutorialStep > 0) {
    showTutorialStep(currentTutorialStep - 1);
  }
}

async function skipTutorial() {
  await markTutorialSeen();
  closeTutorial();
}

async function finishTutorial() {
  await markTutorialSeen();
  closeTutorial();
  showToast("Tutorial concluído! Acesse a qualquer momento pelo botão Tutorial.");
}

function closeTutorial() {
  tutorialActive = false;
  document.querySelectorAll(".tutorial-highlight").forEach(el => el.classList.remove("tutorial-highlight"));
  const backdrop = document.getElementById("tutorialBackdrop");
  const spotlight = document.getElementById("tutorialSpotlight");
  const card = document.getElementById("tutorialCard");
  const welcome = document.getElementById("tutorialWelcomeModal");
  if (backdrop) backdrop.classList.remove("active");
  if (spotlight) spotlight.classList.remove("active");
  if (card) card.classList.remove("active");
  if (welcome) welcome.classList.remove("active");
}

async function markTutorialSeen() {
  try {
    localStorage.setItem("unisoma_tutorial_seen", "true");
  } catch (_) {}
  try {
    await apiPost("/api/tutorial_status", { seen: true });
  } catch (_) {}
}

async function checkTutorialFirstRun() {
  let seen = false;
  try {
    if (localStorage.getItem("unisoma_tutorial_seen") === "true") {
      seen = true;
    }
  } catch (_) {}

  if (!seen) {
    try {
      const res = await apiPost("/api/tutorial_status", {});
      if (res && res.seen) {
        seen = true;
        try { localStorage.setItem("unisoma_tutorial_seen", "true"); } catch (_) {}
      }
    } catch (_) {}
  }

  if (!seen) {
    startTutorial(true);
  }
}

window.addEventListener("resize", () => {
  if (tutorialActive) {
    showTutorialStep(currentTutorialStep);
  }
});

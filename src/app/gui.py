"""Interface gráfica principal (CustomTkinter) — Desafio UniSoma 2026 (ABC Aprendiz).

Funcionalidades implementadas:
- Identidade visual oficial da ONG ABC Aprendiz (https://www.abcaprendiz.org.br/) + Logo com CTkImage (HighDPI scaling).
- Barra lateral esquerda contendo todos os controles (Seleção de Planilha, Modelo, Iniciar Ensalamento,
  Abrir no Excel e Ajuste Rápido de Vagas e Turmas), liberando toda a altura da tela para as abas.
- Visualização rica organizada em 4 abas:
    1. Inconsistências & Validação (com contadores por severidade e filtro rápido)
    2. Dashboard do Ensalamento (duas colunas: Manhã à esquerda e Tarde à direita, barra de
       proporção Azul para Masculino e Vermelho para Feminino, sem exibir Diferença |M - F|)
    3. Consulta de Turmas e Alunos (busca por nome, filtro por turma/gênero e ordenação
       Alfabética A-Z ou pela Ordem de Entrada do Excel)
    4. Logs do Sistema (histórico técnico completo e relatório diagnóstico)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import platform
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import traceback
from typing import Any, Callable, Optional

import customtkinter as ctk
import openpyxl

try:
    from PIL import Image, ImageChops
except ImportError:
    Image = None  # type: ignore[assignment]
    ImageChops = None  # type: ignore[assignment]

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models.solver import SolverParameters, SolverResult, solve_ensalamento
from src.models.solver_1step import solve_ensalamento_1step
from src.pos_process import PostProcessArtifacts, pos_process
from src.pre_process import (
    GENERO_F,
    GENERO_M,
    TURNO_MANHA,
    TURNO_TARDE,
    ProcessedInstance,
    Student,
    TurmaSpec,
    pre_process,
)
from src.read_instance import normalize_token, read_instance

# =============================================================================
# PALETA DE CORES OFICIAL — ONG ABC APRENDIZ (https://www.abcaprendiz.org.br/)
# =============================================================================
ABC_NAVY = "#2A469A"          # Azul Marinho Institucional
ABC_NAVY_DARK = "#1E3373"     # Hover do Azul Marinho
ABC_CYAN = "#0E76BC"          # Azul Ciano Intermediário
ABC_CYAN_DARK = "#0A5A91"     # Hover do Azul Ciano
ABC_TEAL = "#3DBD9D"          # Verde Água / Turquesa
ABC_TEAL_DARK = "#2F9587"     # Turquesa Escuro (Hover / Texto forte)
ABC_LIME = "#9CCD58"          # Verde Claro / Limão
ABC_LIME_DARK = "#6E9934"     # Verde Limão Escuro para texto em fundo claro

ABC_BG = "#F2F5FA"            # Fundo geral claro
ABC_CARD = "#FFFFFF"          # Fundo de cartões
ABC_BORDER = "#D8E1EE"        # Borda sutil de cartões
ABC_TEXT = "#1E293B"          # Texto primário escuro
ABC_MUTED = "#5A6A85"         # Texto secundário

COLOR_MASC_BLUE = "#0E76BC"   # Azul para número de alunos Masculinos (M)
COLOR_FEM_RED = "#E11D48"     # Vermelho para número de alunas Femininas (F)
COLOR_VAZIO_GRAY = "#CBD5E1"  # Cinza para espaços vazios na barra da sala
COLOR_VAZIO_TEXT = "#64748B"  # Cinza escuro para legenda de espaços vazios

COLOR_IMPEDITIVA = "#DC2626"  # Coral/Vermelho para inconsistência impeditiva
COLOR_ALERTA = "#D97706"      # Âmbar para alerta de duplicidade
COLOR_TRATADA = "#2F9587"     # Turquesa para padronização tratada

MODEL_1STEP_LABEL = "Abordagem 1 — Passagem Única (1-Step)"
MODEL_2STEP_LABEL = "Abordagem 2 — Lexicográfica (2-Step)"

MODEL_SOLVERS: dict[str, Callable[[ProcessedInstance, Optional[SolverParameters]], SolverResult]] = {
    MODEL_1STEP_LABEL: solve_ensalamento_1step,
    MODEL_2STEP_LABEL: solve_ensalamento,
}

SORT_EXCEL_LABEL = "Ordem da Planilha (Excel)"
SORT_ALPHA_LABEL = "Ordem Alfabética (A-Z)"


@dataclass
class GuiPipelineOutcome:
    """Resultado consolidado de uma execução disparada pela interface."""

    processed: ProcessedInstance
    solver_result: SolverResult
    artifacts: PostProcessArtifacts
    validation_log: str


def get_asset_path(relative_name: str) -> Path:
    """Localiza arquivo de asset (ex.: logo) tanto em modo script quanto no .exe PyInstaller."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundled = Path(getattr(sys, "_MEIPASS")) / "src" / "app" / "assets" / relative_name
        if bundled.exists():
            return bundled
        bundled_flat = Path(getattr(sys, "_MEIPASS")) / "assets" / relative_name
        if bundled_flat.exists():
            return bundled_flat
    return Path(__file__).resolve().parent / "assets" / relative_name


def get_reports_dir(input_excel_path: Path) -> Path:
    """Determina o diretório onde salvar o relatório diagnóstico .txt."""
    if getattr(sys, "frozen", False):
        return input_excel_path.resolve().parent / "reports"
    return PROJECT_ROOT / "reports"


def open_file_in_system(filepath: str | Path) -> None:
    """Abre um arquivo (ex.: planilha .xlsx) no programa padrão do sistema operacional."""
    path = Path(filepath).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")

    sys_name = platform.system()
    if sys_name == "Windows":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys_name == "Darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def update_turmas_in_excel(
    filepath: str | Path,
    turmas_manha: int,
    vagas_manha: int,
    turmas_tarde: int,
    vagas_tarde: int,
) -> None:
    """Atualiza os parâmetros de quantidade de turmas e vagas na aba 'Turmas' do Excel."""
    if any(v < 0 for v in (turmas_manha, vagas_manha, turmas_tarde, vagas_tarde)):
        raise ValueError("Os valores de turmas e vagas devem ser inteiros não-negativos.")

    path = Path(filepath).resolve()
    raw = read_instance(path)

    wb = openpyxl.load_workbook(path)
    try:
        ws = wb[raw.turmas_sheet_name]
        updated_keys: set[str] = set()

        for r_idx in range(1, ws.max_row + 1):
            raw_key = ws.cell(row=r_idx, column=1).value
            if raw_key is None or str(raw_key).strip() == "":
                continue
            key_tok = re.sub(r"[\s\-]+", "_", normalize_token(raw_key))
            if r_idx == 1 and key_tok in {"recursos", "recurso", "parametro", "parametros"}:
                continue

            if "turma" in key_tok and "manha" in key_tok:
                ws.cell(row=r_idx, column=2, value=int(turmas_manha))
                updated_keys.add("turmas_manha")
            elif "turma" in key_tok and "tarde" in key_tok:
                ws.cell(row=r_idx, column=2, value=int(turmas_tarde))
                updated_keys.add("turmas_tarde")
            elif ("vaga" in key_tok or "capacidade" in key_tok) and "manha" in key_tok:
                ws.cell(row=r_idx, column=2, value=int(vagas_manha))
                updated_keys.add("vagas_manha")
            elif ("vaga" in key_tok or "capacidade" in key_tok) and "tarde" in key_tok:
                ws.cell(row=r_idx, column=2, value=int(vagas_tarde))
                updated_keys.add("vagas_tarde")

        defaults = [
            ("turmas_manha", int(turmas_manha)),
            ("turmas_tarde", int(turmas_tarde)),
            ("vagas_manha", int(vagas_manha)),
            ("vagas_tarde", int(vagas_tarde)),
        ]
        for key_name, val in defaults:
            if key_name not in updated_keys:
                ws.append([key_name, val])

        wb.save(path)
    finally:
        wb.close()


def format_validation_log(instance: ProcessedInstance, severity_filter: str = "TODAS") -> str:
    """Formata o resumo de validação da entrada e a listagem de inconsistências."""
    sep = "-" * 88
    lines: list[str] = []
    lines.append(sep)
    lines.append(f" VALIDAÇÃO DA PLANILHA DE ENTRADA: {instance.raw.filepath.name}")
    lines.append(sep)

    n_raw = len(instance.raw.students)
    n_valid = len(instance.students)
    n_invalid = len(instance.invalid_records)

    t_manha = len(instance.turmas_por_turno.get(TURNO_MANHA, []))
    t_tarde = len(instance.turmas_por_turno.get(TURNO_TARDE, []))
    c_manha = instance.capacidade_por_turno.get(TURNO_MANHA, 0)
    c_tarde = instance.capacidade_por_turno.get(TURNO_TARDE, 0)

    lines.append(
        f"  • Abas identificadas   : Alunos='{instance.raw.alunos_sheet_name}' | "
        f"Turmas='{instance.raw.turmas_sheet_name}'"
    )
    lines.append(
        f"  • Estrutura de turmas  : MANHÃ = {t_manha} turma(s) x {c_manha} vagas ({t_manha * c_manha} vagas) | "
        f"TARDE = {t_tarde} turma(s) x {c_tarde} vagas ({t_tarde * c_tarde} vagas)"
    )
    lines.append(
        f"  • Registros de alunos  : {n_raw} lidos -> {n_valid} válidos para ensalamento | "
        f"{n_invalid} retidos por erro crítico"
    )

    inc_tratadas = [i for i in instance.inconsistencies if i.severidade == "TRATADA"]
    inc_alertas = [i for i in instance.inconsistencies if i.severidade == "ALERTA"]
    inc_impeditivas = [i for i in instance.inconsistencies if i.severidade == "IMPEDITIVA"]

    lines.append(
        f"  • Inconsistências      : {len(instance.inconsistencies)} detectada(s) "
        f"({len(inc_tratadas)} tratada(s) | {len(inc_alertas)} alerta(s) de duplicidade | "
        f"{len(inc_impeditivas)} impeditiva(s)/crítica(s))"
    )

    filtered_incs = instance.inconsistencies
    if severity_filter != "TODAS":
        filtered_incs = [i for i in instance.inconsistencies if i.severidade == severity_filter]

    if not instance.inconsistencies:
        lines.append("\n  [OK] Nenhuma inconsistência encontrada na planilha de entrada.")
    elif not filtered_incs:
        lines.append(f"\n  [INFO] Nenhuma inconsistência na categoria '{severity_filter}'.")
    else:
        lines.append(f"\n  Detalhamento das inconsistências (Filtro: {severity_filter}):")
        for inc in filtered_incs:
            loc = f"Linha {inc.row_number:>3}" if inc.row_number is not None else "Global   "
            lines.append(
                f"    [{inc.severidade:<10}] {loc} | {inc.categoria:<24} | {inc.nome}: {inc.mensagem}"
            )

    if n_invalid > 0:
        lines.append(
            f"\n  [AVISO] Foram encontrados {n_invalid} registro(s) com erro crítico de preenchimento. "
            f"O ensalamento prosseguirá normalmente utilizando os {n_valid} alunos válidos restantes, "
            f"e os erros ficarão registrados na aba 'Inconsistências'."
        )

    if not instance.capacity_feasible:
        lines.append(
            "\n  [ALERTA DE CAPACIDADE] O número de alunos válidos excede a quantidade de vagas ofertadas! "
            "Você pode aumentar o número de turmas ou vagas no painel 'Ajuste Rápido de Vagas e Turmas' à esquerda."
        )

    lines.append(sep)
    return "\n".join(lines)


def filter_allocated_students(
    instance: ProcessedInstance,
    result: SolverResult,
    search_query: str = "",
    turma_filter: str = "Todas as Turmas",
    genero_filter: str = "Todos",
    sort_by: str = SORT_EXCEL_LABEL,
) -> list[tuple[Student, TurmaSpec]]:
    """Filtra e ordena os alunos alocados por nome, turma, gênero e critério de ordenação."""
    if not result.feasible or not result.student_to_turma:
        return []

    turma_by_id = {t.id: t for t in instance.turmas}
    q_norm = normalize_token(search_query)

    rows: list[tuple[Student, TurmaSpec]] = []
    for st in instance.students:
        t_id = result.student_to_turma.get(st.id)
        if t_id is None:
            continue
        turma = turma_by_id[t_id]

        if turma_filter != "Todas as Turmas" and turma.codigo != turma_filter:
            continue
        if genero_filter != "Todos" and st.sexo != genero_filter:
            continue
        if q_norm and q_norm not in normalize_token(st.nome):
            continue

        rows.append((st, turma))

    sort_tok = normalize_token(sort_by)
    if "alfabet" in sort_tok or "a-z" in sort_tok or "nome" in sort_tok:
        rows.sort(key=lambda pair: (normalize_token(pair[0].nome), pair[0].row_number))
    else:
        rows.sort(key=lambda pair: pair[0].row_number)

    return rows


def execute_ensalamento_workflow(
    input_excel_path: str | Path,
    model_label: str = MODEL_1STEP_LABEL,
    excel_output_path: Optional[str | Path] = None,
    report_output_path: Optional[str | Path] = None,
    solver_params: Optional[SolverParameters] = None,
    log_callback: Optional[Callable[[str], None]] = None,
) -> GuiPipelineOutcome:
    """Executa validação de entrada, otimização com o modelo escolhido e pós-processamento."""
    path = Path(input_excel_path).resolve()

    def _emit(msg: str) -> None:
        if log_callback is not None:
            log_callback(msg)

    solver_fn = MODEL_SOLVERS.get(model_label, solve_ensalamento_1step)

    timestamp = datetime.now().strftime("%H:%M:%S")
    _emit(f"[{timestamp}] [ETAPA 1/3] Lendo e validando planilha: {path}\n")

    raw = read_instance(path)
    processed = pre_process(raw)
    val_log = format_validation_log(processed)
    _emit(val_log + "\n\n")

    timestamp = datetime.now().strftime("%H:%M:%S")
    _emit(
        f"[{timestamp}] [ETAPA 2/3] Iniciando otimização matemática — Modelo: {model_label} "
        f"({len(processed.students)} alunos válidos, {len(processed.turmas)} turmas)...\n"
    )

    result = solver_fn(processed, solver_params)

    timestamp = datetime.now().strftime("%H:%M:%S")
    _emit(
        f"[{timestamp}] [ETAPA 3/3] Gravando abas 'Ensalamento' e 'Inconsistências' no Excel e gerando relatório...\n"
    )

    if report_output_path is None:
        reports_dir = get_reports_dir(path)
        report_output_path = reports_dir / f"{path.stem}_relatorio.txt"

    artifacts = pos_process(
        instance=processed,
        result=result,
        excel_output_path=excel_output_path,
        report_output_path=report_output_path,
        print_to_terminal=False,
    )

    _emit("\n" + artifacts.report_text + "\n")
    timestamp = datetime.now().strftime("%H:%M:%S")
    _emit(
        f"\n[{timestamp}] [CONCLUÍDO] Planilha atualizada com sucesso em:\n"
        f"  -> Excel    : {artifacts.excel_output_path}\n"
        f"  -> Relatório: {artifacts.report_file_path}\n"
    )

    return GuiPipelineOutcome(
        processed=processed,
        solver_result=result,
        artifacts=artifacts,
        validation_log=val_log,
    )


def load_cropped_logo_pil(max_width: int = 160, max_height: int = 95) -> Optional[tuple[Any, tuple[int, int]]]:
    """Carrega a logo da ABC Aprendiz via PIL, remove margens brancas excessivas e calcula tamanho proporcional."""
    if Image is None:
        return None
    logo_path = get_asset_path("logo_abc_aprendiz.png")
    if not logo_path.exists():
        return None
    try:
        img = Image.open(logo_path).convert("RGBA")
        # Remove margens brancas extras ao redor do desenho da logo
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        if ImageChops is not None:
            diff = ImageChops.difference(img, bg).convert("RGB")
            bbox = diff.getbbox()
            if bbox:
                pad = 12
                left = max(0, bbox[0] - pad)
                top = max(0, bbox[1] - pad)
                right = min(img.width, bbox[2] + pad)
                bottom = min(img.height, bbox[3] + pad)
                img = img.crop((left, top, right, bottom))

        w, h = img.size
        scale = min(max_width / max(w, 1), max_height / max(h, 1))
        disp_size = (max(1, round(w * scale)), max(1, round(h * scale)))
        return img, disp_size
    except Exception:
        return None


class EnsalamentoApp(ctk.CTk):
    """Janela principal da aplicação de ensalamento com barra lateral esquerda e abas em tela cheia."""

    def __init__(self) -> None:
        super().__init__(fg_color=ABC_BG)

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.title("ABC Aprendiz — Sistema Inteligente de Ensalamento (Desafio UniSoma 2026)")
        self.geometry("1260x820")
        self.minsize(1020, 680)

        self.selected_file_path: Optional[Path] = None
        self.current_processed: Optional[ProcessedInstance] = None
        self.current_outcome: Optional[GuiPipelineOutcome] = None
        self._is_running: bool = False
        self._msg_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._ctk_logo_image: Optional[ctk.CTkImage] = None

        self._build_layout()
        self._poll_queue()

    def _get_mono_font(self, size: int = 12, weight: str = "normal") -> ctk.CTkFont:
        family = "Consolas" if platform.system() == "Windows" else "DejaVu Sans Mono"
        return ctk.CTkFont(family=family, size=size, weight=weight)

    def _load_logo(self) -> Optional[ctk.CTkImage]:
        loaded = load_cropped_logo_pil(max_width=150, max_height=88)
        if loaded is None:
            return None
        pil_img, disp_size = loaded
        self._ctk_logo_image = ctk.CTkImage(
            light_image=pil_img,
            dark_image=pil_img,
            size=disp_size,
        )
        return self._ctk_logo_image

    def _build_layout(self) -> None:
        # Coluna 0: Barra lateral esquerda (fixa) | Coluna 1: Área principal de Abas (expansível)
        self.grid_columnconfigure(0, weight=0, minsize=320)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # =====================================================================
        # COLUNA ESQUERDA: BARRA LATERAL DE CONTROLES
        # =====================================================================
        sidebar = ctk.CTkFrame(
            self,
            width=320,
            fg_color=ABC_CARD,
            corner_radius=12,
            border_width=1,
            border_color=ABC_BORDER,
        )
        sidebar.grid(row=0, column=0, padx=(14, 8), pady=14, sticky="nsew")
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(4, weight=1)  # Espaçador flexível antes da barra de progresso

        # Faixa superior institucional
        accent_bar = ctk.CTkFrame(sidebar, fg_color=ABC_NAVY, height=6, corner_radius=6)
        accent_bar.grid(row=0, column=0, sticky="ew", padx=2, pady=(2, 8))

        # --- Bloco 1: Logo + Identidade ABC Aprendiz + Status ---
        brand_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand_frame.grid(row=1, column=0, padx=14, pady=(0, 8), sticky="ew")
        brand_frame.grid_columnconfigure(0, weight=1)

        logo_ctk = self._load_logo()
        if logo_ctk is not None:
            logo_lbl = ctk.CTkLabel(
                brand_frame,
                text="",
                image=logo_ctk,
            )
            logo_lbl.grid(row=0, column=0, pady=(2, 6))
        else:
            badge_lbl = ctk.CTkLabel(
                brand_frame,
                text="ABC aprendiz",
                font=ctk.CTkFont(size=18, weight="bold"),
                fg_color=ABC_NAVY,
                text_color="#FFFFFF",
                corner_radius=8,
                padx=16,
                pady=8,
            )
            badge_lbl.grid(row=0, column=0, pady=(2, 6))

        title_lbl = ctk.CTkLabel(
            brand_frame,
            text="Ensalamento de Turmas",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=ABC_NAVY,
        )
        title_lbl.grid(row=1, column=0, pady=(0, 2))

        subtitle_lbl = ctk.CTkLabel(
            brand_frame,
            text="Otimização Matemática • Desafio UniSoma",
            font=ctk.CTkFont(size=11),
            text_color=ABC_MUTED,
        )
        subtitle_lbl.grid(row=2, column=0, pady=(0, 8))

        self.lbl_status_badge = ctk.CTkLabel(
            brand_frame,
            text="Aguardando Planilha",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#E2E8F0",
            text_color=ABC_TEXT,
            corner_radius=8,
            height=30,
        )
        self.lbl_status_badge.grid(row=3, column=0, sticky="ew", pady=(0, 4))

        # --- Bloco 2: Seleção de Planilha, Modelo e Execução ---
        exec_box = ctk.CTkFrame(
            sidebar,
            fg_color="#F8FAFC",
            corner_radius=10,
            border_width=1,
            border_color=ABC_BORDER,
        )
        exec_box.grid(row=2, column=0, padx=14, pady=6, sticky="ew")
        exec_box.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            exec_box,
            text="1. Planilha & Otimização",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=ABC_NAVY,
            anchor="w",
        ).grid(row=0, column=0, padx=12, pady=(10, 6), sticky="ew")

        self.btn_select_file = ctk.CTkButton(
            exec_box,
            text="Selecionar Planilha (.xlsx)",
            height=36,
            fg_color=ABC_CYAN,
            hover_color=ABC_CYAN_DARK,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._on_select_file,
        )
        self.btn_select_file.grid(row=1, column=0, padx=12, pady=(0, 6), sticky="ew")

        self.entry_file_path = ctk.CTkEntry(
            exec_box,
            placeholder_text="Nenhuma planilha selecionada...",
            height=32,
            fg_color="#FFFFFF",
            border_color=ABC_BORDER,
            text_color=ABC_TEXT,
            font=ctk.CTkFont(size=11),
            state="readonly",
        )
        self.entry_file_path.grid(row=2, column=0, padx=12, pady=(0, 8), sticky="ew")

        ctk.CTkLabel(
            exec_box,
            text="Modelo Matemático (Validação):",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=ABC_MUTED,
            anchor="w",
        ).grid(row=3, column=0, padx=12, pady=(0, 2), sticky="ew")

        self.model_var = ctk.StringVar(value=MODEL_1STEP_LABEL)
        self.option_model = ctk.CTkOptionMenu(
            exec_box,
            variable=self.model_var,
            values=[MODEL_1STEP_LABEL, MODEL_2STEP_LABEL],
            height=32,
            fg_color=ABC_NAVY,
            button_color=ABC_NAVY_DARK,
            button_hover_color=ABC_CYAN,
            font=ctk.CTkFont(size=11),
            dynamic_resizing=False,
        )
        self.option_model.grid(row=4, column=0, padx=12, pady=(0, 10), sticky="ew")

        self.btn_run = ctk.CTkButton(
            exec_box,
            text="▶ Iniciar Ensalamento",
            height=40,
            fg_color=ABC_TEAL_DARK,
            hover_color=ABC_TEAL,
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._on_start_ensalamento,
        )
        self.btn_run.grid(row=5, column=0, padx=12, pady=(0, 8), sticky="ew")

        self.btn_open_excel = ctk.CTkButton(
            exec_box,
            text="Abrir Solução no Excel",
            height=34,
            fg_color=ABC_NAVY,
            hover_color=ABC_NAVY_DARK,
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=12, weight="bold"),
            state="disabled",
            command=self._on_open_in_excel,
        )
        self.btn_open_excel.grid(row=6, column=0, padx=12, pady=(0, 12), sticky="ew")

        # --- Bloco 3: Ajuste Rápido de Vagas e Turmas ---
        turmas_box = ctk.CTkFrame(
            sidebar,
            fg_color="#F8FAFC",
            corner_radius=10,
            border_width=1,
            border_color=ABC_BORDER,
        )
        turmas_box.grid(row=3, column=0, padx=14, pady=6, sticky="ew")
        turmas_box.grid_columnconfigure(0, weight=1)
        turmas_box.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            turmas_box,
            text="2. Ajuste Rápido de Vagas e Turmas",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=ABC_NAVY,
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, padx=12, pady=(10, 6), sticky="ew")

        # Linha Manhã
        ctk.CTkLabel(
            turmas_box,
            text="Turmas Manhã:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=ABC_CYAN,
            anchor="w",
        ).grid(row=1, column=0, padx=(12, 6), pady=(2, 0), sticky="w")

        ctk.CTkLabel(
            turmas_box,
            text="Vagas/Sala Manhã:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=ABC_CYAN,
            anchor="w",
        ).grid(row=1, column=1, padx=(6, 12), pady=(2, 0), sticky="w")

        self.var_turmas_manha = ctk.StringVar(value="-")
        self.entry_turmas_manha = ctk.CTkEntry(
            turmas_box,
            textvariable=self.var_turmas_manha,
            height=30,
            fg_color="#FFFFFF",
            justify="center",
        )
        self.entry_turmas_manha.grid(row=2, column=0, padx=(12, 6), pady=(0, 6), sticky="ew")

        self.var_vagas_manha = ctk.StringVar(value="-")
        self.entry_vagas_manha = ctk.CTkEntry(
            turmas_box,
            textvariable=self.var_vagas_manha,
            height=30,
            fg_color="#FFFFFF",
            justify="center",
        )
        self.entry_vagas_manha.grid(row=2, column=1, padx=(6, 12), pady=(0, 6), sticky="ew")

        # Linha Tarde
        ctk.CTkLabel(
            turmas_box,
            text="Turmas Tarde:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=ABC_TEAL_DARK,
            anchor="w",
        ).grid(row=3, column=0, padx=(12, 6), pady=(2, 0), sticky="w")

        ctk.CTkLabel(
            turmas_box,
            text="Vagas/Sala Tarde:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=ABC_TEAL_DARK,
            anchor="w",
        ).grid(row=3, column=1, padx=(6, 12), pady=(2, 0), sticky="w")

        self.var_turmas_tarde = ctk.StringVar(value="-")
        self.entry_turmas_tarde = ctk.CTkEntry(
            turmas_box,
            textvariable=self.var_turmas_tarde,
            height=30,
            fg_color="#FFFFFF",
            justify="center",
        )
        self.entry_turmas_tarde.grid(row=4, column=0, padx=(12, 6), pady=(0, 8), sticky="ew")

        self.var_vagas_tarde = ctk.StringVar(value="-")
        self.entry_vagas_tarde = ctk.CTkEntry(
            turmas_box,
            textvariable=self.var_vagas_tarde,
            height=30,
            fg_color="#FFFFFF",
            justify="center",
        )
        self.entry_vagas_tarde.grid(row=4, column=1, padx=(6, 12), pady=(0, 8), sticky="ew")

        self.lbl_cap_summary = ctk.CTkLabel(
            turmas_box,
            text="Carregue uma planilha para editar.",
            font=ctk.CTkFont(size=11),
            text_color=ABC_MUTED,
            wraplength=260,
            justify="left",
            anchor="w",
        )
        self.lbl_cap_summary.grid(row=5, column=0, columnspan=2, padx=12, pady=(0, 8), sticky="ew")

        self.btn_save_turmas = ctk.CTkButton(
            turmas_box,
            text="Salvar na Planilha",
            height=34,
            fg_color=ABC_CYAN,
            hover_color=ABC_CYAN_DARK,
            font=ctk.CTkFont(size=12, weight="bold"),
            state="disabled",
            command=self._on_save_turmas_clicked,
        )
        self.btn_save_turmas.grid(row=6, column=0, columnspan=2, padx=12, pady=(0, 12), sticky="ew")

        # Barra de progresso no rodapé da barra lateral
        self.progress_bar = ctk.CTkProgressBar(
            sidebar,
            mode="determinate",
            height=8,
            fg_color="#DCE4F0",
            progress_color=ABC_TEAL,
        )
        self.progress_bar.grid(row=5, column=0, padx=14, pady=(6, 14), sticky="ew")
        self.progress_bar.set(0)

        # =====================================================================
        # COLUNA DIREITA: SEÇÃO DE ABAS EM ALTURA TOTAL
        # =====================================================================
        self.tabview = ctk.CTkTabview(
            self,
            fg_color=ABC_CARD,
            segmented_button_fg_color="#CBD5E1",
            segmented_button_selected_color=ABC_NAVY,
            segmented_button_selected_hover_color=ABC_NAVY_DARK,
            segmented_button_unselected_color="#E2E8F0",
            segmented_button_unselected_hover_color="#CBD5E1",
            text_color=ABC_TEXT,
            corner_radius=12,
            border_width=1,
            border_color=ABC_BORDER,
        )
        self.tabview.grid(row=0, column=1, padx=(4, 14), pady=14, sticky="nsew")

        self.tab_validacao = self.tabview.add("1. Inconsistências & Validação")
        self.tab_dashboard = self.tabview.add("2. Dashboard do Ensalamento")
        self.tab_consulta = self.tabview.add("3. Consulta de Turmas e Alunos")
        self.tab_logs = self.tabview.add("4. Logs do Sistema")

        # Aumenta o tamanho dos botões das abas e aplica alto contraste entre aba ativa e inativa
        self.tabview._button_height = 40
        self.tabview._segmented_button.configure(
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.tabview._configure_grid()
        self._enhance_segmented_button_contrast(
            self.tabview._segmented_button,
            selected_text_color="#FFFFFF",
            unselected_text_color=ABC_TEXT,
            extra_ipadx=10,
        )

        self._build_tab_validacao()
        self._build_tab_dashboard()
        self._build_tab_consulta()
        self._build_tab_logs()

    # -------------------------------------------------------------------------
    # Construção da Aba 1: Inconsistências & Validação
    # -------------------------------------------------------------------------
    def _build_tab_validacao(self) -> None:
        self.tab_validacao.grid_columnconfigure(0, weight=1)
        self.tab_validacao.grid_rowconfigure(2, weight=1)

        kpi_frame = ctk.CTkFrame(self.tab_validacao, fg_color="transparent")
        kpi_frame.grid(row=0, column=0, padx=8, pady=(6, 6), sticky="ew")
        for c in range(4):
            kpi_frame.grid_columnconfigure(c, weight=1)

        self.lbl_val_validos = self._create_kpi_card(
            kpi_frame, 0, "Alunos Válidos / Lidos", "-", "Prontos para ensalar", ABC_NAVY
        )
        self.lbl_val_impeditivas = self._create_kpi_card(
            kpi_frame, 1, "Erros Impeditivos", "-", "Sexo/Turno inválido ou vazio", COLOR_IMPEDITIVA
        )
        self.lbl_val_alertas = self._create_kpi_card(
            kpi_frame, 2, "Alertas de Duplicidade", "-", "Homônimos alocados", COLOR_ALERTA
        )
        self.lbl_val_tratadas = self._create_kpi_card(
            kpi_frame, 3, "Padronizações Automáticas", "-", "Corrigidas pelo sistema", COLOR_TRATADA
        )

        filter_bar = ctk.CTkFrame(self.tab_validacao, fg_color="#F8FAFC", corner_radius=8)
        filter_bar.grid(row=1, column=0, padx=8, pady=(2, 6), sticky="ew")

        ctk.CTkLabel(
            filter_bar,
            text="Filtrar ocorrências por tipo:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=ABC_TEXT,
        ).grid(row=0, column=0, padx=(12, 8), pady=6, sticky="w")

        self.var_inc_filter = ctk.StringVar(value="TODAS")
        self.seg_inc_filter = ctk.CTkSegmentedButton(
            filter_bar,
            values=["TODAS", "IMPEDITIVA", "ALERTA", "TRATADA"],
            variable=self.var_inc_filter,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#CBD5E1",
            selected_color=ABC_CYAN,
            selected_hover_color=ABC_CYAN_DARK,
            unselected_color="#E2E8F0",
            unselected_hover_color="#CBD5E1",
            text_color=ABC_TEXT,
            command=self._on_inc_filter_changed,
        )
        self.seg_inc_filter.grid(row=0, column=1, padx=8, pady=6, sticky="w")
        self._enhance_segmented_button_contrast(
            self.seg_inc_filter,
            selected_text_color="#FFFFFF",
            unselected_text_color=ABC_TEXT,
            extra_ipadx=6,
        )

        self.textbox_validacao = ctk.CTkTextbox(
            self.tab_validacao,
            font=self._get_mono_font(12),
            wrap="none",
            fg_color="#F8FAFC",
            text_color=ABC_TEXT,
            border_width=1,
            border_color=ABC_BORDER,
            corner_radius=8,
        )
        self.textbox_validacao.grid(row=2, column=0, padx=8, pady=(0, 6), sticky="nsew")
        self._set_textbox_content(
            self.textbox_validacao,
            "Selecione uma planilha Excel (.xlsx) na barra lateral esquerda para visualizar o diagnóstico de validação e inconsistências.\n",
        )

    # -------------------------------------------------------------------------
    # Construção da Aba 2: Dashboard do Ensalamento
    # -------------------------------------------------------------------------
    def _build_tab_dashboard(self) -> None:
        self.tab_dashboard.grid_columnconfigure(0, weight=1)
        self.tab_dashboard.grid_rowconfigure(1, weight=1)

        kpi_frame = ctk.CTkFrame(self.tab_dashboard, fg_color="transparent")
        kpi_frame.grid(row=0, column=0, padx=8, pady=(6, 6), sticky="ew")
        for c in range(3):
            kpi_frame.grid_columnconfigure(c, weight=1)

        self.lbl_dash_total = self._create_kpi_card(
            kpi_frame, 0, "Total Alocados / Vagas", "-", "Ocupação Global", ABC_NAVY
        )
        self.lbl_dash_manha = self._create_kpi_card(
            kpi_frame, 1, "Turno MANHÃ", "-", "Lotação e Gênero", ABC_CYAN
        )
        self.lbl_dash_tarde = self._create_kpi_card(
            kpi_frame, 2, "Turno TARDE", "-", "Lotação e Gênero", ABC_TEAL_DARK
        )

        # Scrollable frame dividido em duas colunas: Coluna 0 = MANHÃ | Coluna 1 = TARDE
        self.scroll_dashboard = ctk.CTkScrollableFrame(
            self.tab_dashboard,
            fg_color="#F8FAFC",
            corner_radius=8,
            border_width=1,
            border_color=ABC_BORDER,
        )
        self.scroll_dashboard.grid(row=1, column=0, padx=8, pady=(0, 6), sticky="nsew")
        self.scroll_dashboard.grid_columnconfigure(0, weight=1)
        self.scroll_dashboard.grid_columnconfigure(1, weight=1)

        self._render_empty_dashboard()

    # -------------------------------------------------------------------------
    # Construção da Aba 3: Consulta de Turmas e Alunos
    # -------------------------------------------------------------------------
    def _build_tab_consulta(self) -> None:
        self.tab_consulta.grid_columnconfigure(0, weight=1)
        self.tab_consulta.grid_rowconfigure(1, weight=1)

        filter_frame = ctk.CTkFrame(self.tab_consulta, fg_color="#F8FAFC", corner_radius=8)
        filter_frame.grid(row=0, column=0, padx=8, pady=(6, 6), sticky="ew")
        filter_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            filter_frame,
            text="Buscar Aluno:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=ABC_TEXT,
        ).grid(row=0, column=0, padx=(12, 6), pady=8, sticky="w")

        self.var_search_student = ctk.StringVar(value="")
        self.entry_search_student = ctk.CTkEntry(
            filter_frame,
            textvariable=self.var_search_student,
            placeholder_text="Digite parte do nome do aluno...",
            height=32,
        )
        self.entry_search_student.grid(row=0, column=1, padx=(0, 10), pady=8, sticky="ew")
        self.entry_search_student.bind("<KeyRelease>", lambda _e: self._refresh_consulta_tab())

        ctk.CTkLabel(
            filter_frame,
            text="Turma:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=ABC_TEXT,
        ).grid(row=0, column=2, padx=(4, 4), pady=8)

        self.var_filter_turma = ctk.StringVar(value="Todas as Turmas")
        self.option_filter_turma = ctk.CTkOptionMenu(
            filter_frame,
            variable=self.var_filter_turma,
            values=["Todas as Turmas"],
            width=145,
            height=32,
            fg_color=ABC_CYAN,
            button_color=ABC_CYAN_DARK,
            command=lambda _v: self._refresh_consulta_tab(),
        )
        self.option_filter_turma.grid(row=0, column=3, padx=(0, 10), pady=8)

        ctk.CTkLabel(
            filter_frame,
            text="Sexo:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=ABC_TEXT,
        ).grid(row=0, column=4, padx=(4, 4), pady=8)

        self.var_filter_genero = ctk.StringVar(value="Todos")
        self.option_filter_genero = ctk.CTkOptionMenu(
            filter_frame,
            variable=self.var_filter_genero,
            values=["Todos", "M", "F"],
            width=85,
            height=32,
            fg_color=ABC_NAVY,
            button_color=ABC_NAVY_DARK,
            command=lambda _v: self._refresh_consulta_tab(),
        )
        self.option_filter_genero.grid(row=0, column=5, padx=(0, 10), pady=8)

        ctk.CTkLabel(
            filter_frame,
            text="Ordenar:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=ABC_TEXT,
        ).grid(row=0, column=6, padx=(4, 4), pady=8)

        self.var_sort_order = ctk.StringVar(value=SORT_EXCEL_LABEL)
        self.option_sort_order = ctk.CTkOptionMenu(
            filter_frame,
            variable=self.var_sort_order,
            values=[SORT_EXCEL_LABEL, SORT_ALPHA_LABEL],
            width=195,
            height=32,
            fg_color=ABC_TEAL_DARK,
            button_color=ABC_TEAL,
            command=lambda _v: self._refresh_consulta_tab(),
        )
        self.option_sort_order.grid(row=0, column=7, padx=(0, 10), pady=8)

        self.lbl_consulta_count = ctk.CTkLabel(
            filter_frame,
            text="0 alunos",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=ABC_MUTED,
        )
        self.lbl_consulta_count.grid(row=0, column=8, padx=(2, 12), pady=8, sticky="e")

        self.textbox_consulta = ctk.CTkTextbox(
            self.tab_consulta,
            font=self._get_mono_font(12),
            wrap="none",
            fg_color="#F8FAFC",
            text_color=ABC_TEXT,
            border_width=1,
            border_color=ABC_BORDER,
            corner_radius=8,
        )
        self.textbox_consulta.grid(row=1, column=0, padx=8, pady=(0, 6), sticky="nsew")
        self._set_textbox_content(
            self.textbox_consulta,
            "Execute o ensalamento para consultar a lista de alunos alocados por turma.\n",
        )

    # -------------------------------------------------------------------------
    # Construção da Aba 4: Logs do Sistema
    # -------------------------------------------------------------------------
    def _build_tab_logs(self) -> None:
        self.tab_logs.grid_columnconfigure(0, weight=1)
        self.tab_logs.grid_rowconfigure(1, weight=1)

        top_bar = ctk.CTkFrame(self.tab_logs, fg_color="transparent")
        top_bar.grid(row=0, column=0, padx=8, pady=(4, 4), sticky="ew")
        top_bar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            top_bar,
            text="Histórico de Execução, Métricas do Solver e Relatório Diagnóstico",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=ABC_NAVY,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            top_bar,
            text="Limpar Histórico de Logs",
            width=160,
            height=28,
            fg_color="#E2E8F0",
            hover_color="#CBD5E1",
            text_color=ABC_TEXT,
            font=ctk.CTkFont(size=12),
            command=self._clear_logs,
        ).grid(row=0, column=1, sticky="e")

        self.textbox_log = ctk.CTkTextbox(
            self.tab_logs,
            font=self._get_mono_font(12),
            wrap="none",
            fg_color="#F8FAFC",
            text_color=ABC_TEXT,
            border_width=1,
            border_color=ABC_BORDER,
            corner_radius=8,
        )
        self.textbox_log.grid(row=1, column=0, padx=8, pady=(0, 6), sticky="nsew")
        self.textbox_log.configure(state="disabled")

        self._append_log(
            "Bem-vindo ao Sistema de Ensalamento Otimizado — ABC Aprendiz (Desafio UniSoma 2026).\n"
            "1. Clique em 'Selecionar Planilha (.xlsx)' na coluna à esquerda para carregar os dados.\n"
            "2. Confira ou edite as quantidades de turmas/vagas no painel 'Ajuste Rápido'.\n"
            "3. Clique em '▶ Iniciar Ensalamento' para otimizar e atualizar a planilha.\n"
            + ("=" * 88)
            + "\n"
        )

    # -------------------------------------------------------------------------
    # Utilitários Visuais (Cards, Textboxes, Dashboard)
    # -------------------------------------------------------------------------
    def _enhance_segmented_button_contrast(
        self,
        seg_btn: ctk.CTkSegmentedButton,
        selected_text_color: str = "#FFFFFF",
        unselected_text_color: str = ABC_TEXT,
        extra_ipadx: int = 8,
    ) -> None:
        """Garante contraste legível entre botões ativos (texto claro) e inativos (texto escuro) e aumenta área."""
        orig_select = seg_btn._select_button_by_value
        orig_unselect = seg_btn._unselect_button_by_value

        def _custom_select(value: str) -> None:
            orig_select(value)
            for val, btn in seg_btn._buttons_dict.items():
                btn.configure(
                    text_color=selected_text_color if val == value else unselected_text_color
                )

        def _custom_unselect(value: str) -> None:
            orig_unselect(value)
            if value in seg_btn._buttons_dict:
                seg_btn._buttons_dict[value].configure(text_color=unselected_text_color)

        seg_btn._select_button_by_value = _custom_select  # type: ignore[method-assign]
        seg_btn._unselect_button_by_value = _custom_unselect  # type: ignore[method-assign]

        current = seg_btn.get()
        for val, btn in seg_btn._buttons_dict.items():
            btn.configure(
                text_color=selected_text_color if val == current else unselected_text_color
            )
            if extra_ipadx > 0:
                btn.grid_configure(ipadx=extra_ipadx)

    def _create_kpi_card(
        self,
        parent: ctk.CTkFrame,
        col: int,
        title: str,
        value: str,
        subtitle: str,
        accent_color: str,
    ) -> tuple[ctk.CTkLabel, ctk.CTkLabel]:
        card = ctk.CTkFrame(
            parent,
            fg_color="#F8FAFC",
            corner_radius=10,
            border_width=1,
            border_color=ABC_BORDER,
        )
        card.grid(row=0, column=col, padx=5, pady=2, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)

        stripe = ctk.CTkFrame(card, fg_color=accent_color, height=4, corner_radius=4)
        stripe.grid(row=0, column=0, sticky="ew", padx=2, pady=(2, 4))

        lbl_title = ctk.CTkLabel(
            card,
            text=title,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=ABC_MUTED,
            anchor="w",
        )
        lbl_title.grid(row=1, column=0, padx=12, pady=(2, 0), sticky="ew")

        lbl_val = ctk.CTkLabel(
            card,
            text=value,
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=accent_color,
            anchor="w",
        )
        lbl_val.grid(row=2, column=0, padx=12, pady=(0, 0), sticky="ew")

        lbl_sub = ctk.CTkLabel(
            card,
            text=subtitle,
            font=ctk.CTkFont(size=11),
            text_color=ABC_MUTED,
            anchor="w",
        )
        lbl_sub.grid(row=3, column=0, padx=12, pady=(0, 8), sticky="ew")
        return lbl_val, lbl_sub

    def _set_textbox_content(self, textbox: ctk.CTkTextbox, text: str) -> None:
        textbox.configure(state="normal")
        textbox.delete("1.0", "end")
        textbox.insert("1.0", text)
        textbox.configure(state="disabled")

    def _append_log(self, text: str) -> None:
        self.textbox_log.configure(state="normal")
        self.textbox_log.insert("end", text)
        self.textbox_log.see("end")
        self.textbox_log.configure(state="disabled")

    def _clear_logs(self) -> None:
        self._set_textbox_content(self.textbox_log, "")

    def _set_file_entry(self, text: str) -> None:
        self.entry_file_path.configure(state="normal")
        self.entry_file_path.delete(0, "end")
        self.entry_file_path.insert(0, text)
        self.entry_file_path.configure(state="readonly")

    # -------------------------------------------------------------------------
    # Atualização das Abas e Painéis com Dados da Instância
    # -------------------------------------------------------------------------
    def _populate_from_processed_instance(self, proc: ProcessedInstance) -> None:
        self.current_processed = proc

        tm = len(proc.turmas_por_turno.get(TURNO_MANHA, []))
        tt = len(proc.turmas_por_turno.get(TURNO_TARDE, []))
        vm = proc.capacidade_por_turno.get(TURNO_MANHA, 0)
        vt = proc.capacidade_por_turno.get(TURNO_TARDE, 0)

        self.var_turmas_manha.set(str(tm))
        self.var_vagas_manha.set(str(vm))
        self.var_turmas_tarde.set(str(tt))
        self.var_vagas_tarde.set(str(vt))

        aloc_m = sum(1 for s in proc.students if s.turnos_compativeis == (TURNO_MANHA,))
        aloc_t = sum(1 for s in proc.students if s.turnos_compativeis == (TURNO_TARDE,))
        cap_m = tm * vm
        cap_t = tt * vt

        cap_text = f"Manhã: {aloc_m}/{cap_m} vagas\nTarde: {aloc_t}/{cap_t} vagas"
        cap_color = ABC_TEAL_DARK if proc.capacity_feasible else COLOR_IMPEDITIVA
        self.lbl_cap_summary.configure(text=cap_text, text_color=cap_color)

        n_raw = len(proc.raw.students)
        n_val = len(proc.students)
        n_inv = len(proc.invalid_records)

        inc_imp = [i for i in proc.inconsistencies if i.severidade == "IMPEDITIVA"]
        inc_ale = [i for i in proc.inconsistencies if i.severidade == "ALERTA"]
        inc_tra = [i for i in proc.inconsistencies if i.severidade == "TRATADA"]

        self.lbl_val_validos[0].configure(text=f"{n_val} / {n_raw}")
        self.lbl_val_validos[1].configure(
            text=f"{n_inv} retido(s) por erro crítico" if n_inv > 0 else "100% dos alunos válidos"
        )

        self.lbl_val_impeditivas[0].configure(text=str(len(inc_imp)))
        self.lbl_val_impeditivas[1].configure(
            text="Atenção: verifique a aba Inconsistências" if inc_imp else "Nenhum erro impeditivo"
        )

        self.lbl_val_alertas[0].configure(text=str(len(inc_ale)))
        self.lbl_val_alertas[1].configure(
            text="Nomes repetidos (alocados em duplicidade)" if inc_ale else "Sem homônimos detectados"
        )

        self.lbl_val_tratadas[0].configure(text=str(len(inc_tra)))
        self.lbl_val_tratadas[1].configure(
            text="Grafias/espaços padronizados" if inc_tra else "Nenhuma correção necessária"
        )

        self._refresh_validacao_textbox()

    def _refresh_validacao_textbox(self) -> None:
        if self.current_processed is None:
            return
        flt = self.var_inc_filter.get()
        self._set_textbox_content(
            self.textbox_validacao,
            format_validation_log(self.current_processed, severity_filter=flt),
        )

    def _on_inc_filter_changed(self, _value: str) -> None:
        self._refresh_validacao_textbox()

    def _render_empty_dashboard(self) -> None:
        for child in self.scroll_dashboard.winfo_children():
            child.destroy()
        info = ctk.CTkLabel(
            self.scroll_dashboard,
            text="Clique em '▶ Iniciar Ensalamento' na barra lateral para visualizar os cartões de lotação e proporção de gênero por turma.",
            font=ctk.CTkFont(size=13),
            text_color=ABC_MUTED,
        )
        info.grid(row=0, column=0, columnspan=2, padx=16, pady=36)

    def _populate_dashboard_and_consulta(self, outcome: GuiPipelineOutcome) -> None:
        self.current_outcome = outcome
        proc = outcome.processed
        res = outcome.solver_result

        if not res.feasible:
            self.lbl_dash_total[0].configure(text="Inviável")
            self.lbl_dash_total[1].configure(text=res.reason[:45])
            self._render_empty_dashboard()
            return

        # 1. Atualiza KPIs do Dashboard (sem estatística de proporção global e sem desvios máx entre salas)
        total_aloc = sum(res.y_turma.values())
        total_cap = sum(t.capacidade for t in proc.turmas)
        ocup_global = (100.0 * total_aloc / total_cap) if total_cap > 0 else 0.0

        self.lbl_dash_total[0].configure(text=f"{total_aloc} / {total_cap} ({ocup_global:.1f}%)")
        self.lbl_dash_total[1].configure(text=f"{len(proc.turmas)} turmas ativas • {total_cap - total_aloc} vagas livres")

        for turno, kpi_pair in ((TURNO_MANHA, self.lbl_dash_manha), (TURNO_TARDE, self.lbl_dash_tarde)):
            t_list = proc.turmas_por_turno.get(turno, [])
            aloc_t = sum(res.y_turma[t.id] for t in t_list)
            cap_t = sum(t.capacidade for t in t_list)
            m_t = sum(res.z_turma_gen[(t.id, GENERO_M)] for t in t_list)
            f_t = sum(res.z_turma_gen[(t.id, GENERO_F)] for t in t_list)
            ocup_t = (100.0 * aloc_t / cap_t) if cap_t > 0 else 0.0

            kpi_pair[0].configure(text=f"{aloc_t}/{cap_t} alunos ({m_t}M / {f_t}F)")
            kpi_pair[1].configure(text=f"{len(t_list)} turma(s) • Ocupação: {ocup_t:.1f}% ({cap_t - aloc_t} livres)")

        # 2. Renderiza Turmas em 2 Colunas: Coluna 0 = MANHÃ | Coluna 1 = TARDE
        for child in self.scroll_dashboard.winfo_children():
            child.destroy()

        col_manha = ctk.CTkFrame(self.scroll_dashboard, fg_color="transparent")
        col_manha.grid(row=0, column=0, padx=(4, 6), pady=4, sticky="nsew")
        col_manha.grid_columnconfigure(0, weight=1)

        col_tarde = ctk.CTkFrame(self.scroll_dashboard, fg_color="transparent")
        col_tarde.grid(row=0, column=1, padx=(6, 4), pady=4, sticky="nsew")
        col_tarde.grid_columnconfigure(0, weight=1)

        turmas_manha = proc.turmas_por_turno.get(TURNO_MANHA, [])
        turmas_tarde = proc.turmas_por_turno.get(TURNO_TARDE, [])

        # Cabeçalho Coluna Manhã (sem emoji)
        hdr_manha = ctk.CTkFrame(col_manha, fg_color=ABC_CYAN, corner_radius=8)
        hdr_manha.grid(row=0, column=0, padx=4, pady=(2, 6), sticky="ew")
        ctk.CTkLabel(
            hdr_manha,
            text=f"Turmas da Manhã ({len(turmas_manha)} sala(s))",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#FFFFFF",
        ).pack(padx=12, pady=6, anchor="w")

        for r_idx, t in enumerate(turmas_manha, start=1):
            self._create_turma_card(col_manha, r_idx, t, res)

        # Cabeçalho Coluna Tarde (sem emoji)
        hdr_tarde = ctk.CTkFrame(col_tarde, fg_color=ABC_TEAL_DARK, corner_radius=8)
        hdr_tarde.grid(row=0, column=0, padx=4, pady=(2, 6), sticky="ew")
        ctk.CTkLabel(
            hdr_tarde,
            text=f"Turmas da Tarde ({len(turmas_tarde)} sala(s))",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#FFFFFF",
        ).pack(padx=12, pady=6, anchor="w")

        for r_idx, t in enumerate(turmas_tarde, start=1):
            self._create_turma_card(col_tarde, r_idx, t, res)

        # 3. Atualiza opções de filtro e tabela da Aba 3 (Consulta de Turmas e Alunos)
        turma_codes = ["Todas as Turmas"] + [t.codigo for t in proc.turmas]
        self.option_filter_turma.configure(values=turma_codes)
        self.var_filter_turma.set("Todas as Turmas")
        self._refresh_consulta_tab()

    def _create_turma_card(
        self,
        parent: ctk.CTkFrame,
        row: int,
        turma: TurmaSpec,
        res: SolverResult,
    ) -> None:
        tot = res.y_turma.get(turma.id, 0)
        m_c = res.z_turma_gen.get((turma.id, GENERO_M), 0)
        f_c = res.z_turma_gen.get((turma.id, GENERO_F), 0)
        cap = turma.capacidade
        livres = max(0, cap - tot)
        ocup_pct = (100.0 * tot / cap) if cap > 0 else 0.0

        accent = ABC_CYAN if turma.turno == TURNO_MANHA else ABC_TEAL_DARK

        card = ctk.CTkFrame(
            parent,
            fg_color=ABC_CARD,
            corner_radius=10,
            border_width=1,
            border_color=ABC_BORDER,
        )
        card.grid(row=row, column=0, padx=4, pady=6, sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.grid(row=0, column=0, padx=14, pady=(10, 4), sticky="ew")
        top.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            top,
            text=turma.codigo,
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=accent,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            top,
            text=f"Lotação: {tot}/{cap} ({ocup_pct:.1f}%) • {livres} livres",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=ABC_TEXT,
            anchor="e",
        ).grid(row=0, column=1, sticky="e")

        # Barra tripartida representando a capacidade total da sala:
        # Azul = meninos (M) | Vermelho = meninas (F) | Cinza = espaços vazios
        bar_canvas = tk.Canvas(
            card,
            height=16,
            bg=COLOR_VAZIO_GRAY,
            highlightthickness=0,
            bd=0,
        )
        bar_canvas.grid(row=1, column=0, padx=14, pady=(2, 6), sticky="ew")

        def _draw_gender_bar(event: Optional[tk.Event] = None) -> None:  # type: ignore[type-arg]
            w = event.width if event is not None else bar_canvas.winfo_width()
            h = bar_canvas.winfo_height() or 16
            if w <= 1:
                return
            bar_canvas.delete("all")
            # Fundo total da barra (espaços vazios em cinza)
            bar_canvas.create_rectangle(0, 0, w, h, fill=COLOR_VAZIO_GRAY, outline="")
            if cap <= 0:
                return

            w_m = round(w * (m_c / cap))
            w_f = round(w * (f_c / cap))
            if livres == 0 and (m_c + f_c) > 0:
                w_f = max(0, w - w_m)
            else:
                w_f = min(w_f, max(0, w - w_m))

            # 1º segmento: Meninos em Azul
            if m_c > 0 and w_m > 0:
                bar_canvas.create_rectangle(0, 0, w_m, h, fill=COLOR_MASC_BLUE, outline="")
            # 2º segmento: Meninas em Vermelho
            if f_c > 0 and w_f > 0:
                bar_canvas.create_rectangle(w_m, 0, w_m + w_f, h, fill=COLOR_FEM_RED, outline="")

        bar_canvas.bind("<Configure>", _draw_gender_bar)

        # Legenda dos 3 segmentos: Meninos (Azul), Meninas (Vermelho) e Vagas Vazias (Cinza)
        legend_frame = ctk.CTkFrame(card, fg_color="transparent")
        legend_frame.grid(row=2, column=0, padx=14, pady=(0, 10), sticky="ew")
        legend_frame.grid_columnconfigure(0, weight=1)
        legend_frame.grid_columnconfigure(1, weight=1)
        legend_frame.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(
            legend_frame,
            text=f"■ Meninos (M): {m_c}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLOR_MASC_BLUE,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            legend_frame,
            text=f"■ Meninas (F): {f_c}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLOR_FEM_RED,
            anchor="center",
        ).grid(row=0, column=1)

        ctk.CTkLabel(
            legend_frame,
            text=f"■ Vagas Vazias: {livres}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLOR_VAZIO_TEXT,
            anchor="e",
        ).grid(row=0, column=2, sticky="e")

    def _refresh_consulta_tab(self) -> None:
        if self.current_outcome is None or not self.current_outcome.solver_result.feasible:
            return

        rows = filter_allocated_students(
            instance=self.current_outcome.processed,
            result=self.current_outcome.solver_result,
            search_query=self.var_search_student.get(),
            turma_filter=self.var_filter_turma.get(),
            genero_filter=self.var_filter_genero.get(),
            sort_by=self.var_sort_order.get(),
        )
        self.lbl_consulta_count.configure(text=f"{len(rows)} aluno(s)")

        sep = "-" * 96
        lines = [
            sep,
            f" {'Nº':>4} | {'Linha Excel':>11} | {'Nome do Aluno':<44} | {'Sexo':^6} | {'Turno':^8} | {'Turma Alocada':<12}",
            sep,
        ]
        for idx, (st, turma) in enumerate(rows, start=1):
            disp_out = turma.turno if st.disponibilidade == "INTEGRAL" else st.disponibilidade
            dup_tag = " *" if st.is_duplicate_name else ""
            nome_fmt = (st.nome + dup_tag)[:44]
            lines.append(
                f" {idx:>4} | {st.row_number:>11} | {nome_fmt:<44} | {st.sexo:^6} | {disp_out:^8} | {turma.codigo:<12}"
            )
        if not rows:
            lines.append("  Nenhum aluno encontrado para os filtros selecionados.")
        lines.append(sep)
        lines.append("  Nota: '*' indica nome homônimo / em duplicidade sinalizado na aba Inconsistências.")

        self._set_textbox_content(self.textbox_consulta, "\n".join(lines))

    # -------------------------------------------------------------------------
    # Callbacks de Eventos do Usuário
    # -------------------------------------------------------------------------
    def _on_select_file(self) -> None:
        if self._is_running:
            return

        initial_dir = PROJECT_ROOT / "instances" / "public"
        if not initial_dir.exists():
            initial_dir = Path.cwd()

        chosen = filedialog.askopenfilename(
            title="Selecionar Planilha de Entrada (.xlsx)",
            initialdir=str(initial_dir),
            filetypes=[
                ("Planilhas Excel", "*.xlsx *.xlsm"),
                ("Todos os arquivos", "*.*"),
            ],
        )
        if not chosen:
            return

        self._load_selected_file(Path(chosen).resolve())

    def _load_selected_file(self, path: Path) -> None:
        self.selected_file_path = path
        self._set_file_entry(str(path))
        self.btn_open_excel.configure(state="normal")
        self.btn_save_turmas.configure(state="normal")
        self.lbl_status_badge.configure(
            text=f"Planilha: {path.name}",
            fg_color="#DBEAFE",
            text_color=ABC_NAVY,
        )

        timestamp = datetime.now().strftime("%H:%M:%S")
        self._append_log(f"\n[{timestamp}] Planilha carregada: {path}\n")

        try:
            raw = read_instance(path)
            processed = pre_process(raw)
            self._populate_from_processed_instance(processed)
            self._append_log(format_validation_log(processed) + "\n")
            self.tabview.set("1. Inconsistências & Validação")
        except Exception as exc:
            self._append_log(f"[ERRO NA LEITURA DA PLANILHA] {exc}\n")
            messagebox.showerror("Erro ao ler planilha", f"Não foi possível ler '{path.name}':\n{exc}")

    def _on_open_in_excel(self) -> None:
        if self.selected_file_path is None:
            return
        try:
            open_file_in_system(self.selected_file_path)
        except Exception as exc:
            messagebox.showerror(
                "Erro ao abrir planilha",
                f"Não foi possível abrir o arquivo automaticamente:\n{exc}",
            )

    def _parse_turmas_entries(self) -> tuple[int, int, int, int]:
        try:
            tm = int(self.var_turmas_manha.get().strip())
            vm = int(self.var_vagas_manha.get().strip())
            tt = int(self.var_turmas_tarde.get().strip())
            vt = int(self.var_vagas_tarde.get().strip())
        except ValueError as exc:
            raise ValueError(
                "Todos os campos de Turmas e Vagas devem ser preenchidos com números inteiros."
            ) from exc
        if any(v < 0 for v in (tm, vm, tt, vt)):
            raise ValueError("Os valores de Turmas e Vagas não podem ser negativos.")
        return tm, vm, tt, vt

    def _apply_turmas_changes_if_needed(self, show_confirmation: bool = False) -> bool:
        if self.selected_file_path is None:
            return False
        try:
            tm, vm, tt, vt = self._parse_turmas_entries()
        except ValueError as exc:
            messagebox.showerror("Valores inválidos de Turmas/Vagas", str(exc))
            return False

        changed = True
        if self.current_processed is not None:
            cur_tm = len(self.current_processed.turmas_por_turno.get(TURNO_MANHA, []))
            cur_tt = len(self.current_processed.turmas_por_turno.get(TURNO_TARDE, []))
            cur_vm = self.current_processed.capacidade_por_turno.get(TURNO_MANHA, 0)
            cur_vt = self.current_processed.capacidade_por_turno.get(TURNO_TARDE, 0)
            changed = (tm, vm, tt, vt) != (cur_tm, cur_vm, cur_tt, cur_vt)

        if not changed and not show_confirmation:
            return True

        try:
            update_turmas_in_excel(self.selected_file_path, tm, vm, tt, vt)
            raw = read_instance(self.selected_file_path)
            proc = pre_process(raw)
            self._populate_from_processed_instance(proc)
            timestamp = datetime.now().strftime("%H:%M:%S")
            self._append_log(
                f"\n[{timestamp}] [AJUSTE DE TURMAS] Aba 'Turmas' atualizada na planilha: "
                f"Manhã={tm}x{vm} ({tm*vm} vagas) | Tarde={tt}x{vt} ({tt*vt} vagas).\n"
            )
            if show_confirmation:
                messagebox.showinfo(
                    "Turmas atualizadas",
                    f"Parâmetros salvos com sucesso na aba 'Turmas' de '{self.selected_file_path.name}'!\n\n"
                    f"• Manhã: {tm} turma(s) x {vm} vagas = {tm * vm} vagas\n"
                    f"• Tarde: {tt} turma(s) x {vt} vagas = {tt * vt} vagas",
                )
            return True
        except PermissionError:
            messagebox.showerror(
                "Planilha aberta no Excel",
                f"Feche o arquivo '{self.selected_file_path.name}' no Excel antes de salvar alterações.",
            )
            return False
        except Exception as exc:
            messagebox.showerror("Erro ao atualizar Turmas", str(exc))
            return False

    def _on_save_turmas_clicked(self) -> None:
        if self._is_running:
            return
        self._apply_turmas_changes_if_needed(show_confirmation=True)

    def _set_running_state(self, running: bool, badge_text: str, badge_bg: str, badge_fg: str) -> None:
        self._is_running = running
        state = "disabled" if running else "normal"
        self.btn_select_file.configure(state=state)
        self.btn_run.configure(state=state)
        self.btn_open_excel.configure(state=state)
        self.btn_save_turmas.configure(state=state)
        self.option_model.configure(state=state)
        self.lbl_status_badge.configure(text=badge_text, fg_color=badge_bg, text_color=badge_fg)

        if running:
            self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start()
        else:
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")
            self.progress_bar.set(1.0)

    def _on_start_ensalamento(self) -> None:
        if self._is_running:
            return

        if self.selected_file_path is None:
            messagebox.showwarning(
                "Planilha não selecionada",
                "Por favor, selecione primeiro uma planilha Excel (.xlsx) antes de iniciar o ensalamento.",
            )
            return

        if not self.selected_file_path.exists():
            messagebox.showerror(
                "Arquivo não encontrado",
                f"O arquivo selecionado não existe:\n{self.selected_file_path}",
            )
            return

        if not self._apply_turmas_changes_if_needed(show_confirmation=False):
            return

        model_label = self.model_var.get()
        self._set_running_state(True, "Otimizando Ensalamento...", "#FEF3C7", COLOR_ALERTA)
        self._append_log("\n" + ("#" * 88) + "\n")

        worker = threading.Thread(
            target=self._run_worker,
            args=(self.selected_file_path, model_label),
            daemon=True,
        )
        worker.start()

    def _run_worker(self, filepath: Path, model_label: str) -> None:
        try:
            outcome = execute_ensalamento_workflow(
                input_excel_path=filepath,
                model_label=model_label,
                excel_output_path=filepath,
                log_callback=lambda msg: self._msg_queue.put(("LOG", msg)),
            )
            self._msg_queue.put(("OUTCOME", outcome))
        except PermissionError:
            err_msg = (
                f"Permissão negada ao gravar no arquivo '{filepath.name}'.\n"
                "Verifique se a planilha não está aberta no Microsoft Excel / LibreOffice e tente novamente."
            )
            self._msg_queue.put(("LOG", f"\n[ERRO DE PERMISSÃO] {err_msg}\n"))
            self._msg_queue.put(("ERROR_DIALOG", err_msg))
        except Exception as exc:
            tb = traceback.format_exc()
            self._msg_queue.put(("LOG", f"\n[ERRO INESPERADO] {exc}\n{tb}\n"))
            self._msg_queue.put(("ERROR_DIALOG", f"Falha durante o processamento:\n{exc}"))

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self._msg_queue.get_nowait()
                if kind == "LOG":
                    self._append_log(str(payload))
                elif kind == "OUTCOME":
                    outcome: GuiPipelineOutcome = payload  # type: ignore[assignment]
                    self._populate_from_processed_instance(outcome.processed)
                    self._populate_dashboard_and_consulta(outcome)
                    if outcome.solver_result.feasible:
                        ms = outcome.solver_result.metrics.total_time_s * 1000
                        self._set_running_state(
                            False,
                            f"Concluído ({ms:.0f} ms)",
                            "#DCFCE7",
                            "#15803D",
                        )
                        self.tabview.set("2. Dashboard do Ensalamento")
                    else:
                        self._set_running_state(
                            False,
                            "Ensalamento Inviável",
                            "#FEE2E2",
                            COLOR_IMPEDITIVA,
                        )
                        self.tabview.set("1. Inconsistências & Validação")
                        messagebox.showwarning(
                            "Ensalamento não concluído",
                            f"Não foi possível alocar as turmas:\n{outcome.solver_result.reason}",
                        )
                elif kind == "ERROR_DIALOG":
                    self._set_running_state(False, "Erro na Execução", "#FEE2E2", COLOR_IMPEDITIVA)
                    messagebox.showerror("Erro ao executar ensalamento", str(payload))
        except queue.Empty:
            pass
        finally:
            self.after(50, self._poll_queue)


def run_gui() -> None:
    """Inicializa e executa o loop principal da interface gráfica."""
    app = EnsalamentoApp()
    app.mainloop()


if __name__ == "__main__":
    run_gui()

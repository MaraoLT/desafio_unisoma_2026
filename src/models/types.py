"""Estruturas de dados, hiperparâmetros, métricas e utilitários determinísticos do solver."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Optional

from src.pre_process import Student, TURNO_MANHA


ProfileKey = tuple[str, tuple[str, ...]]


def _ascii_turno(turno: str) -> str:
    """Converte nome do turno para identificador ASCII seguro para arquivos .lp do CBC."""
    return "MANHA" if turno == TURNO_MANHA else "TARDE"


def _compute_instance_seed(students: list[Student]) -> bytes:
    """Gera uma semente criptográfica determinística exclusiva para o conjunto de alunos da planilha.

    Garante que a seleção para as turmas e para a lista de espera seja:
    1. Aleatória para cada planilha (sem viés de posição/linha no Excel ou de ordem alfabética);
    2. Reprodutível para a mesma planilha (impedindo que se fique gerando salas repetidamente
       ou reordenando linhas na tentativa de escolher os alunos que serão selecionados).
    """
    canonical_entries = sorted(
        f"{st.nome.strip().lower()}|{st.sexo}|{','.join(st.turnos_compativeis)}"
        for st in students
    )
    return hashlib.sha256("\n".join(canonical_entries).encode("utf-8")).digest()


def _order_students_for_spreadsheet(
    students: list[Student], sheet_seed: bytes
) -> list[Student]:
    """Ordena os alunos de forma pseudoaleatória determinística atrelada à semente da planilha."""
    canonical = sorted(
        students,
        key=lambda st: (
            st.nome.strip().lower(),
            st.sexo,
            st.turnos_compativeis,
            st.row_number,
        ),
    )
    keyed: list[tuple[bytes, int, Student]] = []
    for occ_idx, st in enumerate(canonical):
        token = (
            f"{st.nome.strip().lower()}|{st.sexo}|{','.join(st.turnos_compativeis)}|{occ_idx}"
        ).encode("utf-8")
        draw_hash = hashlib.sha256(sheet_seed + b"|" + token).digest()
        keyed.append((draw_hash, st.row_number, st))
    keyed.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in keyed]


def _sum_pairwise_abs(vals: list[int]) -> float:
    """Calcula exatamente sum_{a < b} |vals[a] - vals[b]| em O(m log m)."""
    m = len(vals)
    if m < 2:
        return 0.0
    arr = sorted(vals)
    return float(sum((2 * idx - m + 1) * arr[idx] for idx in range(m)))


@dataclass
class SolverParameters:
    """Hiperparâmetros do modelo de otimização matemática."""

    w_qtd: float = 1.0
    w_gen: float = 1.0
    epsilon: float = 1e-4
    enable_phase2: bool = True
    auto_skip_phase2: bool = False
    allow_unallocated: bool = False
    use_decomposition: bool = True
    time_limit_s: Optional[int] = 60
    msg: bool = False


@dataclass
class SolverMetrics:
    """Métricas de execução, tempo e dimensão do problema MILP."""

    solver_name: str
    status_phase1: str
    status_phase2: str
    z1_objective: Optional[float]
    z2_objective: Optional[float]
    z2_pairwise_pure: Optional[float]
    build_time_s: float
    phase1_wall_time_s: float
    phase1_solver_time_s: float
    phase2_wall_time_s: float
    phase2_solver_time_s: float
    total_time_s: float
    num_variables: int
    num_binary_vars: int
    num_integer_vars: int
    num_continuous_vars: int
    num_constraints_phase1: int
    num_constraints_phase2: int
    num_unallocated: int = 0


@dataclass
class SolverResult:
    """Resultado completo retornado pelo solver de ensalamento."""

    feasible: bool
    optimal: bool
    reason: str
    params: SolverParameters
    metrics: SolverMetrics
    # Mapeamentos da solução (vazios se inviável)
    student_to_turma: dict[int, int] = field(default_factory=dict)  # student.id -> turma.id
    unallocated_students: list[int] = field(default_factory=list)  # student.id sem turma
    y_turma: dict[int, int] = field(default_factory=dict)  # turma.id -> lotação total
    z_turma_gen: dict[tuple[int, str], int] = field(default_factory=dict)  # (turma.id, g) -> qtd
    delta_qtd: dict[str, float] = field(default_factory=dict)  # turno -> amplitude máx qtd
    delta_gen: dict[tuple[str, str], float] = field(default_factory=dict)  # (turno, g) -> amp máx
    delta_intra: dict[str, float] = field(default_factory=dict)  # turno -> máx |M - F|
    d_intra: dict[int, float] = field(default_factory=dict)  # turma.id -> |M - F|


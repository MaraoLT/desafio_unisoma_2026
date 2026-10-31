"""Solver de Programação Inteira Mista (MILP) com Otimização Lexicográfica em PuLP.

Implementa a modelagem matemática da Equipe 10 | Grupo 20:
- Fase 1 (Pior Caso / Min-Max): minimiza amplitudes máximas de quantidade e gênero por turno.
- Fase 2 (Suavização Interna Par-a-Par): trava Z1* ótimo e minimiza a soma das
  diferenças absolutas par-a-par entre turmas do mesmo turno (com termo secundário
  epsilon para equilíbrio intra-turma 50/50).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Optional

import pulp

from src.pre_process import (
    GENERO_F,
    GENERO_M,
    GENEROS,
    TURNO_MANHA,
    TURNO_TARDE,
    ProcessedInstance,
)


def _ascii_turno(turno: str) -> str:
    """Converte nome do turno para identificador ASCII seguro para arquivos .lp do CBC."""
    return "MANHA" if turno == TURNO_MANHA else "TARDE"


@dataclass
class SolverParameters:
    """Hiperparâmetros do modelo de otimização matemática."""

    w_qtd: float = 1.0
    w_gen: float = 1.0
    epsilon: float = 1e-4
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
    y_turma: dict[int, int] = field(default_factory=dict)  # turma.id -> lotação total
    z_turma_gen: dict[tuple[int, str], int] = field(default_factory=dict)  # (turma.id, g) -> qtd
    delta_qtd: dict[str, float] = field(default_factory=dict)  # turno -> amplitude máx qtd
    delta_gen: dict[tuple[str, str], float] = field(default_factory=dict)  # (turno, g) -> amp máx
    delta_intra: dict[str, float] = field(default_factory=dict)  # turno -> máx |M - F|
    d_intra: dict[int, float] = field(default_factory=dict)  # turma.id -> |M - F|


def solve_ensalamento(
    instance: ProcessedInstance,
    params: Optional[SolverParameters] = None,
) -> SolverResult:
    """Constrói e resolve o modelo lexicográfico de duas etapas usando PuLP (CBC)."""
    if params is None:
        params = SolverParameters()

    t_total_start = time.perf_counter()

    # Pré-checagens rápidas de viabilidade estrutural
    if not instance.students:
        elapsed = time.perf_counter() - t_total_start
        return SolverResult(
            feasible=False,
            optimal=False,
            reason="Nenhum aluno válido disponível no conjunto I para alocação.",
            params=params,
            metrics=SolverMetrics(
                solver_name="PULP_CBC_CMD",
                status_phase1="Not Solved (Empty Set I)",
                status_phase2="Not Solved",
                z1_objective=None,
                z2_objective=None,
                z2_pairwise_pure=None,
                build_time_s=elapsed,
                phase1_wall_time_s=0.0,
                phase1_solver_time_s=0.0,
                phase2_wall_time_s=0.0,
                phase2_solver_time_s=0.0,
                total_time_s=elapsed,
                num_variables=0,
                num_binary_vars=0,
                num_integer_vars=0,
                num_continuous_vars=0,
                num_constraints_phase1=0,
                num_constraints_phase2=0,
            ),
        )

    for st in instance.students:
        if not instance.turmas_compativeis_por_aluno.get(st.id):
            elapsed = time.perf_counter() - t_total_start
            return SolverResult(
                feasible=False,
                optimal=False,
                reason=(
                    f"Aluno '{st.nome}' (linha {st.row_number}) não possui nenhuma turma "
                    f"compatível ofertada no turno '{st.disponibilidade}'."
                ),
                params=params,
                metrics=SolverMetrics(
                    solver_name="PULP_CBC_CMD",
                    status_phase1="Infeasible (No Compatible Classes)",
                    status_phase2="Not Solved",
                    z1_objective=None,
                    z2_objective=None,
                    z2_pairwise_pure=None,
                    build_time_s=elapsed,
                    phase1_wall_time_s=0.0,
                    phase1_solver_time_s=0.0,
                    phase2_wall_time_s=0.0,
                    phase2_solver_time_s=0.0,
                    total_time_s=elapsed,
                    num_variables=0,
                    num_binary_vars=0,
                    num_integer_vars=0,
                    num_continuous_vars=0,
                    num_constraints_phase1=0,
                    num_constraints_phase2=0,
                ),
            )

    # =========================================================================
    # 1. CONSTRUÇÃO DO MODELO MATEMÁTICO
    # =========================================================================
    t_build_start = time.perf_counter()
    prob = pulp.LpProblem("Desafio_UniSoma_2026_Ensalamento", pulp.LpMinimize)

    students = instance.students
    turmas = instance.turmas
    K_ids = [t.id for t in turmas]
    S_active = [
        s for s in (TURNO_MANHA, TURNO_TARDE) if len(instance.turmas_por_turno.get(s, [])) > 0
    ]
    K_s: dict[str, list[int]] = {
        s: [t.id for t in instance.turmas_por_turno[s]] for s in S_active
    }
    C_s = instance.capacidade_por_turno
    K_i = instance.turmas_compativeis_por_aluno
    K_i_sets = {i_id: set(k_list) for i_id, k_list in K_i.items()}
    I_g = instance.alunos_por_genero

    # --- Variáveis de Decisão ---
    # x_{i,k} in {0, 1}: alocação do aluno i na turma compatível k
    x: dict[tuple[int, int], pulp.LpVariable] = {}
    for st in students:
        for k in K_i[st.id]:
            x[(st.id, k)] = pulp.LpVariable(f"x_{st.id}_{k}", cat=pulp.LpBinary)

    # y_k in Z_>=0: lotação total da turma k
    y: dict[int, pulp.LpVariable] = {
        k: pulp.LpVariable(f"y_{k}", lowBound=0, cat=pulp.LpInteger) for k in K_ids
    }

    # z_{k,g} in Z_>=0: quantidade de alunos do gênero g na turma k
    z: dict[tuple[int, str], pulp.LpVariable] = {
        (k, g): pulp.LpVariable(f"z_{k}_{g}", lowBound=0, cat=pulp.LpInteger)
        for k in K_ids
        for g in GENEROS
    }

    # Variáveis de desvio de quantidade: Delta_s^qtd e d_{k,k'}^qtd
    delta_qtd: dict[str, pulp.LpVariable] = {
        s: pulp.LpVariable(f"Delta_qtd_{_ascii_turno(s)}", lowBound=0, cat=pulp.LpContinuous)
        for s in S_active
    }
    d_qtd: dict[tuple[int, int], pulp.LpVariable] = {}
    for s in S_active:
        ks_list = K_s[s]
        for idx_a in range(len(ks_list)):
            for idx_b in range(idx_a + 1, len(ks_list)):
                k, kp = ks_list[idx_a], ks_list[idx_b]
                d_qtd[(k, kp)] = pulp.LpVariable(
                    f"d_qtd_{k}_{kp}", lowBound=0, cat=pulp.LpContinuous
                )

    # Variáveis de desvio inter-turmas de gênero: Delta_{s,g}^gen e d_{k,k',g}^gen
    delta_gen: dict[tuple[str, str], pulp.LpVariable] = {
        (s, g): pulp.LpVariable(
            f"Delta_gen_{_ascii_turno(s)}_{g}", lowBound=0, cat=pulp.LpContinuous
        )
        for s in S_active
        for g in GENEROS
    }
    d_gen: dict[tuple[int, int, str], pulp.LpVariable] = {}
    for s in S_active:
        ks_list = K_s[s]
        for g in GENEROS:
            for idx_a in range(len(ks_list)):
                for idx_b in range(idx_a + 1, len(ks_list)):
                    k, kp = ks_list[idx_a], ks_list[idx_b]
                    d_gen[(k, kp, g)] = pulp.LpVariable(
                        f"d_gen_{k}_{kp}_{g}", lowBound=0, cat=pulp.LpContinuous
                    )

    # Variáveis de equilíbrio intra-turma (50/50): d_k^intra e Delta_s^intra
    d_intra: dict[int, pulp.LpVariable] = {
        k: pulp.LpVariable(f"d_intra_{k}", lowBound=0, cat=pulp.LpContinuous) for k in K_ids
    }
    delta_intra: dict[str, pulp.LpVariable] = {
        s: pulp.LpVariable(f"Delta_intra_{_ascii_turno(s)}", lowBound=0, cat=pulp.LpContinuous)
        for s in S_active
    }

    # --- Restrições ---
    # 1. Alocação Obrigatória e Respeito à Disponibilidade (Eq. 3)
    for st in students:
        prob += (
            pulp.lpSum(x[(st.id, k)] for k in K_i[st.id]) == 1,
            f"R1_aloc_aluno_{st.id}",
        )

    # 2. Contabilização de Alunos por Gênero (Eq. 4)
    for k in K_ids:
        for g in GENEROS:
            eligible_students = [i_id for i_id in I_g[g] if k in K_i_sets[i_id]]
            prob += (
                pulp.lpSum(x[(i_id, k)] for i_id in eligible_students) - z[(k, g)] == 0,
                f"R2_cont_gen_{k}_{g}",
            )

    # 3. Contabilização da Lotação Total (Eq. 5)
    for k in K_ids:
        prob += (
            pulp.lpSum(z[(k, g)] for g in GENEROS) - y[k] == 0,
            f"R3_cont_total_{k}",
        )

    # 4. Limite de Capacidade Máxima por Turma (Eq. 6)
    for s in S_active:
        cap = C_s[s]
        for k in K_s[s]:
            prob += (y[k] <= cap, f"R4_cap_max_{k}")

    # 5. Quebra de Simetria - Ordenação Decrescente Intra-Turno (Eq. 7)
    for s in S_active:
        ks_list = K_s[s]
        for idx in range(len(ks_list) - 1):
            k_curr, k_next = ks_list[idx], ks_list[idx + 1]
            prob += (
                y[k_curr] - y[k_next] >= 0,
                f"R5_simetria_{_ascii_turno(s)}_{k_curr}_{k_next}",
            )

    # 6. Equilíbrio em Quantidade - Amplitude Máxima e Par-a-Par (Eqs. 8 e 9)
    for s in S_active:
        ks_list = K_s[s]
        k_first, k_last = ks_list[0], ks_list[-1]
        prob += (
            y[k_first] - y[k_last] - delta_qtd[s] == 0,
            f"R6_amp_qtd_{_ascii_turno(s)}",
        )
        for idx_a in range(len(ks_list)):
            for idx_b in range(idx_a + 1, len(ks_list)):
                k, kp = ks_list[idx_a], ks_list[idx_b]
                prob += (
                    y[k] - y[kp] - d_qtd[(k, kp)] == 0,
                    f"R6_par_qtd_{k}_{kp}",
                )

    # 7. Equilíbrio Intra-Turma de Gênero - Busca pelo 50/50 (Eqs. 10, 11 e 12)
    for s in S_active:
        for k in K_s[s]:
            prob += (
                d_intra[k] - z[(k, GENERO_M)] + z[(k, GENERO_F)] >= 0,
                f"R7_intra_pos_{k}",
            )
            prob += (
                d_intra[k] - z[(k, GENERO_F)] + z[(k, GENERO_M)] >= 0,
                f"R7_intra_neg_{k}",
            )
            prob += (
                delta_intra[s] - d_intra[k] >= 0,
                f"R7_amp_intra_{_ascii_turno(s)}_{k}",
            )

    # 8. Equilíbrio Inter-Turmas de Gênero (Linearização de d_{k,k',g}^gen e Delta_{s,g}^gen)
    for s in S_active:
        ks_list = K_s[s]
        for g in GENEROS:
            if len(ks_list) <= 1:
                prob += (
                    delta_gen[(s, g)] == 0,
                    f"R8_amp_gen_single_{_ascii_turno(s)}_{g}",
                )
            else:
                for idx_a in range(len(ks_list)):
                    for idx_b in range(idx_a + 1, len(ks_list)):
                        k, kp = ks_list[idx_a], ks_list[idx_b]
                        prob += (
                            d_gen[(k, kp, g)] - z[(k, g)] + z[(kp, g)] >= 0,
                            f"R8_par_gen_pos_{k}_{kp}_{g}",
                        )
                        prob += (
                            d_gen[(k, kp, g)] - z[(kp, g)] + z[(k, g)] >= 0,
                            f"R8_par_gen_neg_{k}_{kp}_{g}",
                        )
                        prob += (
                            delta_gen[(s, g)] - d_gen[(k, kp, g)] >= 0,
                            f"R8_amp_gen_{_ascii_turno(s)}_{k}_{kp}_{g}",
                        )

    num_binary = len(x)
    num_integer = len(y) + len(z)
    num_continuous = (
        len(delta_qtd) + len(d_qtd) + len(delta_gen) + len(d_gen) + len(d_intra) + len(delta_intra)
    )
    num_total_vars = num_binary + num_integer + num_continuous
    num_constraints_p1 = len(prob.constraints)

    build_time_s = time.perf_counter() - t_build_start

    # =========================================================================
    # 2. FASE 1: OTIMIZAÇÃO DO PIOR CASO (Eq. 1)
    # =========================================================================
    custo_fase1_expr = pulp.lpSum(
        params.w_qtd * delta_qtd[s]
        + params.w_gen * pulp.lpSum(delta_gen[(s, g)] for g in GENEROS)
        for s in S_active
    )
    prob.setObjective(custo_fase1_expr)

    cbc_phase1 = pulp.PULP_CBC_CMD(msg=params.msg, timeLimit=params.time_limit_s)
    t_p1_start = time.perf_counter()
    status_code_p1 = prob.solve(cbc_phase1)
    phase1_wall_s = time.perf_counter() - t_p1_start
    phase1_solver_s = float(getattr(prob, "solutionTime", phase1_wall_s))
    status_p1_str = pulp.LpStatus.get(status_code_p1, str(status_code_p1))

    if status_code_p1 != pulp.LpStatusOptimal:
        total_elapsed = time.perf_counter() - t_total_start
        return SolverResult(
            feasible=False,
            optimal=False,
            reason=f"Fase 1 encerrou sem solução ótima (Status: {status_p1_str}).",
            params=params,
            metrics=SolverMetrics(
                solver_name="PULP_CBC_CMD",
                status_phase1=status_p1_str,
                status_phase2="Skipped",
                z1_objective=None,
                z2_objective=None,
                z2_pairwise_pure=None,
                build_time_s=build_time_s,
                phase1_wall_time_s=phase1_wall_s,
                phase1_solver_time_s=phase1_solver_s,
                phase2_wall_time_s=0.0,
                phase2_solver_time_s=0.0,
                total_time_s=total_elapsed,
                num_variables=num_total_vars,
                num_binary_vars=num_binary,
                num_integer_vars=num_integer,
                num_continuous_vars=num_continuous,
                num_constraints_phase1=num_constraints_p1,
                num_constraints_phase2=num_constraints_p1,
            ),
        )

    z1_star = float(pulp.value(custo_fase1_expr))

    # Guarda snapshot da solução ótima da Fase 1 como fallback seguro
    p1_student_to_turma = {
        st.id: k
        for st in students
        for k in K_i[st.id]
        if (pulp.value(x[(st.id, k)]) or 0.0) > 0.5
    }
    p1_y = {k: int(round(pulp.value(y[k]) or 0.0)) for k in K_ids}
    p1_z = {(k, g): int(round(pulp.value(z[(k, g)]) or 0.0)) for k in K_ids for g in GENEROS}

    # =========================================================================
    # 3. FASE 2: SUAVIZAÇÃO INTERNA PAR-A-PAR (Eq. 2) + TERMO SECUNDÁRIO EPSILON
    # =========================================================================
    # Trava o limite de qualidade ótimo encontrado na Fase 1 (Custo Fase 1 <= Z1*)
    prob += (custo_fase1_expr <= z1_star + 1e-5, "Lock_Custo_Fase_1")
    num_constraints_p2 = len(prob.constraints)

    pairwise_pure_expr = pulp.lpSum(
        params.w_qtd
        * pulp.lpSum(
            d_qtd[(ks_list[i], ks_list[j])]
            for i in range(len(ks_list))
            for j in range(i + 1, len(ks_list))
        )
        + params.w_gen
        * pulp.lpSum(
            d_gen[(ks_list[i], ks_list[j], g)]
            for g in GENEROS
            for i in range(len(ks_list))
            for j in range(i + 1, len(ks_list))
        )
        for s in S_active
        for ks_list in (K_s[s],)
    )

    intra_smoothing_expr = pulp.lpSum(
        delta_intra[s] + pulp.lpSum(d_intra[k] for k in K_s[s]) for s in S_active
    )

    custo_fase2_expr = pairwise_pure_expr + params.epsilon * intra_smoothing_expr
    prob.setObjective(custo_fase2_expr)

    cbc_phase2 = pulp.PULP_CBC_CMD(
        msg=params.msg,
        timeLimit=params.time_limit_s,
    )
    t_p2_start = time.perf_counter()
    status_code_p2 = prob.solve(cbc_phase2)
    phase2_wall_s = time.perf_counter() - t_p2_start
    phase2_solver_s = float(getattr(prob, "solutionTime", phase2_wall_s))
    status_p2_str = pulp.LpStatus.get(status_code_p2, str(status_code_p2))

    # Extração da solução final (usa Fase 2 se ótima, caso contrário preserva Fase 1 ótima)
    if status_code_p2 == pulp.LpStatusOptimal:
        student_to_turma = {
            st.id: k
            for st in students
            for k in K_i[st.id]
            if (pulp.value(x[(st.id, k)]) or 0.0) > 0.5
        }
        y_vals = {k: int(round(pulp.value(y[k]) or 0.0)) for k in K_ids}
        z_vals = {
            (k, g): int(round(pulp.value(z[(k, g)]) or 0.0)) for k in K_ids for g in GENEROS
        }
        z2_obj = float(pulp.value(custo_fase2_expr) or 0.0)
        z2_pure = float(pulp.value(pairwise_pure_expr) or 0.0)
        is_opt = True
        reason_msg = "Solução ótima global alcançada nas Fases 1 e 2 (Otimização Lexicográfica)."
    else:
        student_to_turma = p1_student_to_turma
        y_vals = p1_y
        z_vals = p1_z
        z2_obj = None
        z2_pure = None
        is_opt = True
        reason_msg = (
            f"Fase 1 ótima alcançada; Fase 2 retornou '{status_p2_str}', "
            "mantendo alocação ótima da Fase 1."
        )

    # Recalcula desvios exatos a partir dos inteiros y_vals e z_vals
    res_delta_qtd: dict[str, float] = {}
    res_delta_gen: dict[tuple[str, str], float] = {}
    res_d_intra: dict[int, float] = {}
    res_delta_intra: dict[str, float] = {}

    for k in K_ids:
        res_d_intra[k] = float(abs(z_vals[(k, GENERO_M)] - z_vals[(k, GENERO_F)]))

    for s in S_active:
        ks_list = K_s[s]
        lots = [y_vals[k] for k in ks_list]
        res_delta_qtd[s] = float(max(lots) - min(lots)) if lots else 0.0
        for g in GENEROS:
            g_counts = [z_vals[(k, g)] for k in ks_list]
            res_delta_gen[(s, g)] = float(max(g_counts) - min(g_counts)) if g_counts else 0.0
        res_delta_intra[s] = max((res_d_intra[k] for k in ks_list), default=0.0)

    total_elapsed = time.perf_counter() - t_total_start

    return SolverResult(
        feasible=True,
        optimal=is_opt,
        reason=reason_msg,
        params=params,
        metrics=SolverMetrics(
            solver_name="PULP_CBC_CMD",
            status_phase1=status_p1_str,
            status_phase2=status_p2_str,
            z1_objective=z1_star,
            z2_objective=z2_obj,
            z2_pairwise_pure=z2_pure,
            build_time_s=build_time_s,
            phase1_wall_time_s=phase1_wall_s,
            phase1_solver_time_s=phase1_solver_s,
            phase2_wall_time_s=phase2_wall_s,
            phase2_solver_time_s=phase2_solver_s,
            total_time_s=total_elapsed,
            num_variables=num_total_vars,
            num_binary_vars=num_binary,
            num_integer_vars=num_integer,
            num_continuous_vars=num_continuous,
            num_constraints_phase1=num_constraints_p1,
            num_constraints_phase2=num_constraints_p2,
        ),
        student_to_turma=student_to_turma,
        y_turma=y_vals,
        z_turma_gen=z_vals,
        delta_qtd=res_delta_qtd,
        delta_gen=res_delta_gen,
        delta_intra=res_delta_intra,
        d_intra=res_d_intra,
    )

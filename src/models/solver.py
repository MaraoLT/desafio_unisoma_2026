"""Solver de Programação Inteira Mista (MILP) com Otimização Lexicográfica em PuLP.

Implementa a modelagem matemática da Equipe 10 | Grupo 20 com:
- Agregação por Perfis Demográficos (eliminação de simetria combinatória de alunos).
- Decomposição Hierárquica Exata em Duas Etapas:
    * Etapa Hierárquica 1 (Macro): Partição ótima dos perfis entre os turnos (Manhã/Tarde
      e eventual lista de espera) via decomposição euclidiana exata em MILP (PuLP/CBC),
      otimizando lexicograficamente Fase 1 (Min-Max) e Fase 2 (Par-a-Par + paridade 50/50).
    * Etapa Hierárquica 2 (Micro Intra-Turno): Subproblemas MILP independentes por turno
      com variáveis agregadas de fluxo por perfil nas salas e cortes exatos no nó raiz.
- Modo legado monolítico opcional (`use_decomposition=False`) preservado para comparação.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import math
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


def compute_min_unallocated(instance: ProcessedInstance) -> int:
    """Calcula analiticamente (Teorema de Hall) o mínimo exato de alunos sem vaga."""
    cap_m = len(instance.turmas_por_turno[TURNO_MANHA]) * instance.capacidade_por_turno[TURNO_MANHA]
    cap_t = len(instance.turmas_por_turno[TURNO_TARDE]) * instance.capacidade_por_turno[TURNO_TARDE]

    only_m = sum(1 for s in instance.students if s.turnos_compativeis == (TURNO_MANHA,))
    only_t = sum(1 for s in instance.students if s.turnos_compativeis == (TURNO_TARDE,))
    both_mt = sum(
        1
        for s in instance.students
        if TURNO_MANHA in s.turnos_compativeis and TURNO_TARDE in s.turnos_compativeis
    )
    none_t = len(instance.students) - only_m - only_t - both_mt

    def_m = max(0, only_m - cap_m)
    free_m = max(0, cap_m - only_m)

    def_t = max(0, only_t - cap_t)
    free_t = max(0, cap_t - only_t)

    def_int = max(0, both_mt - (free_m + free_t))
    return none_t + def_m + def_t + def_int


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

    if not instance.turmas:
        elapsed = time.perf_counter() - t_total_start
        return SolverResult(
            feasible=False,
            optimal=False,
            reason="Nenhuma turma ofertada no conjunto K para alocação.",
            params=params,
            metrics=SolverMetrics(
                solver_name="PULP_CBC_CMD",
                status_phase1="Infeasible (No Classes Offered)",
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
                num_unallocated=len(instance.students),
            ),
        )

    min_unalloc_hall = compute_min_unallocated(instance)

    if not params.allow_unallocated:
        for st in instance.students:
            if not instance.turmas_compativeis_por_aluno.get(st.id):
                elapsed = time.perf_counter() - t_total_start
                return SolverResult(
                    feasible=False,
                    optimal=False,
                    reason=(
                        f"Aluno '{st.nome}' (linha {st.row_number}) não possui nenhuma turma "
                        f"compatível ofertada no turno '{st.disponibilidade}' "
                        "(ative --allow-unallocated para alocação parcial)."
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
                        num_unallocated=min_unalloc_hall,
                    ),
                )

        if min_unalloc_hall > 0:
            elapsed = time.perf_counter() - t_total_start
            return SolverResult(
                feasible=False,
                optimal=False,
                reason=(
                    f"Capacidade insuficiente: pelo menos {min_unalloc_hall} aluno(s) não possui(em) "
                    "vaga compatível disponível (ative --allow-unallocated para ensalar o máximo "
                    "possível e gerar lista de espera)."
                ),
                params=params,
                metrics=SolverMetrics(
                    solver_name="PULP_CBC_CMD",
                    status_phase1="Infeasible (Capacity Deficit)",
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
                    num_unallocated=min_unalloc_hall,
                ),
            )

    if params.use_decomposition and params.w_qtd > 0 and params.w_gen > 0:
        return _solve_decomposed_aggregated(instance, params, t_total_start, min_unalloc_hall)
    return _solve_monolithic(instance, params, t_total_start, min_unalloc_hall)


def _sum_pairwise_abs(vals: list[int]) -> float:
    """Calcula exatamente sum_{a < b} |vals[a] - vals[b]| em O(m log m)."""
    m = len(vals)
    if m < 2:
        return 0.0
    arr = sorted(vals)
    return float(sum((2 * idx - m + 1) * arr[idx] for idx in range(m)))


def _solve_decomposed_aggregated(
    instance: ProcessedInstance,
    params: SolverParameters,
    t_total_start: float,
    min_unalloc_hall: int,
) -> SolverResult:
    """Resolve o ensalamento via Agregação por Perfis + Decomposição Hierárquica em 2 Etapas.

    Etapa Hierárquica 1 (Macro):
        Agrupa os alunos em perfis discretos p = (gênero, turnos_compatíveis) e resolve um
        MILP Macro em PuLP/CBC para determinar os fluxos exatos por turno (e lista de espera),
        otimizando lexicograficamente Fase 1 (Z1*) e Fase 2 (Z2* par-a-par + paridade 50/50).
    Etapa Hierárquica 2 (Micro Intra-Turno por Configurações de Sala):
        Com os totais por turno fixados, decompõe o problema em subproblemas MILP 100%
        independentes para MANHÃ e TARDE sobre as configurações inteiras ótimas de sala,
        seguidos de projeção nominal bijetiva determinística em O(N).
    """
    t_build_start = time.perf_counter()

    students = instance.students
    turmas = instance.turmas
    K_ids = [t.id for t in turmas]
    S_active = [
        s for s in (TURNO_MANHA, TURNO_TARDE) if len(instance.turmas_por_turno.get(s, [])) > 0
    ]
    K_s: dict[str, list[int]] = {
        s: [t.id for t in instance.turmas_por_turno[s]] for s in S_active
    }
    K_s_sets: dict[str, set[int]] = {s: set(K_s[s]) for s in S_active}
    C_s = instance.capacidade_por_turno
    K_i = instance.turmas_compativeis_por_aluno

    # -------------------------------------------------------------------------
    # Passo 0: Agregação O(N) dos alunos nos perfis demográficos p = (sexo, turnos_ativos)
    #          Cache por id(K_i[st.id]) evita materializar N conjuntos de salas em ultra-escala
    # -------------------------------------------------------------------------
    ProfileKey = tuple[str, tuple[str, ...]]
    buckets: dict[ProfileKey, list] = defaultdict(list)
    avail_cache: dict[int, Optional[tuple[str, ...]]] = {}
    for st in students:
        k_list = K_i[st.id]
        list_id = id(k_list)
        if list_id not in avail_cache:
            k_set = set(k_list)
            cand_s = tuple(s for s in S_active if K_s_sets[s].issubset(k_set))
            expected_union = set().union(*(K_s_sets[s] for s in cand_s)) if cand_s else set()
            avail_cache[list_id] = cand_s if expected_union == k_set else None
        avail_s = avail_cache[list_id]
        # Segurança: se algum aluno hipotético tiver elegibilidade parcial intra-turno, usa monolítico
        if avail_s is None:
            return _solve_monolithic(instance, params, t_total_start, min_unalloc_hall)
        buckets[(st.sexo, avail_s)].append(st)

    profile_keys = sorted(buckets.keys(), key=lambda pk: (pk[0], len(pk[1]), pk[1]))
    u_star = min_unalloc_hall if params.allow_unallocated else 0

    total_build_s = 0.0
    total_p1_wall_s = 0.0
    total_p1_solver_s = 0.0
    total_p2_wall_s = 0.0
    total_p2_solver_s = 0.0
    total_binary_vars = 0
    total_integer_vars = 0
    total_continuous_vars = 0
    total_cons_p1 = 0
    total_cons_p2 = 0

    has_multi_shift_profiles = any(len(pk[1]) > 1 for pk in profile_keys)
    needs_macro_milp = has_multi_shift_profiles or (u_star > 0)

    macro_flow: dict[tuple[ProfileKey, str], int] = {}
    macro_unalloc: dict[ProfileKey, int] = {}
    macro_p1_optimal = True
    macro_p2_optimal = True
    macro_status_p1 = "Optimal (Analytical Decoupled)"
    macro_status_p2 = "Disabled (Phase 1 Only)" if not params.enable_phase2 else "Optimal"

    # =========================================================================
    # ETAPA HIERÁRQUICA 1: PARTIÇÃO MACRO ENTRE TURNOS (MILP AGREGADO)
    # =========================================================================
    if not needs_macro_milp:
        # Turnos 100% desacoplados desde a origem (sem Integrais e sem déficit de vagas)
        for pk in profile_keys:
            cnt = len(buckets[pk])
            macro_unalloc[pk] = 0
            for s in pk[1]:
                macro_flow[(pk, s)] = cnt
        total_build_s += time.perf_counter() - t_build_start
    else:
        prob_macro = pulp.LpProblem("Etapa1_Macro_Particao_Turnos", pulp.LpMinimize)

        f_mac: dict[tuple[ProfileKey, str], pulp.LpVariable] = {}
        u_mac: dict[ProfileKey, pulp.LpVariable] = {}

        for p_idx, pk in enumerate(profile_keys):
            cnt = len(buckets[pk])
            for s in pk[1]:
                f_mac[(pk, s)] = pulp.LpVariable(
                    f"f_mac_{p_idx}_{_ascii_turno(s)}",
                    lowBound=0,
                    upBound=cnt,
                    cat=pulp.LpInteger,
                )
            if params.allow_unallocated:
                u_mac[pk] = pulp.LpVariable(
                    f"u_mac_{p_idx}", lowBound=0, upBound=cnt, cat=pulp.LpInteger
                )

        # Conservação de cada perfil demográfico
        for p_idx, pk in enumerate(profile_keys):
            cnt = len(buckets[pk])
            flow_terms = [f_mac[(pk, s)] for s in pk[1]]
            if params.allow_unallocated:
                prob_macro += (
                    pulp.lpSum(flow_terms) + u_mac[pk] == cnt,
                    f"M_cons_perfil_{p_idx}",
                )
            else:
                prob_macro += (pulp.lpSum(flow_terms) == cnt, f"M_cons_perfil_{p_idx}")

        if params.allow_unallocated:
            prob_macro += (
                pulp.lpSum(u_mac[pk] for pk in profile_keys) == u_star,
                "M_min_unalloc_exact",
            )

        # Totais por turno N_{s,g} e N_s e decomposição euclidiana exata (q, beta)
        N_sg: dict[tuple[str, str], pulp.LpVariable] = {}
        N_s_tot: dict[str, pulp.LpVariable] = {}
        delta_qtd_mac: dict[str, pulp.LpAffineExpression | pulp.LpVariable] = {}
        delta_gen_mac: dict[tuple[str, str], pulp.LpAffineExpression | pulp.LpVariable] = {}
        pair_qtd_mac: dict[str, pulp.LpAffineExpression] = {}
        pair_gen_mac: dict[tuple[str, str], pulp.LpAffineExpression] = {}
        s_intra_mac: dict[str, pulp.LpVariable] = {}
        d_max_intra_mac: dict[str, pulp.LpVariable] = {}

        mac_bin = 0
        mac_int = len(f_mac) + len(u_mac)
        mac_cont = 0

        for s in S_active:
            ms = len(K_s[s])
            cap = C_s[s]
            cap_shift = ms * cap
            ts_tag = _ascii_turno(s)

            for g in GENEROS:
                N_sg[(s, g)] = pulp.LpVariable(
                    f"N_{ts_tag}_{g}", lowBound=0, upBound=cap_shift, cat=pulp.LpInteger
                )
                mac_int += 1
                in_terms = [f_mac[(pk, s)] for pk in profile_keys if pk[0] == g and s in pk[1]]
                prob_macro += (
                    pulp.lpSum(in_terms) - N_sg[(s, g)] == 0,
                    f"M_tot_{ts_tag}_{g}",
                )

            N_s_tot[s] = pulp.LpVariable(
                f"N_tot_{ts_tag}", lowBound=0, upBound=cap_shift, cat=pulp.LpInteger
            )
            mac_int += 1
            prob_macro += (
                N_sg[(s, GENERO_M)] + N_sg[(s, GENERO_F)] - N_s_tot[s] == 0,
                f"M_sum_tot_{ts_tag}",
            )
            prob_macro += (N_s_tot[s] <= cap_shift, f"M_cap_{ts_tag}")

            s_intra_mac[s] = pulp.LpVariable(
                f"S_intra_{ts_tag}", lowBound=0, cat=pulp.LpContinuous
            )
            d_max_intra_mac[s] = pulp.LpVariable(
                f"Dmax_intra_{ts_tag}", lowBound=0, cat=pulp.LpContinuous
            )
            mac_cont += 2
            prob_macro += (
                s_intra_mac[s] - N_sg[(s, GENERO_M)] + N_sg[(s, GENERO_F)] >= 0,
                f"M_sintra_pos_{ts_tag}",
            )
            prob_macro += (
                s_intra_mac[s] - N_sg[(s, GENERO_F)] + N_sg[(s, GENERO_M)] >= 0,
                f"M_sintra_neg_{ts_tag}",
            )

            if ms == 1:
                delta_qtd_mac[s] = pulp.LpAffineExpression()
                pair_qtd_mac[s] = pulp.LpAffineExpression()
                for g in GENEROS:
                    delta_gen_mac[(s, g)] = pulp.LpAffineExpression()
                    pair_gen_mac[(s, g)] = pulp.LpAffineExpression()
                prob_macro += (
                    d_max_intra_mac[s] - s_intra_mac[s] >= 0,
                    f"M_dintra_single_{ts_tag}",
                )
            else:
                q_qtd = pulp.LpVariable(
                    f"q_qtd_{ts_tag}", lowBound=0, upBound=cap, cat=pulp.LpInteger
                )
                r_qtd = pulp.LpVariable(
                    f"r_qtd_{ts_tag}", lowBound=0, upBound=ms - 1, cat=pulp.LpInteger
                )
                d_qtd = pulp.LpVariable(f"d_qtd_{ts_tag}", cat=pulp.LpBinary)
                mac_int += 2
                mac_bin += 1
                prob_macro += (
                    ms * q_qtd + r_qtd - N_s_tot[s] == 0,
                    f"M_eucl_qtd_{ts_tag}",
                )
                prob_macro += (r_qtd - (ms - 1) * d_qtd <= 0, f"M_rqtd_ub_{ts_tag}")
                prob_macro += (r_qtd - d_qtd >= 0, f"M_rqtd_lb_{ts_tag}")
                delta_qtd_mac[s] = d_qtd

                # Paridade exata de q_qtd para contar salas ímpares em S_intra
                h_par = pulp.LpVariable(
                    f"h_par_{ts_tag}", lowBound=0, upBound=(cap // 2) + 1, cat=pulp.LpInteger
                )
                pi_par = pulp.LpVariable(f"pi_par_{ts_tag}", cat=pulp.LpBinary)
                mac_int += 1
                mac_bin += 1
                prob_macro += (2 * h_par + pi_par - q_qtd == 0, f"M_par_q_{ts_tag}")
                prob_macro += (
                    s_intra_mac[s] - r_qtd + ms * pi_par >= 0,
                    f"M_odd_evenq_{ts_tag}",
                )
                prob_macro += (
                    s_intra_mac[s] + r_qtd - ms * pi_par >= 0,
                    f"M_odd_oddq_{ts_tag}",
                )

                q_gen_vars: dict[str, pulp.LpVariable] = {}
                r_gen_vars: dict[str, pulp.LpVariable] = {}
                d_gen_vars: dict[str, pulp.LpVariable] = {}
                for g in GENEROS:
                    q_g = pulp.LpVariable(
                        f"q_gen_{ts_tag}_{g}", lowBound=0, upBound=cap, cat=pulp.LpInteger
                    )
                    r_g = pulp.LpVariable(
                        f"r_gen_{ts_tag}_{g}", lowBound=0, upBound=ms - 1, cat=pulp.LpInteger
                    )
                    d_g = pulp.LpVariable(f"d_gen_{ts_tag}_{g}", cat=pulp.LpBinary)
                    q_gen_vars[g] = q_g
                    r_gen_vars[g] = r_g
                    d_gen_vars[g] = d_g
                    mac_int += 2
                    mac_bin += 1
                    prob_macro += (
                        ms * q_g + r_g - N_sg[(s, g)] == 0,
                        f"M_eucl_gen_{ts_tag}_{g}",
                    )
                    prob_macro += (r_g - (ms - 1) * d_g <= 0, f"M_rgen_ub_{ts_tag}_{g}")
                    prob_macro += (r_g - d_g >= 0, f"M_rgen_lb_{ts_tag}_{g}")
                    delta_gen_mac[(s, g)] = d_g

                # Armazena tuplas (r_var, d_var, ms) para acoplar SOS1 logarítmico apenas se Fase 2 precisar
                pair_qtd_mac[s] = (r_qtd, d_qtd, ms)  # type: ignore[assignment]
                for g in GENEROS:
                    pair_gen_mac[(s, g)] = (r_gen_vars[g], d_gen_vars[g], ms)  # type: ignore[assignment]

                prob_macro += (
                    d_max_intra_mac[s]
                    - q_gen_vars[GENERO_M]
                    + q_gen_vars[GENERO_F]
                    - delta_gen_mac[(s, GENERO_M)]
                    >= 0,
                    f"M_dmax_pos_{ts_tag}",
                )
                prob_macro += (
                    d_max_intra_mac[s]
                    - q_gen_vars[GENERO_F]
                    + q_gen_vars[GENERO_M]
                    - delta_gen_mac[(s, GENERO_F)]
                    >= 0,
                    f"M_dmax_neg_{ts_tag}",
                )

        total_binary_vars += mac_bin
        total_integer_vars += mac_int
        total_continuous_vars += mac_cont
        total_cons_p1 += len(prob_macro.constraints)
        total_build_s += time.perf_counter() - t_build_start

        # Fase 1 Macro
        z1_mac_expr = pulp.lpSum(
            params.w_qtd * delta_qtd_mac[s]
            + params.w_gen * pulp.lpSum(delta_gen_mac[(s, g)] for g in GENEROS)
            for s in S_active
        )
        prob_macro.setObjective(z1_mac_expr)
        cbc_m1 = pulp.PULP_CBC_CMD(msg=params.msg, timeLimit=params.time_limit_s)
        t_m1 = time.perf_counter()
        st_m1 = prob_macro.solve(cbc_m1)
        w_m1 = time.perf_counter() - t_m1
        total_p1_wall_s += w_m1
        total_p1_solver_s += float(getattr(prob_macro, "solutionTime", w_m1))
        sol_m1 = getattr(prob_macro, "sol_status", pulp.LpSolutionOptimal)
        macro_status_p1 = (
            "Optimal"
            if (st_m1 == pulp.LpStatusOptimal and sol_m1 == pulp.LpSolutionOptimal)
            else ("Feasible (Time Limit)" if sol_m1 == pulp.LpSolutionIntegerFeasible else pulp.LpStatus.get(st_m1, str(st_m1)))
        )

        has_mac_p1 = (
            st_m1 == pulp.LpStatusOptimal
            or (
                st_m1 == pulp.LpStatusNotSolved
                and all(pulp.value(v) is not None for v in f_mac.values())
            )
        )
        if not has_mac_p1:
            elapsed = time.perf_counter() - t_total_start
            return SolverResult(
                feasible=False,
                optimal=False,
                reason=f"Etapa 1 Macro encerrou sem partição viável (Status: {macro_status_p1}).",
                params=params,
                metrics=SolverMetrics(
                    solver_name="PULP_CBC_CMD (Decomp. Hierárquica + Perfis)",
                    status_phase1=macro_status_p1,
                    status_phase2="Skipped",
                    z1_objective=None,
                    z2_objective=None,
                    z2_pairwise_pure=None,
                    build_time_s=total_build_s,
                    phase1_wall_time_s=total_p1_wall_s,
                    phase1_solver_time_s=total_p1_solver_s,
                    phase2_wall_time_s=0.0,
                    phase2_solver_time_s=0.0,
                    total_time_s=elapsed,
                    num_variables=mac_bin + mac_int + mac_cont,
                    num_binary_vars=mac_bin,
                    num_integer_vars=mac_int,
                    num_continuous_vars=mac_cont,
                    num_constraints_phase1=total_cons_p1,
                    num_constraints_phase2=total_cons_p1,
                    num_unallocated=u_star,
                ),
            )

        macro_p1_optimal = (st_m1 == pulp.LpStatusOptimal and sol_m1 == pulp.LpSolutionOptimal)
        z1_mac_star = float(pulp.value(z1_mac_expr) or 0.0)

        p1_f_mac = {k: int(round(pulp.value(v) or 0.0)) for k, v in f_mac.items()}
        p1_u_mac = (
            {pk: int(round(pulp.value(u_mac[pk]) or 0.0)) for pk in profile_keys}
            if params.allow_unallocated
            else {pk: 0 for pk in profile_keys}
        )

        # Fase 2 Macro (quando habilitada)
        if params.enable_phase2:
            t_b_m2 = time.perf_counter()
            prob_macro += (z1_mac_expr <= z1_mac_star + 1e-5, "Lock_Macro_Fase1")

            def _attach_vn_sos1_pair(
                tag_prefix: str, spec_val: object
            ) -> pulp.LpAffineExpression:
                if isinstance(spec_val, pulp.LpAffineExpression):
                    return spec_val
                r_v, d_v, m_len = spec_val  # type: ignore[misc]
                if z1_mac_star <= 1e-6:
                    # Com Z1* == 0 e pesos positivos, d_v == 0 (r_v == 0) é forçado pela trava!
                    return pulp.LpAffineExpression()
                if m_len == 2:
                    return pulp.LpAffineExpression([(d_v, 1.0)])
                nonlocal total_binary_vars, total_continuous_vars
                betas = [None] + [
                    pulp.LpVariable(f"b_{tag_prefix}_{j}", lowBound=0, upBound=1, cat=pulp.LpContinuous)
                    for j in range(1, m_len)
                ]
                total_continuous_vars += m_len - 1
                prob_macro.addConstraint(
                    pulp.lpSum(betas[1:]) - d_v == 0, f"M2_bsum_{tag_prefix}"
                )
                prob_macro.addConstraint(
                    pulp.lpSum(j * betas[j] for j in range(1, m_len)) - r_v == 0,
                    f"M2_beucl_{tag_prefix}",
                )
                # Codificação SOS1 logarítmica em código Gray (Vielma & Nemhauser, 2011):
                # apenas ceil(log2(m_s)) variáveis binárias ramificam por bissecção de intervalos!
                nbits = (m_len - 1).bit_length()
                for b_idx in range(nbits):
                    gb = pulp.LpVariable(f"gb_{tag_prefix}_{b_idx}", cat=pulp.LpBinary)
                    total_binary_vars += 1
                    prob_macro.addConstraint(
                        pulp.lpSum(
                            betas[j]
                            for j in range(1, m_len)
                            if (((j ^ (j >> 1)) >> b_idx) & 1)
                        )
                        - gb
                        == 0,
                        f"M2_gray_{tag_prefix}_{b_idx}",
                    )
                return pulp.lpSum(j * (m_len - j) * betas[j] for j in range(1, m_len))

            z2_terms_mac: list[pulp.LpAffineExpression] = []
            for s in S_active:
                ts_tag = _ascii_turno(s)
                pq_expr = _attach_vn_sos1_pair(f"qtd_{ts_tag}", pair_qtd_mac[s])
                z2_terms_mac.append(params.w_qtd * pq_expr)
                for g in GENEROS:
                    pg_expr = _attach_vn_sos1_pair(f"gen_{ts_tag}_{g}", pair_gen_mac[(s, g)])
                    z2_terms_mac.append(params.w_gen * pg_expr)
                z2_terms_mac.append(params.epsilon * (d_max_intra_mac[s] + s_intra_mac[s]))

            total_cons_p2 += len(prob_macro.constraints)
            z2_mac_expr = pulp.lpSum(z2_terms_mac)
            prob_macro.setObjective(z2_mac_expr)
            total_build_s += time.perf_counter() - t_b_m2

            cbc_m2 = pulp.PULP_CBC_CMD(msg=params.msg, timeLimit=params.time_limit_s)
            t_m2 = time.perf_counter()
            st_m2 = prob_macro.solve(cbc_m2)
            w_m2 = time.perf_counter() - t_m2
            total_p2_wall_s += w_m2
            total_p2_solver_s += float(getattr(prob_macro, "solutionTime", w_m2))
            sol_m2 = getattr(prob_macro, "sol_status", pulp.LpSolutionOptimal)
            macro_status_p2 = (
                "Optimal"
                if (st_m2 == pulp.LpStatusOptimal and sol_m2 == pulp.LpSolutionOptimal)
                else ("Feasible (Time Limit)" if sol_m2 == pulp.LpSolutionIntegerFeasible else pulp.LpStatus.get(st_m2, str(st_m2)))
            )

            has_mac_p2 = st_m2 == pulp.LpStatusOptimal or (
                st_m2 == pulp.LpStatusNotSolved
                and all(pulp.value(v) is not None for v in f_mac.values())
            )
            if has_mac_p2:
                macro_p2_optimal = (st_m2 == pulp.LpStatusOptimal and sol_m2 == pulp.LpSolutionOptimal)
                macro_flow = {k: int(round(pulp.value(v) or 0.0)) for k, v in f_mac.items()}
                macro_unalloc = (
                    {pk: int(round(pulp.value(u_mac[pk]) or 0.0)) for pk in profile_keys}
                    if params.allow_unallocated
                    else {pk: 0 for pk in profile_keys}
                )
            else:
                macro_p2_optimal = False
                macro_flow = p1_f_mac
                macro_unalloc = p1_u_mac
        else:
            total_cons_p2 += total_cons_p1
            macro_flow = p1_f_mac
            macro_unalloc = p1_u_mac

    # =========================================================================
    # ETAPA HIERÁRQUICA 2: SUBPROBLEMAS MILP INTRA-TURNO (CONFIGURAÇÕES DE SALA)
    # =========================================================================
    y_vals: dict[int, int] = {}
    z_vals: dict[tuple[int, str], int] = {}
    student_to_turma: dict[int, int] = {}
    profile_cursor: dict[ProfileKey, int] = {pk: 0 for pk in profile_keys}
    stage2_all_opt = True

    for s in S_active:
        t_b2 = time.perf_counter()
        ks_list = K_s[s]
        ms = len(ks_list)
        cap = C_s[s]
        ts_tag = _ascii_turno(s)

        active_pks = [pk for pk in profile_keys if s in pk[1] and macro_flow.get((pk, s), 0) > 0]
        n_s_m = sum(macro_flow[(pk, s)] for pk in active_pks if pk[0] == GENERO_M)
        n_s_f = sum(macro_flow[(pk, s)] for pk in active_pks if pk[0] == GENERO_F)

        q_m, r_m = divmod(n_s_m, ms)
        q_f, r_f = divmod(n_s_f, ms)

        # Subproblema MILP Exato de Configurações de Sala (Dantzig-Wolfe / Config MILP):
        # Todas as salas ótimas pertencem às 4 configurações inteiras (q_M + a, q_F + b), a,b in {0,1}.
        prob_s = pulp.LpProblem(f"Etapa2_Config_{ts_tag}", pulp.LpMinimize)

        t_00 = pulp.LpVariable(f"t00_{ts_tag}", lowBound=0, upBound=ms, cat=pulp.LpInteger)
        t_10 = pulp.LpVariable(f"t10_{ts_tag}", lowBound=0, upBound=r_m, cat=pulp.LpInteger)
        t_01 = pulp.LpVariable(f"t01_{ts_tag}", lowBound=0, upBound=r_f, cat=pulp.LpInteger)
        t_11_ub = 0 if (q_m + q_f + 2 > cap) else min(r_m, r_f)
        t_11 = pulp.LpVariable(f"t11_{ts_tag}", lowBound=0, upBound=t_11_ub, cat=pulp.LpInteger)

        u_low = pulp.LpVariable(f"ulow_{ts_tag}", cat=pulp.LpBinary)
        u_high = pulp.LpVariable(f"uhigh_{ts_tag}", cat=pulp.LpBinary)

        prob_s += (t_00 + t_10 + t_01 + t_11 == ms, f"S2_rooms_{ts_tag}")
        prob_s += (t_10 + t_11 == r_m, f"S2_rm_{ts_tag}")
        prob_s += (t_01 + t_11 == r_f, f"S2_rf_{ts_tag}")
        prob_s += (t_00 - ms * u_low <= 0, f"S2_ulow_{ts_tag}")
        prob_s += (t_11 - ms * u_high <= 0, f"S2_uhigh_{ts_tag}")

        prob_s.setObjective(u_low + u_high)

        total_binary_vars += 2
        total_integer_vars += 4
        total_cons_p1 += len(prob_s.constraints)
        total_cons_p2 += len(prob_s.constraints)
        total_build_s += time.perf_counter() - t_b2

        cbc_s1 = pulp.PULP_CBC_CMD(msg=params.msg, timeLimit=params.time_limit_s)
        t_s1 = time.perf_counter()
        st_s1 = prob_s.solve(cbc_s1)
        w_s1 = time.perf_counter() - t_s1
        total_p1_wall_s += w_s1
        total_p1_solver_s += float(getattr(prob_s, "solutionTime", w_s1))

        if st_s1 != pulp.LpStatusOptimal:
            stage2_all_opt = False

        c_11 = int(round(pulp.value(t_11) or 0.0))
        c_10 = int(round(pulp.value(t_10) or 0.0))
        c_01 = int(round(pulp.value(t_01) or 0.0))
        c_00 = int(round(pulp.value(t_00) or 0.0))

        # Expansão ordenada decrescente lexicográfica (y_k, z_{k,M}) nas m_s salas do turno
        room_configs = (
            [(q_m + 1, q_f + 1)] * c_11
            + [(q_m + 1, q_f)] * c_10
            + [(q_m, q_f + 1)] * c_01
            + [(q_m, q_f)] * c_00
        )

        # Projeção nominal bijetiva determinística O(N_s) dos perfis para as salas do turno
        pool_m: list[int] = []
        pool_f: list[int] = []
        for pk in active_pks:
            qty_s = macro_flow[(pk, s)]
            cur = profile_cursor[pk]
            st_slice = buckets[pk][cur : cur + qty_s]
            profile_cursor[pk] = cur + qty_s
            if pk[0] == GENERO_M:
                pool_m.extend(st.id for st in st_slice)
            else:
                pool_f.extend(st.id for st in st_slice)

        idx_m = 0
        idx_f = 0
        for k, (m_k, f_k) in zip(ks_list, room_configs):
            y_vals[k] = m_k + f_k
            z_vals[(k, GENERO_M)] = m_k
            z_vals[(k, GENERO_F)] = f_k
            for offset in range(m_k):
                student_to_turma[pool_m[idx_m + offset]] = k
            idx_m += m_k
            for offset in range(f_k):
                student_to_turma[pool_f[idx_f + offset]] = k
            idx_f += f_k

    unallocated_ids = [st.id for st in students if st.id not in student_to_turma]

    # Cálculo exato das métricas globais Z1*, Z2* e desvios em O(m_s log m_s)
    res_delta_qtd: dict[str, float] = {}
    res_delta_gen: dict[tuple[str, str], float] = {}
    res_d_intra: dict[int, float] = {}
    res_delta_intra: dict[str, float] = {}

    for k in K_ids:
        res_d_intra[k] = float(abs(z_vals[(k, GENERO_M)] - z_vals[(k, GENERO_F)]))

    z1_final = 0.0
    z2_pure_final = 0.0
    intra_smooth_final = 0.0

    for s in S_active:
        ks_list = K_s[s]
        lots = [y_vals[k] for k in ks_list]
        dq = float(max(lots) - min(lots)) if lots else 0.0
        res_delta_qtd[s] = dq
        z1_final += params.w_qtd * dq
        z2_pure_final += params.w_qtd * _sum_pairwise_abs(lots)

        for g in GENEROS:
            g_counts = [z_vals[(k, g)] for k in ks_list]
            dg = float(max(g_counts) - min(g_counts)) if g_counts else 0.0
            res_delta_gen[(s, g)] = dg
            z1_final += params.w_gen * dg
            z2_pure_final += params.w_gen * _sum_pairwise_abs(g_counts)

        d_max_s = max((res_d_intra[k] for k in ks_list), default=0.0)
        res_delta_intra[s] = d_max_s
        intra_smooth_final += d_max_s + sum(res_d_intra[k] for k in ks_list)

    z2_obj_final = z2_pure_final + params.epsilon * intra_smooth_final
    is_opt = macro_p1_optimal and (macro_p2_optimal if params.enable_phase2 else True) and stage2_all_opt

    status_p1_out = "Optimal" if (macro_p1_optimal and stage2_all_opt) else macro_status_p1
    if not params.enable_phase2:
        status_p2_out = "Disabled (Phase 1 Only)"
    elif not needs_macro_milp:
        status_p2_out = "Optimal (Unique Intra-Shift Profile)"
    else:
        status_p2_out = "Optimal" if is_opt else macro_status_p2

    if is_opt:
        reason_msg = (
            "Solução ótima global alcançada via Agregação por Perfis + "
            "Decomposição Hierárquica em 2 Etapas."
            if params.enable_phase2
            else "Solução ótima da Fase 1 alcançada via Agregação por Perfis + Decomposição Hierárquica (Fase 2 desativada)."
        )
    else:
        reason_msg = f"Solução inteira viável obtida ({status_p1_out} / {status_p2_out})."

    if unallocated_ids:
        reason_msg = (
            f"{reason_msg} Alocação parcial concluída: {len(student_to_turma)}/{len(students)} "
            f"ensalados e {len(unallocated_ids)} em lista de espera (sem turma)."
        )

    num_total_vars = total_binary_vars + total_integer_vars + total_continuous_vars
    total_elapsed = time.perf_counter() - t_total_start

    return SolverResult(
        feasible=True,
        optimal=is_opt,
        reason=reason_msg,
        params=params,
        metrics=SolverMetrics(
            solver_name="PULP_CBC_CMD (Decomp. Hierárquica + Perfis)",
            status_phase1=status_p1_out,
            status_phase2=status_p2_out,
            z1_objective=z1_final,
            z2_objective=z2_obj_final,
            z2_pairwise_pure=z2_pure_final,
            build_time_s=total_build_s,
            phase1_wall_time_s=total_p1_wall_s,
            phase1_solver_time_s=total_p1_solver_s,
            phase2_wall_time_s=total_p2_wall_s,
            phase2_solver_time_s=total_p2_solver_s,
            total_time_s=total_elapsed,
            num_variables=num_total_vars,
            num_binary_vars=total_binary_vars,
            num_integer_vars=total_integer_vars,
            num_continuous_vars=total_continuous_vars,
            num_constraints_phase1=total_cons_p1,
            num_constraints_phase2=total_cons_p2,
            num_unallocated=len(unallocated_ids),
        ),
        student_to_turma=student_to_turma,
        unallocated_students=unallocated_ids,
        y_turma=y_vals,
        z_turma_gen=z_vals,
        delta_qtd=res_delta_qtd,
        delta_gen=res_delta_gen,
        delta_intra=res_delta_intra,
        d_intra=res_d_intra,
    )


def _solve_monolithic(
    instance: ProcessedInstance,
    params: SolverParameters,
    t_total_start: float,
    min_unalloc_hall: int,
) -> SolverResult:
    """Modelo monolítico original baseado em variáveis binárias individuais x_{i,k}."""
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

    # u_i in {0, 1}: indicador de lista de espera (sem turma) quando allow_unallocated=True
    u: dict[int, pulp.LpVariable] = {}
    if params.allow_unallocated:
        for st in students:
            u[st.id] = pulp.LpVariable(f"u_{st.id}", cat=pulp.LpBinary)

    u_star = min_unalloc_hall if params.allow_unallocated else 0
    expected_allocated = len(students) - u_star

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
    # 1. Alocação Obrigatória (ou Parcial c/ Folga Mínima Exata) e Disponibilidade (Eq. 3)
    if params.allow_unallocated:
        for st in students:
            prob += (
                pulp.lpSum(x[(st.id, k)] for k in K_i[st.id]) + u[st.id] == 1,
                f"R1_aloc_aluno_{st.id}",
            )
        # Trava Prioridade 0 lexicográfica: maximizar o total de alunos alocados (sum u_i == U*)
        prob += (
            pulp.lpSum(u[st.id] for st in students) == u_star,
            "R0_min_unallocated_exact",
        )
        for s_fixed in (TURNO_MANHA, TURNO_TARDE):
            cap_tot_s = len(instance.turmas_por_turno[s_fixed]) * C_s[s_fixed]
            only_s_ids = [s.id for s in students if s.turnos_compativeis == (s_fixed,)]
            def_s = len(only_s_ids) - cap_tot_s
            if def_s > 0:
                prob += (
                    pulp.lpSum(u[i_id] for i_id in only_s_ids) >= def_s,
                    f"R0_deficit_{_ascii_turno(s_fixed)}",
                )
    else:
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

    # 5. Quebra de Simetria - Ordenação Decrescente Intra-Turno (Eq. 7 + desempate lexicográfico em M)
    for s in S_active:
        ks_list = K_s[s]
        cap = C_s[s]
        for idx in range(len(ks_list) - 1):
            k_curr, k_next = ks_list[idx], ks_list[idx + 1]
            prob += (
                y[k_curr] - y[k_next] >= 0,
                f"R5_simetria_{_ascii_turno(s)}_{k_curr}_{k_next}",
            )
            prob += (
                (cap + 1) * (y[k_curr] - y[k_next])
                + (z[(k_curr, GENERO_M)] - z[(k_next, GENERO_M)])
                >= 0,
                f"R5_simetria_lex_{_ascii_turno(s)}_{k_curr}_{k_next}",
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

    num_binary = len(x) + len(u)
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

    has_incumbent_p1 = (
        status_code_p1 == pulp.LpStatusOptimal
        or (
            status_code_p1 == pulp.LpStatusNotSolved
            and all(pulp.value(y[k]) is not None for k in K_ids)
            and sum(int(round(pulp.value(y[k]) or 0.0)) for k in K_ids) == expected_allocated
        )
    )

    if not has_incumbent_p1:
        total_elapsed = time.perf_counter() - t_total_start
        return SolverResult(
            feasible=False,
            optimal=False,
            reason=f"Fase 1 encerrou sem solução inteira viável (Status: {status_p1_str}).",
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
                num_unallocated=u_star,
            ),
        )

    p1_optimal = status_code_p1 == pulp.LpStatusOptimal
    if not p1_optimal:
        status_p1_str = "Feasible (Time Limit)"

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

    has_flexible_students = any(
        not any(K_i_sets[st.id] == set(K_s[s]) for s in S_active) for st in students
    )
    unit_amplitudes = all(
        (max(p1_y[k] for k in K_s[s]) - min(p1_y[k] for k in K_s[s]) <= 1)
        and all(
            max(p1_z[(k, g)] for k in K_s[s]) - min(p1_z[(k, g)] for k in K_s[s]) <= 1
            for g in GENEROS
        )
        for s in S_active
    )
    can_auto_skip_p2 = (
        params.auto_skip_phase2
        and p1_optimal
        and u_star == 0
        and params.w_qtd > 0
        and params.w_gen > 0
        and not has_flexible_students
        and unit_amplitudes
    )

    if (not params.enable_phase2) or can_auto_skip_p2:
        # Calcula o valor equivalente de Z2 a partir dos inteiros y/z da Fase 1 para comparação justa
        p1_z2_pure = 0.0
        p1_intra_sum = 0.0
        for s in S_active:
            ks_list = K_s[s]
            for i in range(len(ks_list)):
                for j in range(i + 1, len(ks_list)):
                    ka, kb = ks_list[i], ks_list[j]
                    p1_z2_pure += params.w_qtd * abs(p1_y[ka] - p1_y[kb])
                    for g in GENEROS:
                        p1_z2_pure += params.w_gen * abs(p1_z[(ka, g)] - p1_z[(kb, g)])
            max_intra_s = 0.0
            for k in ks_list:
                di = float(abs(p1_z[(k, GENERO_M)] - p1_z[(k, GENERO_F)]))
                p1_intra_sum += di
                if di > max_intra_s:
                    max_intra_s = di
            p1_intra_sum += max_intra_s

        student_to_turma = p1_student_to_turma
        y_vals = p1_y
        z_vals = p1_z
        z2_pure = p1_z2_pure
        z2_obj = p1_z2_pure + params.epsilon * p1_intra_sum
        is_opt = p1_optimal
        status_p2_str = (
            "Auto-Skipped (Unique Optimal)" if can_auto_skip_p2 else "Disabled (Phase 1 Only)"
        )
        phase2_wall_s = 0.0
        phase2_solver_s = 0.0
        num_constraints_p2 = num_constraints_p1
        if can_auto_skip_p2:
            reason_msg = (
                "Solução ótima global obtida na Fase 1 (Fase 2 omitida automaticamente por "
                "unicidade matemática do perfil ótimo de turmas)."
            )
        else:
            reason_msg = (
                "Solução ótima da Fase 1 obtida (Fase 2 desativada)."
                if p1_optimal
                else f"Solução inteira viável da Fase 1 obtida no limite de tempo ({status_p1_str}; Fase 2 desativada)."
            )
    else:
        # Trava o limite de qualidade ótimo encontrado na Fase 1 (Custo Fase 1 <= Z1*)
        prob += (custo_fase1_expr <= z1_star + 1e-5, "Lock_Custo_Fase_1")
        num_constraints_p2 = len(prob.constraints)
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

        has_incumbent_p2 = (
            status_code_p2 == pulp.LpStatusOptimal
            or (
                status_code_p2 == pulp.LpStatusNotSolved
                and all(pulp.value(y[k]) is not None for k in K_ids)
                and sum(int(round(pulp.value(y[k]) or 0.0)) for k in K_ids) == expected_allocated
            )
        )
        if status_code_p2 != pulp.LpStatusOptimal and has_incumbent_p2:
            status_p2_str = "Feasible (Time Limit)"

        # Extração da solução final (usa Fase 2 se viável/ótima, caso contrário preserva Fase 1)
        if has_incumbent_p2:
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
            is_opt = p1_optimal and (status_code_p2 == pulp.LpStatusOptimal)
            reason_msg = (
                "Solução ótima global alcançada nas Fases 1 e 2 (Otimização Lexicográfica)."
                if is_opt
                else f"Solução inteira viável obtida no limite de tempo ({status_p1_str} / {status_p2_str})."
            )
        else:
            student_to_turma = p1_student_to_turma
            y_vals = p1_y
            z_vals = p1_z
            z2_obj = None
            z2_pure = None
            is_opt = False
            reason_msg = (
                f"Fase 1 concluída ({status_p1_str}); Fase 2 retornou '{status_p2_str}', "
                "mantendo alocação da Fase 1."
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

    unallocated_ids = [st.id for st in students if st.id not in student_to_turma]
    if unallocated_ids:
        reason_msg = (
            f"{reason_msg} Alocação parcial concluída: {len(student_to_turma)}/{len(students)} "
            f"ensalados e {len(unallocated_ids)} em lista de espera (sem turma)."
        )

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
            num_unallocated=len(unallocated_ids),
        ),
        student_to_turma=student_to_turma,
        unallocated_students=unallocated_ids,
        y_turma=y_vals,
        z_turma_gen=z_vals,
        delta_qtd=res_delta_qtd,
        delta_gen=res_delta_gen,
        delta_intra=res_delta_intra,
        d_intra=res_d_intra,
    )

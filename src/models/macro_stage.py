"""Etapa 1 (Macro): Agregação por perfis demográficos e partição ótima entre turnos via MILP."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
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
    Student,
)
from src.models.types import (
    ProfileKey,
    SolverParameters,
    _ascii_turno,
    _compute_instance_seed,
    _order_students_for_spreadsheet,
)


@dataclass
class MacroStageOutput:
    """Resultados consolidados da Etapa 1 Macro."""

    success: bool
    reason: str
    macro_flow: dict[tuple[ProfileKey, str], int]
    macro_unalloc: dict[ProfileKey, int]
    buckets: dict[ProfileKey, list[Student]]
    profile_keys: list[ProfileKey]
    macro_p1_optimal: bool
    macro_p2_optimal: bool
    macro_status_p1: str
    macro_status_p2: str
    total_build_s: float
    total_p1_wall_s: float
    total_p1_solver_s: float
    total_p2_wall_s: float
    total_p2_solver_s: float
    total_binary_vars: int
    total_integer_vars: int
    total_continuous_vars: int
    total_cons_p1: int
    total_cons_p2: int
    needs_macro_milp: bool


def aggregate_profiles(
    instance: ProcessedInstance,
    S_active: list[str],
    K_s_sets: dict[str, set[int]],
) -> tuple[dict[ProfileKey, list[Student]], list[ProfileKey], bool]:
    """Agrupa alunos em perfis demográficos p = (sexo, turnos_ativos) em O(N).

    Retorna (buckets, profile_keys, is_valid). Se algum aluno tiver elegibilidade parcial
    intra-turno atípica, is_valid será False para acionar fallback.
    """
    students = instance.students
    K_i = instance.turmas_compativeis_por_aluno
    buckets: dict[ProfileKey, list[Student]] = defaultdict(list)
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
        if avail_s is None:
            return {}, [], False
        buckets[(st.sexo, avail_s)].append(st)

    sheet_seed = _compute_instance_seed(students)
    profile_keys = sorted(buckets.keys(), key=lambda pk: (pk[0], len(pk[1]), pk[1]))
    for pk in profile_keys:
        buckets[pk] = _order_students_for_spreadsheet(buckets[pk], sheet_seed)

    return buckets, profile_keys, True


def solve_macro_stage(
    instance: ProcessedInstance,
    params: SolverParameters,
    buckets: dict[ProfileKey, list[Student]],
    profile_keys: list[ProfileKey],
    S_active: list[str],
    K_s: dict[str, list[int]],
    C_s: dict[str, int],
    u_star: int,
    t_total_start: float,
) -> MacroStageOutput:
    """Executa a partição macro de turnos via divisão euclidiana exata em MILP."""
    t_build_start = time.perf_counter()

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

    if not needs_macro_milp:
        # Turnos 100% desacoplados desde a origem (sem Integrais e sem déficit de vagas)
        for pk in profile_keys:
            cnt = len(buckets[pk])
            macro_unalloc[pk] = 0
            for s in pk[1]:
                macro_flow[(pk, s)] = cnt
        total_build_s += time.perf_counter() - t_build_start

        return MacroStageOutput(
            success=True,
            reason="Ótimo analítico desacoplado.",
            macro_flow=macro_flow,
            macro_unalloc=macro_unalloc,
            buckets=buckets,
            profile_keys=profile_keys,
            macro_p1_optimal=True,
            macro_p2_optimal=True,
            macro_status_p1="Optimal (Analytical Decoupled)",
            macro_status_p2="Disabled (Phase 1 Only)" if not params.enable_phase2 else "Optimal",
            total_build_s=total_build_s,
            total_p1_wall_s=0.0,
            total_p1_solver_s=0.0,
            total_p2_wall_s=0.0,
            total_p2_solver_s=0.0,
            total_binary_vars=0,
            total_integer_vars=0,
            total_continuous_vars=0,
            total_cons_p1=0,
            total_cons_p2=0,
            needs_macro_milp=False,
        )

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

            # Paridade de q_qtd para contar salas ímpares em S_intra
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

    # Fase 1 Macro: Min-Max
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
        return MacroStageOutput(
            success=False,
            reason=f"Etapa 1 Macro encerrou sem partição viável (Status: {macro_status_p1}).",
            macro_flow={},
            macro_unalloc={},
            buckets=buckets,
            profile_keys=profile_keys,
            macro_p1_optimal=False,
            macro_p2_optimal=False,
            macro_status_p1=macro_status_p1,
            macro_status_p2="Skipped",
            total_build_s=total_build_s,
            total_p1_wall_s=total_p1_wall_s,
            total_p1_solver_s=total_p1_solver_s,
            total_p2_wall_s=0.0,
            total_p2_solver_s=0.0,
            total_binary_vars=total_binary_vars,
            total_integer_vars=total_integer_vars,
            total_continuous_vars=total_continuous_vars,
            total_cons_p1=total_cons_p1,
            total_cons_p2=total_cons_p1,
            needs_macro_milp=True,
        )

    macro_p1_optimal = (st_m1 == pulp.LpStatusOptimal and sol_m1 == pulp.LpSolutionOptimal)
    z1_mac_star = float(pulp.value(z1_mac_expr) or 0.0)

    p1_f_mac = {k: int(round(pulp.value(v) or 0.0)) for k, v in f_mac.items()}
    p1_u_mac = (
        {pk: int(round(pulp.value(u_mac[pk]) or 0.0)) for pk in profile_keys}
        if params.allow_unallocated
        else {pk: 0 for pk in profile_keys}
    )

    # Fase 2 Macro: Suavização Par-a-Par
    macro_p2_optimal = True
    macro_status_p2 = "Disabled (Phase 1 Only)" if not params.enable_phase2 else "Optimal"

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

    return MacroStageOutput(
        success=True,
        reason="Partição macro concluída com sucesso.",
        macro_flow=macro_flow,
        macro_unalloc=macro_unalloc,
        buckets=buckets,
        profile_keys=profile_keys,
        macro_p1_optimal=macro_p1_optimal,
        macro_p2_optimal=macro_p2_optimal,
        macro_status_p1=macro_status_p1,
        macro_status_p2=macro_status_p2,
        total_build_s=total_build_s,
        total_p1_wall_s=total_p1_wall_s,
        total_p1_solver_s=total_p1_solver_s,
        total_p2_wall_s=total_p2_wall_s,
        total_p2_solver_s=total_p2_solver_s,
        total_binary_vars=total_binary_vars,
        total_integer_vars=total_integer_vars,
        total_continuous_vars=total_continuous_vars,
        total_cons_p1=total_cons_p1,
        total_cons_p2=total_cons_p2,
        needs_macro_milp=True,
    )


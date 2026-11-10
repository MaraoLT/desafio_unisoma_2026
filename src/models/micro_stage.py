"""Etapa 2 (Micro): Subproblemas intra-turno de configurações de sala e projeção nominal O(N)."""

from __future__ import annotations

import time

import pulp

from src.pre_process import (
    GENERO_F,
    GENERO_M,
    GENEROS,
    ProcessedInstance,
)
from src.models.types import (
    ProfileKey,
    SolverMetrics,
    SolverParameters,
    SolverResult,
    _ascii_turno,
    _sum_pairwise_abs,
)
from src.models.macro_stage import MacroStageOutput


def solve_micro_stage(
    instance: ProcessedInstance,
    params: SolverParameters,
    macro_out: MacroStageOutput,
    S_active: list[str],
    K_s: dict[str, list[int]],
    C_s: dict[str, int],
    u_star: int,
    t_total_start: float,
) -> SolverResult:
    """Resolve subproblemas de configurações de sala e projeta os alunos nominais."""
    students = instance.students
    turmas = instance.turmas
    K_ids = [t.id for t in turmas]
    buckets = macro_out.buckets
    profile_keys = macro_out.profile_keys
    macro_flow = macro_out.macro_flow

    total_build_s = macro_out.total_build_s
    total_p1_wall_s = macro_out.total_p1_wall_s
    total_p1_solver_s = macro_out.total_p1_solver_s
    total_p2_wall_s = macro_out.total_p2_wall_s
    total_p2_solver_s = macro_out.total_p2_solver_s
    total_binary_vars = macro_out.total_binary_vars
    total_integer_vars = macro_out.total_integer_vars
    total_continuous_vars = macro_out.total_continuous_vars
    total_cons_p1 = macro_out.total_cons_p1
    total_cons_p2 = macro_out.total_cons_p2

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

        # Subproblema MILP Exato de Configurações de Sala (4 configurações inteiras):
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

        # Expansão ordenada decrescente lexicográfica (y_k, z_{k,M})
        room_configs = (
            [(q_m + 1, q_f + 1)] * c_11
            + [(q_m + 1, q_f)] * c_10
            + [(q_m, q_f + 1)] * c_01
            + [(q_m, q_f)] * c_00
        )

        # Projeção nominal bijetiva determinística O(N_s)
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

    # Cálculo exato das métricas globais Z1*, Z2* e desvios
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
    is_opt = macro_out.macro_p1_optimal and (macro_out.macro_p2_optimal if params.enable_phase2 else True) and stage2_all_opt

    status_p1_out = "Optimal" if (macro_out.macro_p1_optimal and stage2_all_opt) else macro_out.macro_status_p1
    if not params.enable_phase2:
        status_p2_out = "Disabled (Phase 1 Only)"
    elif not macro_out.needs_macro_milp:
        status_p2_out = "Optimal (Unique Intra-Shift Profile)"
    else:
        status_p2_out = "Optimal" if is_opt else macro_out.macro_status_p2

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


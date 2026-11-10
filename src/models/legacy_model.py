"""Modelo MILP monolítico clássico baseado em variáveis binárias individuais x_{i,k}.

Mantido como modelo legado de referência formal, testes comparativos de equivalência
e verificação analítica.
"""

from __future__ import annotations

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
from src.models.types import (
    SolverMetrics,
    SolverParameters,
    SolverResult,
    _ascii_turno,
    _compute_instance_seed,
    _order_students_for_spreadsheet,
)


def solve_legacy_monolithic(
    instance: ProcessedInstance,
    params: SolverParameters,
    t_total_start: float,
    min_unalloc_hall: int,
) -> SolverResult:
    """Resolve o ensalamento via modelo monolítico individual clássico."""
    t_build_start = time.perf_counter()
    prob = pulp.LpProblem("Desafio_UniSoma_2026_Ensalamento_Legacy", pulp.LpMinimize)

    students = instance.students
    sheet_seed = _compute_instance_seed(students)
    students_shuffled = _order_students_for_spreadsheet(students, sheet_seed)
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
    x: dict[tuple[int, int], pulp.LpVariable] = {}
    for st in students_shuffled:
        for k in K_i[st.id]:
            x[(st.id, k)] = pulp.LpVariable(f"x_{st.id}_{k}", cat=pulp.LpBinary)

    u: dict[int, pulp.LpVariable] = {}
    if params.allow_unallocated:
        for st in students_shuffled:
            u[st.id] = pulp.LpVariable(f"u_{st.id}", cat=pulp.LpBinary)

    u_star = min_unalloc_hall if params.allow_unallocated else 0
    expected_allocated = len(students) - u_star

    y: dict[int, pulp.LpVariable] = {
        k: pulp.LpVariable(f"y_{k}", lowBound=0, cat=pulp.LpInteger) for k in K_ids
    }

    z: dict[tuple[int, str], pulp.LpVariable] = {
        (k, g): pulp.LpVariable(f"z_{k}_{g}", lowBound=0, cat=pulp.LpInteger)
        for k in K_ids
        for g in GENEROS
    }

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

    d_intra: dict[int, pulp.LpVariable] = {
        k: pulp.LpVariable(f"d_intra_{k}", lowBound=0, cat=pulp.LpContinuous) for k in K_ids
    }
    delta_intra: dict[str, pulp.LpVariable] = {
        s: pulp.LpVariable(f"Delta_intra_{_ascii_turno(s)}", lowBound=0, cat=pulp.LpContinuous)
        for s in S_active
    }

    # --- Restrições ---
    # 1. Alocação Obrigatória e Compatibilidade
    if params.allow_unallocated:
        for st in students:
            prob += (
                pulp.lpSum(x[(st.id, k)] for k in K_i[st.id]) + u[st.id] == 1,
                f"R1_aloc_aluno_{st.id}",
            )
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

    # 2. Contabilização de Alunos por Gênero
    for k in K_ids:
        for g in GENEROS:
            eligible_students = [i_id for i_id in I_g[g] if k in K_i_sets[i_id]]
            prob += (
                pulp.lpSum(x[(i_id, k)] for i_id in eligible_students) - z[(k, g)] == 0,
                f"R2_cont_gen_{k}_{g}",
            )

    # 3. Contabilização da Lotação Total
    for k in K_ids:
        prob += (
            pulp.lpSum(z[(k, g)] for g in GENEROS) - y[k] == 0,
            f"R3_cont_total_{k}",
        )

    # 4. Limite de Capacidade Máxima
    for s in S_active:
        cap = C_s[s]
        for k in K_s[s]:
            prob += (y[k] <= cap, f"R4_cap_max_{k}")

    # 5. Quebra de Simetria e Ordenação Monótona
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

    # 6. Equilíbrio em Quantidade Total
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

    # 7. Equilíbrio Intra-Turma de Gênero (50/50)
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

    # 8. Equilíbrio Inter-Turmas de Gênero
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

    # Fase 1: Min-Max
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
                solver_name="PULP_CBC_CMD (Legacy Monolithic)",
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

    p1_student_to_turma = {
        st.id: k
        for st in students
        for k in K_i[st.id]
        if (pulp.value(x[(st.id, k)]) or 0.0) > 0.5
    }
    p1_y = {k: int(round(pulp.value(y[k]) or 0.0)) for k in K_ids}
    p1_z = {(k, g): int(round(pulp.value(z[(k, g)]) or 0.0)) for k in K_ids for g in GENEROS}

    # Fase 2: Suavização Par-a-Par
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

        p1_z2_obj = p1_z2_pure + params.epsilon * p1_intra_sum
        total_elapsed = time.perf_counter() - t_total_start
        status_p2_str = "Skipped (Auto)" if can_auto_skip_p2 else "Disabled (Phase 1 Only)"
        p1_unallocated = [st.id for st in students if st.id not in p1_student_to_turma]

        return SolverResult(
            feasible=True,
            optimal=p1_optimal,
            reason=(
                "Solução ótima da Fase 1 obtida (Fase 2 ignorada por otimalidade comprovada)."
                if can_auto_skip_p2
                else (
                    "Solução ótima da Fase 1 alcançada."
                    if p1_optimal
                    else "Solução inteira viável da Fase 1 obtida dentro do tempo limite."
                )
            ),
            params=params,
            metrics=SolverMetrics(
                solver_name="PULP_CBC_CMD (Legacy Monolithic)",
                status_phase1=status_p1_str,
                status_phase2=status_p2_str,
                z1_objective=z1_star,
                z2_objective=p1_z2_obj,
                z2_pairwise_pure=p1_z2_pure,
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
                num_unallocated=len(p1_unallocated),
            ),
            student_to_turma=p1_student_to_turma,
            unallocated_students=p1_unallocated,
            y_turma=p1_y,
            z_turma_gen=p1_z,
            delta_qtd={s: float(pulp.value(delta_qtd[s]) or 0.0) for s in S_active},
            delta_gen={(s, g): float(pulp.value(delta_gen[(s, g)]) or 0.0) for s in S_active for g in GENEROS},
            delta_intra={s: float(pulp.value(delta_intra[s]) or 0.0) for s in S_active},
            d_intra={k: float(pulp.value(d_intra[k]) or 0.0) for k in K_ids},
        )

    # Execução da Fase 2
    t_p2_build = time.perf_counter()
    prob += (custo_fase1_expr <= z1_star + 1e-5, "Lock_Fase1_Optimum")
    prob.setObjective(custo_fase2_expr)
    num_constraints_p2 = len(prob.constraints)
    build_time_s += time.perf_counter() - t_p2_build

    cbc_phase2 = pulp.PULP_CBC_CMD(msg=params.msg, timeLimit=params.time_limit_s)
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

    if not has_incumbent_p2:
        total_elapsed = time.perf_counter() - t_total_start
        p1_unallocated = [st.id for st in students if st.id not in p1_student_to_turma]
        return SolverResult(
            feasible=True,
            optimal=False,
            reason=f"Fase 2 encerrou sem solução viável (Status: {status_p2_str}). Usando solução ótima da Fase 1.",
            params=params,
            metrics=SolverMetrics(
                solver_name="PULP_CBC_CMD (Legacy Monolithic)",
                status_phase1=status_p1_str,
                status_phase2=status_p2_str,
                z1_objective=z1_star,
                z2_objective=None,
                z2_pairwise_pure=None,
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
                num_unallocated=len(p1_unallocated),
            ),
            student_to_turma=p1_student_to_turma,
            unallocated_students=p1_unallocated,
            y_turma=p1_y,
            z_turma_gen=p1_z,
            delta_qtd={s: float(pulp.value(delta_qtd[s]) or 0.0) for s in S_active},
            delta_gen={(s, g): float(pulp.value(delta_gen[(s, g)]) or 0.0) for s in S_active for g in GENEROS},
            delta_intra={s: float(pulp.value(delta_intra[s]) or 0.0) for s in S_active},
            d_intra={k: float(pulp.value(d_intra[k]) or 0.0) for k in K_ids},
        )

    p2_optimal = status_code_p2 == pulp.LpStatusOptimal
    if not p2_optimal:
        status_p2_str = "Feasible (Time Limit)"

    z1_val = float(pulp.value(custo_fase1_expr))
    z2_val = float(pulp.value(custo_fase2_expr))
    z2_pure_val = float(pulp.value(pairwise_pure_expr))

    student_to_turma = {
        st.id: k
        for st in students
        for k in K_i[st.id]
        if (pulp.value(x[(st.id, k)]) or 0.0) > 0.5
    }
    unallocated_students = [st.id for st in students if st.id not in student_to_turma]

    total_elapsed = time.perf_counter() - t_total_start
    is_fully_optimal = p1_optimal and p2_optimal

    return SolverResult(
        feasible=True,
        optimal=is_fully_optimal,
        reason=(
            "Solução ótima global alcançada nas Fases 1 e 2."
            if is_fully_optimal
            else f"Solução inteira viável obtida ({status_p1_str} / {status_p2_str})."
        ),
        params=params,
        metrics=SolverMetrics(
            solver_name="PULP_CBC_CMD (Legacy Monolithic)",
            status_phase1=status_p1_str,
            status_phase2=status_p2_str,
            z1_objective=z1_val,
            z2_objective=z2_val,
            z2_pairwise_pure=z2_pure_val,
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
            num_unallocated=len(unallocated_students),
        ),
        student_to_turma=student_to_turma,
        unallocated_students=unallocated_students,
        y_turma={k: int(round(pulp.value(y[k]) or 0.0)) for k in K_ids},
        z_turma_gen={(k, g): int(round(pulp.value(z[(k, g)]) or 0.0)) for k in K_ids for g in GENEROS},
        delta_qtd={s: float(pulp.value(delta_qtd[s]) or 0.0) for s in S_active},
        delta_gen={(s, g): float(pulp.value(delta_gen[(s, g)]) or 0.0) for s in S_active for g in GENEROS},
        delta_intra={s: float(pulp.value(delta_intra[s]) or 0.0) for s in S_active},
        d_intra={k: float(pulp.value(d_intra[k]) or 0.0) for k in K_ids},
    )


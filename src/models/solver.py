"""Solver de Programação Inteira Mista (MILP) com Otimização Lexicográfica em PuLP.

Fachada principal (Façade Pattern) que orquestra:
1. Pré-checagem de viabilidade estrutural e Teorema de Hall (feasibility.py);
2. Agregação por perfis demográficos e partição macro em 2 fases (macro_stage.py);
3. Subproblemas intra-turno de configurações de sala e projeção nominal O(N) (micro_stage.py);
4. Modo legado opcional (legacy_model.py).
"""

from __future__ import annotations

import time
from typing import Optional

from src.pre_process import (
    TURNO_MANHA,
    TURNO_TARDE,
    ProcessedInstance,
)
from src.models.types import (
    ProfileKey,
    SolverMetrics,
    SolverParameters,
    SolverResult,
    _ascii_turno,
    _compute_instance_seed,
    _order_students_for_spreadsheet,
    _sum_pairwise_abs,
)
from src.models.feasibility import (
    check_structural_feasibility,
    compute_min_unallocated,
)
from src.models.macro_stage import (
    aggregate_profiles,
    solve_macro_stage,
)
from src.models.micro_stage import (
    solve_micro_stage,
)
from src.models.legacy_model import (
    solve_legacy_model,
)

__all__ = [
    "SolverParameters",
    "SolverMetrics",
    "SolverResult",
    "solve_ensalamento",
    "compute_min_unallocated",
]


def solve_ensalamento(
    instance: ProcessedInstance,
    params: Optional[SolverParameters] = None,
) -> SolverResult:
    """Constrói e resolve o modelo lexicográfico de ensalamento usando PuLP (CBC)."""
    if params is None:
        params = SolverParameters()

    t_total_start = time.perf_counter()

    # 1. Pré-checagens rápidas de viabilidade estrutural e Teorema de Hall
    infeas_res, min_unalloc_hall = check_structural_feasibility(
        instance, params, t_total_start
    )
    if infeas_res is not None:
        return infeas_res

    # 2. Se o modo legado for solicitado explicitamente
    if (not params.use_decomposition) or (params.w_qtd <= 0) or (params.w_gen <= 0):
        return solve_legacy_model(instance, params, t_total_start, min_unalloc_hall)

    # 3. Resolução via Agregação por Perfis + Decomposição Hierárquica em 2 Etapas
    S_active = [
        s for s in (TURNO_MANHA, TURNO_TARDE) if len(instance.turmas_por_turno.get(s, [])) > 0
    ]
    K_s: dict[str, list[int]] = {
        s: [t.id for t in instance.turmas_por_turno[s]] for s in S_active
    }
    K_s_sets: dict[str, set[int]] = {s: set(K_s[s]) for s in S_active}
    C_s = instance.capacidade_por_turno
    u_star = min_unalloc_hall if params.allow_unallocated else 0

    # Agregação O(N) dos alunos nos perfis demográficos
    buckets, profile_keys, is_valid = aggregate_profiles(instance, S_active, K_s_sets)
    if not is_valid:
        # Fallback de segurança para o modelo legado se houver restrição atípica intra-turno
        return solve_legacy_model(instance, params, t_total_start, min_unalloc_hall)

    # ETAPA 1: Partição Macro entre Turnos
    macro_out = solve_macro_stage(
        instance=instance,
        params=params,
        buckets=buckets,
        profile_keys=profile_keys,
        S_active=S_active,
        K_s=K_s,
        C_s=C_s,
        u_star=u_star,
        t_total_start=t_total_start,
    )

    if not macro_out.success:
        elapsed = time.perf_counter() - t_total_start
        return SolverResult(
            feasible=False,
            optimal=False,
            reason=macro_out.reason,
            params=params,
            metrics=SolverMetrics(
                solver_name="PULP_CBC_CMD (Decomp. Hierárquica + Perfis)",
                status_phase1=macro_out.macro_status_p1,
                status_phase2="Skipped",
                z1_objective=None,
                z2_objective=None,
                z2_pairwise_pure=None,
                build_time_s=macro_out.total_build_s,
                phase1_wall_time_s=macro_out.total_p1_wall_s,
                phase1_solver_time_s=macro_out.total_p1_solver_s,
                phase2_wall_time_s=0.0,
                phase2_solver_time_s=0.0,
                total_time_s=elapsed,
                num_variables=macro_out.total_binary_vars + macro_out.total_integer_vars + macro_out.total_continuous_vars,
                num_binary_vars=macro_out.total_binary_vars,
                num_integer_vars=macro_out.total_integer_vars,
                num_continuous_vars=macro_out.total_continuous_vars,
                num_constraints_phase1=macro_out.total_cons_p1,
                num_constraints_phase2=macro_out.total_cons_p1,
                num_unallocated=u_star,
            ),
        )

    # ETAPA 2: Subproblemas Micro Intra-Turno e Projeção Nominal O(N)
    return solve_micro_stage(
        instance=instance,
        params=params,
        macro_out=macro_out,
        S_active=S_active,
        K_s=K_s,
        C_s=C_s,
        u_star=u_star,
        t_total_start=t_total_start,
    )

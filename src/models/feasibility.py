"""Análise estrutural de capacidade e cálculo analítico de déficit via Teorema de Hall."""

from __future__ import annotations

import time
from typing import Optional

from src.pre_process import ProcessedInstance, TURNO_MANHA, TURNO_TARDE
from src.models.types import SolverMetrics, SolverParameters, SolverResult


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


def check_structural_feasibility(
    instance: ProcessedInstance,
    params: SolverParameters,
    t_total_start: float,
) -> tuple[Optional[SolverResult], int]:
    """Valida a viabilidade estrutural da instância antes de disparar o solver.

    Retorna (None, min_unalloc_hall) se a instância for estruturalmente viável,
    ou (SolverResult, min_unalloc_hall) caso haja inviabilidade intransponível.
    """
    if not instance.students:
        elapsed = time.perf_counter() - t_total_start
        return (
            SolverResult(
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
            ),
            0,
        )

    if not instance.turmas:
        elapsed = time.perf_counter() - t_total_start
        return (
            SolverResult(
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
            ),
            len(instance.students),
        )

    min_unalloc_hall = compute_min_unallocated(instance)

    if not params.allow_unallocated:
        for st in instance.students:
            if not instance.turmas_compativeis_por_aluno.get(st.id):
                elapsed = time.perf_counter() - t_total_start
                return (
                    SolverResult(
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
                    ),
                    min_unalloc_hall,
                )

        if min_unalloc_hall > 0:
            elapsed = time.perf_counter() - t_total_start
            alunos_str = "aluno não possui" if min_unalloc_hall == 1 else "alunos não possuem"
            return (
                SolverResult(
                    feasible=False,
                    optimal=False,
                    reason=(
                        f"Capacidade insuficiente: pelo menos {min_unalloc_hall} {alunos_str} "
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
                ),
                min_unalloc_hall,
            )

    return None, min_unalloc_hall


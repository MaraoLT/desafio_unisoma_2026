"""Benchmark experimental: Modelo Apenas Fase 1 vs. Modelo Fase 1 + Fase 2.

Executa comparação sistemática entre resolver apenas a Fase 1 (Min-Max das amplitudes)
e resolver o modelo completo de duas etapas (Fase 1 + Fase 2 de suavização par-a-par
e paridade intra-sala), além de construir e testar instâncias específicas onde a
Fase 1 sozinha é cega a soluções severamente piores.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.instance_generator import GeneratedInstanceSpec, materialize_instance_excel
from src.models.solver import SolverParameters, SolverResult, solve_ensalamento
from src.pre_process import GENERO_F, GENERO_M, ProcessedInstance, pre_process
from src.read_instance import read_instance


@dataclass
class ComparisonRow:
    label: str
    has_integral: bool
    n_students: int
    n_rooms: int
    # Fase 1 apenas
    status_p1_only: str
    t_p1_only_ms: float
    z1_p1: float
    z2_pure_p1: float
    sum_intra_mf_p1: int
    max_intra_mf_p1: int
    # Fase 1 + Fase 2
    status_p1p2: str
    t_p1p2_ms: float
    z1_p2: float
    z2_pure_p2: float
    sum_intra_mf_p2: int
    max_intra_mf_p2: int
    # Diferenças
    same_profile: bool


def create_phase2_counterexamples(out_dir: Path) -> list[Path]:
    """Cria instâncias cirúrgicas projetadas para expor limitações da Fase 1 isolada."""
    ce_dir = out_dir / "CE_phase2_counterexamples"
    ce_dir.mkdir(parents=True, exist_ok=True)

    # CE1: gcd(3, 9) = 3 não divide 100 M nem 100 F (Total = 200: 27M/27F Manhã, 70M/70F Tarde, 3M/3F Integrais).
    # Qualquer partição deixa resto não-nulo em Manhã (3 salas) ou Tarde (9 salas).
    # Na Fase 1, enviar os 6 Integrais para a Manhã (30M/30F -> Delta_Manha=0) deixa Tarde com
    # 70M/70F (resto 7 em M, 7 em F, 5 no total -> Z1* = 3 e Z2_puro = 48 pares desbalanceados!).
    # Já enviar 2M+2F para a Tarde zera os desvios das 9 salas da Tarde (72M/72F -> 8M/8F cada)
    # e concentra o resto apenas nas 3 salas da Manhã (28M/28F -> Z1* = 3 e Z2_puro = 6 pares: 8x menor!).
    ce1 = GeneratedInstanceSpec(
        family="CE_phase2_counterexamples",
        name="CE1_gcd3_9_pairwise_trap_n200",
        description=(
            "Contraexemplo aritmético gcd(3,9)=3 com 100M e 100F (6 Integrais): "
            "Fase 1 prova otimalidade em ~1.3s empatando Z1*=3 entre espalhar desvios "
            "nas 9 salas da Tarde (Z2_puro=48) ou concentrá-los nas 3 da Manhã (Z2_puro=6, 8x menor)."
        ),
        filepath=str(ce_dir / "CE1_gcd3_9_pairwise_trap_n200.xlsx"),
        seed=9001,
        total_students=200,
        has_integral=True,
        turmas_manha=3,
        turmas_tarde=9,
        vagas_manha=30,
        vagas_tarde=25,
        cap_total_manha=90,
        cap_total_tarde=225,
        cap_total_global=315,
        global_occupancy_pct=round(100.0 * 200 / 315, 2),
        count_manha_m=27,
        count_manha_f=27,
        count_tarde_m=70,
        count_tarde_f=70,
        count_integral_m=3,
        count_integral_f=3,
        homonym_pairs=0,
        noisy_cells=0,
    )

    # CE2: Segregação demográfica oculta sob Z1* = 0 com alunos Integrais.
    # Manhã (4 salas) começa 12M / 52F; Tarde (4 salas) começa 52M / 12F; 72 Integrais (36M / 36F).
    # Qualquer envio múltiplo de 4 mantém Z1* = 0 na Fase 1, mas só a Fase 2 direciona
    # 36M -> Manhã e 36F -> Tarde para atingir 12M/13F em todas as 8 salas!
    ce2 = GeneratedInstanceSpec(
        family="CE_phase2_counterexamples",
        name="CE2_gender_segregation_trap_n200",
        description=(
            "Contraexemplo de segregação intra-sala sob Z1*=0: múltiplas alocações de "
            "alunos Integrais têm amplitude zero entre turmas do mesmo turno, mas apenas "
            "a Fase 2 corrige a proporção M/F interna das salas."
        ),
        filepath=str(ce_dir / "CE2_gender_segregation_trap_n200.xlsx"),
        seed=9002,
        total_students=200,
        has_integral=True,
        turmas_manha=4,
        turmas_tarde=4,
        vagas_manha=30,
        vagas_tarde=30,
        cap_total_manha=120,
        cap_total_tarde=120,
        cap_total_global=240,
        global_occupancy_pct=round(100.0 * 200 / 240, 2),
        count_manha_m=12,
        count_manha_f=52,
        count_tarde_m=52,
        count_tarde_f=12,
        count_integral_m=36,
        count_integral_f=36,
        homonym_pairs=0,
        noisy_cells=0,
    )

    p1 = materialize_instance_excel(ce1)
    p2 = materialize_instance_excel(ce2)
    return [p1, p2]


def _extract_profile(instance: ProcessedInstance, res: SolverResult) -> list[tuple[str, int, int, int]]:
    """Retorna lista canônica por turma (turno, y_k, z_kM, z_kF) para checar equivalência."""
    prof = []
    for t in instance.turmas:
        yk = res.y_turma[t.id]
        zm = res.z_turma_gen[(t.id, GENERO_M)]
        zf = res.z_turma_gen[(t.id, GENERO_F)]
        prof.append((t.turno, yk, zm, zf))
    return prof


def evaluate_instance(filepath: Path, allow_integral: bool, time_limit_s: int = 30) -> ComparisonRow:
    raw = read_instance(filepath)
    proc = pre_process(raw, allow_integral=allow_integral)

    res_p1 = solve_ensalamento(
        proc,
        SolverParameters(enable_phase2=False, time_limit_s=time_limit_s),
    )
    res_p2 = solve_ensalamento(
        proc,
        SolverParameters(enable_phase2=True, time_limit_s=time_limit_s),
    )

    sum_mf_p1 = int(sum(res_p1.d_intra.values()))
    max_mf_p1 = int(max(res_p1.d_intra.values(), default=0.0))

    sum_mf_p2 = int(sum(res_p2.d_intra.values()))
    max_mf_p2 = int(max(res_p2.d_intra.values(), default=0.0))

    prof_p1 = _extract_profile(proc, res_p1)
    prof_p2 = _extract_profile(proc, res_p2)

    st_p1 = "Opt" if res_p1.optimal else "TL"
    st_p2 = "Opt" if res_p2.optimal else "TL"

    return ComparisonRow(
        label=filepath.stem,
        has_integral=any(s.disponibilidade == "INTEGRAL" for s in proc.students),
        n_students=len(proc.students),
        n_rooms=len(proc.turmas),
        status_p1_only=st_p1,
        t_p1_only_ms=res_p1.metrics.total_time_s * 1000.0,
        z1_p1=res_p1.metrics.z1_objective or 0.0,
        z2_pure_p1=res_p1.metrics.z2_pairwise_pure or 0.0,
        sum_intra_mf_p1=sum_mf_p1,
        max_intra_mf_p1=max_mf_p1,
        status_p1p2=st_p2,
        t_p1p2_ms=res_p2.metrics.total_time_s * 1000.0,
        z1_p2=res_p2.metrics.z1_objective or 0.0,
        z2_pure_p2=res_p2.metrics.z2_pairwise_pure or 0.0,
        sum_intra_mf_p2=sum_mf_p2,
        max_intra_mf_p2=max_mf_p2,
        same_profile=(prof_p1 == prof_p2),
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    gen_root = PROJECT_ROOT / "instances" / "generated"
    ce_paths = create_phase2_counterexamples(gen_root)

    test_cases: list[tuple[Path, bool]] = [
        # 1. Instâncias públicas oficiais (sem integrais)
        (PROJECT_ROOT / "instances/public/instancia_1.xlsx", False),
        (PROJECT_ROOT / "instances/public/instancia_2.xlsx", False),
        (PROJECT_ROOT / "instances/public/instancia_3.xlsx", False),
        (PROJECT_ROOT / "instances/public/instancia_4.xlsx", False),
        # 2. Instâncias difíceis sem integrais (F1)
        (gen_root / "F1_modular_conflict/F1_modular_conflict_n200.xlsx", False),
        (gen_root / "F1_modular_conflict/F1_modular_conflict_n500.xlsx", False),
        # 3. Instâncias difíceis com integrais (F2..F5, N=200 e N=500)
        (gen_root / "F2_gender_cross_integral/F2_gender_cross_integral_n200.xlsx", True),
        (gen_root / "F2_gender_cross_integral/F2_gender_cross_integral_n500.xlsx", True),
        (gen_root / "F3_bottleneck_integral/F3_bottleneck_integral_n200.xlsx", True),
        (gen_root / "F3_bottleneck_integral/F3_bottleneck_integral_n500.xlsx", True),
        (gen_root / "F4_extreme_minority_integral/F4_extreme_minority_integral_n200.xlsx", True),
        (gen_root / "F4_extreme_minority_integral/F4_extreme_minority_integral_n500.xlsx", True),
        (gen_root / "F5_noisy_realistic_integral/F5_noisy_realistic_integral_n200.xlsx", True),
        (gen_root / "F5_noisy_realistic_integral/F5_noisy_realistic_integral_n500.xlsx", True),
        # 4. Contraexemplos específicos construídos (CE1 e CE2)
        (ce_paths[0], True),
        (ce_paths[1], True),
    ]

    rows: list[ComparisonRow] = []
    for path, allow_int in test_cases:
        row = evaluate_instance(path, allow_integral=allow_int, time_limit_s=30)
        rows.append(row)

    print("=" * 136)
    print(" COMPARATIVO EXPERIMENTAL: APENAS FASE 1 vs. FASE 1 + FASE 2")
    print("=" * 136)
    header = (
        f"{'Instância':<36} | {'Int?':<4} | {'Status':<7} | {'Tempo F1':>9} | {'Tempo F1+2':>10} | "
        f"{'Z1*':>4} | {'Z2_puro (F1 -> F1+2)':>20} | {'Soma |M-F| (F1 -> F1+2)':>25} | {'Mudou?'}"
    )
    print(header)
    print("-" * 136)

    lines_out = [header, "-" * 136]
    for r in rows:
        int_flag = "Sim" if r.has_integral else "Não"
        st_cmp = f"{r.status_p1_only}/{r.status_p1p2}"
        z2_cmp = f"{r.z2_pure_p1:>6.1f} -> {r.z2_pure_p2:<6.1f}"
        mf_cmp = f"{r.sum_intra_mf_p1:>4d} (máx {r.max_intra_mf_p1:>2d}) -> {r.sum_intra_mf_p2:>4d} (máx {r.max_intra_mf_p2:>2d})"
        changed = "NÃO (idêntica)" if r.same_profile else "SIM (MELHOROU!)"
        line = (
            f"{r.label:<36} | {int_flag:<4} | {st_cmp:<7} | {r.t_p1_only_ms:>7.1f}ms | {r.t_p1p2_ms:>8.1f}ms | "
            f"{r.z1_p2:>4.0f} | {z2_cmp:>20} | {mf_cmp:>25} | {changed}"
        )
        print(line)
        lines_out.append(line)
    print("=" * 136)

    md_out = PROJECT_ROOT / "reports" / "comparativo_fase1_vs_fase2.txt"
    md_out.write_text("\n".join(lines_out), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


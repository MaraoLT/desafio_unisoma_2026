"""Ponto de entrada e orquestrador do pipeline — Desafio UniSoma 2026.

Fluxo orquestrado:
    1. read_instance  -> Leitura agnóstica do arquivo Excel (.xlsx)
    2. pre_process    -> Higienização, padronização e checagem de inconsistências
    3. solver (PuLP)  -> Otimização Lexicográfica MILP em 2 Etapas (CBC)
    4. pos_process    -> Gravação das abas 'Ensalamento' e 'Inconsistências' + Relatório
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import glob
from pathlib import Path
import sys
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models.solver import SolverParameters, SolverResult, solve_ensalamento
from src.pos_process import PostProcessArtifacts, pos_process
from src.pre_process import ProcessedInstance, pre_process
from src.read_instance import RawInstance, read_instance


@dataclass
class PipelineExecution:
    """Agrega todos os objetos produzidos em uma execução completa do pipeline."""

    raw_instance: RawInstance
    processed_instance: ProcessedInstance
    solver_result: SolverResult
    artifacts: PostProcessArtifacts


def run_pipeline(
    input_excel_path: str | Path,
    excel_output_path: Optional[str | Path] = None,
    report_output_path: Optional[str | Path] = None,
    allow_integral: bool = False,
    solver_params: Optional[SolverParameters] = None,
    print_report: bool = True,
) -> PipelineExecution:
    """Executa o fluxo ponta-a-ponta para uma instância .xlsx."""
    raw = read_instance(input_excel_path)
    processed = pre_process(raw, allow_integral=allow_integral)
    result = solve_ensalamento(processed, params=solver_params)
    artifacts = pos_process(
        instance=processed,
        result=result,
        excel_output_path=excel_output_path,
        report_output_path=report_output_path,
        print_to_terminal=print_report,
    )
    return PipelineExecution(
        raw_instance=raw,
        processed_instance=processed,
        solver_result=result,
        artifacts=artifacts,
    )


def _configure_utf8_console() -> None:
    """Garante saída UTF-8 no terminal Windows."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Orquestrador de Ensalamento Otimizado — Desafio UniSoma 2026"
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help=(
            "Caminhos para arquivos .xlsx, pastas ou padrão glob. "
            "Se omitido (e sem --all), processa todas as planilhas em instances/public/."
        ),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Executa todas as instâncias públicas de instances/public/.",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Suprime os relatórios longos no terminal (continua salvando em reports/) e exibe tabela resumo.",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Salva as abas 'Ensalamento' e 'Inconsistências' no próprio arquivo de entrada.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "instances" / "experiments",
        help="Diretório de saída para os arquivos .xlsx quando --in-place não é usado.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=PROJECT_ROOT / "reports",
        help="Diretório onde os relatórios diagnósticos .txt são salvos.",
    )
    parser.add_argument(
        "--allow-integral",
        action="store_true",
        help="Trata disponibilidade 'Integral'/'Ambos' como flexível entre Manhã e Tarde.",
    )
    parser.add_argument(
        "--allow-unallocated",
        action="store_true",
        help=(
            "Permite alocação parcial quando faltar vaga (sum x_ik + u_i = 1), "
            "maximizando os ensalados de forma equilibrada e gerando lista de espera."
        ),
    )
    parser.add_argument(
        "--w-qtd",
        type=float,
        default=1.0,
        help="Peso W_qtd para penalização de desequilíbrio de quantidade (padrão: 1.0).",
    )
    parser.add_argument(
        "--w-gen",
        type=float,
        default=1.0,
        help="Peso W_gen para penalização de desequilíbrio de gênero (padrão: 1.0).",
    )
    parser.add_argument(
        "--epsilon",
        type=float,
        default=1e-4,
        help="Peso secundário epsilon para suavização intra-turma 50/50 (padrão: 1e-4).",
    )
    parser.add_argument(
        "--no-phase2",
        action="store_true",
        help="Desativa a Fase 2 (resolve apenas a Fase 1 Min-Max).",
    )
    parser.add_argument(
        "--auto-phase2",
        action="store_true",
        help=(
            "Pula a Fase 2 automaticamente quando a solução ótima da Fase 1 já possui "
            "perfil de turmas matematicamente único (ex.: turnos fixos com amplitude <= 1)."
        ),
    )
    parser.add_argument(
        "--legacy-model",
        action="store_true",
        help="Usa o modelo legado antigo com variáveis individuais x_ik (para benchmark).",
    )
    parser.add_argument(
        "--time-limit",
        type=int,
        default=60,
        help="Limite de tempo em segundos por fase do solver CBC (padrão: 60).",
    )
    parser.add_argument(
        "--solver-verbose",
        action="store_true",
        help="Exibe logs detalhados internos do solver CBC.",
    )
    return parser.parse_args(argv)


def _collect_xlsx_from_target(target: Path) -> list[Path]:
    """Coleta recursivamente arquivos .xlsx válidos a partir de um arquivo ou diretório."""
    if target.is_file():
        return [target]
    if target.is_dir():
        return sorted(
            p
            for p in target.rglob("*.xlsx")
            if not p.name.startswith("~$") and not p.stem.lower().endswith("_validacao")
        )
    return []


def _resolve_input_paths(args: argparse.Namespace) -> list[Path]:
    """Resolve lista final de arquivos .xlsx a partir de --all, pastas, globs ou padrão."""
    collected: list[Path] = []
    if args.all or not args.inputs:
        collected.extend(_collect_xlsx_from_target(PROJECT_ROOT / "instances" / "public"))
    else:
        for raw_item in args.inputs:
            p = Path(raw_item)
            if p.exists():
                collected.extend(_collect_xlsx_from_target(p))
            else:
                for matched in sorted(glob.glob(raw_item, recursive=True)):
                    collected.extend(_collect_xlsx_from_target(Path(matched)))

    # Remove eventuais duplicatas mantendo a ordem
    seen: set[Path] = set()
    unique_paths: list[Path] = []
    for p in collected:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            unique_paths.append(p)
    return unique_paths


def main(argv: Optional[list[str]] = None) -> int:
    _configure_utf8_console()
    args = _parse_args(argv)

    instance_paths = _resolve_input_paths(args)
    if not instance_paths:
        print("Nenhuma instância .xlsx encontrada para os parâmetros informados.")
        return 1

    params = SolverParameters(
        w_qtd=args.w_qtd,
        w_gen=args.w_gen,
        epsilon=args.epsilon,
        enable_phase2=not args.no_phase2,
        auto_skip_phase2=args.auto_phase2,
        allow_unallocated=args.allow_unallocated,
        use_decomposition=not args.legacy_model,
        time_limit_s=args.time_limit,
        msg=args.solver_verbose,
    )

    executions: list[PipelineExecution] = []
    for idx, inst_path in enumerate(instance_paths, start=1):
        if idx > 1 and not args.summary_only:
            print("\n")
        excel_out = None if args.in_place else (args.output_dir / inst_path.name)
        report_out = args.reports_dir / f"{inst_path.stem}_relatorio.txt"

        ex = run_pipeline(
            input_excel_path=inst_path,
            excel_output_path=excel_out,
            report_output_path=report_out,
            allow_integral=args.allow_integral,
            solver_params=params,
            print_report=not args.summary_only,
        )
        executions.append(ex)

    if len(executions) > 1:
        print("\n" + "=" * 112)
        print(f" RESUMO DO LOTE EXECUTADO ({len(executions)} instâncias)")
        print("=" * 112)
        print(
            f"  {'Instância':<38} | {'Status':<10} | {'Alocados':>11} | {'S/Turma':>7} | "
            f"{'Z1*':>5} | {'Z2_puro*':>8} | {'Tempo Solver':>12}"
        )
        print("  " + "-" * 108)
        for ex in executions:
            sr = ex.solver_result
            m = sr.metrics
            n_tot = len(ex.processed_instance.students)
            n_aloc = len(sr.student_to_turma)
            st_lbl = "Optimal" if sr.optimal else ("Feasible" if sr.feasible else "Infeasible")
            z1_s = f"{m.z1_objective:.0f}" if m.z1_objective is not None else "-"
            z2_s = f"{m.z2_pairwise_pure:.0f}" if m.z2_pairwise_pure is not None else "-"
            print(
                f"  {ex.raw_instance.filepath.stem:<38} | {st_lbl:<10} | "
                f"{f'{n_aloc}/{n_tot}':>11} | {m.num_unallocated:>7} | "
                f"{z1_s:>5} | {z2_s:>8} | {m.total_time_s * 1000:>9.1f} ms"
            )
        print("=" * 112)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

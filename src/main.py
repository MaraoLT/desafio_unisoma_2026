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
            "Caminho(s) para arquivo(s) .xlsx de instância. "
            "Se omitido, processa todas as planilhas em instances/public/."
        ),
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


def main(argv: Optional[list[str]] = None) -> int:
    _configure_utf8_console()
    args = _parse_args(argv)

    if args.inputs:
        instance_paths = [Path(p) for p in args.inputs]
    else:
        public_dir = PROJECT_ROOT / "instances" / "public"
        instance_paths = sorted(
            p
            for p in public_dir.glob("*.xlsx")
            if not p.name.startswith("~$") and not p.stem.lower().endswith("_validacao")
        )
        if not instance_paths:
            print(f"Nenhuma instância .xlsx encontrada em: {public_dir}")
            return 1

    params = SolverParameters(
        w_qtd=args.w_qtd,
        w_gen=args.w_gen,
        epsilon=args.epsilon,
        time_limit_s=args.time_limit,
        msg=args.solver_verbose,
    )

    for idx, inst_path in enumerate(instance_paths, start=1):
        if idx > 1:
            print("\n")
        excel_out = None if args.in_place else (args.output_dir / inst_path.name)
        report_out = args.reports_dir / f"{inst_path.stem}_relatorio.txt"

        run_pipeline(
            input_excel_path=inst_path,
            excel_output_path=excel_out,
            report_output_path=report_out,
            allow_integral=args.allow_integral,
            solver_params=params,
            print_report=True,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

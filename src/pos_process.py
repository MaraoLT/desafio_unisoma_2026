"""Módulo de pós-processamento: exportação no template Excel e relatório analítico.

Responsabilidades:
1. Gravar as abas 'Ensalamento' e 'Inconsistências' seguindo estritamente o
   template exigido no Modelo Conceitual do Desafio UniSoma 2026.
2. Produzir um diagnóstico completo da solução (tempos do solver, distribuição
   Manhã vs. Tarde, gênero por sala, viabilidade de salas vazias / economia de
   recursos e recomendações práticas para melhorar o balanceamento).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from pathlib import Path
import shutil
from typing import Optional

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from src.models.solver import SolverResult
from src.pre_process import (
    GENERO_F,
    GENERO_M,
    TURNO_MANHA,
    TURNO_TARDE,
    ProcessedInstance,
    TurmaSpec,
)
from src.read_instance import normalize_token

SHEET_ENSALAMENTO = "Ensalamento"
SHEET_INCONSISTENCIAS = "Inconsistências"


@dataclass
class PostProcessArtifacts:
    """Caminhos e textos gerados na etapa de pós-processamento."""

    excel_output_path: Path
    report_text: str
    report_file_path: Optional[Path] = None


def _get_or_reset_sheet(
    wb: openpyxl.Workbook,
    canonical_name: str,
    aliases: tuple[str, ...],
) -> openpyxl.worksheet.worksheet.Worksheet:
    """Recria aba limpa na mesma posição (se já existir) ou cria nova ao final."""
    for idx, sname in enumerate(list(wb.sheetnames)):
        if normalize_token(sname) in aliases:
            wb.remove(wb[sname])
            return wb.create_sheet(title=canonical_name, index=idx)

    return wb.create_sheet(title=canonical_name)


def _auto_adjust_columns(ws: openpyxl.worksheet.worksheet.Worksheet) -> None:
    """Ajusta largura das colunas (amostrando até 1.000 linhas p/ ultra-escala)."""
    max_scan_row = min(ws.max_row, 1000)
    max_col = ws.max_column
    if max_scan_row < 1 or max_col < 1:
        return
    max_lens = [0] * max_col
    for row_vals in ws.iter_rows(
        min_row=1, max_row=max_scan_row, max_col=max_col, values_only=True
    ):
        for c_idx, val in enumerate(row_vals):
            if val is not None:
                v_len = len(str(val))
                if v_len > max_lens[c_idx]:
                    max_lens[c_idx] = v_len
    for c_idx, m_len in enumerate(max_lens, start=1):
        col_letter = get_column_letter(c_idx)
        ws.column_dimensions[col_letter].width = min(max(m_len + 4, 12), 75)


def write_excel_output(
    instance: ProcessedInstance,
    result: SolverResult,
    output_path: Optional[str | Path] = None,
) -> Path:
    """Salva o resultado nas abas 'Ensalamento' e 'Inconsistências' do Excel.

    Se output_path for omitido ou igual ao arquivo de entrada, atualiza o próprio
    arquivo de entrada. Caso contrário, copia o arquivo original preservando
    integralmente as abas 'Alunos' e 'Turmas' e grava as abas de saída na cópia.
    """
    src_path = instance.raw.filepath.resolve()
    dst_path = src_path if output_path is None else Path(output_path).resolve()
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    if dst_path != src_path:
        shutil.copy2(src_path, dst_path)

    wb = openpyxl.load_workbook(dst_path)
    try:
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        center_align = Alignment(horizontal="center", vertical="center")
        left_align = Alignment(horizontal="left", vertical="center")

        # ---------------------------------------------------------------------
        # 1. Aba Ensalamento (exatamente na ordem e colunas do template oficial)
        #    Colunas: Nome | Sexo | Disponibilidade | Turma
        # ---------------------------------------------------------------------
        ws_ens = _get_or_reset_sheet(
            wb,
            SHEET_ENSALAMENTO,
            ("ensalamento", "alocacao", "distribuicao"),
        )
        ens_headers = ["Nome", "Sexo", "Disponibilidade", "Turma"]
        ws_ens.append(ens_headers)
        for col_idx in range(1, len(ens_headers) + 1):
            cell = ws_ens.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_align if col_idx > 1 else left_align

        turma_by_id: dict[int, TurmaSpec] = {t.id: t for t in instance.turmas}

        if result.feasible and result.student_to_turma:
            for st in instance.students:
                t_id = result.student_to_turma.get(st.id)
                if t_id is None:
                    continue
                turma = turma_by_id[t_id]
                # No template do Modelo Conceitual (pág. 3):
                # Disponibilidade: MANHÃ / TARDE | Turma: [PERÍODO] - [LETRA]
                disp_out = turma.turno if st.disponibilidade == "INTEGRAL" else st.disponibilidade
                ws_ens.append([st.nome, st.sexo, disp_out, turma.codigo])

            if ws_ens.max_row <= 5000:
                for r_idx in range(2, ws_ens.max_row + 1):
                    ws_ens.cell(row=r_idx, column=1).alignment = left_align
                    ws_ens.cell(row=r_idx, column=2).alignment = center_align
                    ws_ens.cell(row=r_idx, column=3).alignment = center_align
                    ws_ens.cell(row=r_idx, column=4).alignment = center_align

        _auto_adjust_columns(ws_ens)

        # ---------------------------------------------------------------------
        # 2. Aba Inconsistências (todas as inconsistências tratadas, alertas e
        #    impeditivas reunidas de uma única vez)
        # ---------------------------------------------------------------------
        ws_inc = _get_or_reset_sheet(
            wb,
            SHEET_INCONSISTENCIAS,
            ("inconsistencias", "inconsistencia", "erros", "alertas"),
        )
        inc_headers = [
            "Linha",
            "Nome",
            "Sexo Informado",
            "Disponibilidade Informada",
            "Categoria",
            "Severidade",
            "Status",
            "Motivo / Ação",
        ]
        ws_inc.append(inc_headers)
        for col_idx in range(1, len(inc_headers) + 1):
            cell = ws_inc.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_align if col_idx in {1, 3, 4, 6, 7} else left_align

        all_inconsistencies = list(instance.inconsistencies)
        if not result.feasible and instance.capacity_feasible:
            ws_inc.append(
                [
                    "-",
                    "-",
                    "-",
                    "-",
                    "Execução do Solver",
                    "IMPEDITIVA",
                    "Requer Ação",
                    result.reason,
                ]
            )

        for inc in all_inconsistencies:
            if inc.categoria == "Capacidade Insuficiente" and result.feasible:
                status_label = "Tratada via Lista de Espera"
            elif inc.severidade == "TRATADA":
                status_label = "Tratada Automaticamente"
            elif inc.severidade == "ALERTA":
                status_label = "Alerta (Alocado em Duplicidade)"
            else:
                status_label = "Pendente de Correção"
            ws_inc.append(
                [
                    inc.row_number if inc.row_number is not None else "-",
                    inc.nome,
                    inc.sexo_original,
                    inc.disp_original,
                    inc.categoria,
                    inc.severidade,
                    status_label,
                    inc.mensagem,
                ]
            )

        if result.feasible and result.unallocated_students:
            unalloc_set = set(result.unallocated_students)
            for st in instance.students:
                if st.id in unalloc_set:
                    ws_inc.append(
                        [
                            st.row_number,
                            st.nome,
                            st.sexo,
                            st.disponibilidade,
                            "Sem Turma (Lista de Espera)",
                            "ALERTA",
                            "Não Alocado (Excedente de Vagas)",
                            (
                                f"Excedente de capacidade para disponibilidade '{st.disponibilidade}'; "
                                "aluno registrado na lista de espera otimizada."
                            ),
                        ]
                    )

        if ws_inc.max_row == 1:
            ws_inc.append(
                [
                    "-",
                    "-",
                    "-",
                    "-",
                    "Validação Geral",
                    "OK",
                    "Sem Inconsistências",
                    "Nenhuma inconsistência encontrada na planilha de entrada.",
                ]
            )

        _auto_adjust_columns(ws_inc)
        wb.save(dst_path)
    finally:
        wb.close()

    return dst_path


def build_diagnostic_report(
    instance: ProcessedInstance,
    result: SolverResult,
    excel_output_path: Optional[Path] = None,
) -> str:
    """Constrói relatório textual completo para exibição no terminal e arquivo .txt."""
    sep_heavy = "=" * 88
    sep_light = "-" * 88
    lines: list[str] = []

    lines.append(sep_heavy)
    lines.append(f" RELATÓRIO DIAGNÓSTICO DE ENSALAMENTO — {instance.raw.filepath.name}")
    lines.append(sep_heavy)

    # -------------------------------------------------------------------------
    # 1. Resumo de Leitura, Higienização e Inconsistências
    # -------------------------------------------------------------------------
    n_raw = len(instance.raw.students)
    n_valid = len(instance.students)
    n_invalid = len(instance.invalid_records)
    n_footer = len(instance.ignored_summary_rows)

    inc_impeditivas = [i for i in instance.inconsistencies if i.severidade == "IMPEDITIVA"]
    inc_alertas = [i for i in instance.inconsistencies if i.severidade == "ALERTA"]
    inc_tratadas = [i for i in instance.inconsistencies if i.severidade == "TRATADA"]

    lines.append("\n[1] PRÉ-PROCESSAMENTO & QUALIDADE DOS DADOS")
    lines.append(sep_light)
    lines.append(f"  Arquivo de entrada          : {instance.raw.filepath}")
    if excel_output_path is not None:
        lines.append(f"  Arquivo Excel gerado        : {excel_output_path}")
    lines.append(
        f"  Linhas lidas na aba Alunos  : {n_raw} "
        f"(Válidos em I: {n_valid} | Inválidos retidos: {n_invalid} | Rodapés ignorados: {n_footer})"
    )
    lines.append(
        f"  Inconsistências detectadas  : {len(instance.inconsistencies)} total "
        f"({len(inc_tratadas)} tratadas auto | {len(inc_alertas)} alertas duplicidade | "
        f"{len(inc_impeditivas)} impeditivas)"
    )

    if instance.inconsistencies:
        lines.append("\n  Detalhamento das ocorrências:")
        max_inc_show = 25 if len(instance.inconsistencies) > 30 else len(instance.inconsistencies)
        for inc in instance.inconsistencies[:max_inc_show]:
            loc = f"Linha {inc.row_number:>3}" if inc.row_number is not None else "Global   "
            lines.append(f"    • [{inc.severidade:<10}] {loc} | {inc.nome}: {inc.mensagem}")
        if len(instance.inconsistencies) > max_inc_show:
            rem_inc = len(instance.inconsistencies) - max_inc_show
            lines.append(
                f"    ... (+{rem_inc} ocorrências adicionais registradas integralmente na aba '{SHEET_INCONSISTENCIAS}')"
            )

    # -------------------------------------------------------------------------
    # 2. Métricas de Execução do Solver Matemático (PuLP / CBC)
    # -------------------------------------------------------------------------
    m = result.metrics
    lines.append("\n[2] INFORMAÇÕES DO SOLVER MATEMÁTICO (MILP LEXICOGRÁFICO - PULP)")
    lines.append(sep_light)
    lines.append(f"  Solver utilizado            : {m.solver_name}")
    lines.append(
        f"  Pesos do modelo             : W_qtd={result.params.w_qtd}, "
        f"W_gen={result.params.w_gen}, epsilon={result.params.epsilon}"
    )
    lines.append(
        f"  Dimensão do modelo          : {m.num_variables} variáveis "
        f"({m.num_binary_vars} binárias, {m.num_integer_vars} inteiras de fluxo/perfil, "
        f"{m.num_continuous_vars} contínuas)"
    )
    lines.append(
        f"  Restrições lineares         : {m.num_constraints_phase1} (Fase 1) -> "
        f"{m.num_constraints_phase2} (Fase 2 com trava lexicográfica)"
    )
    lines.append(
        f"  Status Fase 1 (Min-Max)     : {m.status_phase1}"
        + (f" | Z1* = {m.z1_objective:.4f}" if m.z1_objective is not None else "")
    )
    lines.append(
        f"  Status Fase 2 (Par-a-Par)   : {m.status_phase2}"
        + (
            f" | Z2* = {m.z2_pairwise_pure:.4f} (total c/ eps: {m.z2_objective:.6f})"
            if m.z2_objective is not None and m.z2_pairwise_pure is not None
            else ""
        )
    )
    lines.append(
        f"  Tempos de execução          : Build = {m.build_time_s * 1000:.1f} ms | "
        f"Fase 1 = {m.phase1_wall_time_s * 1000:.1f} ms | "
        f"Fase 2 = {m.phase2_wall_time_s * 1000:.1f} ms | "
        f"TOTAL = {m.total_time_s * 1000:.1f} ms ({m.total_time_s:.4f} s)"
    )
    lines.append(f"  Diagnóstico de parada       : {result.reason}")

    if not result.feasible:
        lines.append("\n[!] O ensalamento ótimo não pôde ser concluído devido à inviabilidade acima.")
        lines.append(sep_heavy)
        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # 3. Panorama por Turno (Manhã vs. Tarde)
    # -------------------------------------------------------------------------
    lines.append("\n[3] DISTRIBUIÇÃO GERAL POR TURNO (MANHÃ vs. TARDE)")
    lines.append(sep_light)

    total_alocados = sum(result.y_turma.values())
    total_m = sum(result.z_turma_gen[(t.id, GENERO_M)] for t in instance.turmas)
    total_f = sum(result.z_turma_gen[(t.id, GENERO_F)] for t in instance.turmas)
    total_cap = sum(t.capacidade for t in instance.turmas)

    turno_stats: dict[str, dict[str, float]] = {}

    for turno in (TURNO_MANHA, TURNO_TARDE):
        t_list = instance.turmas_por_turno[turno]
        n_turmas = len(t_list)
        cap_unit = instance.capacidade_por_turno[turno]
        cap_tot = n_turmas * cap_unit
        aloc_t = sum(result.y_turma[t.id] for t in t_list)
        m_t = sum(result.z_turma_gen[(t.id, GENERO_M)] for t in t_list)
        f_t = sum(result.z_turma_gen[(t.id, GENERO_F)] for t in t_list)
        livres_t = cap_tot - aloc_t
        ocup_pct = (100.0 * aloc_t / cap_tot) if cap_tot > 0 else 0.0
        share_pct = (100.0 * aloc_t / total_alocados) if total_alocados > 0 else 0.0
        pct_m = (100.0 * m_t / aloc_t) if aloc_t > 0 else 0.0
        pct_f = (100.0 * f_t / aloc_t) if aloc_t > 0 else 0.0

        turno_stats[turno] = {
            "n_turmas": n_turmas,
            "cap_unit": cap_unit,
            "cap_tot": cap_tot,
            "aloc": aloc_t,
            "m": m_t,
            "f": f_t,
            "livres": livres_t,
            "ocup_pct": ocup_pct,
            "pct_m": pct_m,
            "pct_f": pct_f,
        }

        amp_qtd = int(round(result.delta_qtd.get(turno, 0.0)))
        amp_m = int(round(result.delta_gen.get((turno, GENERO_M), 0.0)))
        amp_f = int(round(result.delta_gen.get((turno, GENERO_F), 0.0)))
        amp_intra = int(round(result.delta_intra.get(turno, 0.0)))

        lines.append(
            f"  • {turno:<6}: {aloc_t:>3} alunos ({share_pct:5.1f}% do total) | "
            f"Vagas: {aloc_t:>3}/{cap_tot:<3} ({ocup_pct:5.1f}% ocup, {livres_t:>2} livres) | "
            f"Gênero: {m_t:>2} M ({pct_m:4.1f}%) / {f_t:>2} F ({pct_f:4.1f}%)"
        )
        lines.append(
            f"            Amplitudes máx no turno -> Qtd (Delta_qtd): {amp_qtd} | "
            f"Masc (Delta_M): {amp_m} | Fem (Delta_F): {amp_f} | Máx |M-F| intra-sala: {amp_intra}"
        )

    ocup_global = (100.0 * total_alocados / total_cap) if total_cap > 0 else 0.0
    lines.append(
        f"  • TOTAL : {total_alocados:>3} alunos alocados em {len(instance.turmas)} salas | "
        f"Capacidade Global: {total_alocados}/{total_cap} ({ocup_global:5.1f}% ocup) | "
        f"{total_m} M / {total_f} F"
    )

    if result.unallocated_students:
        unalloc_set = set(result.unallocated_students)
        unalloc_objs = [s for s in instance.students if s.id in unalloc_set]
        u_m = sum(1 for s in unalloc_objs if s.sexo == GENERO_M)
        u_f = sum(1 for s in unalloc_objs if s.sexo == GENERO_F)
        u_manha = sum(1 for s in unalloc_objs if s.disponibilidade == TURNO_MANHA)
        u_tarde = sum(1 for s in unalloc_objs if s.disponibilidade == TURNO_TARDE)
        u_int = sum(1 for s in unalloc_objs if s.disponibilidade == "INTEGRAL")
        lines.append(
            f"  • LISTA DE ESPERA (SEM TURMA): {len(unalloc_objs)} de {len(instance.students)} "
            f"alunos válidos não alocados ({100.0 * len(unalloc_objs) / len(instance.students):.1f}%) | "
            f"Por turno: {u_manha} Manhã, {u_tarde} Tarde, {u_int} Integral | "
            f"Gênero: {u_m} M / {u_f} F"
        )
        preview = ", ".join(f"{s.nome} ({s.sexo}/{s.disponibilidade})" for s in unalloc_objs[:6])
        suffix = (
            f" ... (+{len(unalloc_objs) - 6} listados na aba '{SHEET_INCONSISTENCIAS}')"
            if len(unalloc_objs) > 6
            else ""
        )
        lines.append(f"            Exemplos s/ turma -> {preview}{suffix}")

    integral_students = [s for s in instance.students if s.disponibilidade == "INTEGRAL"]
    if integral_students:
        turma_turno_map = {t.id: t.turno for t in instance.turmas}
        int_m_manha = sum(
            1
            for s in integral_students
            if s.sexo == GENERO_M and turma_turno_map.get(result.student_to_turma.get(s.id, -1)) == TURNO_MANHA
        )
        int_f_manha = sum(
            1
            for s in integral_students
            if s.sexo == GENERO_F and turma_turno_map.get(result.student_to_turma.get(s.id, -1)) == TURNO_MANHA
        )
        int_m_tarde = sum(
            1
            for s in integral_students
            if s.sexo == GENERO_M and turma_turno_map.get(result.student_to_turma.get(s.id, -1)) == TURNO_TARDE
        )
        int_f_tarde = sum(
            1
            for s in integral_students
            if s.sexo == GENERO_F and turma_turno_map.get(result.student_to_turma.get(s.id, -1)) == TURNO_TARDE
        )
        tot_int_manha = int_m_manha + int_f_manha
        tot_int_tarde = int_m_tarde + int_f_tarde
        tot_int_unalloc = len(integral_students) - tot_int_manha - tot_int_tarde
        extra_unalloc_str = (
            f" | {tot_int_unalloc} em lista de espera" if tot_int_unalloc > 0 else ""
        )
        lines.append(
            f"  • DECISÃO DE ALUNOS INTEGRAIS ({len(integral_students)} flexíveis): "
            f"{tot_int_manha} enviados p/ MANHÃ ({int_m_manha} M, {int_f_manha} F) | "
            f"{tot_int_tarde} enviados p/ TARDE ({int_m_tarde} M, {int_f_tarde} F)"
            f"{extra_unalloc_str}"
        )

    # -------------------------------------------------------------------------
    # 4. Detalhamento por Sala (Quantidade e Gênero em Cada Sala)
    # -------------------------------------------------------------------------
    lines.append("\n[4] DETALHAMENTO POR SALA (LOTAÇÃO E GÊNERO)")
    lines.append(sep_light)

    empty_rooms_current = sum(1 for t in instance.turmas if result.y_turma[t.id] == 0)

    def _format_room_row(t: TurmaSpec) -> str:
        tot = result.y_turma[t.id]
        m_c = result.z_turma_gen[(t.id, GENERO_M)]
        f_c = result.z_turma_gen[(t.id, GENERO_F)]
        livres = t.capacidade - tot
        ocup = (100.0 * tot / t.capacidade) if t.capacidade > 0 else 0.0
        pm = (100.0 * m_c / tot) if tot > 0 else 0.0
        pf = (100.0 * f_c / tot) if tot > 0 else 0.0
        diff_mf = abs(m_c - f_c)
        return (
            f"  {t.codigo:<12} | {t.turno:<6} | {tot:>4}/{t.capacidade:<5} | {ocup:>6.1f}% | "
            f"{livres:>6} | {m_c:>4} ({pm:>3.0f}%) | {f_c:>4} ({pf:>3.0f}%) | {diff_mf:>7}"
        )

    header_table = (
        f"  {'Turma':<12} | {'Turno':<6} | {'Lotação':>10} | {'Ocup.':>7} | "
        f"{'Livres':>6} | {'Masc (M)':>11} | {'Fem (F)':>11} | {'|M - F|':>7}"
    )

    if len(instance.turmas) <= 80:
        lines.append(header_table)
        lines.append("  " + "-" * (len(header_table) - 2))
        for t in instance.turmas:
            lines.append(_format_room_row(t))
    else:
        lines.append(
            f"  Resumo Agrupado por Perfil de Sala ({len(instance.turmas)} salas no total):"
        )
        prof_counts: Counter[tuple[str, int, int, int, int]] = Counter()
        for t in instance.turmas:
            tot = result.y_turma[t.id]
            m_c = result.z_turma_gen[(t.id, GENERO_M)]
            f_c = result.z_turma_gen[(t.id, GENERO_F)]
            prof_counts[(t.turno, tot, t.capacidade, m_c, f_c)] += 1

        prof_header = (
            f"  {'Turno':<6} | {'Qtd Salas':>9} | {'Lotação':>10} | {'Ocup.':>7} | "
            f"{'Masc (M)':>9} | {'Fem (F)':>9} | {'|M - F|':>7}"
        )
        lines.append(prof_header)
        lines.append("  " + "-" * (len(prof_header) - 2))
        for (turno_p, tot_p, cap_p, m_p, f_p), qtd_salas in sorted(
            prof_counts.items(), key=lambda item: (0 if item[0][0] == TURNO_MANHA else 1, -item[0][1], -item[0][3])
        ):
            ocup_p = (100.0 * tot_p / cap_p) if cap_p > 0 else 0.0
            lines.append(
                f"  {turno_p:<6} | {qtd_salas:>9} | {tot_p:>4}/{cap_p:<5} | {ocup_p:>6.1f}% | "
                f"{m_p:>9} | {f_p:>9} | {abs(m_p - f_p):>7}"
            )

        lines.append("\n  Amostra nominal de salas (primeiras 15 e últimas 10):")
        lines.append(header_table)
        lines.append("  " + "-" * (len(header_table) - 2))
        for t in instance.turmas[:15]:
            lines.append(_format_room_row(t))
        omitted = len(instance.turmas) - 25
        lines.append(
            f"  ... (+{omitted} salas intermediárias omitidas no resumo; "
            f"alocação completa disponível na aba '{SHEET_ENSALAMENTO}')"
        )
        for t in instance.turmas[-10:]:
            lines.append(_format_room_row(t))

    # -------------------------------------------------------------------------
    # 5. Análise de Economia de Recursos (Viabilidade de Salas Vazias)
    # -------------------------------------------------------------------------
    lines.append("\n[5] ANÁLISE DE RECURSOS — EXISTE SOLUÇÃO COM SALAS VAZIAS?")
    lines.append(sep_light)
    if empty_rooms_current > 0:
        lines.append(f"  Na solução atual já há {empty_rooms_current} sala(s) vazia(s).")

    total_savable_rooms = 0
    for turno in (TURNO_MANHA, TURNO_TARDE):
        st_info = turno_stats[turno]
        n_turmas = int(st_info["n_turmas"])
        cap_unit = int(st_info["cap_unit"])
        aloc_t = int(st_info["aloc"])

        if n_turmas == 0 or cap_unit == 0:
            continue

        min_rooms_needed = math.ceil(aloc_t / cap_unit) if aloc_t > 0 else 0
        savable = n_turmas - min_rooms_needed
        total_savable_rooms += max(0, savable)

        if savable > 0:
            avg_current = aloc_t / n_turmas
            avg_compact = (aloc_t / min_rooms_needed) if min_rooms_needed > 0 else 0.0
            ocup_compact = (
                (100.0 * aloc_t / (min_rooms_needed * cap_unit)) if min_rooms_needed > 0 else 0.0
            )
            lines.append(
                f"  • {turno:<6}: SIM! É matematicamente possível deixar até {savable} sala(s) VAZIA(S) "
                f"(usando {min_rooms_needed} de {n_turmas} turmas)."
            )
            lines.append(
                f"            Trade-off: economiza {savable} sala(s)/professor(es), mas eleva a média "
                f"de {avg_current:.1f} alunos/sala ({st_info['ocup_pct']:.1f}% ocup.) para "
                f"{avg_compact:.1f} alunos/sala ({ocup_compact:.1f}% ocup.)."
            )
            lines.append(
                f"            Nota: o modelo padrão ocupou todas as {n_turmas} salas porque a regra "
                "de Equilíbrio em Quantidade penaliza turmas vazias frente às cheias."
            )
        else:
            max_with_one_less = max(0, n_turmas - 1) * cap_unit
            deficit_if_closed = aloc_t - max_with_one_less
            lines.append(
                f"  • {turno:<6}: NÃO. Todas as {n_turmas} sala(s) são estritamente necessárias "
                f"(mínimo teórico = ceil({aloc_t}/{cap_unit}) = {min_rooms_needed} salas)."
            )
            lines.append(
                f"            Se 1 sala fosse fechada, restariam {max_with_one_less} vagas para "
                f"{aloc_t} alunos (faltariam {deficit_if_closed} vagas)."
            )

    if total_savable_rooms == 0:
        lines.append(
            "  => Conclusão de Recursos: A infraestrutura ofertada está enxuta; "
            "nenhuma sala pode ficar vazia sem violar o limite máximo de vagas."
        )
    else:
        lines.append(
            f"  => Conclusão de Recursos: Há potencial para economizar até {total_savable_rooms} "
            "sala(s) caso a ONG priorize redução de custos sobre turmas menores."
        )

    # -------------------------------------------------------------------------
    # 6. Recomendações de Como Melhorar o Balanceamento
    # -------------------------------------------------------------------------
    lines.append("\n[6] COMO MELHORAR O BALANCEAMENTO — DIAGNÓSTICO E RECOMENDAÇÕES")
    lines.append(sep_light)
    rec_items: list[str] = []

    # 6.1 Análise do limite teórico intra-turno (divisibilidade inteira)
    for turno in (TURNO_MANHA, TURNO_TARDE):
        st_info = turno_stats[turno]
        n_turmas = int(st_info["n_turmas"])
        aloc_t = int(st_info["aloc"])
        m_t = int(st_info["m"])
        f_t = int(st_info["f"])
        if n_turmas <= 1:
            rec_items.append(
                f"[Turno {turno}] Possui apenas 1 turma ({aloc_t} alunos); não há variabilidade "
                "entre turmas neste período."
            )
            continue

        amp_q = int(round(result.delta_qtd.get(turno, 0.0)))
        amp_m = int(round(result.delta_gen.get((turno, GENERO_M), 0.0)))
        amp_f = int(round(result.delta_gen.get((turno, GENERO_F), 0.0)))
        rem_q = aloc_t % n_turmas

        if amp_q == 0 and amp_m <= 1 and amp_f <= 1:
            rec_items.append(
                f"[Ótimo Teórico - {turno}] O ensalamento atingiu equilíbrio perfeito de quantidade "
                f"({aloc_t // n_turmas} alunos em cada sala) e o menor desvio inteiro possível "
                f"de gênero entre salas (Delta_M={amp_m}, Delta_F={amp_f})."
            )
        elif amp_q == 1 and rem_q != 0:
            faltam_para_igualar = n_turmas - rem_q
            rec_items.append(
                f"[Indivisibilidade Inteira - {turno}] A diferença de 1 aluno entre salas "
                f"({aloc_t} alunos / {n_turmas} salas deixa resto {rem_q}) é matematicamente "
                f"irredutível; {faltam_para_igualar} nova(s) matrícula(s) igualariam todas as salas."
            )

        # Desequilíbrio demográfico 50/50 dentro do turno
        diff_turno_mf = abs(m_t - f_t)
        if diff_turno_mf >= n_turmas:
            gen_maior = "Feminino (F)" if f_t > m_t else "Masculino (M)"
            gen_menor = "Masculino (M)" if f_t > m_t else "Feminino (F)"
            rec_items.append(
                f"[Paridade 50/50 - {turno}] A base de inscritos do turno tem mais {gen_maior} ({max(m_t, f_t)}) "
                f"do que {gen_menor} ({min(m_t, f_t)}), gerando diferença média de "
                f"~{diff_turno_mf / n_turmas:.1f} por sala. Para aproximar cada sala do 50/50, "
                f"seria necessário captar/migrar ~{diff_turno_mf} aluno(s) do gênero {gen_menor}."
            )

    # 6.2 Complementaridade de gênero e ocupação entre Manhã e Tarde
    m_manha, f_manha = int(turno_stats[TURNO_MANHA]["m"]), int(turno_stats[TURNO_MANHA]["f"])
    m_tarde, f_tarde = int(turno_stats[TURNO_TARDE]["m"]), int(turno_stats[TURNO_TARDE]["f"])
    imb_manha = m_manha - f_manha  # >0 mais M, <0 mais F
    imb_tarde = m_tarde - f_tarde

    if imb_manha * imb_tarde < 0:
        trocas_uteis = min(abs(imb_manha), abs(imb_tarde)) // 2
        if trocas_uteis > 0:
            rec_items.append(
                f"[Sinergia entre Turnos] Manhã e Tarde têm desvios de gênero em direções opostas "
                f"(Manhã: {m_manha}M/{f_manha}F vs. Tarde: {m_tarde}M/{f_tarde}F). Caso alguns "
                f"alunos tenham disponibilidade flexível (Integral), permutar até {trocas_uteis} "
                "par(es) entre turnos melhoraria simultaneamente a paridade 50/50 nos dois períodos."
            )

    ocup_m = turno_stats[TURNO_MANHA]["ocup_pct"]
    ocup_t = turno_stats[TURNO_TARDE]["ocup_pct"]
    if abs(ocup_m - ocup_t) >= 15.0:
        turno_cheio = TURNO_MANHA if ocup_m > ocup_t else TURNO_TARDE
        turno_leve = TURNO_TARDE if ocup_m > ocup_t else TURNO_MANHA
        rec_items.append(
            f"[Balanceamento de Infraestrutura] A taxa de ocupação de {turno_cheio} ({max(ocup_m, ocup_t):.1f}%) "
            f"difere bastante de {turno_leve} ({min(ocup_m, ocup_t):.1f}%). Avaliar remanejamento de "
            f"turmas/salas ou direcionamento de novas matrículas para o período da {turno_leve}."
        )

    # 6.3 Impacto da lista de espera (quando allow_unallocated=True) e registros inválidos
    if result.unallocated_students:
        unalloc_set = set(result.unallocated_students)
        unalloc_objs = [s for s in instance.students if s.id in unalloc_set]
        u_manha = sum(1 for s in unalloc_objs if s.disponibilidade == TURNO_MANHA)
        u_tarde = sum(1 for s in unalloc_objs if s.disponibilidade == TURNO_TARDE)
        u_int = sum(1 for s in unalloc_objs if s.disponibilidade == "INTEGRAL")
        cap_u_m = max(1, int(turno_stats[TURNO_MANHA]["cap_unit"]))
        cap_u_t = max(1, int(turno_stats[TURNO_TARDE]["cap_unit"]))
        livres_tot = int(turno_stats[TURNO_MANHA]["livres"] + turno_stats[TURNO_TARDE]["livres"])
        salas_extra_m = math.ceil(u_manha / cap_u_m) if u_manha > 0 else 0
        salas_extra_t = math.ceil((u_tarde + u_int) / cap_u_t) if (u_tarde + u_int) > 0 else 0
        rec_items.append(
            f"[Expansão de Vagas / Lista de Espera] {len(unalloc_objs)} aluno(s) ficaram sem turma "
            f"por limite físico de capacidade ({u_manha} Manhã, {u_tarde} Tarde, {u_int} Integral; "
            f"vagas ociosas incompatíveis restantes: {livres_tot}). Abrir +{salas_extra_m} turma(s) na "
            f"Manhã e +{salas_extra_t} na Tarde (ou ampliar vagas/sala) absorveria 100% da fila."
        )

    if n_invalid > 0:
        vagas_livres_totais = int(
            turno_stats[TURNO_MANHA]["livres"] + turno_stats[TURNO_TARDE]["livres"]
        )
        rec_items.append(
            f"[Saneamento Cadastral] Existem {n_invalid} registro(s) não alocados por erro de "
            f"preenchimento (ver aba '{SHEET_INCONSISTENCIAS}'). Há {vagas_livres_totais} vagas "
            f"ociosas no total ({int(turno_stats[TURNO_MANHA]['livres'])} Manhã / "
            f"{int(turno_stats[TURNO_TARDE]['livres'])} Tarde), suficientes para absorvê-los "
            "assim que corrigidos pela secretaria."
        )

    for idx, item in enumerate(rec_items, start=1):
        lines.append(f"  {idx}. {item}")

    lines.append("\n" + sep_heavy)
    return "\n".join(lines)


def pos_process(
    instance: ProcessedInstance,
    result: SolverResult,
    excel_output_path: Optional[str | Path] = None,
    report_output_path: Optional[str | Path] = None,
    print_to_terminal: bool = True,
) -> PostProcessArtifacts:
    """Executa pós-processamento completo: grava Excel oficial e gera relatório."""
    saved_excel_path = write_excel_output(
        instance=instance,
        result=result,
        output_path=excel_output_path,
    )

    report_text = build_diagnostic_report(
        instance=instance,
        result=result,
        excel_output_path=saved_excel_path,
    )

    saved_report_path: Optional[Path] = None
    if report_output_path is not None:
        saved_report_path = Path(report_output_path).resolve()
        saved_report_path.parent.mkdir(parents=True, exist_ok=True)
        saved_report_path.write_text(report_text, encoding="utf-8")

    if print_to_terminal:
        print(report_text)

    return PostProcessArtifacts(
        excel_output_path=saved_excel_path,
        report_text=report_text,
        report_file_path=saved_report_path,
    )

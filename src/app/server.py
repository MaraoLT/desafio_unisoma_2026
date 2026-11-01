"""Backend de estado, edição de planilha, solver e assistente offline — Desafio UniSoma 2026."""

from __future__ import annotations

from pathlib import Path
import tempfile
import traceback
from typing import Any, Optional

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from src.app.pdf_lists import generate_class_lists_pdf
from src.models.solver import SolverParameters, solve_ensalamento
from src.pos_process import write_excel_output
from src.pre_process import GENERO_F, GENERO_M, TURNO_MANHA, TURNO_TARDE, pre_process
from src.read_instance import (
    RawInstance,
    RawStudentRow,
    RawTurmasConfig,
    normalize_token,
)

DEFAULT_PAGE_SIZE = 5000


class AppBackend:
    """Gerencia a planilha aberta em memória, o solver MILP e o assistente determinístico."""

    def __init__(self) -> None:
        self.current_filepath: Optional[Path] = None
        self.sheets_data: dict[str, list[list[str]]] = {}
        self.active_sheet: str = "Alunos"
        self.dirty: bool = False
        self.solver_result = None
        self.processed_instance = None
        self.last_summary: Optional[dict[str, Any]] = None
        self.undo_stack: list[dict[str, list[list[str]]]] = []
        self.redo_stack: list[dict[str, list[list[str]]]] = []

    def _clone_sheets(self) -> dict[str, list[list[str]]]:
        return {s: [list(r) for r in rows] for s, rows in self.sheets_data.items()}

    def _push_undo(self) -> None:
        self.undo_stack.append(self._clone_sheets())
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self) -> dict[str, Any]:
        if not self.undo_stack:
            return {"success": False, "error": "Nada para desfazer (Ctrl+Z)."}
        self.redo_stack.append(self._clone_sheets())
        self.sheets_data = self.undo_stack.pop()
        self.dirty = True
        validation = self.validate_data()
        page_payload = self.get_sheet_page(self.active_sheet, page=1, search_query="")
        return {
            **page_payload,
            "dirty": self.dirty,
            "summary": validation.get("summary") if validation.get("success") else None,
        }

    def redo(self) -> dict[str, Any]:
        if not self.redo_stack:
            return {"success": False, "error": "Nada para refazer (Ctrl+Y)."}
        self.undo_stack.append(self._clone_sheets())
        self.sheets_data = self.redo_stack.pop()
        self.dirty = True
        validation = self.validate_data()
        page_payload = self.get_sheet_page(self.active_sheet, page=1, search_query="")
        return {
            **page_payload,
            "dirty": self.dirty,
            "summary": validation.get("summary") if validation.get("success") else None,
        }

    def load_excel(self, file_path_str: str) -> dict[str, Any]:
        """Carrega todas as abas de um arquivo .xlsx para edição em memória."""
        p = Path(file_path_str).resolve()
        if not p.exists():
            return {"success": False, "error": f"Arquivo não encontrado: {p}"}

        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        loaded_sheets: dict[str, list[list[str]]] = {}
        try:
            for sname in wb.sheetnames:
                ws = wb[sname]
                rows: list[list[str]] = []
                is_turmas = normalize_token(sname) == "turmas"
                for row in ws.iter_rows(values_only=True):
                    row_strs: list[str] = []
                    for c_i, v in enumerate(row):
                        if v is None:
                            row_strs.append("")
                        elif is_turmas and c_i == 1 and isinstance(v, (int, float)):
                            # Converte capacidades e turmas para inteiro sem vírgula/ponto flutuante
                            try:
                                row_strs.append(str(int(round(float(v)))))
                            except Exception:
                                row_strs.append(str(v))
                        elif isinstance(v, float) and v.is_integer():
                            row_strs.append(str(int(v)))
                        else:
                            row_strs.append(str(v))
                    rows.append(row_strs)
                while rows and all(c == "" for c in rows[-1]):
                    rows.pop()
                loaded_sheets[sname] = rows if rows else [[""]]
        finally:
            wb.close()

        self.current_filepath = p
        self.sheets_data = loaded_sheets
        self.dirty = False
        self.solver_result = None
        self.processed_instance = None
        self.last_summary = None
        self.undo_stack.clear()
        self.redo_stack.clear()

        if "Alunos" in self.sheets_data:
            self.active_sheet = "Alunos"
        else:
            self.active_sheet = next(iter(self.sheets_data.keys()), "Alunos")

        validation = self.validate_data()
        page_payload = self.get_sheet_page(self.active_sheet, page=1, search_query="")
        return {
            **page_payload,
            "filename": p.name,
            "filepath": str(p),
            "dirty": self.dirty,
            "has_ensalamento": "Ensalamento" in self.sheets_data
            and len(self.sheets_data["Ensalamento"]) > 1,
            "summary": validation.get("summary") if validation.get("success") else None,
        }

    def _compute_flagged_rows(self, sheet_name: str) -> dict[int, str]:
        """Retorna mapa {excel_row: severidade} para destacar inconsistências na grade."""
        flagged_rows: dict[int, str] = {}
        if sheet_name == "Alunos" and self.last_summary:
            for inc in self.last_summary.get("inconsistencias", []):
                sev = inc.get("severidade", "ALERTA")
                all_rows = inc.get("linhas") or ([inc.get("linha")] if inc.get("linha") else [])
                for rn in all_rows:
                    if isinstance(rn, int):
                        prev = flagged_rows.get(rn)
                        if sev == "IMPEDITIVA" or prev is None or (prev == "TRATADA" and sev == "ALERTA"):
                            flagged_rows[rn] = sev
        return flagged_rows

    def get_sheet_page(
        self,
        sheet_name: str,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        search_query: str = "",
    ) -> dict[str, Any]:
        """Retorna cabeçalho e fatia paginada/filtrada de linhas preservando o índice real."""
        if sheet_name not in self.sheets_data:
            return {"success": False, "error": f"Aba '{sheet_name}' não existe."}

        self.active_sheet = sheet_name
        matrix = self.sheets_data[sheet_name]
        if not matrix:
            matrix = [[""]]
            self.sheets_data[sheet_name] = matrix

        header_row = matrix[0]
        num_cols = max((len(r) for r in matrix[: min(len(matrix), 200)]), default=3)
        num_cols = max(num_cols, len(header_row), 2)

        q_norm = normalize_token(search_query) if search_query.strip() else ""

        # Constrói lista de (row_index_in_matrix, row_values) para linhas de dados (1..N-1)
        indexed_rows: list[tuple[int, list[str]]] = []
        for r_idx in range(1, len(matrix)):
            row_vals = matrix[r_idx]
            if q_norm:
                joined = normalize_token(" ".join(row_vals))
                if q_norm not in joined and q_norm != str(r_idx + 1):
                    continue
            indexed_rows.append((r_idx, row_vals))

        total_data_rows = len(indexed_rows)
        page_size = max(50, page_size)
        total_pages = max(1, (total_data_rows + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))

        start = (page - 1) * page_size
        end = start + page_size
        sliced = indexed_rows[start:end]

        flagged_rows = self._compute_flagged_rows(sheet_name)

        rows_out = []
        for mat_idx, r_vals in sliced:
            excel_row_num = mat_idx + 1
            padded = [r_vals[c] if c < len(r_vals) else "" for c in range(num_cols)]
            rows_out.append(
                {
                    "mat_idx": mat_idx,
                    "excel_row": excel_row_num,
                    "cells": padded,
                    "flag": flagged_rows.get(excel_row_num, ""),
                }
            )

        header_padded = [
            header_row[c] if c < len(header_row) else "" for c in range(num_cols)
        ]

        return {
            "success": True,
            "sheet_names": list(self.sheets_data.keys()),
            "active_sheet": sheet_name,
            "num_cols": num_cols,
            "header": header_padded,
            "rows": rows_out,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "total_rows": total_data_rows,
            "dirty": self.dirty,
        }

    def jump_to_row(
        self, sheet_name: str, excel_row: int, page_size: int = DEFAULT_PAGE_SIZE
    ) -> dict[str, Any]:
        """Calcula a página onde está a linha solicitada e retorna os dados dessa página."""
        if sheet_name not in self.sheets_data:
            return {"success": False, "error": f"Aba '{sheet_name}' não existe."}
        mat_idx = max(1, excel_row - 1)
        page = ((mat_idx - 1) // max(50, page_size)) + 1
        res = self.get_sheet_page(sheet_name, page=page, page_size=page_size, search_query="")
        res["highlight_excel_row"] = excel_row
        return res

    def validate_data(self, allow_integral: bool = True) -> dict[str, Any]:
        """Executa pré-processamento/validação imediata dos dados em memória sem rodar o solver."""
        if "Alunos" not in self.sheets_data or "Turmas" not in self.sheets_data:
            return {"success": False, "error": "A planilha precisa conter as abas 'Alunos' e 'Turmas'."}

        try:
            raw = self._build_raw_from_memory()
            proc = pre_process(raw, allow_integral=allow_integral)
            self.processed_instance = proc

            stats_turnos: dict[str, Any] = {}
            for t_code in (TURNO_MANHA, TURNO_TARDE):
                t_list = proc.turmas_por_turno.get(t_code, [])
                n_salas = len(t_list)
                cap_unit = proc.capacidade_por_turno.get(t_code, 0)
                tot_cap = n_salas * cap_unit
                demand = sum(1 for st in proc.students if t_code in st.turnos_compativeis)
                m_t = sum(1 for st in proc.students if st.sexo == GENERO_M and t_code in st.turnos_compativeis)
                f_t = sum(1 for st in proc.students if st.sexo == GENERO_F and t_code in st.turnos_compativeis)

                # Se já temos um ensalamento gerado em memória, usa os alocados reais
                aloc_t = demand
                if self.solver_result and self.solver_result.feasible:
                    aloc_t = sum(
                        1
                        for st in proc.students
                        if self.solver_result.student_to_turma.get(st.id) in {t.id for t in t_list}
                    )

                stats_turnos[t_code] = {
                    "salas": n_salas,
                    "capacidade_unitaria": cap_unit,
                    "capacidade_total": tot_cap,
                    "demanda": demand,
                    "alocados": aloc_t,
                    "masculino": m_t,
                    "feminino": f_t,
                    "livres": max(0, tot_cap - aloc_t),
                    "ocupacao_pct": round(100.0 * aloc_t / tot_cap, 1) if tot_cap > 0 else 0.0,
                }

            turmas_summary = []
            if self.solver_result and self.solver_result.feasible:
                for t in proc.turmas:
                    tot_s = self.solver_result.y_turma.get(t.id, 0) if self.solver_result.y_turma else 0
                    m_s = self.solver_result.z_turma_gen.get((t.id, GENERO_M), 0) if self.solver_result.z_turma_gen else 0
                    f_s = self.solver_result.z_turma_gen.get((t.id, GENERO_F), 0) if self.solver_result.z_turma_gen else 0
                    turmas_summary.append(
                        {
                            "codigo": t.codigo,
                            "turno": t.turno,
                            "capacidade": t.capacidade,
                            "lotacao": tot_s,
                            "masculino": m_s,
                            "feminino": f_s,
                            "livres": max(0, t.capacidade - tot_s),
                            "ocupacao_pct": round(100.0 * tot_s / t.capacidade, 1) if t.capacidade > 0 else 0.0,
                        }
                    )
            elif "Ensalamento" in self.sheets_data and len(self.sheets_data["Ensalamento"]) > 1:
                ens_mat = self.sheets_data["Ensalamento"]
                counts_by_code: dict[str, dict[str, int]] = {}
                for r in ens_mat[1:]:
                    if len(r) < 4 or not r[3].strip():
                        continue
                    code = r[3].strip()
                    sex = normalize_token(r[1]).upper()
                    entry = counts_by_code.setdefault(code, {"tot": 0, "m": 0, "f": 0})
                    entry["tot"] += 1
                    if sex.startswith("M"):
                        entry["m"] += 1
                    elif sex.startswith("F"):
                        entry["f"] += 1
                for t in proc.turmas:
                    c_info = counts_by_code.get(t.codigo, {"tot": 0, "m": 0, "f": 0})
                    tot_s = c_info["tot"]
                    turmas_summary.append(
                        {
                            "codigo": t.codigo,
                            "turno": t.turno,
                            "capacidade": t.capacidade,
                            "lotacao": tot_s,
                            "masculino": c_info["m"],
                            "feminino": c_info["f"],
                            "livres": max(0, t.capacidade - tot_s),
                            "ocupacao_pct": round(100.0 * tot_s / t.capacidade, 1) if t.capacidade > 0 else 0.0,
                        }
                    )

            incons_list = []
            for inc in proc.inconsistencies:
                item: dict[str, Any] = {
                    "linha": inc.row_number,
                    "nome": inc.nome,
                    "severidade": inc.severidade,
                    "categoria": inc.categoria,
                    "mensagem": inc.mensagem,
                    "sexo_original": inc.sexo_original,
                    "disp_original": inc.disp_original,
                }
                # Se for duplicidade de nome, mapeia todas as linhas do grupo para permitir ciclo n-plicado
                if inc.categoria == "Duplicidade de Nome" and inc.nome in proc.duplicate_groups:
                    item["linhas"] = proc.duplicate_groups[inc.nome]
                elif inc.row_number:
                    item["linhas"] = [inc.row_number]
                else:
                    item["linhas"] = []

                # Se for erro de capacidade insuficiente, marca target_sheet='Turmas' para navegação direta
                if inc.categoria == "Capacidade Insuficiente":
                    item["target_sheet"] = "Turmas"
                    item["target_row"] = 2
                else:
                    item["target_sheet"] = "Alunos"
                    item["target_row"] = inc.row_number

                # Apenas erros com normalização automática aplicável (espaços, turno, sexo limpo)
                if inc.severidade == "TRATADA":
                    item["can_review"] = True
                    item["review_type"] = "sanitize"
                else:
                    item["can_review"] = False

                incons_list.append(item)

            # Ordena os erros pela ordem das linhas na planilha (menores linhas primeiro; erros globais no fim)
            incons_list.sort(
                key=lambda x: (
                    0 if (x.get("linhas") or [None])[0] is not None else 1,
                    (x.get("linhas") or [9999999])[0] if (x.get("linhas") or [None])[0] is not None else 9999999,
                    0 if x.get("severidade") == "IMPEDITIVA" else 1,
                )
            )

            n_imped = sum(1 for i in incons_list if i["severidade"] == "IMPEDITIVA")
            n_alert = sum(1 for i in incons_list if i["severidade"] == "ALERTA")
            n_trat = sum(1 for i in incons_list if i["severidade"] == "TRATADA")

            summary: dict[str, Any] = {
                "feasible": proc.is_fully_clean_or_treated if self.solver_result is None else self.solver_result.feasible,
                "optimal": False if self.solver_result is None else self.solver_result.optimal,
                "reason": ("Validação cadastral em tempo real" if self.solver_result is None else self.solver_result.reason),
                "total_lidos": len(raw.students),
                "total_validos": len(proc.students),
                "total_invalidos": len(proc.invalid_records),
                "total_alocados": (len(proc.students) if self.solver_result is None else len(self.solver_result.student_to_turma)),
                "total_espera": (0 if self.solver_result is None else len(self.solver_result.unallocated_students)),
                "total_salas": len(proc.turmas),
                "stats_turnos": stats_turnos,
                "turmas": turmas_summary,
                "turmas_truncated": 0,
                "inconsistencias": incons_list,  # Lista completa de erros/alertas
                "incons_counts": {
                    "total": len(incons_list),
                    "impeditivas": n_imped,
                    "alertas": n_alert,
                    "tratadas": n_trat,
                },
                "tempo_ms": 0.0 if self.solver_result is None else round(self.solver_result.metrics.total_time_s * 1000, 1),
            }

            self.last_summary = summary
            return {"success": True, "summary": summary}
        except Exception as exc:
            return {"success": False, "error": f"Erro ao validar dados: {exc}"}

    def update_cells(self, sheet_name: str, updates: list[dict[str, Any]]) -> dict[str, Any]:
        """Atualiza uma ou mais células na matriz em memória com suporte a undo em lote."""
        if sheet_name not in self.sheets_data:
            return {"success": False, "error": "Aba não encontrada."}

        matrix = self.sheets_data[sheet_name]
        changed = False
        snapshot_pushed = False

        for u in updates:
            mat_idx = int(u.get("mat_idx", 0))
            col = int(u.get("col", 0))
            val = "" if u.get("value") is None else str(u.get("value"))
            if mat_idx < 0 or col < 0:
                continue

            cur_val = (
                matrix[mat_idx][col]
                if mat_idx < len(matrix) and col < len(matrix[mat_idx])
                else ""
            )
            if cur_val != val:
                if not snapshot_pushed:
                    self._push_undo()
                    snapshot_pushed = True
                while len(matrix) <= mat_idx:
                    matrix.append([])
                while len(matrix[mat_idx]) <= col:
                    matrix[mat_idx].append("")
                matrix[mat_idx][col] = val
                changed = True

        if changed:
            self.dirty = True

        validation = self.validate_data()
        flagged = {str(k): v for k, v in self._compute_flagged_rows(sheet_name).items()}
        return {
            "success": True,
            "dirty": self.dirty,
            "flagged_rows": flagged,
            "summary": validation.get("summary") if validation.get("success") else None,
        }

    def update_cell(self, sheet_name: str, mat_idx: int, col: int, value: str) -> dict[str, Any]:
        """Atualiza uma célula específica na matriz em memória."""
        return self.update_cells(
            sheet_name, [{"mat_idx": mat_idx, "col": col, "value": value}]
        )

    def add_row(
        self,
        sheet_name: str,
        after_row: Optional[int] = None,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> dict[str, Any]:
        """Adiciona uma nova linha editável logo abaixo de after_row (ou ao final se None)."""
        if sheet_name not in self.sheets_data:
            return {"success": False, "error": "Aba não encontrada."}

        self._push_undo()
        matrix = self.sheets_data[sheet_name]
        num_cols = len(matrix[0]) if matrix else 3
        new_row = [""] * num_cols

        if after_row is not None and 1 <= after_row <= len(matrix):
            # after_row é 1-based (ex.: linha 3). Inserir logo abaixo significa índice after_row
            insert_idx = after_row
            matrix.insert(insert_idx, new_row)
            target_excel_row = insert_idx + 1
        else:
            matrix.append(new_row)
            target_excel_row = len(matrix)

        self.dirty = True
        validation = self.validate_data()
        res = self.jump_to_row(sheet_name, excel_row=target_excel_row, page_size=page_size)
        res["summary"] = validation.get("summary") if validation.get("success") else None
        return res

    def add_column(
        self,
        sheet_name: str,
        after_col: Optional[int] = None,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> dict[str, Any]:
        """Adiciona uma nova coluna vazia à direita de after_col (ou ao final se None)."""
        if sheet_name not in self.sheets_data:
            return {"success": False, "error": "Aba não encontrada."}

        self._push_undo()
        matrix = self.sheets_data[sheet_name]
        if not matrix:
            matrix.append([""])

        num_cols = len(matrix[0])
        col_idx = (after_col + 1) if (after_col is not None and 0 <= after_col < num_cols) else num_cols

        for r in matrix:
            while len(r) < num_cols:
                r.append("")
            r.insert(col_idx, "")

        self.dirty = True
        validation = self.validate_data()
        res = self.get_sheet_page(sheet_name, page=1, page_size=page_size)
        res["summary"] = validation.get("summary") if validation.get("success") else None
        return res

    def delete_row(
        self,
        sheet_name: str,
        mat_idx: int = -1,
        mat_indices: Optional[list[int]] = None,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        search_query: str = "",
    ) -> dict[str, Any]:
        """Exclui uma ou mais linhas de dados (preservando a linha 1 de cabeçalho)."""
        if sheet_name not in self.sheets_data:
            return {"success": False, "error": "Aba não encontrada."}

        matrix = self.sheets_data[sheet_name]
        indices_to_delete: list[int] = []
        if mat_indices:
            indices_to_delete = sorted([i for i in mat_indices if 0 < i < len(matrix)], reverse=True)
        elif 0 < mat_idx < len(matrix):
            indices_to_delete = [mat_idx]

        if not indices_to_delete:
            return {"success": False, "error": "Selecione uma linha de dados válida para excluir."}

        self._push_undo()
        for idx in indices_to_delete:
            matrix.pop(idx)
        self.dirty = True
        validation = self.validate_data()
        res = self.get_sheet_page(
            sheet_name, page=page, page_size=page_size, search_query=search_query
        )
        res["summary"] = validation.get("summary") if validation.get("success") else None
        return res

    def resolve_issue(
        self,
        action: str,
        issue_type: str,
        target_rows: list[int],
        extra: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Aplica ou rejeita resolução estilo VS Code (Accept / Reject / Quick Fix) diretamente na planilha."""
        if "Alunos" not in self.sheets_data:
            return {"success": False, "error": "Aba 'Alunos' não encontrada."}

        self._push_undo()
        extra = extra or {}
        matrix = self.sheets_data["Alunos"]
        headers = [normalize_token(c) for c in matrix[0]] if matrix else []
        col_nome = headers.index("nome") if "nome" in headers else 0
        col_sexo = headers.index("sexo") if "sexo" in headers else 1
        col_disp = (
            headers.index("disponibilidade")
            if "disponibilidade" in headers
            else (2 if len(headers) > 2 else 2)
        )

        modified = False

        if action == "accept_sanitize":
            # Aceita a higienização proposta (remover espaços, normalizar Sexo p/ M/F, turno)
            for r_num in target_rows:
                mat_idx = r_num - 1
                if 1 <= mat_idx < len(matrix):
                    r = matrix[mat_idx]
                    nome_val = r[col_nome].strip() if col_nome < len(r) else ""
                    sexo_val = r[col_sexo].strip() if col_sexo < len(r) else ""
                    disp_val = r[col_disp].strip() if col_disp < len(r) else ""

                    # Normaliza Sexo
                    sexo_tok = normalize_token(sexo_val)
                    if sexo_tok in {"m", "masculino", "masc", "homem", "menino"}:
                        r[col_sexo] = "M"
                    elif sexo_tok in {"f", "feminino", "fem", "mulher", "menina"}:
                        r[col_sexo] = "F"

                    # Normaliza Disponibilidade
                    disp_tok = normalize_token(disp_val)
                    if "manha" in disp_tok:
                        r[col_disp] = "Manhã"
                    elif "tarde" in disp_tok:
                        r[col_disp] = "Tarde"
                    elif "integral" in disp_tok:
                        r[col_disp] = "Integral"

                    # Remove espaços do nome
                    import re

                    r[col_nome] = re.sub(r"\s+", " ", nome_val)
                    modified = True

        elif action == "remove_duplicates":
            # Remove as linhas excedentes do aluno n-plicado, mantendo apenas a primeira
            if len(target_rows) > 1:
                # Ordena decrescente para não deslocar índices durante o pop
                rows_to_remove = sorted(target_rows[1:], reverse=True)
                for r_num in rows_to_remove:
                    mat_idx = r_num - 1
                    if 1 <= mat_idx < len(matrix):
                        matrix.pop(mat_idx)
                        modified = True

        elif action == "quick_fix_field":
            # Aplica valor sugerido em campo específico
            field_name = extra.get("field", "")
            new_val = extra.get("value", "")
            for r_num in target_rows:
                mat_idx = r_num - 1
                if 1 <= mat_idx < len(matrix):
                    r = matrix[mat_idx]
                    if field_name == "sexo" and col_sexo < len(r):
                        r[col_sexo] = new_val
                        modified = True
                    elif field_name == "disponibilidade" and col_disp < len(r):
                        r[col_disp] = new_val
                        modified = True

        if modified:
            self.dirty = True

        validation = self.validate_data()
        page_payload = self.get_sheet_page(self.active_sheet, page=1, search_query="")
        return {
            **page_payload,
            "dirty": self.dirty,
            "summary": validation.get("summary") if validation.get("success") else None,
            "modified": modified,
        }

    def save_excel(self, save_as_path: Optional[str] = None) -> dict[str, Any]:
        """Salva todas as abas no arquivo Excel preservando formatação limpa e tipos numéricos."""
        target_path = Path(save_as_path).resolve() if save_as_path else self.current_filepath
        if not target_path:
            return {"success": False, "error": "Nenhum arquivo selecionado para salvar."}

        try:
            wb = openpyxl.Workbook()
            wb.remove(wb.active)

            header_font = Font(bold=True, color="FFFFFF")
            header_fill = PatternFill(
                start_color="107C41", end_color="107C41", fill_type="solid"
            )
            center_align = Alignment(horizontal="center", vertical="center")
            left_align = Alignment(horizontal="left", vertical="center")

            for sname, matrix in self.sheets_data.items():
                ws = wb.create_sheet(title=sname)
                is_turmas = normalize_token(sname) == "turmas"
                is_inc = "inconsist" in normalize_token(sname)

                for r_idx, r_vals in enumerate(matrix):
                    if r_idx > 0 and is_turmas and len(r_vals) >= 2:
                        val_b: Any = r_vals[1]
                        try:
                            val_b = int(float(str(r_vals[1]).strip().replace(",", ".")))
                        except Exception:
                            pass
                        ws.append([r_vals[0], val_b] + r_vals[2:])
                    elif r_idx > 0 and is_inc and len(r_vals) >= 1:
                        val_a: Any = r_vals[0]
                        if str(val_a).strip().isdigit():
                            val_a = int(str(val_a).strip())
                        ws.append([val_a] + r_vals[1:])
                    else:
                        ws.append(r_vals)

                if ws.max_row >= 1:
                    for c_idx in range(1, ws.max_column + 1):
                        c = ws.cell(row=1, column=c_idx)
                        c.font = header_font
                        c.fill = header_fill
                        c.alignment = left_align if c_idx == 1 else center_align

                max_scan = min(ws.max_row, 800)
                max_lens = [0] * ws.max_column
                for row_v in ws.iter_rows(
                    min_row=1, max_row=max_scan, max_col=ws.max_column, values_only=True
                ):
                    for idx_c, v in enumerate(row_v):
                        if v is not None:
                            max_lens[idx_c] = max(max_lens[idx_c], len(str(v)))
                for idx_c, m_len in enumerate(max_lens, start=1):
                    ws.column_dimensions[get_column_letter(idx_c)].width = min(
                        max(m_len + 4, 13), 70
                    )

            target_path.parent.mkdir(parents=True, exist_ok=True)
            wb.save(target_path)
            wb.close()

            self.current_filepath = target_path
            self.dirty = False
            validation = self.validate_data()
            return {
                "success": True,
                "filename": target_path.name,
                "filepath": str(target_path),
                "dirty": False,
                "summary": validation.get("summary") if validation.get("success") else None,
            }
        except PermissionError:
            return {
                "success": False,
                "error": (
                    f"O arquivo '{target_path.name}' está aberto em outro programa (ex.: Excel). "
                    "Feche-o lá antes de salvar aqui."
                ),
            }
        except Exception as exc:
            return {"success": False, "error": f"Falha ao salvar planilha: {exc}"}

    def _build_raw_from_memory(self) -> RawInstance:
        """Constrói RawInstance a partir das matrizes editáveis em memória."""
        alunos_matrix = self.sheets_data.get("Alunos", [])
        raw_students: list[RawStudentRow] = []

        if len(alunos_matrix) >= 1:
            headers = [normalize_token(c) for c in alunos_matrix[0]]
            col_nome = headers.index("nome") if "nome" in headers else 0
            col_sexo = headers.index("sexo") if "sexo" in headers else 1
            col_disp = (
                headers.index("disponibilidade")
                if "disponibilidade" in headers
                else (2 if len(headers) > 2 else 2)
            )

            for r_idx, r in enumerate(alunos_matrix[1:], start=2):
                nome = r[col_nome].strip() if col_nome < len(r) else ""
                sexo = r[col_sexo].strip() if col_sexo < len(r) else ""
                disp = r[col_disp].strip() if col_disp < len(r) else ""
                if not nome and not sexo and not disp:
                    continue
                raw_students.append(
                    RawStudentRow(
                        row_number=r_idx,
                        nome=nome or None,
                        sexo=sexo or None,
                        disponibilidade=disp or None,
                    )
                )

        turmas_matrix = self.sheets_data.get("Turmas", [])
        raw_entries: dict[str, Any] = {}
        parse_errors: list[str] = []
        t_manha: Optional[int] = None
        t_tarde: Optional[int] = None
        v_manha: Optional[int] = None
        v_tarde: Optional[int] = None

        for r_idx, r in enumerate(turmas_matrix[1:], start=2):
            key_raw = r[0].strip() if len(r) > 0 else ""
            val_raw = r[1].strip() if len(r) > 1 else ""
            if not key_raw and not val_raw:
                continue
            raw_entries[key_raw] = val_raw
            norm_k = normalize_token(key_raw).replace(" ", "_")
            try:
                parsed_int = int(float(val_raw.replace(",", ".")))
            except Exception:
                parse_errors.append(
                    f"Linha {r_idx} da aba Turmas ('{key_raw}'): valor '{val_raw}' não é inteiro."
                )
                continue

            if "turmas_manha" in norm_k or norm_k == "manha":
                t_manha = parsed_int
            elif "turmas_tarde" in norm_k or norm_k == "tarde":
                t_tarde = parsed_int
            elif "vagas_manha" in norm_k:
                v_manha = parsed_int
            elif "vagas_tarde" in norm_k:
                v_tarde = parsed_int

        turmas_cfg = RawTurmasConfig(
            turmas_manha=t_manha,
            turmas_tarde=t_tarde,
            vagas_manha=v_manha,
            vagas_tarde=v_tarde,
            raw_entries=raw_entries,
            parse_errors=parse_errors,
        )

        return RawInstance(
            filepath=self.current_filepath or Path("planilha.xlsx"),
            sheet_names=list(self.sheets_data.keys()),
            alunos_sheet_name="Alunos",
            turmas_sheet_name="Turmas",
            header_mapping={
                "nome": "Nome",
                "sexo": "Sexo",
                "disponibilidade": "Disponibilidade",
            },
            header_warnings=[],
            students=raw_students,
            turmas=turmas_cfg,
        )

    def run_ensalamento(
        self,
        allow_integral: bool = True,
        allow_unallocated: bool = False,
    ) -> dict[str, Any]:
        """Executa higienização + solver MILP sobre os dados atuais da planilha."""
        if "Alunos" not in self.sheets_data or "Turmas" not in self.sheets_data:
            return {
                "success": False,
                "error": "A planilha precisa conter as abas 'Alunos' e 'Turmas'.",
            }

        try:
            raw = self._build_raw_from_memory()
            proc = pre_process(raw, allow_integral=allow_integral)
            self.processed_instance = proc

            params = SolverParameters(
                w_qtd=1.0,
                w_gen=1.0,
                epsilon=1e-4,
                enable_phase2=True,
                auto_skip_phase2=True,
                allow_unallocated=allow_unallocated,
                use_decomposition=True,
            )
            res = solve_ensalamento(proc, params=params)
            self.solver_result = res

            # Gera as abas 'Ensalamento' e 'Inconsistências' exatamente no padrão oficial
            turma_by_id = {t.id: t for t in proc.turmas}
            ens_rows: list[list[str]] = [["Nome", "Sexo", "Disponibilidade", "Turma"]]
            if res.feasible and res.student_to_turma:
                for st in proc.students:
                    t_id = res.student_to_turma.get(st.id)
                    if t_id is None:
                        continue
                    turma = turma_by_id[t_id]
                    disp_out = (
                        turma.turno if st.disponibilidade == "INTEGRAL" else st.disponibilidade
                    )
                    ens_rows.append([st.nome, st.sexo, disp_out, turma.codigo])

            inc_rows: list[list[str]] = [
                [
                    "Linha",
                    "Nome",
                    "Sexo Informado",
                    "Disponibilidade Informada",
                    "Categoria",
                    "Severidade",
                    "Status",
                    "Motivo / Ação",
                ]
            ]
            if not res.feasible and proc.capacity_feasible:
                inc_rows.append(
                    ["-", "-", "-", "-", "Execução do Solver", "IMPEDITIVA", "Requer Ação", res.reason]
                )

            for inc in proc.inconsistencies:
                if inc.categoria == "Capacidade Insuficiente" and res.feasible:
                    status_lbl = "Tratada via Lista de Espera"
                elif inc.severidade == "TRATADA":
                    status_lbl = "Tratada Automaticamente"
                elif inc.severidade == "ALERTA":
                    status_lbl = "Alerta (Alocado em Duplicidade)"
                else:
                    status_lbl = "Pendente de Correção"
                inc_rows.append(
                    [
                        str(inc.row_number) if inc.row_number is not None else "-",
                        inc.nome,
                        inc.sexo_original,
                        inc.disp_original,
                        inc.categoria,
                        inc.severidade,
                        status_lbl,
                        inc.mensagem,
                    ]
                )

            if res.feasible and res.unallocated_students:
                unalloc_set = set(res.unallocated_students)
                for st in proc.students:
                    if st.id in unalloc_set:
                        inc_rows.append(
                            [
                                str(st.row_number),
                                st.nome,
                                st.sexo,
                                st.disponibilidade,
                                "Sem Turma (Lista de Espera)",
                                "ALERTA",
                                "Não Alocado (Excedente de Vagas)",
                                f"Excedente de vagas em '{st.disponibilidade}'; incluído na lista de espera.",
                            ]
                        )

            if len(inc_rows) == 1:
                inc_rows.append(
                    [
                        "-",
                        "-",
                        "-",
                        "-",
                        "Validação Geral",
                        "OK",
                        "Sem Inconsistências",
                        "Nenhuma inconsistência encontrada na planilha.",
                    ]
                )

            self.sheets_data["Ensalamento"] = ens_rows
            self.sheets_data["Inconsistências"] = inc_rows
            self.dirty = True

            # Constrói resumo enxuto e amigável para o painel direito
            stats_turnos: dict[str, Any] = {}
            for t_code in (TURNO_MANHA, TURNO_TARDE):
                t_list = proc.turmas_por_turno.get(t_code, [])
                n_salas = len(t_list)
                cap_unit = proc.capacidade_por_turno.get(t_code, 0)
                tot_cap = n_salas * cap_unit
                aloc_t = sum(res.y_turma.get(t.id, 0) for t in t_list) if res.y_turma else 0
                m_t = (
                    sum(res.z_turma_gen.get((t.id, GENERO_M), 0) for t in t_list)
                    if res.z_turma_gen
                    else 0
                )
                f_t = (
                    sum(res.z_turma_gen.get((t.id, GENERO_F), 0) for t in t_list)
                    if res.z_turma_gen
                    else 0
                )
                stats_turnos[t_code] = {
                    "salas": n_salas,
                    "vagas_sala": cap_unit,
                    "capacidade_total": tot_cap,
                    "alocados": aloc_t,
                    "masculino": m_t,
                    "feminino": f_t,
                    "livres": tot_cap - aloc_t,
                    "ocupacao_pct": round(100.0 * aloc_t / tot_cap, 1) if tot_cap > 0 else 0.0,
                }

            turmas_summary = []
            for t in proc.turmas:
                tot_s = res.y_turma.get(t.id, 0) if res.y_turma else 0
                m_s = res.z_turma_gen.get((t.id, GENERO_M), 0) if res.z_turma_gen else 0
                f_s = res.z_turma_gen.get((t.id, GENERO_F), 0) if res.z_turma_gen else 0
                turmas_summary.append(
                    {
                        "codigo": t.codigo,
                        "turno": t.turno,
                        "capacidade": t.capacidade,
                        "lotacao": tot_s,
                        "masculino": m_s,
                        "feminino": f_s,
                        "livres": max(0, t.capacidade - tot_s),
                        "ocupacao_pct": round(100.0 * tot_s / t.capacidade, 1) if t.capacidade > 0 else 0.0,
                    }
                )

            incons_list = []
            for inc in proc.inconsistencies:
                item: dict[str, Any] = {
                    "linha": inc.row_number,
                    "nome": inc.nome,
                    "severidade": inc.severidade,
                    "categoria": inc.categoria,
                    "mensagem": inc.mensagem,
                    "sexo_original": inc.sexo_original,
                    "disp_original": inc.disp_original,
                }
                # Se for duplicidade de nome, mapeia todas as linhas do grupo para permitir ciclo n-plicado
                if inc.categoria == "Duplicidade de Nome" and inc.nome in proc.duplicate_groups:
                    item["linhas"] = proc.duplicate_groups[inc.nome]
                elif inc.row_number:
                    item["linhas"] = [inc.row_number]
                else:
                    item["linhas"] = []

                # Se for erro de capacidade insuficiente, marca target_sheet='Turmas' para navegação direta
                if inc.categoria == "Capacidade Insuficiente":
                    item["target_sheet"] = "Turmas"
                    item["target_row"] = 2
                else:
                    item["target_sheet"] = "Alunos"
                    item["target_row"] = inc.row_number

                # Apenas erros com normalização automática aplicável (espaços, turno, sexo limpo)
                if inc.severidade == "TRATADA":
                    item["can_review"] = True
                    item["review_type"] = "sanitize"
                else:
                    item["can_review"] = False

                incons_list.append(item)

            # Ordena os erros pela ordem das linhas na planilha (menores linhas primeiro; erros globais no fim)
            incons_list.sort(
                key=lambda x: (
                    0 if (x.get("linhas") or [None])[0] is not None else 1,
                    (x.get("linhas") or [9999999])[0] if (x.get("linhas") or [None])[0] is not None else 9999999,
                    0 if x.get("severidade") == "IMPEDITIVA" else 1,
                )
            )

            n_imped = sum(1 for i in incons_list if i["severidade"] == "IMPEDITIVA")
            n_alert = sum(1 for i in incons_list if i["severidade"] == "ALERTA")
            n_trat = sum(1 for i in incons_list if i["severidade"] == "TRATADA")

            self.last_summary = {
                "feasible": res.feasible,
                "optimal": res.optimal,
                "reason": res.reason,
                "total_lidos": len(raw.students),
                "total_validos": len(proc.students),
                "total_invalidos": len(proc.invalid_records),
                "total_alocados": len(res.student_to_turma),
                "total_espera": len(res.unallocated_students),
                "total_salas": len(proc.turmas),
                "stats_turnos": stats_turnos,
                "turmas": turmas_summary,
                "turmas_truncated": max(0, len(proc.turmas) - len(turmas_summary)),
                "inconsistencias": incons_list[:80],
                "incons_counts": {
                    "total": len(incons_list),
                    "impeditivas": n_imped,
                    "alertas": n_alert,
                    "tratadas": n_trat,
                },
                "tempo_ms": round(res.metrics.total_time_s * 1000, 1),
            }

            target_tab = "Ensalamento" if res.feasible else "Inconsistências"
            page_payload = self.get_sheet_page(target_tab, page=1, search_query="")
            return {
                **page_payload,
                "summary": self.last_summary,
            }
        except Exception as exc:
            traceback.print_exc()
            return {"success": False, "error": f"Erro ao processar ensalamento: {exc}"}

    def export_pdf(self, output_path: str) -> dict[str, Any]:
        """Gera o PDF limpo apenas com os alunos de cada turma (para envio aos alunos)."""
        if not self.solver_result or not self.solver_result.feasible or not self.processed_instance:
            # Caso a planilha aberta já possua aba 'Ensalamento' pronta, também permite gerar!
            ens_mat = self.sheets_data.get("Ensalamento", [])
            if len(ens_mat) > 1:
                return self._export_pdf_from_ensalamento_sheet(output_path, ens_mat)
            return {
                "success": False,
                "error": "Execute o ensalamento primeiro para gerar a lista de turmas em PDF.",
            }

        try:
            t_map: dict[int, list[dict[str, str]]] = {
                t.id: [] for t in self.processed_instance.turmas
            }
            for st in self.processed_instance.students:
                t_id = self.solver_result.student_to_turma.get(st.id)
                if t_id is not None and t_id in t_map:
                    t_map[t_id].append({"nome": st.nome})

            turmas_data = []
            for t in self.processed_instance.turmas:
                alunos_ord = sorted(t_map[t.id], key=lambda a: normalize_token(a["nome"]))
                turmas_data.append(
                    {
                        "codigo": t.codigo,
                        "turno": t.turno,
                        "alunos": alunos_ord,
                    }
                )

            title = self.current_filepath.stem if self.current_filepath else "Ensalamento"
            pdf_path = generate_class_lists_pdf(output_path, title, turmas_data)
            return {"success": True, "pdf_path": str(pdf_path)}
        except Exception as exc:
            traceback.print_exc()
            return {"success": False, "error": f"Falha ao gerar PDF: {exc}"}

    def _export_pdf_from_ensalamento_sheet(
        self, output_path: str, ens_mat: list[list[str]]
    ) -> dict[str, Any]:
        """Permite gerar o PDF diretamente de uma aba 'Ensalamento' já existente."""
        try:
            grouped: dict[str, list[dict[str, str]]] = {}
            turno_of: dict[str, str] = {}
            for r in ens_mat[1:]:
                if len(r) < 4 or not r[0].strip() or not r[3].strip():
                    continue
                nome, _, disp, turma = r[0].strip(), r[1].strip(), r[2].strip(), r[3].strip()
                grouped.setdefault(turma, []).append({"nome": nome})
                turno_of[turma] = disp or ("MANHÃ" if "MANH" in turma.upper() else "TARDE")

            turmas_data = [
                {
                    "codigo": codigo,
                    "turno": turno_of.get(codigo, ""),
                    "alunos": sorted(lst, key=lambda a: normalize_token(a["nome"])),
                }
                for codigo, lst in grouped.items()
            ]
            title = self.current_filepath.stem if self.current_filepath else "Ensalamento"
            pdf_path = generate_class_lists_pdf(output_path, title, turmas_data)
            return {"success": True, "pdf_path": str(pdf_path)}
        except Exception as exc:
            return {"success": False, "error": f"Falha ao gerar PDF: {exc}"}

    def ask_assistant(self, user_prompt: str) -> str:
        """Assistente local determinístico (100% offline, 0% erro/alucinação)."""
        raw_q = user_prompt.strip()
        q = normalize_token(raw_q)

        if not self.sheets_data:
            return (
                "Nenhuma planilha está aberta no momento. Clique em **Abrir Excel** na barra "
                "superior para carregar os alunos e turmas."
            )

        # 1. Busca específica por código de turma (ex.: "manhã - a", "turma b", "tarde - c")
        if self.processed_instance and self.solver_result and self.solver_result.feasible:
            for t in self.processed_instance.turmas:
                code_norm = normalize_token(t.codigo)
                letter_norm = code_norm.split("-")[-1].strip()
                if code_norm in q or f"turma {letter_norm}" in q or f"sala {letter_norm}" in q:
                    alunos_t = sorted(
                        [
                            st.nome
                            for st in self.processed_instance.students
                            if self.solver_result.student_to_turma.get(st.id) == t.id
                        ]
                    )
                    m_c = self.solver_result.z_turma_gen.get((t.id, GENERO_M), 0)
                    f_c = self.solver_result.z_turma_gen.get((t.id, GENERO_F), 0)
                    sample = ", ".join(alunos_t[:8])
                    more = f" *(+{len(alunos_t) - 8} alunos)*" if len(alunos_t) > 8 else ""
                    return (
                        f"**{t.codigo}** ({t.turno}):\n"
                        f"• Lotação: **{len(alunos_t)} / {t.capacidade}** vagas\n"
                        f"• Equilíbrio: **{m_c} M** e **{f_c} F**\n"
                        f"• Alunos: {sample}{more}"
                    )

        # 2. Perguntas sobre erros / inconsistências / cadastros inválidos
        if any(w in q for w in ("erro", "inconsist", "problema", "duplicad", "homonim", "invalid", "alerta", "corrig")):
            if not self.last_summary:
                return "Clique em **Otimizar Turmas** para verificar todos os erros e alertas da planilha."
            counts = self.last_summary["incons_counts"]
            if counts["total"] == 0:
                return "Nenhum erro ou inconsistência foi encontrado na planilha."
            lines = [
                f"Encontrei **{counts['total']} ocorrência(s)** na revisão cadastral:",
                f"• **{counts['impeditivas']}** erro(s) impeditivo(s) (alunos sem sexo/turno válido que precisam de correção)",
                f"• **{counts['alertas']}** alerta(s) de homônimos/nomes repetidos",
                f"• **{counts['tratadas']}** ajuste(s) automático(s) de grafia/acentos",
            ]
            impeds = [
                i for i in self.last_summary["inconsistencias"] if i["severidade"] == "IMPEDITIVA"
            ]
            if impeds:
                ex = "; ".join(f"Linha {i['linha']} ({i['nome']})" for i in impeds[:4])
                lines.append(f"\nCorrija na aba **Alunos**: {ex}.")
            return "\n".join(lines)

        # 3. Perguntas sobre vagas, capacidade, salas ou resumo
        if any(w in q for w in ("resumo", "quantas turma", "quantas sala", "vaga", "capacidade", "ocupacao", "turno")):
            if not self.last_summary:
                n_al = max(0, len(self.sheets_data.get("Alunos", [])) - 1)
                return (
                    f"A aba **Alunos** possui **{n_al} linhas**. Clique em **Otimizar Turmas** "
                    "para calcular a ocupação das salas."
                )
            s = self.last_summary
            sm = s["stats_turnos"][TURNO_MANHA]
            st = s["stats_turnos"][TURNO_TARDE]
            return (
                f"**Resumo exato do ensalamento:**\n"
                f"• Alocados: **{s['total_alocados']}** de **{s['total_validos']}** alunos válidos\n"
                f"• **Manhã**: {sm['alocados']}/{sm['capacidade_total']} vagas em {sm['salas']} sala(s) ({sm['ocupacao_pct']}%)\n"
                f"• **Tarde**: {st['alocados']}/{st['capacidade_total']} vagas em {st['salas']} sala(s) ({st['ocupacao_pct']}%)\n"
                f"• Lista de espera: **{s['total_espera']}** aluno(s)"
            )

        # 4. Perguntas sobre gênero (meninos / meninas)
        if any(w in q for w in ("genero", "menino", "menina", "masculin", "feminin", "sexo", "equilibrio", "proporcao")):
            if not self.last_summary:
                return "Execute **Otimizar Turmas** primeiro para ver o equilíbrio exato entre meninos e meninas."
            sm = self.last_summary["stats_turnos"][TURNO_MANHA]
            st = self.last_summary["stats_turnos"][TURNO_TARDE]
            return (
                f"**Equilíbrio de gênero por turno:**\n"
                f"• **Manhã**: {sm['masculino']} Masculino / {sm['feminino']} Feminino\n"
                f"• **Tarde**: {st['masculino']} Masculino / {st['feminino']} Feminino\n"
                "Dentro de cada turno, a diferença entre quaisquer duas salas foi minimizada matematicamente."
            )

        # 5. Perguntas sobre lista de espera / sem turma
        if any(w in q for w in ("espera", "sem turma", "ficou de fora", "nao alocado", "excedente")):
            if not self.last_summary:
                return "Clique em **Otimizar Turmas** para verificar se há alunos excedentes."
            esp = self.last_summary["total_espera"]
            if esp == 0:
                return "Nenhum aluno válido ficou sem turma — **100% foram alocados**."
            return (
                f"Há **{esp} aluno(s)** na lista de espera por falta de vagas compatíveis. "
                "Eles estão detalhados na aba **Inconsistências**."
            )

        # 6. Perguntas sobre PDF / impressão
        if any(w in q for w in ("pdf", "imprimir", "mandar", "enviar", "lista")):
            return (
                "Clique em **PDF p/ Alunos** no topo da janela para salvar um PDF limpo contendo "
                "apenas os nomes dos estudantes separados por turma, pronto para enviar aos alunos."
            )

        # 7. Busca nominal por aluno (ex.: "Qual a turma da Maria?" ou apenas digitar parte do nome!)
        clean_search = q
        for prefix in (
            "qual a turma de ",
            "qual a turma do ",
            "qual a turma da ",
            "onde ficou ",
            "onde esta ",
            "procurar ",
            "buscar ",
            "aluno ",
            "aluna ",
        ):
            if clean_search.startswith(prefix):
                clean_search = clean_search[len(prefix) :].strip(" ?.!\"'")
                break

        if len(clean_search) >= 3:
            ens_mat = self.sheets_data.get("Ensalamento", [])
            if len(ens_mat) > 1:
                matches = [
                    r for r in ens_mat[1:] if len(r) >= 4 and clean_search in normalize_token(r[0])
                ]
                if matches:
                    top = matches[:6]
                    bullets = "\n".join(f"• **{r[0]}** ({r[1]}) → **{r[3]}**" for r in top)
                    extra = f"\n*(+{len(matches) - 6} outros resultados)*" if len(matches) > 6 else ""
                    return f"Encontrei **{len(matches)}** estudante(s) no ensalamento:\n{bullets}{extra}"

            al_mat = self.sheets_data.get("Alunos", [])
            if len(al_mat) > 1:
                matches_al = [
                    (idx, r)
                    for idx, r in enumerate(al_mat[1:], start=2)
                    if len(r) >= 1 and clean_search in normalize_token(r[0])
                ]
                if matches_al:
                    top = matches_al[:6]
                    bullets = "\n".join(
                        f"• Linha {idx}: **{r[0]}** ({r[1] if len(r) > 1 else '-'} / {r[2] if len(r) > 2 else '-'})"
                        for idx, r in top
                    )
                    return (
                        f"Encontrei na aba **Alunos** (rode **Otimizar Turmas** para ver a sala):\n{bullets}"
                    )

        return (
            "Você pode consultar dados exatos perguntando, por exemplo:\n"
            "• **Resumo das vagas** ou **proporção de gênero**\n"
            "• **Quais erros tem na planilha?**\n"
            "• **Quem ficou na Manhã - A?**\n"
            "• Ou digite o **nome de qualquer aluno** para descobrir a turma dele!"
        )

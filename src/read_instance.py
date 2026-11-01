"""Módulo de leitura agnóstica das planilhas de entrada (.xlsx).

Responsável exclusivamente por extrair os dados brutos das abas 'Alunos' e 'Turmas'
de forma tolerante a diferenças de capitalização, acentuação e pequenas variações
de cabeçalho, sem qualquer dependência do solver matemático.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import unicodedata
from typing import Any, Optional

import openpyxl


def normalize_token(value: Any) -> str:
    """Remove acentos, espaços extras e converte para minúsculas."""
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text)


@dataclass
class RawStudentRow:
    """Representa uma linha bruta lida da aba Alunos."""

    row_number: int
    nome: Optional[str]
    sexo: Optional[str]
    disponibilidade: Optional[str]


EXPECTED_ALUNOS_COLUMNS: tuple[str, ...] = ("Nome", "Sexo", "Disponibilidade")
EXPECTED_TURMAS_COLUMNS: tuple[str, ...] = ("Recursos", "Quantidade")


@dataclass
class HeaderValidationError:
    """Representa um erro de validação de cabeçalho (coluna esperada ausente)."""

    sheet_name: str
    expected_columns: tuple[str, ...]
    found_columns: list[str]
    missing_columns: list[str]
    message: str


def validate_sheet_headers(
    sheet_name: str,
    header_cells: list[Any],
    expected_columns: tuple[str, ...] = EXPECTED_ALUNOS_COLUMNS,
) -> Optional[HeaderValidationError]:
    """Valida se o cabeçalho de uma aba/DataFrame possui todas as colunas esperadas.

    O nome das colunas deve corresponder exatamente ao padrão oficial de `instancia_2.xlsx`:
    - Aba 'Alunos': ('Nome', 'Sexo', 'Disponibilidade')
    - Aba 'Turmas': ('Recursos', 'Quantidade')
    """
    found_columns = [
        str(c).strip() for c in (header_cells or []) if c is not None and str(c).strip() != ""
    ]
    missing_columns = [col for col in expected_columns if col not in found_columns]
    if not missing_columns:
        return None

    esperadas_str = ", ".join(expected_columns)
    faltantes_str = ", ".join(f"'{c}'" for c in missing_columns)
    if not found_columns:
        msg = (
            f"Aba '{sheet_name}' (Linha 1): Cabeçalho vazio ou ausente. "
            f"Falta(m) a(s) coluna(s) esperada(s): {faltantes_str}. "
            f"As colunas obrigatórias são: {esperadas_str}."
        )
    else:
        encontradas_str = ", ".join(f"'{c}'" for c in found_columns)
        msg = (
            f"Aba '{sheet_name}' (Linha 1): Falta(m) a(s) coluna(s) esperada(s): {faltantes_str} "
            f"(cabeçalho encontrado: [{encontradas_str}]). "
            f"O nome das colunas deve ser igual ao padrão oficial: {esperadas_str}."
        )

    return HeaderValidationError(
        sheet_name=sheet_name,
        expected_columns=expected_columns,
        found_columns=found_columns,
        missing_columns=missing_columns,
        message=msg,
    )


def validate_instance_columns(
    alunos_header: list[Any],
    turmas_header: Optional[list[Any]] = None,
    alunos_sheet_name: str = "Alunos",
    turmas_sheet_name: str = "Turmas",
) -> list[HeaderValidationError]:
    """Executa a checagem prévia dos cabeçalhos das abas 'Alunos' e 'Turmas'."""
    errors: list[HeaderValidationError] = []
    err_alunos = validate_sheet_headers(
        alunos_sheet_name, alunos_header, EXPECTED_ALUNOS_COLUMNS
    )
    if err_alunos is not None:
        errors.append(err_alunos)

    if turmas_header is not None:
        err_turmas = validate_sheet_headers(
            turmas_sheet_name, turmas_header, EXPECTED_TURMAS_COLUMNS
        )
        if err_turmas is not None:
            errors.append(err_turmas)

    return errors


@dataclass
class RawTurmasConfig:
    """Representa os parâmetros brutos lidos da aba Turmas."""

    turmas_manha: Optional[int] = None
    turmas_tarde: Optional[int] = None
    vagas_manha: Optional[int] = None
    vagas_tarde: Optional[int] = None
    raw_entries: dict[str, Any] = field(default_factory=dict)
    parse_errors: list[str] = field(default_factory=list)


@dataclass
class RawInstance:
    """Estrutura de dados bruta extraída do arquivo Excel."""

    filepath: Path
    sheet_names: list[str]
    alunos_sheet_name: str
    turmas_sheet_name: str
    header_mapping: dict[str, str]
    header_warnings: list[str]
    students: list[RawStudentRow]
    turmas: RawTurmasConfig
    header_errors: list[HeaderValidationError] = field(default_factory=list)


def _find_sheet_name(sheet_names: list[str], candidates: tuple[str, ...]) -> Optional[str]:
    """Busca o nome real de uma aba de forma case-insensitive e sem acentos."""
    normalized_map = {normalize_token(name): name for name in sheet_names}
    for cand in candidates:
        if cand in normalized_map:
            return normalized_map[cand]
    for norm_name, real_name in normalized_map.items():
        if any(cand in norm_name for cand in candidates):
            return real_name
    return None


def _looks_like_data_row(cells: list[Any]) -> bool:
    """Verifica se a primeira linha já parece conter dados de aluno em vez de cabeçalho."""
    if len(cells) < 3:
        return False
    sexo_tok = normalize_token(cells[1])
    disp_tok = normalize_token(cells[2])
    return sexo_tok in {"m", "f", "masculino", "feminino"} and disp_tok in {
        "manha",
        "tarde",
        "integral",
    }


def _detect_student_columns(
    header_cells: list[Any],
) -> tuple[dict[str, int], dict[str, str], list[str], bool]:
    """Identifica os índices das colunas Nome, Sexo e Disponibilidade.

    Retorna: (col_indices, header_mapping_original, warnings, first_row_is_data)
    """
    warnings: list[str] = []
    if _looks_like_data_row(header_cells):
        warnings.append(
            "Linha 1 parece conter dados de aluno (sem cabeçalho explícito); "
            "assumindo colunas padrão A=Nome, B=Sexo, C=Disponibilidade."
        )
        return (
            {"nome": 0, "sexo": 1, "disponibilidade": 2},
            {"nome": "<sem_cabecalho>", "sexo": "<sem_cabecalho>", "disponibilidade": "<sem_cabecalho>"},
            warnings,
            True,
        )

    col_indices: dict[str, int] = {}
    for idx, raw_val in enumerate(header_cells[:6]):
        tok = normalize_token(raw_val)
        if not tok:
            continue
        if "nome" not in col_indices and any(k in tok for k in ("nome", "aluno", "matriculad", "estudante")):
            col_indices["nome"] = idx
        elif "sexo" not in col_indices and any(k in tok for k in ("sexo", "genero")):
            col_indices["sexo"] = idx
        elif "disponibilidade" not in col_indices and any(
            k in tok for k in ("disponibilidade", "turno", "periodo", "horario")
        ):
            col_indices["disponibilidade"] = idx

    expected_fields = ("nome", "sexo", "disponibilidade")
    missing_fields = [f for f in expected_fields if f not in col_indices]

    if len(missing_fields) == 1 and set(col_indices.values()).issubset({0, 1, 2}):
        remaining_idx = ({0, 1, 2} - set(col_indices.values())).pop()
        missing = missing_fields[0]
        raw_header = str(header_cells[remaining_idx]) if remaining_idx < len(header_cells) else ""
        col_indices[missing] = remaining_idx
        warnings.append(
            f"Cabeçalho atípico na coluna {chr(65 + remaining_idx)} ('{raw_header.strip()}') "
            f"interpretado automaticamente como '{missing.capitalize()}'."
        )
    elif missing_fields:
        default_map = {"nome": 0, "sexo": 1, "disponibilidade": 2}
        used = set(col_indices.values())
        for field_name in missing_fields:
            pref_idx = default_map[field_name]
            if pref_idx not in used:
                col_indices[field_name] = pref_idx
                used.add(pref_idx)
            else:
                for candidate_idx in range(6):
                    if candidate_idx not in used:
                        col_indices[field_name] = candidate_idx
                        used.add(candidate_idx)
                        break
        warnings.append(
            f"Colunas {missing_fields} não identificadas pelo nome no cabeçalho; "
            f"mapeamento posicional aplicado: {col_indices}."
        )

    header_mapping = {
        field_name: (
            str(header_cells[idx]).strip()
            if idx < len(header_cells) and header_cells[idx] is not None
            else ""
        )
        for field_name, idx in col_indices.items()
    }
    return col_indices, header_mapping, warnings, False


def _parse_int_quantity(raw_val: Any, resource_name: str, errors: list[str]) -> Optional[int]:
    """Converte valor de quantidade da aba Turmas para inteiro de forma segura."""
    if raw_val is None or str(raw_val).strip() == "":
        errors.append(f"Recurso '{resource_name}' está com quantidade vazia na aba Turmas.")
        return None
    try:
        num = float(str(raw_val).strip().replace(",", "."))
        if abs(num - round(num)) > 1e-6:
            errors.append(
                f"Recurso '{resource_name}' possui valor não inteiro ({raw_val}); arredondado."
            )
        val = int(round(num))
        if val < 0:
            errors.append(f"Recurso '{resource_name}' possui valor negativo ({val}).")
        return val
    except (ValueError, TypeError):
        errors.append(f"Recurso '{resource_name}' possui valor inválido ('{raw_val}').")
        return None


def read_instance(filepath: str | Path) -> RawInstance:
    """Lê um arquivo .xlsx de instância do Desafio UniSoma e retorna RawInstance."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de instância não encontrado: {path}")
    if path.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise ValueError(f"Formato de arquivo inválido ('{path.suffix}'). Esperado arquivo .xlsx.")

    wb = openpyxl.load_workbook(path, data_only=True)
    try:
        sheet_names = list(wb.sheetnames)
        alunos_sheet_name = _find_sheet_name(sheet_names, ("alunos", "aluno", "matriculados"))
        turmas_sheet_name = _find_sheet_name(sheet_names, ("turmas", "turma", "recursos", "vagas"))

        if alunos_sheet_name is None:
            raise ValueError(
                f"Aba 'Alunos' não encontrada em '{path.name}'. Abas disponíveis: {sheet_names}"
            )
        if turmas_sheet_name is None:
            raise ValueError(
                f"Aba 'Turmas' não encontrada em '{path.name}'. Abas disponíveis: {sheet_names}"
            )

        # 1. Leitura da aba Alunos
        ws_alunos = wb[alunos_sheet_name]
        rows_iter = list(ws_alunos.iter_rows(values_only=True))

        header_row_idx: Optional[int] = None
        for idx, row in enumerate(rows_iter):
            if row and any(cell is not None and str(cell).strip() != "" for cell in row):
                header_row_idx = idx
                break

        students: list[RawStudentRow] = []
        header_mapping: dict[str, str] = {}
        header_warnings: list[str] = []
        header_errors: list[HeaderValidationError] = []

        alunos_header_cells = list(rows_iter[header_row_idx]) if header_row_idx is not None else []
        alunos_hdr_err = validate_sheet_headers(
            alunos_sheet_name, alunos_header_cells, EXPECTED_ALUNOS_COLUMNS
        )
        if alunos_hdr_err is not None:
            header_errors.append(alunos_hdr_err)

        if header_row_idx is not None:
            header_cells = alunos_header_cells
            col_indices, header_mapping, header_warnings, first_is_data = _detect_student_columns(
                header_cells
            )
            start_idx = header_row_idx if first_is_data else header_row_idx + 1
            max_col = max(col_indices.values())

            for idx in range(start_idx, len(rows_iter)):
                row = rows_iter[idx]
                if not row:
                    continue
                # Verifica se todas as células relevantes (e da linha) estão vazias
                if all(cell is None or str(cell).strip() == "" for cell in row[: max(max_col + 1, 3)]):
                    continue

                def _cell_str(col_key: str) -> Optional[str]:
                    c_idx = col_indices[col_key]
                    if c_idx >= len(row) or row[c_idx] is None:
                        return None
                    return str(row[c_idx])

                students.append(
                    RawStudentRow(
                        row_number=idx + 1,  # 1-based como no Excel
                        nome=_cell_str("nome"),
                        sexo=_cell_str("sexo"),
                        disponibilidade=_cell_str("disponibilidade"),
                    )
                )

        # 2. Leitura da aba Turmas
        ws_turmas = wb[turmas_sheet_name]
        turmas_rows = list(ws_turmas.iter_rows(values_only=True))
        turmas_header_cells = list(turmas_rows[0]) if turmas_rows else []
        turmas_hdr_err = validate_sheet_headers(
            turmas_sheet_name, turmas_header_cells, EXPECTED_TURMAS_COLUMNS
        )
        if turmas_hdr_err is not None:
            header_errors.append(turmas_hdr_err)

        turmas_cfg = RawTurmasConfig()

        for r_idx, row in enumerate(turmas_rows, start=1):
            if not row or len(row) < 2:
                continue
            raw_key, raw_val = row[0], row[1]
            if raw_key is None or str(raw_key).strip() == "":
                continue

            key_tok = re.sub(r"[\s\-]+", "_", normalize_token(raw_key))
            # Ignora linha 1 de cabeçalho quando não for diretamente um parâmetro de turma/vaga
            if r_idx == 1 and not any(k in key_tok for k in ("turma", "vaga", "capacidade")):
                continue

            turmas_cfg.raw_entries[str(raw_key).strip()] = raw_val

            if "turma" in key_tok and "manha" in key_tok:
                turmas_cfg.turmas_manha = _parse_int_quantity(
                    raw_val, "turmas_manha", turmas_cfg.parse_errors
                )
            elif "turma" in key_tok and "tarde" in key_tok:
                turmas_cfg.turmas_tarde = _parse_int_quantity(
                    raw_val, "turmas_tarde", turmas_cfg.parse_errors
                )
            elif ("vaga" in key_tok or "capacidade" in key_tok) and "manha" in key_tok:
                turmas_cfg.vagas_manha = _parse_int_quantity(
                    raw_val, "vagas_manha", turmas_cfg.parse_errors
                )
            elif ("vaga" in key_tok or "capacidade" in key_tok) and "tarde" in key_tok:
                turmas_cfg.vagas_tarde = _parse_int_quantity(
                    raw_val, "vagas_tarde", turmas_cfg.parse_errors
                )

        return RawInstance(
            filepath=path,
            sheet_names=sheet_names,
            alunos_sheet_name=alunos_sheet_name,
            turmas_sheet_name=turmas_sheet_name,
            header_mapping=header_mapping,
            header_warnings=header_warnings,
            students=students,
            turmas=turmas_cfg,
            header_errors=header_errors,
        )
    finally:
        wb.close()

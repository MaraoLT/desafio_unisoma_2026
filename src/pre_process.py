"""Módulo de pré-processamento, higienização e validação de inconsistências.

Transforma os dados brutos (RawInstance) em conjuntos matemáticos limpos e
validados (ProcessedInstance), prontos para qualquer solver de otimização,
identificando todas as inconsistências tratadas, alertas de duplicidade e
inconsistências impeditivas de uma só vez.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import re
from typing import Optional

from src.read_instance import RawInstance, RawStudentRow, normalize_token

TURNO_MANHA = "MANHÃ"
TURNO_TARDE = "TARDE"
TURNOS = (TURNO_MANHA, TURNO_TARDE)

GENERO_M = "M"
GENERO_F = "F"
GENEROS = (GENERO_M, GENERO_F)


def index_to_letters(index: int) -> str:
    """Converte índice 0-based em sequência alfabética contínua (A..Z, AA..AZ...)."""
    if index < 0:
        raise ValueError("Índice de turma deve ser não-negativo.")
    letters = []
    n = index
    while True:
        n, rem = divmod(n, 26)
        letters.append(chr(ord("A") + rem))
        if n == 0:
            break
        n -= 1
    return "".join(reversed(letters))


@dataclass(frozen=True)
class Student:
    """Aluno validado pertencente ao conjunto I da modelagem matemática."""

    id: int
    row_number: int
    nome: str
    sexo: str  # 'M' ou 'F'
    disponibilidade: str  # 'MANHÃ', 'TARDE' ou 'INTEGRAL'
    turnos_compativeis: tuple[str, ...]
    is_duplicate_name: bool = False


@dataclass(frozen=True)
class TurmaSpec:
    """Turma k pertencente ao conjunto K da modelagem matemática."""

    id: int
    codigo: str  # Padrão '[PERÍODO] - [LETRA]', ex.: 'MANHÃ - A', 'TARDE - C'
    turno: str  # 'MANHÃ' ou 'TARDE'
    letra: str  # 'A', 'B', ...
    capacidade: int


@dataclass
class Inconsistency:
    """Registro estruturado de inconsistência para relatório e aba 'Inconsistências'."""

    row_number: Optional[int]
    nome: str
    sexo_original: str
    disp_original: str
    categoria: str
    severidade: str  # 'TRATADA' | 'ALERTA' | 'IMPEDITIVA'
    tratada: bool
    mensagem: str


@dataclass
class InvalidStudentRecord:
    """Linha de aluno que não pôde ser incluída em I por inconsistência impeditiva."""

    row_number: int
    nome_raw: str
    sexo_raw: str
    disp_raw: str
    motivos: list[str]


@dataclass
class ProcessedInstance:
    """Instância higienizada e estruturada nos conjuntos do modelo matemático."""

    raw: RawInstance
    students: list[Student]  # Conjunto I
    invalid_records: list[InvalidStudentRecord]
    ignored_summary_rows: list[int]
    turmas: list[TurmaSpec]  # Conjunto K
    turmas_por_turno: dict[str, list[TurmaSpec]]  # K_s
    capacidade_por_turno: dict[str, int]  # C_s
    turmas_compativeis_por_aluno: dict[int, list[int]]  # K_i (student.id -> [turma.id])
    alunos_por_genero: dict[str, list[int]]  # I_g (genero -> [student.id])
    inconsistencies: list[Inconsistency] = field(default_factory=list)
    duplicate_groups: dict[str, list[int]] = field(default_factory=dict)  # nome_exibicao -> [row_numbers]
    capacity_feasible: bool = True
    has_blocking_student_errors: bool = False

    @property
    def is_fully_clean_or_treated(self) -> bool:
        """Retorna True se não há inconsistências impeditivas (de cadastro ou capacidade)."""
        return self.capacity_feasible and not self.has_blocking_student_errors


def _clean_spaces(text: Optional[str]) -> str:
    if text is None:
        return ""
    return re.sub(r"\s+", " ", text.strip())


def _parse_sexo(raw_sexo: Optional[str]) -> tuple[Optional[str], list[str], Optional[str]]:
    """Valida e padroniza o campo Sexo.

    Retorna: (sexo_padronizado, avisos_tratados, erro_impeditivo)
    """
    notes: list[str] = []
    if raw_sexo is None or raw_sexo.strip() == "":
        return None, notes, "Sexo não informado (vazio); esperado 'M' ou 'F'."

    stripped = raw_sexo.strip()
    if stripped != raw_sexo:
        notes.append(f"Espaços extras removidos no campo Sexo ('{raw_sexo}' -> '{stripped}').")

    tok = normalize_token(stripped)
    if tok in {"m", "masculino", "masc", "homem", "menino"} or (sorted(tok) == sorted("masculino") and len(tok) >= 5):
        if stripped != GENERO_M:
            notes.append(f"Sexo '{stripped}' padronizado automaticamente para 'M'.")
        return GENERO_M, notes, None

    if tok in {"f", "feminino", "fem", "mulher", "menina"} or (sorted(tok) == sorted("feminino") and len(tok) >= 5):
        if stripped != GENERO_F:
            notes.append(f"Sexo '{stripped}' padronizado automaticamente para 'F'.")
        return GENERO_F, notes, None

    return None, notes, f"Sexo inválido ('{stripped}'); valores aceitos são 'M' ou 'F'."


def _parse_disponibilidade(
    raw_disp: Optional[str],
    allow_integral: bool = False,
) -> tuple[Optional[str], tuple[str, ...], list[str], Optional[str]]:
    """Valida e padroniza o campo Disponibilidade.

    Retorna: (disp_padronizada, turnos_compativeis, avisos_tratados, erro_impeditivo)
    """
    notes: list[str] = []
    if raw_disp is None or raw_disp.strip() == "":
        return (
            None,
            (),
            notes,
            "Disponibilidade não informada (vazia); esperado 'Manhã' ou 'Tarde'.",
        )

    stripped = raw_disp.strip()
    if stripped != raw_disp:
        notes.append(
            f"Espaços extras removidos no campo Disponibilidade ('{raw_disp}' -> '{stripped}')."
        )

    tok = normalize_token(stripped)

    # Permutações simples / anagramas de "manha" (ex.: mahna, mahan, manah, mnah, etc.)
    sorted_tok = sorted(tok)
    is_manha_perm = (sorted_tok == sorted("manha")) or tok in {"manha", "matutino", "periodo manha", "turno manha", "m"}
    if is_manha_perm:
        if stripped not in {"Manhã", "MANHÃ"}:
            notes.append(f"Disponibilidade '{stripped}' corrigida e padronizada para 'MANHÃ'.")
        return TURNO_MANHA, (TURNO_MANHA,), notes, None

    # Permutações simples / anagramas de "tarde" (ex.: tadre, tader, trdae, etc.)
    is_tarde_perm = (sorted_tok == sorted("tarde")) or tok in {"tarde", "vespertino", "periodo tarde", "turno tarde", "t"}
    if is_tarde_perm:
        if stripped not in {"Tarde", "TARDE"}:
            notes.append(f"Disponibilidade '{stripped}' corrigida e padronizada para 'TARDE'.")
        return TURNO_TARDE, (TURNO_TARDE,), notes, None

    # Permutações de "integral" (ex.: itnegral, inetgral) ou sinônimos
    is_integral_perm = (sorted_tok == sorted("integral")) or tok in {"integral", "ambos", "manha/tarde", "manha e tarde", "qualquer", "livre"}
    if is_integral_perm:
        if allow_integral:
            if stripped not in {"Integral", "INTEGRAL"}:
                notes.append(
                    f"Disponibilidade '{stripped}' padronizada para 'INTEGRAL' (compatível com Manhã e Tarde)."
                )
            return "INTEGRAL", (TURNO_MANHA, TURNO_TARDE), notes, None
        return (
            None,
            (),
            notes,
            f"Disponibilidade inválida ('{stripped}'); permitido apenas 'Manhã' ou 'Tarde'.",
        )

    return (
        None,
        (),
        notes,
        f"Disponibilidade inválida ('{stripped}'); não há oferta para esse turno (esperado 'Manhã' ou 'Tarde').",
    )


def _is_summary_footer_row(row: RawStudentRow) -> bool:
    """Detecta linhas de rodapé/totalização no fim da planilha (ex: 'Total' sem sexo/turno)."""
    nome_tok = normalize_token(row.nome)
    sexo_empty = row.sexo is None or row.sexo.strip() == ""
    disp_empty = row.disponibilidade is None or row.disponibilidade.strip() == ""
    return sexo_empty and disp_empty and nome_tok in {"total", "totais", "subtotal", "soma"}


def pre_process(raw: RawInstance, allow_integral: bool = False) -> ProcessedInstance:
    """Executa higienização completa, validação de regras de negócio e montagem dos conjuntos."""
    inconsistencies: list[Inconsistency] = []
    invalid_records: list[InvalidStudentRecord] = []
    ignored_summary_rows: list[int] = []

    # 1. Avisos de cabeçalho (ex.: A1 = 'Recebi as instâncias ' na instancia_1)
    for warn in raw.header_warnings:
        inconsistencies.append(
            Inconsistency(
                row_number=1,
                nome="-",
                sexo_original="-",
                disp_original="-",
                categoria="Cabeçalho da Planilha",
                severidade="TRATADA",
                tratada=True,
                mensagem=warn,
            )
        )

    # 2. Validação da estrutura de Turmas
    for err in raw.turmas.parse_errors:
        inconsistencies.append(
            Inconsistency(
                row_number=None,
                nome="-",
                sexo_original="-",
                disp_original="-",
                categoria="Configuração de Turmas",
                severidade="IMPEDITIVA",
                tratada=False,
                mensagem=err,
            )
        )

    qtd_turmas_manha = raw.turmas.turmas_manha if raw.turmas.turmas_manha is not None else 0
    qtd_turmas_tarde = raw.turmas.turmas_tarde if raw.turmas.turmas_tarde is not None else 0
    vagas_manha = raw.turmas.vagas_manha if raw.turmas.vagas_manha is not None else 0
    vagas_tarde = raw.turmas.vagas_tarde if raw.turmas.vagas_tarde is not None else 0

    for label, val in (
        ("turmas_manha", raw.turmas.turmas_manha),
        ("turmas_tarde", raw.turmas.turmas_tarde),
        ("vagas_manha", raw.turmas.vagas_manha),
        ("vagas_tarde", raw.turmas.vagas_tarde),
    ):
        if val is None:
            inconsistencies.append(
                Inconsistency(
                    row_number=None,
                    nome="-",
                    sexo_original="-",
                    disp_original="-",
                    categoria="Configuração de Turmas",
                    severidade="IMPEDITIVA",
                    tratada=False,
                    mensagem=f"Parâmetro obrigatório '{label}' ausente ou inválido na aba Turmas.",
                )
            )

    # Criação das turmas em sequência alfabética contínua:
    # Manhã: A, B, ... | Tarde: continua a sequência de letras!
    turmas: list[TurmaSpec] = []
    turmas_por_turno: dict[str, list[TurmaSpec]] = {TURNO_MANHA: [], TURNO_TARDE: []}
    capacidade_por_turno: dict[str, int] = {
        TURNO_MANHA: max(0, vagas_manha),
        TURNO_TARDE: max(0, vagas_tarde),
    }

    letter_Cursor = 0
    turma_id_cursor = 1

    for _ in range(max(0, qtd_turmas_manha)):
        letra = index_to_letters(letter_Cursor)
        spec = TurmaSpec(
            id=turma_id_cursor,
            codigo=f"{TURNO_MANHA} - {letra}",
            turno=TURNO_MANHA,
            letra=letra,
            capacidade=max(0, vagas_manha),
        )
        turmas.append(spec)
        turmas_por_turno[TURNO_MANHA].append(spec)
        letter_Cursor += 1
        turma_id_cursor += 1

    for _ in range(max(0, qtd_turmas_tarde)):
        letra = index_to_letters(letter_Cursor)
        spec = TurmaSpec(
            id=turma_id_cursor,
            codigo=f"{TURNO_TARDE} - {letra}",
            turno=TURNO_TARDE,
            letra=letra,
            capacidade=max(0, vagas_tarde),
        )
        turmas.append(spec)
        turmas_por_turno[TURNO_TARDE].append(spec)
        letter_Cursor += 1
        turma_id_cursor += 1

    # 3. Higienização e validação linha a linha da aba Alunos
    prelim_students: list[tuple[int, str, str, str, tuple[str, ...]]] = []
    name_occurrences: dict[str, list[tuple[int, str, str, str]]] = defaultdict(list)

    for row in raw.students:
        raw_nome_display = "" if row.nome is None else str(row.nome)
        raw_sexo_display = "" if row.sexo is None else str(row.sexo)
        raw_disp_display = "" if row.disponibilidade is None else str(row.disponibilidade)

        row_errors: list[str] = []
        row_notes: list[str] = []

        # Validação do Nome
        cleaned_nome = _clean_spaces(row.nome)
        if not cleaned_nome:
            row_errors.append("Nome do aluno não informado (vazio).")
        elif row.nome is not None and cleaned_nome != row.nome:
            row_notes.append(f"Espaços extras ajustados no Nome ('{row.nome}' -> '{cleaned_nome}').")

        # Validação do Sexo
        sexo_val, sexo_notes, sexo_err = _parse_sexo(row.sexo)
        row_notes.extend(sexo_notes)
        if sexo_err:
            row_errors.append(sexo_err)

        # Validação da Disponibilidade
        disp_val, turnos_comp, disp_notes, disp_err = _parse_disponibilidade(
            row.disponibilidade, allow_integral=allow_integral
        )
        row_notes.extend(disp_notes)
        if disp_err:
            row_errors.append(disp_err)

        if row_errors:
            invalid_records.append(
                InvalidStudentRecord(
                    row_number=row.row_number,
                    nome_raw=raw_nome_display,
                    sexo_raw=raw_sexo_display,
                    disp_raw=raw_disp_display,
                    motivos=row_errors,
                )
            )
            inconsistencies.append(
                Inconsistency(
                    row_number=row.row_number,
                    nome=cleaned_nome if cleaned_nome else f"Linha {row.row_number} (sem nome)",
                    sexo_original=raw_sexo_display if raw_sexo_display else "<VAZIO>",
                    disp_original=raw_disp_display if raw_disp_display else "<VAZIO>",
                    categoria="Erro de Preenchimento",
                    severidade="IMPEDITIVA",
                    tratada=False,
                    mensagem=f"Linha {row.row_number}: " + " | ".join(row_errors),
                )
            )
            continue

        assert sexo_val is not None and disp_val is not None

        if row_notes:
            inconsistencies.append(
                Inconsistency(
                    row_number=row.row_number,
                    nome=cleaned_nome,
                    sexo_original=raw_sexo_display,
                    disp_original=raw_disp_display,
                    categoria="Padronização Automática",
                    severidade="TRATADA",
                    tratada=True,
                    mensagem=" | ".join(row_notes),
                )
            )

        prelim_students.append((row.row_number, cleaned_nome, sexo_val, disp_val, turnos_comp))
        name_key = normalize_token(cleaned_nome)
        name_occurrences[name_key].append((row.row_number, cleaned_nome, sexo_val, disp_val))

    # 4. Detecção de Duplicidade de Nomes (Homônimos / Possível Duplo Cadastro)
    duplicate_keys: set[str] = set()
    duplicate_groups: dict[str, list[int]] = {}

    for name_key, occs in name_occurrences.items():
        if len(occs) > 1:
            duplicate_keys.add(name_key)
            canonical_name = occs[0][1]
            rows_list = [o[0] for o in occs]
            duplicate_groups[canonical_name] = rows_list

            turnos_set = {o[3] for o in occs}
            sexos_set = {o[2] for o in occs}
            linhas_str = ", ".join(str(r) for r in rows_list)

            inconsistencies.append(
                Inconsistency(
                    row_number=rows_list[0],
                    nome=canonical_name,
                    sexo_original="/".join(sorted(sexos_set)),
                    disp_original="/".join(sorted(turnos_set)),
                    categoria="Duplicidade de Nome",
                    severidade="ALERTA",
                    tratada=True,
                    mensagem=(
                        f'"{canonical_name}" aparece {len(occs)} vezes (Linhas {linhas_str}). '
                        "Verifique se é cadastro duplicado."
                    ),
                )
            )

    # 5. Construção dos objetos Student (Conjunto I) e mapeamentos K_i e I_g
    students: list[Student] = []
    turmas_compativeis_por_aluno: dict[int, list[int]] = {}
    alunos_por_genero: dict[str, list[int]] = {GENERO_M: [], GENERO_F: []}
    shared_comp_cache: dict[tuple[str, ...], list[int]] = {}

    for idx, (row_num, nome, sexo, disp, turnos_comp) in enumerate(prelim_students, start=1):
        is_dup = normalize_token(nome) in duplicate_keys
        st = Student(
            id=idx,
            row_number=row_num,
            nome=nome,
            sexo=sexo,
            disponibilidade=disp,
            turnos_compativeis=turnos_comp,
            is_duplicate_name=is_dup,
        )
        students.append(st)
        alunos_por_genero[sexo].append(st.id)

        comp_ids = shared_comp_cache.get(turnos_comp)
        if comp_ids is None:
            comp_ids = []
            for t_turno in turnos_comp:
                comp_ids.extend(t.id for t in turmas_por_turno.get(t_turno, []))
            shared_comp_cache[turnos_comp] = comp_ids
        turmas_compativeis_por_aluno[st.id] = comp_ids

    # 6. Verificação Global de Capacidade por Turno
    capacity_feasible = True
    fixed_manha = sum(1 for s in students if s.turnos_compativeis == (TURNO_MANHA,))
    fixed_tarde = sum(1 for s in students if s.turnos_compativeis == (TURNO_TARDE,))
    flex_count = sum(1 for s in students if len(s.turnos_compativeis) > 1)

    cap_manha = len(turmas_por_turno[TURNO_MANHA]) * capacidade_por_turno[TURNO_MANHA]
    cap_tarde = len(turmas_por_turno[TURNO_TARDE]) * capacidade_por_turno[TURNO_TARDE]

    if fixed_manha > cap_manha:
        capacity_feasible = False
        excesso = fixed_manha - cap_manha
        inconsistencies.append(
            Inconsistency(
                row_number=None,
                nome="-",
                sexo_original="-",
                disp_original=TURNO_MANHA,
                categoria="Capacidade Insuficiente",
                severidade="IMPEDITIVA",
                tratada=False,
                mensagem=(
                    f"Turno MANHÃ possui {fixed_manha} alunos válidos para apenas {cap_manha} vagas "
                    f"({len(turmas_por_turno[TURNO_MANHA])} turmas x {capacidade_por_turno[TURNO_MANHA]} vagas). "
                    f"Déficit de {excesso} vaga(s)."
                ),
            )
        )

    if fixed_tarde > cap_tarde:
        capacity_feasible = False
        excesso = fixed_tarde - cap_tarde
        inconsistencies.append(
            Inconsistency(
                row_number=None,
                nome="-",
                sexo_original="-",
                disp_original=TURNO_TARDE,
                categoria="Capacidade Insuficiente",
                severidade="IMPEDITIVA",
                tratada=False,
                mensagem=(
                    f"Turno TARDE possui {fixed_tarde} alunos válidos para apenas {cap_tarde} vagas "
                    f"({len(turmas_por_turno[TURNO_TARDE])} turmas x {capacidade_por_turno[TURNO_TARDE]} vagas). "
                    f"Déficit de {excesso} vaga(s)."
                ),
            )
        )

    if (fixed_manha + fixed_tarde + flex_count) > (cap_manha + cap_tarde):
        capacity_feasible = False
        excesso = (fixed_manha + fixed_tarde + flex_count) - (cap_manha + cap_tarde)
        inconsistencies.append(
            Inconsistency(
                row_number=None,
                nome="-",
                sexo_original="-",
                disp_original="GLOBAL",
                categoria="Capacidade Insuficiente",
                severidade="IMPEDITIVA",
                tratada=False,
                mensagem=(
                    f"Total de alunos válidos ({len(students)}) excede a soma total de vagas "
                    f"da instituição ({cap_manha + cap_tarde}). Déficit global de {excesso} vaga(s)."
                ),
            )
        )

    has_blocking_errors = len(invalid_records) > 0 or len(raw.turmas.parse_errors) > 0

    return ProcessedInstance(
        raw=raw,
        students=students,
        invalid_records=invalid_records,
        ignored_summary_rows=ignored_summary_rows,
        turmas=turmas,
        turmas_por_turno=turmas_por_turno,
        capacidade_por_turno=capacidade_por_turno,
        turmas_compativeis_por_aluno=turmas_compativeis_por_aluno,
        alunos_por_genero=alunos_por_genero,
        inconsistencies=inconsistencies,
        duplicate_groups=duplicate_groups,
        capacity_feasible=capacity_feasible,
        has_blocking_student_errors=has_blocking_errors,
    )


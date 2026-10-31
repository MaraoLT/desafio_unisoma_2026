"""Gerador de famílias de instâncias difíceis — Desafio UniSoma 2026.

Gera benchmarks sintéticos estruturados em famílias de alta dificuldade de
balanceamento nos portes de 200, 500, 1000, 2000, 10000 e 50000 alunos,
incluindo famílias com alunos de disponibilidade 'Integral', excesso de demanda
(lista de espera) e regimes extremos de infraestrutura (muitas salas minúsculas
e poucas salas gigantes).

Famílias disponíveis:
  1. F1_modular_conflict          : Sem integrais; conflito modular primo (r_M + r_F > |K_s|) e ~98% ocupação.
  2. F2_gender_cross_integral     : ~30% Integrais; inversão demográfica cruzada (Manhã F-heavy vs Tarde M-heavy).
  3. F3_bottleneck_integral       : ~40% Integrais; gargalo severo na Manhã + salas assimétricas + ~98.5% ocupação.
  4. F4_extreme_minority_integral : ~25% Integrais; escassez extrema do gênero minoritário (~18% M / 82% F).
  5. F5_noisy_realistic_integral  : ~20% Integrais; ruído realista de grafia, homônimos (~5%) e salas economizáveis.
  6. F6_shift_overflow_fixed      : Sem integrais; excesso de demanda na Manhã (~115%, alunos sem turma) e vagas ociosas na Tarde.
  7. F7_global_overflow_integral  : ~25% Integrais; excesso global de demanda (~110% da capacidade total) + inversão de gênero.
  8. F8_many_tiny_rooms_integral  : ~30% Integrais; muitas salas muito pequenas (~9-11 vagas/sala, até 4.644 salas em N=50k).
  9. F9_few_huge_rooms_integral   : ~35% Integrais; poucas salas muito grandes / auditórios (2-4 por turno, até 8.600 vagas/sala).
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import random
import sys
from typing import Optional

import openpyxl
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font, PatternFill

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BENCHMARK_SIZES: tuple[int, ...] = (200, 500, 1000, 2000, 10000, 50000)

FIRST_NAMES_M: tuple[str, ...] = (
    "Arthur", "Bernardo", "Bruno", "Caio", "Carlos", "Daniel", "Davi", "Diego",
    "Eduardo", "Emanuel", "Enzo", "Felipe", "Gabriel", "Gael", "Guilherme",
    "Gustavo", "Heitor", "Henrique", "Hugo", "Igor", "Isaac", "João", "Joaquim",
    " Kauã".strip(), "Leonardo", "Lorenzo", "Lucas", "Lucca", "Matheus", "Miguel",
    "Murilo", "Nathan", "Nicolas", "Noah", "Otávio", "Pedro", "Pietro", "Rafael",
    "Raul", "Rodrigo", "Samuel", "Theo", "Thiago", "Tomás", "Vinícius", "Vitor",
    "Yuri", "André", "Antônio", " Augusto".strip(), "Benício", "Breno", "Caleb",
)

FIRST_NAMES_F: tuple[str, ...] = (
    "Agatha", "Alice", "Amanda", "Ana", "Antonella", "Beatriz", "Bianca", "Bruna",
    "Camila", "Carolina", "Catarina", "Cecília", "Clara", "Eduarda", "Elisa",
    "Emanuelly", "Esther", "Fernanda", "Gabriela", "Giovanna", "Helena", "Heloísa",
    "Isabela", "Isadora", "Júlia", "Juliana", "Lara", "Larissa", "Laura", "Lavínia",
    "Letícia", "Lívia", "Lorena", "Luana", "Luísa", "Maitê", "Manuela", "Marcela",
    "Maria", "Mariana", "Marina", "Melissa", "Mirella", "Natália", "Nicole",
    "Olívia", "Pietra", "Rafaela", "Rebeca", "Sarah", "Sophia", " Stella".strip(),
    "Valentina", "Vitória", "Yasmin",
)

LAST_NAMES: tuple[str, ...] = (
    "Almeida", "Alves", "Andrade", "Araújo", "Barbosa", "Barros", "Batista",
    "Borges", "Campos", "Cardoso", "Carvalho", "Castro", "Cavalcanti", "Correia",
    "Costa", "Cunha", "Dias", "Duarte", "Fernandes", "Ferreira", "Freitas",
    "Garcia", "Gomes", "Gonçalves", "Lima", "Lopes", "Machado", "Marques",
    "Martins", "Medeiros", "Melo", "Mendes", "Miranda", "Monteiro", "Moraes",
    "Moreira", "Moura", "Nascimento", "Nogueira", "Nunes", "Oliveira", "Pereira",
    "Pinto", "Ramos", "Reis", "Ribeiro", "Rocha", "Rodrigues", "Santana",
    "Santos", "Silva", "Soares", "Souza", "Teixeira", "Vieira",
)

PREPOSITIONS: tuple[str, ...] = ("", "", "", "de ", "da ", "do ", "dos ")


@dataclass
class GeneratedInstanceSpec:
    """Metadados e parâmetros matemáticos exatos de uma instância gerada."""

    family: str
    name: str
    description: str
    filepath: str
    seed: int
    total_students: int
    has_integral: bool
    turmas_manha: int
    turmas_tarde: int
    vagas_manha: int
    vagas_tarde: int
    cap_total_manha: int
    cap_total_tarde: int
    cap_total_global: int
    global_occupancy_pct: float
    count_manha_m: int
    count_manha_f: int
    count_tarde_m: int
    count_tarde_f: int
    count_integral_m: int
    count_integral_f: int
    homonym_pairs: int
    noisy_cells: int
    allow_capacity_deficit: bool = False
    expected_unallocated: int = 0


def _verify_spec_feasibility(spec: GeneratedInstanceSpec) -> None:
    """Valida a consistência matemática de contagens e déficit esperado da instância."""
    tot = (
        spec.count_manha_m
        + spec.count_manha_f
        + spec.count_tarde_m
        + spec.count_tarde_f
        + spec.count_integral_m
        + spec.count_integral_f
    )
    if tot != spec.total_students:
        raise AssertionError(
            f"[{spec.name}] Soma de alunos ({tot}) != total_students ({spec.total_students})."
        )

    fix_manha = spec.count_manha_m + spec.count_manha_f
    fix_tarde = spec.count_tarde_m + spec.count_tarde_f
    tot_int = spec.count_integral_m + spec.count_integral_f
    cap_m = spec.turmas_manha * spec.vagas_manha
    cap_t = spec.turmas_tarde * spec.vagas_tarde

    def_m = max(0, fix_manha - cap_m)
    free_m = max(0, cap_m - fix_manha)
    def_t = max(0, fix_tarde - cap_t)
    free_t = max(0, cap_t - fix_tarde)
    def_int = max(0, tot_int - (free_m + free_t))
    hall_unallocated = def_m + def_t + def_int

    if not spec.allow_capacity_deficit:
        if fix_manha > cap_m:
            raise AssertionError(
                f"[{spec.name}] Fixos Manhã ({fix_manha}) > Capacidade Manhã ({cap_m})."
            )
        if fix_tarde > cap_t:
            raise AssertionError(
                f"[{spec.name}] Fixos Tarde ({fix_tarde}) > Capacidade Tarde ({cap_t})."
            )
        if tot > cap_m + cap_t:
            raise AssertionError(
                f"[{spec.name}] Total de alunos ({tot}) > Capacidade Global ({cap_m + cap_t})."
            )
    else:
        if hall_unallocated <= 0:
            raise AssertionError(
                f"[{spec.name}] Família de excesso de demanda deveria ter hall_unallocated > 0."
            )
        if spec.expected_unallocated != hall_unallocated:
            raise AssertionError(
                f"[{spec.name}] expected_unallocated ({spec.expected_unallocated}) != "
                f"Teorema de Hall ({hall_unallocated})."
            )


def _generate_full_name(gender: str, rng: random.Random, used_names: set[str]) -> str:
    """Gera um nome completo brasileiro único coerente com o gênero."""
    pool_first = FIRST_NAMES_M if gender == "M" else FIRST_NAMES_F
    for _ in range(500):
        first = rng.choice(pool_first)
        # Com 35% de chance usa nome composto para ampliar espaço combinatório em N=2000
        if rng.random() < 0.35:
            second = rng.choice(pool_first)
            if second != first:
                first = f"{first} {second}"
        n_surnames = rng.choice((2, 2, 3))
        chosen_last = rng.sample(LAST_NAMES, k=n_surnames)
        parts = [first]
        for idx, surname in enumerate(chosen_last):
            prep = rng.choice(PREPOSITIONS) if idx > 0 else ""
            parts.append(f"{prep}{surname}")
        candidate = " ".join(parts)
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
    fallback = f"{rng.choice(pool_first)} {rng.choice(LAST_NAMES)} {len(used_names) + 1}"
    used_names.add(fallback)
    return fallback


def _modular_hard_split(total_shift: int, k_rooms: int, target_m_ratio: float = 0.47) -> tuple[int, int]:
    """Divide total_shift em (M, F) forçando r_M + r_F > k_rooms (conflito modular)."""
    if k_rooms < 3 or total_shift < 2 * k_rooms:
        n_m = int(round(total_shift * target_m_ratio))
        return n_m, total_shift - n_m

    # Garante que n_m ≡ k_rooms - 1 (mod k_rooms).
    # Assim, se total_shift ≡ r_q (mod k_rooms) com r_q >= 1, teremos:
    # r_M = k_rooms - 1 != 0, r_F = (r_q + 1) mod k_rooms, e r_M + r_F = k_rooms + r_q > k_rooms!
    approx_m = int(round(total_shift * target_m_ratio))
    q = max(0, (approx_m - (k_rooms - 1)) // k_rooms)
    n_m = q * k_rooms + (k_rooms - 1)
    if n_m >= total_shift:
        n_m -= k_rooms
    n_m = max(1, min(total_shift - 1, n_m))
    n_f = total_shift - n_m
    return n_m, n_f


def _build_f1_modular_conflict(n: int, out_dir: Path, seed: int) -> GeneratedInstanceSpec:
    """Família 1: Conflito modular primo (r_M + r_F > |K_s|) e ~98% de ocupação, sem Integrais."""
    rooms_map = {
        200: (3, 5),
        500: (7, 9),
        1000: (13, 19),
        2000: (29, 37),
        10000: (149, 179),
        50000: (743, 887),
    }
    if n in rooms_map:
        km, kt = rooms_map[n]
    else:
        km = max(3, round(n / 62))
        kt = max(3, round(n / 54))
        if km % 2 == 0:
            km += 1
        if kt % 2 == 0:
            kt += 1

    # Escolhe N_manha com resto não-nulo (ex.: km - 2) e N_tarde = n - N_manha (ajustando se divisível)
    target_nm = int(round(n * (km / (km + kt))))
    rem_m = max(1, km - 2)
    nm = (target_nm // km) * km + rem_m
    if nm >= n - kt:
        nm -= km
    nt = n - nm
    if nt % kt == 0 or nt % kt == kt - 1:
        nm -= 1
        nt += 1
        if nm % km == 0 or nm % km == km - 1:
            nm -= 1
            nt += 1

    m_manha, f_manha = _modular_hard_split(nm, km, target_m_ratio=0.46)
    m_tarde, f_tarde = _modular_hard_split(nt, kt, target_m_ratio=0.53)

    # Capacidade estritamente no teto mínimo ceil(N_s / K_s): folga quase zero!
    vm = math.ceil(nm / km)
    vt = math.ceil(nt / kt)

    cap_m, cap_t = km * vm, kt * vt
    name = f"F1_modular_conflict_n{n}"
    fpath = out_dir / "F1_modular_conflict" / f"{name}.xlsx"

    return GeneratedInstanceSpec(
        family="F1_modular_conflict",
        name=name,
        description=(
            "Sem alunos integrais; números ímpares/coprimos de turmas, ocupação no limite "
            "máximo e restos modulares acoplados (r_M + r_F > |K_s|) em ambos os turnos."
        ),
        filepath=str(fpath),
        seed=seed,
        total_students=n,
        has_integral=False,
        turmas_manha=km,
        turmas_tarde=kt,
        vagas_manha=vm,
        vagas_tarde=vt,
        cap_total_manha=cap_m,
        cap_total_tarde=cap_t,
        cap_total_global=cap_m + cap_t,
        global_occupancy_pct=round(100.0 * n / (cap_m + cap_t), 2),
        count_manha_m=m_manha,
        count_manha_f=f_manha,
        count_tarde_m=m_tarde,
        count_tarde_f=f_tarde,
        count_integral_m=0,
        count_integral_f=0,
        homonym_pairs=max(2, n // 100),
        noisy_cells=0,
    )


def _build_f2_gender_cross_integral(n: int, out_dir: Path, seed: int) -> GeneratedInstanceSpec:
    """Família 2: ~30% Integrais + Inversão Demográfica Cruzada (Manhã F-heavy vs Tarde M-heavy)."""
    rooms_map = {
        200: (4, 5),
        500: (8, 9),
        1000: (16, 17),
        2000: (31, 33),
        10000: (157, 163),
        50000: (787, 811),
    }
    km, kt = rooms_map.get(n, (max(3, n // 60), max(4, n // 58)))

    n_int = int(round(0.30 * n))
    rem_fixed = n - n_int
    n_fix_m = int(round(rem_fixed * (km / (km + kt))))
    n_fix_t = rem_fixed - n_fix_m

    # Manhã fixa: ~78% Feminino | Tarde fixa: ~78% Masculino
    f_manha = int(round(0.78 * n_fix_m))
    m_manha = n_fix_m - f_manha

    m_tarde = int(round(0.78 * n_fix_t))
    f_tarde = n_fix_t - m_tarde

    # Integrais (~50/50 com assimetria ímpar para criar dilema de arredondamento)
    m_int = (n_int // 2) + 1 if n_int >= 4 else n_int // 2
    f_int = n_int - m_int

    # Capacidade global enxuta (~96% ocupação), exigindo dividir os Integrais entre os dois turnos
    total_rooms = km + kt
    target_cap_global = math.ceil(n / 0.96)
    avg_vagas = math.ceil(target_cap_global / total_rooms)
    vm = max(math.ceil(n_fix_m / km) + 2, avg_vagas)
    vt = max(math.ceil(n_fix_t / kt) + 2, avg_vagas)
    while km * vm + kt * vt < n:
        vt += 1

    cap_m, cap_t = km * vm, kt * vt
    name = f"F2_gender_cross_integral_n{n}"
    fpath = out_dir / "F2_gender_cross_integral" / f"{name}.xlsx"

    return GeneratedInstanceSpec(
        family="F2_gender_cross_integral",
        name=name,
        description=(
            "~30% de alunos Integrais; Manhã fixa fortemente feminina (78% F) e Tarde fixa "
            "fortemente masculina (78% M). O solver precisa decidir o turno de cada aluno "
            "Integral para corrigir simultaneamente os restos modulares e a paridade 50/50."
        ),
        filepath=str(fpath),
        seed=seed,
        total_students=n,
        has_integral=True,
        turmas_manha=km,
        turmas_tarde=kt,
        vagas_manha=vm,
        vagas_tarde=vt,
        cap_total_manha=cap_m,
        cap_total_tarde=cap_t,
        cap_total_global=cap_m + cap_t,
        global_occupancy_pct=round(100.0 * n / (cap_m + cap_t), 2),
        count_manha_m=m_manha,
        count_manha_f=f_manha,
        count_tarde_m=m_tarde,
        count_tarde_f=f_tarde,
        count_integral_m=m_int,
        count_integral_f=f_int,
        homonym_pairs=max(2, n // 100),
        noisy_cells=0,
    )


def _build_f3_bottleneck_integral(n: int, out_dir: Path, seed: int) -> GeneratedInstanceSpec:
    """Família 3: ~40% Integrais + Gargalo severo de vagas na Manhã + salas assimétricas."""
    cfg_map = {
        200: (4, 23, 4, 28),      # Cap: 92 M + 112 T = 204 (98.0% ocup!)
        500: (9, 25, 9, 32),      # Cap: 225 M + 288 T = 513 (97.5% ocup!)
        1000: (17, 25, 19, 31),   # Cap: 425 M + 589 T = 1014 (98.6% ocup!)
        2000: (33, 26, 37, 32),   # Cap: 858 M + 1184 T = 2042 (97.9% ocup!)
        10000: (167, 26, 181, 32),  # Cap: 4342 M + 5792 T = 10134 (98.7% ocup!)
        50000: (829, 26, 911, 32),  # Cap: 21554 M + 29152 T = 50706 (98.6% ocup!)
    }
    if n in cfg_map:
        km, vm, kt, vt = cfg_map[n]
    else:
        km = max(3, round(n / 60))
        vm = 25
        kt = max(3, round(n / 55))
        vt = math.ceil((math.ceil(n / 0.98) - km * vm) / kt)

    cap_m, cap_t = km * vm, kt * vt
    n_int = int(round(0.40 * n))
    rem_fixed = n - n_int

    # Manhã fixa já consome ~93% da capacidade da Manhã (gargalo severo!)
    n_fix_m = min(rem_fixed - kt, int(round(0.93 * cap_m)))
    n_fix_t = rem_fixed - n_fix_m

    # Manhã fixa tem déficit masculino (32% M), mas quase não tem vagas sobrando!
    m_manha = int(round(0.32 * n_fix_m))
    f_manha = n_fix_m - m_manha

    m_tarde = int(round(0.58 * n_fix_t))
    f_tarde = n_fix_t - m_tarde

    # Integrais têm 55% M / 45% F
    m_int = int(round(0.55 * n_int))
    f_int = n_int - m_int

    name = f"F3_bottleneck_integral_n{n}"
    fpath = out_dir / "F3_bottleneck_integral" / f"{name}.xlsx"

    return GeneratedInstanceSpec(
        family="F3_bottleneck_integral",
        name=name,
        description=(
            "~40% de alunos Integrais; gargalo severo na Manhã (~93% já tomada por alunos fixos "
            "em salas menores) e ocupação global ~98%. Exige filtragem cirúrgica de quais "
            "poucos alunos Integrais preencherão as vagas finais da Manhã vs. Tarde."
        ),
        filepath=str(fpath),
        seed=seed,
        total_students=n,
        has_integral=True,
        turmas_manha=km,
        turmas_tarde=kt,
        vagas_manha=vm,
        vagas_tarde=vt,
        cap_total_manha=cap_m,
        cap_total_tarde=cap_t,
        cap_total_global=cap_m + cap_t,
        global_occupancy_pct=round(100.0 * n / (cap_m + cap_t), 2),
        count_manha_m=m_manha,
        count_manha_f=f_manha,
        count_tarde_m=m_tarde,
        count_tarde_f=f_tarde,
        count_integral_m=m_int,
        count_integral_f=f_int,
        homonym_pairs=max(2, n // 100),
        noisy_cells=0,
    )


def _build_f4_extreme_minority_integral(n: int, out_dir: Path, seed: int) -> GeneratedInstanceSpec:
    """Família 4: ~25% Integrais + Escassez extrema de um gênero (~18% M / 82% F)."""
    rooms_map = {
        200: (5, 3),
        500: (11, 7),
        1000: (19, 15),
        2000: (37, 31),
        10000: (181, 157),
        50000: (907, 787),
    }
    km, kt = rooms_map.get(n, (max(3, n // 50), max(3, n // 65)))

    n_int = int(round(0.25 * n))
    rem_fixed = n - n_int
    n_fix_m = int(round(rem_fixed * (km / (km + kt))))
    n_fix_t = rem_fixed - n_fix_m

    # Apenas ~17-19% de alunos do gênero M no total, gerando ~4-5 meninos por sala
    m_manha = max(1, int(round(0.16 * n_fix_m)))
    f_manha = n_fix_m - m_manha

    m_tarde = max(1, int(round(0.19 * n_fix_t)))
    f_tarde = n_fix_t - m_tarde

    m_int = max(1, int(round(0.21 * n_int)))
    f_int = n_int - m_int

    total_rooms = km + kt
    avg_vagas = math.ceil(math.ceil(n / 0.965) / total_rooms)
    vm = max(math.ceil(n_fix_m / km) + 2, avg_vagas)
    vt = max(math.ceil(n_fix_t / kt) + 2, avg_vagas)
    while km * vm + kt * vt < n:
        vm += 1

    cap_m, cap_t = km * vm, kt * vt
    name = f"F4_extreme_minority_integral_n{n}"
    fpath = out_dir / "F4_extreme_minority_integral" / f"{name}.xlsx"

    return GeneratedInstanceSpec(
        family="F4_extreme_minority_integral",
        name=name,
        description=(
            "~25% de alunos Integrais; escassez severa do gênero minoritário (~18% M e ~82% F) "
            "em quantidades primas de turmas. Cada menino Integral deslocado altera o "
            "balanceamento fino par-a-par de dezenas de pares de salas."
        ),
        filepath=str(fpath),
        seed=seed,
        total_students=n,
        has_integral=True,
        turmas_manha=km,
        turmas_tarde=kt,
        vagas_manha=vm,
        vagas_tarde=vt,
        cap_total_manha=cap_m,
        cap_total_tarde=cap_t,
        cap_total_global=cap_m + cap_t,
        global_occupancy_pct=round(100.0 * n / (cap_m + cap_t), 2),
        count_manha_m=m_manha,
        count_manha_f=f_manha,
        count_tarde_m=m_tarde,
        count_tarde_f=f_tarde,
        count_integral_m=m_int,
        count_integral_f=f_int,
        homonym_pairs=max(2, n // 100),
        noisy_cells=0,
    )


def _build_f5_noisy_realistic_integral(n: int, out_dir: Path, seed: int) -> GeneratedInstanceSpec:
    """Família 5: ~20% Integrais + Ruído realista tratável + Homônimos + Salas economizáveis."""
    cfg_map = {
        200: (5, 30, 3, 30),        # Cap: 150 M + 90 T = 240 (permite sala vazia na Manhã!)
        500: (11, 32, 8, 30),       # Cap: 352 M + 240 T = 592
        1000: (22, 32, 16, 30),     # Cap: 704 M + 480 T = 1184
        2000: (43, 32, 31, 30),     # Cap: 1376 M + 930 T = 2306
        10000: (211, 32, 151, 30),  # Cap: 6752 M + 4530 T = 11282
        50000: (1051, 32, 751, 30), # Cap: 33632 M + 22530 T = 56162
    }
    if n in cfg_map:
        km, vm, kt, vt = cfg_map[n]
    else:
        vm, vt = 32, 30
        km = max(4, math.ceil((0.60 * n) / vm) + 1)
        kt = max(3, math.ceil((0.45 * n) / vt))

    cap_m, cap_t = km * vm, kt * vt
    n_int = int(round(0.20 * n))
    rem_fixed = n - n_int

    # Fixos Tarde deixam a Tarde apertada (~85% só com fixos), Manhã com folga p/ economia de salas
    n_fix_t = min(rem_fixed - km, int(round(0.84 * cap_t)))
    n_fix_m = rem_fixed - n_fix_t

    m_manha, f_manha = _modular_hard_split(n_fix_m, km, target_m_ratio=0.42)
    m_tarde, f_tarde = _modular_hard_split(n_fix_t, kt, target_m_ratio=0.57)
    m_int = int(round(0.49 * n_int))
    f_int = n_int - m_int

    name = f"F5_noisy_realistic_integral_n{n}"
    fpath = out_dir / "F5_noisy_realistic_integral" / f"{name}.xlsx"

    return GeneratedInstanceSpec(
        family="F5_noisy_realistic_integral",
        name=name,
        description=(
            "~20% de alunos Integrais + ~12% de células com ruído tratável de grafia/espaços/case "
            "+ ~5% de homônimos + folga estrutural na Manhã que viabiliza soluções com salas vazias."
        ),
        filepath=str(fpath),
        seed=seed,
        total_students=n,
        has_integral=True,
        turmas_manha=km,
        turmas_tarde=kt,
        vagas_manha=vm,
        vagas_tarde=vt,
        cap_total_manha=cap_m,
        cap_total_tarde=cap_t,
        cap_total_global=cap_m + cap_t,
        global_occupancy_pct=round(100.0 * n / (cap_m + cap_t), 2),
        count_manha_m=m_manha,
        count_manha_f=f_manha,
        count_tarde_m=m_tarde,
        count_tarde_f=f_tarde,
        count_integral_m=m_int,
        count_integral_f=f_int,
        homonym_pairs=max(5, n // 20),
        noisy_cells=max(15, int(round(0.12 * n))),
    )


def _build_f6_shift_overflow_fixed(n: int, out_dir: Path, seed: int) -> GeneratedInstanceSpec:
    """Família 6: Sem Integrais + Estouro de vagas na Manhã (~115%) com folga ociosa na Tarde."""
    cfg_map = {
        200: (3, 28, 4, 31, 98),         # Cap: 84 M + 124 T = 208 | 98 na Manhã -> 14 sem turma!
        500: (7, 29, 9, 35, 235),        # Cap: 203 M + 315 T = 518 | 235 na Manhã -> 32 sem turma!
        1000: (13, 30, 19, 34, 450),     # Cap: 390 M + 646 T = 1036 | 450 na Manhã -> 60 sem turma!
        2000: (27, 30, 37, 35, 930),     # Cap: 810 M + 1295 T = 2105 | 930 na Manhã -> 120 sem turma!
        10000: (137, 30, 181, 35, 4710), # Cap: 4110 M + 6335 T = 10445 | 4710 na Manhã -> 600 sem turma!
        50000: (683, 30, 907, 35, 23590),# Cap: 20490 M + 31745 T = 52235 | 23590 na Manhã -> 3100 sem turma!
    }
    if n in cfg_map:
        km, vm, kt, vt, nm = cfg_map[n]
    else:
        vm, vt = 29, 34
        km = max(3, int(round(0.40 * n / vm)))
        cap_m_tmp = km * vm
        nm = min(n - 10, int(round(1.15 * cap_m_tmp)))
        nt_tmp = n - nm
        kt = max(3, math.ceil((nt_tmp + (nm - cap_m_tmp) + 12) / vt))

    nt = n - nm
    cap_m, cap_t = km * vm, kt * vt
    expected_unalloc = nm - cap_m

    # Manhã tem viés masculino (~58% M): o solver parcial precisa filtrar quem entra para equilibrar 50/50
    m_manha = int(round(0.58 * nm))
    f_manha = nm - m_manha

    # Tarde cabe inteira, mas possui conflito modular primo entre M e F
    m_tarde, f_tarde = _modular_hard_split(nt, kt, target_m_ratio=0.46)

    name = f"F6_shift_overflow_fixed_n{n}"
    fpath = out_dir / "F6_shift_overflow_fixed" / f"{name}.xlsx"

    return GeneratedInstanceSpec(
        family="F6_shift_overflow_fixed",
        name=name,
        description=(
            "Sem alunos Integrais; excesso de demanda localizado na Manhã (~115% das vagas da "
            "Manhã, deixando alunos sem turma) enquanto sobram vagas ociosas incompatíveis na Tarde."
        ),
        filepath=str(fpath),
        seed=seed,
        total_students=n,
        has_integral=False,
        turmas_manha=km,
        turmas_tarde=kt,
        vagas_manha=vm,
        vagas_tarde=vt,
        cap_total_manha=cap_m,
        cap_total_tarde=cap_t,
        cap_total_global=cap_m + cap_t,
        global_occupancy_pct=round(100.0 * n / (cap_m + cap_t), 2),
        count_manha_m=m_manha,
        count_manha_f=f_manha,
        count_tarde_m=m_tarde,
        count_tarde_f=f_tarde,
        count_integral_m=0,
        count_integral_f=0,
        homonym_pairs=max(2, n // 100),
        noisy_cells=0,
        allow_capacity_deficit=True,
        expected_unallocated=expected_unalloc,
    )


def _build_f7_global_overflow_integral(n: int, out_dir: Path, seed: int) -> GeneratedInstanceSpec:
    """Família 7: ~25% Integrais + Estouro global de capacidade (~110% demanda/vagas) + Inversão M/F."""
    cfg_map = {
        200: (3, 26, 4, 26, 82),         # Cap: 78 M + 104 T = 182 (falta 18 vagas no global!)
        500: (7, 26, 9, 30, 192),        # Cap: 182 M + 270 T = 452 (falta 48 vagas no global!)
        1000: (13, 28, 18, 30, 384),     # Cap: 364 M + 540 T = 904 (falta 96 vagas no global!)
        2000: (27, 28, 35, 30, 796),     # Cap: 756 M + 1050 T = 1806 (falta 194 vagas no global!)
        10000: (137, 28, 173, 30, 3990), # Cap: 3836 M + 5190 T = 9026 (falta 974 vagas no global!)
        50000: (683, 28, 863, 30, 19950),# Cap: 19124 M + 25890 T = 45014 (falta 4986 vagas no global!)
    }
    if n in cfg_map:
        km, vm, kt, vt, n_fix_m = cfg_map[n]
    else:
        vm, vt = 28, 30
        target_cap = int(round(0.91 * n))
        km = max(3, int(round(0.42 * target_cap / vm)))
        kt = max(3, int(round((target_cap - km * vm) / vt)))
        n_fix_m = int(round(1.05 * km * vm))

    cap_m, cap_t = km * vm, kt * vt
    n_int = int(round(0.25 * n))
    n_fix_t = n - n_int - n_fix_m

    # Manhã fixa fortemente masculina (70% M), Tarde fixa fortemente feminina (72% F)
    m_manha = int(round(0.70 * n_fix_m))
    f_manha = n_fix_m - m_manha

    f_tarde = int(round(0.72 * n_fix_t))
    m_tarde = n_fix_t - f_tarde

    m_int = int(round(0.48 * n_int))
    f_int = n_int - m_int

    def_m = max(0, n_fix_m - cap_m)
    free_m = max(0, cap_m - n_fix_m)
    def_t = max(0, n_fix_t - cap_t)
    free_t = max(0, cap_t - n_fix_t)
    expected_unalloc = def_m + def_t + max(0, n_int - (free_m + free_t))

    name = f"F7_global_overflow_integral_n{n}"
    fpath = out_dir / "F7_global_overflow_integral" / f"{name}.xlsx"

    return GeneratedInstanceSpec(
        family="F7_global_overflow_integral",
        name=name,
        description=(
            "~25% de alunos Integrais + superlotação global (~110% da capacidade total da ONG, "
            "lotando 100% das salas e deixando ~9-10% na lista de espera) + viés cruzado M/F."
        ),
        filepath=str(fpath),
        seed=seed,
        total_students=n,
        has_integral=True,
        turmas_manha=km,
        turmas_tarde=kt,
        vagas_manha=vm,
        vagas_tarde=vt,
        cap_total_manha=cap_m,
        cap_total_tarde=cap_t,
        cap_total_global=cap_m + cap_t,
        global_occupancy_pct=round(100.0 * n / (cap_m + cap_t), 2),
        count_manha_m=m_manha,
        count_manha_f=f_manha,
        count_tarde_m=m_tarde,
        count_tarde_f=f_tarde,
        count_integral_m=m_int,
        count_integral_f=f_int,
        homonym_pairs=max(2, n // 100),
        noisy_cells=0,
        allow_capacity_deficit=True,
        expected_unallocated=expected_unalloc,
    )


def _build_f8_many_tiny_rooms_integral(n: int, out_dir: Path, seed: int) -> GeneratedInstanceSpec:
    """Família 8: ~30% Integrais + Muitas salas muito pequenas (~9-11 vagas/sala, até 4.644 salas)."""
    cfg_map = {
        200: (12, 9, 11, 9),          # 23 micro-salas de 9 vagas (Cap: 108 M + 99 T = 207, 96.6% ocup)
        500: (29, 9, 28, 9),          # 57 micro-salas de 9 vagas (Cap: 261 M + 252 T = 513, 97.5% ocup)
        1000: (53, 10, 49, 10),       # 102 micro-salas de 10 vagas (Cap: 530 M + 490 T = 1020, 98.0% ocup)
        2000: (103, 10, 101, 10),     # 204 micro-salas de 10 vagas (Cap: 1030 M + 1010 T = 2040, 98.0% ocup)
        10000: (499, 10, 521, 10),    # 1.020 micro-salas de 10 vagas (Cap: 4990 M + 5210 T = 10200, 98.0% ocup)
        50000: (2297, 11, 2347, 11),  # 4.644 micro-salas de 11 vagas (Cap: 25267 M + 25817 T = 51084, 97.9% ocup)
    }
    if n in cfg_map:
        km, vm, kt, vt = cfg_map[n]
    else:
        vm = vt = 10
        tot_rooms = max(8, math.ceil((n / 0.98) / vm))
        km = tot_rooms // 2
        kt = tot_rooms - km

    cap_m, cap_t = km * vm, kt * vt
    n_int = int(round(0.30 * n))
    rem_fixed = n - n_int
    n_fix_m = min(cap_m, int(round(rem_fixed * (cap_m / (cap_m + cap_t)))))
    n_fix_t = rem_fixed - n_fix_m
    if n_fix_t > cap_t:
        overflow_t = n_fix_t - cap_t
        n_fix_t -= overflow_t
        n_fix_m += overflow_t

    # Conflito modular e viés cruzado moderado (Manhã 68% F vs Tarde 66% M) em centenas/milhares de salas
    m_manha, f_manha = _modular_hard_split(n_fix_m, km, target_m_ratio=0.32)
    m_tarde, f_tarde = _modular_hard_split(n_fix_t, kt, target_m_ratio=0.66)
    m_int = (n_int // 2) + 1 if n_int >= 4 else n_int // 2
    f_int = n_int - m_int

    name = f"F8_many_tiny_rooms_integral_n{n}"
    fpath = out_dir / "F8_many_tiny_rooms_integral" / f"{name}.xlsx"

    return GeneratedInstanceSpec(
        family="F8_many_tiny_rooms_integral",
        name=name,
        description=(
            "~30% de alunos Integrais; pulverização extrema em muitas salas muito pequenas "
            "(oficinas/tutorias de 9 a 11 vagas/sala, chegando a 4.644 turmas em N=50.000) com "
            "ocupação ~98% e restos modulares coprimos."
        ),
        filepath=str(fpath),
        seed=seed,
        total_students=n,
        has_integral=True,
        turmas_manha=km,
        turmas_tarde=kt,
        vagas_manha=vm,
        vagas_tarde=vt,
        cap_total_manha=cap_m,
        cap_total_tarde=cap_t,
        cap_total_global=cap_m + cap_t,
        global_occupancy_pct=round(100.0 * n / (cap_m + cap_t), 2),
        count_manha_m=m_manha,
        count_manha_f=f_manha,
        count_tarde_m=m_tarde,
        count_tarde_f=f_tarde,
        count_integral_m=m_int,
        count_integral_f=f_int,
        homonym_pairs=max(2, min(250, n // 100)),
        noisy_cells=0,
    )


def _build_f9_few_huge_rooms_integral(n: int, out_dir: Path, seed: int) -> GeneratedInstanceSpec:
    """Família 9: ~35% Integrais + Poucas salas muito grandes / auditórios (2-4 por turno)."""
    cfg_map = {
        200: (2, 52, 2, 52),        # 4 salas grandes (Cap: 104 M + 104 T = 208, 96.2% ocup)
        500: (2, 130, 2, 128),      # 4 auditórios (Cap: 260 M + 256 T = 516, 96.9% ocup)
        1000: (2, 260, 3, 170),     # 5 auditórios assimétricos (Cap: 520 M + 510 T = 1030, 97.1% ocup)
        2000: (3, 345, 2, 505),     # 5 mega-auditórios (Cap: 1035 M + 1010 T = 2045, 97.8% ocup)
        10000: (3, 1720, 4, 1255),  # 7 mega-auditórios (Cap: 5160 M + 5020 T = 10180, 98.2% ocup)
        50000: (3, 8600, 4, 6280),  # 7 mega-auditórios gigantes (Cap: 25800 M + 25120 T = 50920, 98.2% ocup)
    }
    if n in cfg_map:
        km, vm, kt, vt = cfg_map[n]
    else:
        km, kt = 3, 4
        target_cap = math.ceil(n / 0.98)
        vm = math.ceil(0.50 * target_cap / km)
        vt = math.ceil((target_cap - km * vm) / kt)

    cap_m, cap_t = km * vm, kt * vt
    n_int = int(round(0.35 * n))
    rem_fixed = n - n_int
    n_fix_m = min(cap_m, int(round(rem_fixed * (cap_m / (cap_m + cap_t)))))
    n_fix_t = rem_fixed - n_fix_m
    if n_fix_t > cap_t:
        overflow_t = n_fix_t - cap_t
        n_fix_t -= overflow_t
        n_fix_m += overflow_t

    # Forte assimetria demográfica cruzada nos fixos (Manhã 74% F vs Tarde 72% M)
    f_manha = int(round(0.74 * n_fix_m))
    m_manha = n_fix_m - f_manha

    m_tarde = int(round(0.72 * n_fix_t))
    f_tarde = n_fix_t - m_tarde

    m_int = (n_int // 2) + 1 if n_int >= 4 else n_int // 2
    f_int = n_int - m_int

    name = f"F9_few_huge_rooms_integral_n{n}"
    fpath = out_dir / "F9_few_huge_rooms_integral" / f"{name}.xlsx"

    return GeneratedInstanceSpec(
        family="F9_few_huge_rooms_integral",
        name=name,
        description=(
            "~35% de alunos Integrais; concentração extrema em poucas salas muito grandes / "
            "auditórios (apenas 2 a 4 salas por turno, até 8.600 vagas/sala em N=50.000) com "
            "assimetria de capacidades M/T e inversão cruzada de gênero."
        ),
        filepath=str(fpath),
        seed=seed,
        total_students=n,
        has_integral=True,
        turmas_manha=km,
        turmas_tarde=kt,
        vagas_manha=vm,
        vagas_tarde=vt,
        cap_total_manha=cap_m,
        cap_total_tarde=cap_t,
        cap_total_global=cap_m + cap_t,
        global_occupancy_pct=round(100.0 * n / (cap_m + cap_t), 2),
        count_manha_m=m_manha,
        count_manha_f=f_manha,
        count_tarde_m=m_tarde,
        count_tarde_f=f_tarde,
        count_integral_m=m_int,
        count_integral_f=f_int,
        homonym_pairs=max(2, min(250, n // 100)),
        noisy_cells=0,
    )


FAMILY_BUILDERS = {
    "F1_modular_conflict": _build_f1_modular_conflict,
    "F2_gender_cross_integral": _build_f2_gender_cross_integral,
    "F3_bottleneck_integral": _build_f3_bottleneck_integral,
    "F4_extreme_minority_integral": _build_f4_extreme_minority_integral,
    "F5_noisy_realistic_integral": _build_f5_noisy_realistic_integral,
    "F6_shift_overflow_fixed": _build_f6_shift_overflow_fixed,
    "F7_global_overflow_integral": _build_f7_global_overflow_integral,
    "F8_many_tiny_rooms_integral": _build_f8_many_tiny_rooms_integral,
    "F9_few_huge_rooms_integral": _build_f9_few_huge_rooms_integral,
}


def _apply_treatable_noise(
    sexo: str,
    disp: str,
    nome: str,
    rng: random.Random,
) -> tuple[str, str, str]:
    """Injeta variações realistas de escrita 100% tratáveis pelo pre_process."""
    kind = rng.choice(("sexo_word", "sexo_case_space", "disp_no_accent", "disp_case_space", "name_space"))
    if kind == "sexo_word":
        sexo = rng.choice(("masculino", "Masculino", "MASC")) if sexo == "M" else rng.choice(("feminino", "Feminino", "FEM"))
    elif kind == "sexo_case_space":
        sexo = f" {sexo.lower()} " if rng.random() < 0.5 else f"  {sexo} "
    elif kind == "disp_no_accent":
        if disp == "Manhã":
            disp = rng.choice(("manha", "Manha", "MANHA"))
        elif disp == "Tarde":
            disp = rng.choice(("tarde", " TARDE"))
        else:
            disp = rng.choice(("integral", "INTEGRAL", "Ambos"))
    elif kind == "disp_case_space":
        disp = f" {disp.upper()} " if rng.random() < 0.5 else f" {disp.lower()}"
    elif kind == "name_space":
        nome = f"  {nome.replace(' ', '  ', 1)} "
    return nome, sexo, disp


def materialize_instance_excel(spec: GeneratedInstanceSpec) -> Path:
    """Materializa a planilha .xlsx com as abas 'Alunos' e 'Turmas' em streaming O(1) RAM."""
    _verify_spec_feasibility(spec)
    rng = random.Random(spec.seed)

    # 1. Monta lista base de perfis (sexo, disponibilidade)
    profiles: list[tuple[str, str]] = []
    profiles.extend([("M", "Manhã")] * spec.count_manha_m)
    profiles.extend([("F", "Manhã")] * spec.count_manha_f)
    profiles.extend([("M", "Tarde")] * spec.count_tarde_m)
    profiles.extend([("F", "Tarde")] * spec.count_tarde_f)
    profiles.extend([("M", "Integral")] * spec.count_integral_m)
    profiles.extend([("F", "Integral")] * spec.count_integral_f)
    rng.shuffle(profiles)

    # 2. Gera nomes únicos por gênero e injeta pares homônimos controlados
    used_names: set[str] = set()
    m_names_history: list[str] = []
    f_names_history: list[str] = []

    homonym_indices = set(
        rng.sample(range(len(profiles)), k=min(spec.homonym_pairs, max(0, len(profiles) // 4)))
    )
    noisy_indices = set(
        rng.sample(range(len(profiles)), k=min(spec.noisy_cells, len(profiles)))
    )

    student_rows: list[tuple[str, str, str]] = []
    for idx, (sexo, disp) in enumerate(profiles):
        history = m_names_history if sexo == "M" else f_names_history
        if idx in homonym_indices and history:
            nome = rng.choice(history)
        else:
            nome = _generate_full_name(sexo, rng, used_names)
            history.append(nome)

        s_out, d_out, n_out = sexo, disp, nome
        if idx in noisy_indices:
            n_out, s_out, d_out = _apply_treatable_noise(s_out, d_out, n_out, rng)

        student_rows.append((n_out, s_out, d_out))

    # Se homonym_indices caiu muito no início (quando history ainda estava vazia), garante homônimos no fim
    actual_dups = len(student_rows) - len({r[0].strip() for r in student_rows})
    if actual_dups < spec.homonym_pairs and len(student_rows) >= 20:
        missing = spec.homonym_pairs - actual_dups
        for offset in range(missing):
            target_idx = len(student_rows) - 1 - offset
            n_cur, s_cur, d_cur = student_rows[target_idx]
            history = m_names_history if s_cur.strip().upper().startswith("M") else f_names_history
            if len(history) >= 2:
                dup_name = history[offset % len(history)]
                student_rows[target_idx] = (dup_name, s_cur, d_cur)

    # 3. Cria Workbook em modo write_only p/ altíssima performance em N=50.000
    out_path = Path(spec.filepath)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook(write_only=True)
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    center_align = Alignment(horizontal="center", vertical="center")
    left_align = Alignment(horizontal="left", vertical="center")

    def _hdr_cell(ws: openpyxl.worksheet._write_only.WriteOnlyWorksheet, val: str, align: Alignment) -> WriteOnlyCell:
        c = WriteOnlyCell(ws, value=val)
        c.font = header_font
        c.fill = header_fill
        c.alignment = align
        return c

    # Aba 1: Alunos
    ws_alunos = wb.create_sheet(title="Alunos")
    ws_alunos.column_dimensions["A"].width = 42
    ws_alunos.column_dimensions["B"].width = 14
    ws_alunos.column_dimensions["C"].width = 20
    ws_alunos.append(
        [
            _hdr_cell(ws_alunos, "Nome", left_align),
            _hdr_cell(ws_alunos, "Sexo", center_align),
            _hdr_cell(ws_alunos, "Disponibilidade", center_align),
        ]
    )
    for row in student_rows:
        ws_alunos.append(list(row))

    # Aba 2: Turmas
    ws_turmas = wb.create_sheet(title="Turmas")
    ws_turmas.column_dimensions["A"].width = 20
    ws_turmas.column_dimensions["B"].width = 15
    ws_turmas.append(
        [
            _hdr_cell(ws_turmas, "Recursos", left_align),
            _hdr_cell(ws_turmas, "Quantidade", center_align),
        ]
    )
    ws_turmas.append(["turmas_manha", spec.turmas_manha])
    ws_turmas.append(["turmas_tarde", spec.turmas_tarde])
    ws_turmas.append(["vagas_manha", spec.vagas_manha])
    ws_turmas.append(["vagas_tarde", spec.vagas_tarde])

    wb.save(out_path)
    wb.close()
    return out_path


def _write_catalog_docs(specs: list[GeneratedInstanceSpec], output_dir: Path) -> None:
    """Gera manifesto JSON e catálogo Markdown descrevendo todas as instâncias."""
    json_path = output_dir / "catalogo_instancias.json"
    json_path.write_text(
        json.dumps([asdict(s) for s in specs], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    md_lines = [
        "# Catálogo de Instâncias Difíceis Geradas — Desafio UniSoma 2026",
        "",
        "Conjunto de benchmarks sintéticos projetados para estressar o balanceamento "
        "de quantidade e gênero, a decisão de horário de alunos **Integrais**, listas "
        "de espera e regimes extremos de infraestrutura (`200` a `50.000` alunos).",
        "",
        "| Instância | Família | Alunos | Integrais | Turmas (M/T) | Vagas/Sala (M/T) | Demanda/Cap. | Mín. s/ Turma | Flags Recomendadas |",
        "| :--- | :--- | ---: | ---: | :---: | :---: | ---: | ---: | :--- |",
    ]

    for s in specs:
        n_int = s.count_integral_m + s.count_integral_f
        pct_int = 100.0 * n_int / s.total_students if s.total_students else 0.0
        flags: list[str] = []
        if s.has_integral:
            flags.append("`--allow-integral`")
        if s.allow_capacity_deficit:
            flags.append("`--allow-unallocated`")
        flag_str = " ".join(flags) if flags else "Padrão"
        md_lines.append(
            f"| `{s.name}.xlsx` | `{s.family}` | {s.total_students} | "
            f"{n_int} ({pct_int:.0f}%) | {s.turmas_manha} / {s.turmas_tarde} | "
            f"{s.vagas_manha} / {s.vagas_tarde} | {s.global_occupancy_pct:.1f}% | "
            f"{s.expected_unallocated} | {flag_str} |"
        )

    md_lines.extend(
        [
            "",
            "## Descrição das Famílias",
            "",
            "1. **`F1_modular_conflict`**: Sem alunos integrais; números ímpares/coprimos de salas, ocupação no teto máximo (~98-99.8%) e conflito modular ($r_M + r_F > |K_s|$).",
            "2. **`F2_gender_cross_integral`**: ~30% de alunos `Integral`; Manhã fixa fortemente feminina (78% F) e Tarde fixa fortemente masculina (78% M), acoplando os dois turnos.",
            "3. **`F3_bottleneck_integral`**: ~40% de alunos `Integral`; gargalo severo de vagas na Manhã (~93% já ocupada por alunos fixos) e ocupação global ~98%.",
            "4. **`F4_extreme_minority_integral`**: ~25% de alunos `Integral`; escassez extrema do gênero minoritário (~18% M / ~82% F) em quantidades primas de turmas.",
            "5. **`F5_noisy_realistic_integral`**: ~20% de alunos `Integral` + ~12% de ruído tratável de escrita/case + ~5% de homônimos + folga de salas na Manhã (permite soluções com salas vazias).",
            "6. **`F6_shift_overflow_fixed`**: Sem alunos `Integral`; excesso de demanda localizado na Manhã (~115% das vagas da Manhã, deixando alunos na lista de espera) enquanto sobram vagas ociosas incompatíveis na Tarde.",
            "7. **`F7_global_overflow_integral`**: ~25% de alunos `Integral`; superlotação global (~110% da capacidade total da ONG, lotando 100% das salas e deixando ~9-10% dos inscritos sem turma) combinada com inversão demográfica cruzada.",
            "8. **`F8_many_tiny_rooms_integral`**: ~30% de alunos `Integral`; **muitas salas muito pequenas** (micro-turmas/oficinas de 9 a 11 vagas/sala, escalando até **4.644 salas** em `N=50000`) com ocupação ~98% e contagens primas.",
            "9. **`F9_few_huge_rooms_integral`**: ~35% de alunos `Integral`; **poucas salas muito grandes** (auditórios/aulões com apenas 2 a 4 salas por turno e até **8.600 vagas/sala** em `N=50000`), capacidades assimétricas e viés cruzado de gênero.",
            "",
        ]
    )

    (output_dir / "README.md").write_text("\n".join(md_lines), encoding="utf-8")


def generate_benchmark_suite(
    output_dir: str | Path = PROJECT_ROOT / "instances" / "generated",
    families: Optional[list[str]] = None,
    sizes: tuple[int, ...] = BENCHMARK_SIZES,
    base_seed: int = 2026,
) -> list[GeneratedInstanceSpec]:
    """Gera todas as famílias e tamanhos solicitados, salvando .xlsx e catálogo."""
    out_root = Path(output_dir).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    selected_families = families if families else list(FAMILY_BUILDERS.keys())
    generated_specs: list[GeneratedInstanceSpec] = []

    for f_idx, fam_key in enumerate(selected_families, start=1):
        if fam_key not in FAMILY_BUILDERS:
            raise ValueError(
                f"Família desconhecida: '{fam_key}'. Opções: {list(FAMILY_BUILDERS.keys())}"
            )
        builder = FAMILY_BUILDERS[fam_key]
        for s_idx, n_students in enumerate(sizes, start=1):
            instance_seed = base_seed + f_idx * 1000 + n_students + s_idx
            spec = builder(n_students, out_root, instance_seed)
            materialize_instance_excel(spec)
            generated_specs.append(spec)

    _write_catalog_docs(generated_specs, out_root)
    return generated_specs


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gerador de Famílias de Instâncias Difíceis — Desafio UniSoma 2026"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "instances" / "generated",
        help="Diretório raiz onde as famílias de instâncias serão salvas.",
    )
    parser.add_argument(
        "--families",
        nargs="+",
        choices=list(FAMILY_BUILDERS.keys()),
        default=None,
        help="Subconjunto de famílias a gerar (padrão: todas as 9 famílias).",
    )
    parser.add_argument(
        "--sizes",
        nargs="+",
        type=int,
        default=list(BENCHMARK_SIZES),
        help="Tamanhos de alunos por instância (padrão: 200 500 1000 2000 10000 50000).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=2026,
        help="Semente pseudoaleatória base para reprodutibilidade (padrão: 2026).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    args = _parse_args(argv)
    specs = generate_benchmark_suite(
        output_dir=args.output_dir,
        families=args.families,
        sizes=tuple(args.sizes),
        base_seed=args.seed,
    )

    print("=" * 112)
    print(f" GERADOR DE INSTÂNCIAS CONCLUÍDO — {len(specs)} instâncias criadas em: {args.output_dir}")
    print("=" * 112)
    print(
        f"  {'Instância':<40} | {'Alunos':>6} | {'Integrais':>9} | "
        f"{'Turmas M/T':>11} | {'Vagas M/T':>11} | {'Dem/Cap':>7} | {'S/Turma':>7}"
    )
    print("  " + "-" * 108)
    for sp in specs:
        n_int = sp.count_integral_m + sp.count_integral_f
        print(
            f"  {sp.name:<40} | {sp.total_students:>6} | {n_int:>9} | "
            f"{sp.turmas_manha:>5}/{sp.turmas_tarde:<5} | "
            f"{sp.vagas_manha:>5}/{sp.vagas_tarde:<5} | {sp.global_occupancy_pct:>6.1f}% | "
            f"{sp.expected_unallocated:>7}"
        )
    print("=" * 112)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


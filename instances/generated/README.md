# Catálogo de Instâncias Difíceis Geradas — Desafio UniSoma 2026

Conjunto de benchmarks sintéticos projetados para estressar o balanceamento de quantidade e gênero, a decisão de horário de alunos **Integrais**, listas de espera e regimes extremos de infraestrutura (`200` a `50.000` alunos).

| Instância | Família | Alunos | Integrais | Turmas (M/T) | Vagas/Sala (M/T) | Demanda/Cap. | Mín. s/ Turma | Flags Recomendadas |
| :--- | :--- | ---: | ---: | :---: | :---: | ---: | ---: | :--- |
| `F1_modular_conflict_n200.xlsx` | `F1_modular_conflict` | 200 | 0 (0%) | 3 / 5 | 25 / 26 | 97.6% | 0 | Padrão |
| `F1_modular_conflict_n500.xlsx` | `F1_modular_conflict` | 500 | 0 (0%) | 7 / 9 | 32 / 31 | 99.4% | 0 | Padrão |
| `F1_modular_conflict_n1000.xlsx` | `F1_modular_conflict` | 1000 | 0 (0%) | 13 / 19 | 32 / 31 | 99.5% | 0 | Padrão |
| `F1_modular_conflict_n2000.xlsx` | `F1_modular_conflict` | 2000 | 0 (0%) | 29 / 37 | 31 / 30 | 99.5% | 0 | Padrão |
| `F1_modular_conflict_n10000.xlsx` | `F1_modular_conflict` | 10000 | 0 (0%) | 149 / 179 | 31 / 31 | 98.3% | 0 | Padrão |
| `F1_modular_conflict_n50000.xlsx` | `F1_modular_conflict` | 50000 | 0 (0%) | 743 / 887 | 31 / 31 | 99.0% | 0 | Padrão |
| `F2_gender_cross_integral_n200.xlsx` | `F2_gender_cross_integral` | 200 | 60 (30%) | 4 / 5 | 24 / 24 | 92.6% | 0 | `--allow-integral` |
| `F2_gender_cross_integral_n500.xlsx` | `F2_gender_cross_integral` | 500 | 150 (30%) | 8 / 9 | 31 / 31 | 94.9% | 0 | `--allow-integral` |
| `F2_gender_cross_integral_n1000.xlsx` | `F2_gender_cross_integral` | 1000 | 300 (30%) | 16 / 17 | 32 / 32 | 94.7% | 0 | `--allow-integral` |
| `F2_gender_cross_integral_n2000.xlsx` | `F2_gender_cross_integral` | 2000 | 600 (30%) | 31 / 33 | 33 / 33 | 94.7% | 0 | `--allow-integral` |
| `F2_gender_cross_integral_n10000.xlsx` | `F2_gender_cross_integral` | 10000 | 3000 (30%) | 157 / 163 | 33 / 33 | 94.7% | 0 | `--allow-integral` |
| `F2_gender_cross_integral_n50000.xlsx` | `F2_gender_cross_integral` | 50000 | 15000 (30%) | 787 / 811 | 33 / 33 | 94.8% | 0 | `--allow-integral` |
| `F3_bottleneck_integral_n200.xlsx` | `F3_bottleneck_integral` | 200 | 80 (40%) | 4 / 4 | 23 / 28 | 98.0% | 0 | `--allow-integral` |
| `F3_bottleneck_integral_n500.xlsx` | `F3_bottleneck_integral` | 500 | 200 (40%) | 9 / 9 | 25 / 32 | 97.5% | 0 | `--allow-integral` |
| `F3_bottleneck_integral_n1000.xlsx` | `F3_bottleneck_integral` | 1000 | 400 (40%) | 17 / 19 | 25 / 31 | 98.6% | 0 | `--allow-integral` |
| `F3_bottleneck_integral_n2000.xlsx` | `F3_bottleneck_integral` | 2000 | 800 (40%) | 33 / 37 | 26 / 32 | 97.9% | 0 | `--allow-integral` |
| `F3_bottleneck_integral_n10000.xlsx` | `F3_bottleneck_integral` | 10000 | 4000 (40%) | 167 / 181 | 26 / 32 | 98.7% | 0 | `--allow-integral` |
| `F3_bottleneck_integral_n50000.xlsx` | `F3_bottleneck_integral` | 50000 | 20000 (40%) | 829 / 911 | 26 / 32 | 98.6% | 0 | `--allow-integral` |
| `F4_extreme_minority_integral_n200.xlsx` | `F4_extreme_minority_integral` | 200 | 50 (25%) | 5 / 3 | 26 / 26 | 96.2% | 0 | `--allow-integral` |
| `F4_extreme_minority_integral_n500.xlsx` | `F4_extreme_minority_integral` | 500 | 125 (25%) | 11 / 7 | 29 / 29 | 95.8% | 0 | `--allow-integral` |
| `F4_extreme_minority_integral_n1000.xlsx` | `F4_extreme_minority_integral` | 1000 | 250 (25%) | 19 / 15 | 31 / 31 | 94.9% | 0 | `--allow-integral` |
| `F4_extreme_minority_integral_n2000.xlsx` | `F4_extreme_minority_integral` | 2000 | 500 (25%) | 37 / 31 | 31 / 31 | 94.9% | 0 | `--allow-integral` |
| `F4_extreme_minority_integral_n10000.xlsx` | `F4_extreme_minority_integral` | 10000 | 2500 (25%) | 181 / 157 | 31 / 31 | 95.4% | 0 | `--allow-integral` |
| `F4_extreme_minority_integral_n50000.xlsx` | `F4_extreme_minority_integral` | 50000 | 12500 (25%) | 907 / 787 | 31 / 31 | 95.2% | 0 | `--allow-integral` |
| `F5_noisy_realistic_integral_n200.xlsx` | `F5_noisy_realistic_integral` | 200 | 40 (20%) | 5 / 3 | 30 / 30 | 83.3% | 0 | `--allow-integral` |
| `F5_noisy_realistic_integral_n500.xlsx` | `F5_noisy_realistic_integral` | 500 | 100 (20%) | 11 / 8 | 32 / 30 | 84.5% | 0 | `--allow-integral` |
| `F5_noisy_realistic_integral_n1000.xlsx` | `F5_noisy_realistic_integral` | 1000 | 200 (20%) | 22 / 16 | 32 / 30 | 84.5% | 0 | `--allow-integral` |
| `F5_noisy_realistic_integral_n2000.xlsx` | `F5_noisy_realistic_integral` | 2000 | 400 (20%) | 43 / 31 | 32 / 30 | 86.7% | 0 | `--allow-integral` |
| `F5_noisy_realistic_integral_n10000.xlsx` | `F5_noisy_realistic_integral` | 10000 | 2000 (20%) | 211 / 151 | 32 / 30 | 88.6% | 0 | `--allow-integral` |
| `F5_noisy_realistic_integral_n50000.xlsx` | `F5_noisy_realistic_integral` | 50000 | 10000 (20%) | 1051 / 751 | 32 / 30 | 89.0% | 0 | `--allow-integral` |
| `F6_shift_overflow_fixed_n200.xlsx` | `F6_shift_overflow_fixed` | 200 | 0 (0%) | 3 / 4 | 28 / 31 | 96.2% | 14 | `--allow-unallocated` |
| `F6_shift_overflow_fixed_n500.xlsx` | `F6_shift_overflow_fixed` | 500 | 0 (0%) | 7 / 9 | 29 / 35 | 96.5% | 32 | `--allow-unallocated` |
| `F6_shift_overflow_fixed_n1000.xlsx` | `F6_shift_overflow_fixed` | 1000 | 0 (0%) | 13 / 19 | 30 / 34 | 96.5% | 60 | `--allow-unallocated` |
| `F6_shift_overflow_fixed_n2000.xlsx` | `F6_shift_overflow_fixed` | 2000 | 0 (0%) | 27 / 37 | 30 / 35 | 95.0% | 120 | `--allow-unallocated` |
| `F6_shift_overflow_fixed_n10000.xlsx` | `F6_shift_overflow_fixed` | 10000 | 0 (0%) | 137 / 181 | 30 / 35 | 95.7% | 600 | `--allow-unallocated` |
| `F6_shift_overflow_fixed_n50000.xlsx` | `F6_shift_overflow_fixed` | 50000 | 0 (0%) | 683 / 907 | 30 / 35 | 95.7% | 3100 | `--allow-unallocated` |
| `F7_global_overflow_integral_n200.xlsx` | `F7_global_overflow_integral` | 200 | 50 (25%) | 3 / 4 | 26 / 26 | 109.9% | 18 | `--allow-integral` `--allow-unallocated` |
| `F7_global_overflow_integral_n500.xlsx` | `F7_global_overflow_integral` | 500 | 125 (25%) | 7 / 9 | 26 / 30 | 110.6% | 48 | `--allow-integral` `--allow-unallocated` |
| `F7_global_overflow_integral_n1000.xlsx` | `F7_global_overflow_integral` | 1000 | 250 (25%) | 13 / 18 | 28 / 30 | 110.6% | 96 | `--allow-integral` `--allow-unallocated` |
| `F7_global_overflow_integral_n2000.xlsx` | `F7_global_overflow_integral` | 2000 | 500 (25%) | 27 / 35 | 28 / 30 | 110.7% | 194 | `--allow-integral` `--allow-unallocated` |
| `F7_global_overflow_integral_n10000.xlsx` | `F7_global_overflow_integral` | 10000 | 2500 (25%) | 137 / 173 | 28 / 30 | 110.8% | 974 | `--allow-integral` `--allow-unallocated` |
| `F7_global_overflow_integral_n50000.xlsx` | `F7_global_overflow_integral` | 50000 | 12500 (25%) | 683 / 863 | 28 / 30 | 111.1% | 4986 | `--allow-integral` `--allow-unallocated` |
| `F8_many_tiny_rooms_integral_n200.xlsx` | `F8_many_tiny_rooms_integral` | 200 | 60 (30%) | 12 / 11 | 9 / 9 | 96.6% | 0 | `--allow-integral` |
| `F8_many_tiny_rooms_integral_n500.xlsx` | `F8_many_tiny_rooms_integral` | 500 | 150 (30%) | 29 / 28 | 9 / 9 | 97.5% | 0 | `--allow-integral` |
| `F8_many_tiny_rooms_integral_n1000.xlsx` | `F8_many_tiny_rooms_integral` | 1000 | 300 (30%) | 53 / 49 | 10 / 10 | 98.0% | 0 | `--allow-integral` |
| `F8_many_tiny_rooms_integral_n2000.xlsx` | `F8_many_tiny_rooms_integral` | 2000 | 600 (30%) | 103 / 101 | 10 / 10 | 98.0% | 0 | `--allow-integral` |
| `F8_many_tiny_rooms_integral_n10000.xlsx` | `F8_many_tiny_rooms_integral` | 10000 | 3000 (30%) | 499 / 521 | 10 / 10 | 98.0% | 0 | `--allow-integral` |
| `F8_many_tiny_rooms_integral_n50000.xlsx` | `F8_many_tiny_rooms_integral` | 50000 | 15000 (30%) | 2297 / 2347 | 11 / 11 | 97.9% | 0 | `--allow-integral` |
| `F9_few_huge_rooms_integral_n200.xlsx` | `F9_few_huge_rooms_integral` | 200 | 70 (35%) | 2 / 2 | 52 / 52 | 96.2% | 0 | `--allow-integral` |
| `F9_few_huge_rooms_integral_n500.xlsx` | `F9_few_huge_rooms_integral` | 500 | 175 (35%) | 2 / 2 | 130 / 128 | 96.9% | 0 | `--allow-integral` |
| `F9_few_huge_rooms_integral_n1000.xlsx` | `F9_few_huge_rooms_integral` | 1000 | 350 (35%) | 2 / 3 | 260 / 170 | 97.1% | 0 | `--allow-integral` |
| `F9_few_huge_rooms_integral_n2000.xlsx` | `F9_few_huge_rooms_integral` | 2000 | 700 (35%) | 3 / 2 | 345 / 505 | 97.8% | 0 | `--allow-integral` |
| `F9_few_huge_rooms_integral_n10000.xlsx` | `F9_few_huge_rooms_integral` | 10000 | 3500 (35%) | 3 / 4 | 1720 / 1255 | 98.2% | 0 | `--allow-integral` |
| `F9_few_huge_rooms_integral_n50000.xlsx` | `F9_few_huge_rooms_integral` | 50000 | 17500 (35%) | 3 / 4 | 8600 / 6280 | 98.2% | 0 | `--allow-integral` |

## Descrição das Famílias

1. **`F1_modular_conflict`**: Sem alunos integrais; números ímpares/coprimos de salas, ocupação no teto máximo (~98-99.8%) e conflito modular ($r_M + r_F > |K_s|$).
2. **`F2_gender_cross_integral`**: ~30% de alunos `Integral`; Manhã fixa fortemente feminina (78% F) e Tarde fixa fortemente masculina (78% M), acoplando os dois turnos.
3. **`F3_bottleneck_integral`**: ~40% de alunos `Integral`; gargalo severo de vagas na Manhã (~93% já ocupada por alunos fixos) e ocupação global ~98%.
4. **`F4_extreme_minority_integral`**: ~25% de alunos `Integral`; escassez extrema do gênero minoritário (~18% M / ~82% F) em quantidades primas de turmas.
5. **`F5_noisy_realistic_integral`**: ~20% de alunos `Integral` + ~12% de ruído tratável de escrita/case + ~5% de homônimos + folga de salas na Manhã (permite soluções com salas vazias).
6. **`F6_shift_overflow_fixed`**: Sem alunos `Integral`; excesso de demanda localizado na Manhã (~115% das vagas da Manhã, deixando alunos na lista de espera) enquanto sobram vagas ociosas incompatíveis na Tarde.
7. **`F7_global_overflow_integral`**: ~25% de alunos `Integral`; superlotação global (~110% da capacidade total da ONG, lotando 100% das salas e deixando ~9-10% dos inscritos sem turma) combinada com inversão demográfica cruzada.
8. **`F8_many_tiny_rooms_integral`**: ~30% de alunos `Integral`; **muitas salas muito pequenas** (micro-turmas/oficinas de 9 a 11 vagas/sala, escalando até **4.644 salas** em `N=50000`) com ocupação ~98% e contagens primas.
9. **`F9_few_huge_rooms_integral`**: ~35% de alunos `Integral`; **poucas salas muito grandes** (auditórios/aulões com apenas 2 a 4 salas por turno e até **8.600 vagas/sala** em `N=50000`), capacidades assimétricas e viés cruzado de gênero.

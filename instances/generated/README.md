# Catálogo de Instâncias Difíceis Geradas — Desafio UniSoma 2026

Conjunto de benchmarks sintéticos projetados para estressar o balanceamento de quantidade e gênero e a decisão de horário de alunos **Integrais**.

| Instância | Família | Alunos | Integrais | Turmas (M/T) | Vagas/Sala (M/T) | Demanda/Cap. | Mín. s/ Turma | Flags Recomendadas |
| :--- | :--- | ---: | ---: | :---: | :---: | ---: | ---: | :--- |
| `F1_modular_conflict_n200.xlsx` | `F1_modular_conflict` | 200 | 0 (0%) | 3 / 5 | 25 / 26 | 97.6% | 0 | Padrão |
| `F1_modular_conflict_n500.xlsx` | `F1_modular_conflict` | 500 | 0 (0%) | 7 / 9 | 32 / 31 | 99.4% | 0 | Padrão |
| `F1_modular_conflict_n1000.xlsx` | `F1_modular_conflict` | 1000 | 0 (0%) | 13 / 19 | 32 / 31 | 99.5% | 0 | Padrão |
| `F1_modular_conflict_n2000.xlsx` | `F1_modular_conflict` | 2000 | 0 (0%) | 29 / 37 | 31 / 30 | 99.5% | 0 | Padrão |
| `F2_gender_cross_integral_n200.xlsx` | `F2_gender_cross_integral` | 200 | 60 (30%) | 4 / 5 | 24 / 24 | 92.6% | 0 | `--allow-integral` |
| `F2_gender_cross_integral_n500.xlsx` | `F2_gender_cross_integral` | 500 | 150 (30%) | 8 / 9 | 31 / 31 | 94.9% | 0 | `--allow-integral` |
| `F2_gender_cross_integral_n1000.xlsx` | `F2_gender_cross_integral` | 1000 | 300 (30%) | 16 / 17 | 32 / 32 | 94.7% | 0 | `--allow-integral` |
| `F2_gender_cross_integral_n2000.xlsx` | `F2_gender_cross_integral` | 2000 | 600 (30%) | 31 / 33 | 33 / 33 | 94.7% | 0 | `--allow-integral` |
| `F3_bottleneck_integral_n200.xlsx` | `F3_bottleneck_integral` | 200 | 80 (40%) | 4 / 4 | 23 / 28 | 98.0% | 0 | `--allow-integral` |
| `F3_bottleneck_integral_n500.xlsx` | `F3_bottleneck_integral` | 500 | 200 (40%) | 9 / 9 | 25 / 32 | 97.5% | 0 | `--allow-integral` |
| `F3_bottleneck_integral_n1000.xlsx` | `F3_bottleneck_integral` | 1000 | 400 (40%) | 17 / 19 | 25 / 31 | 98.6% | 0 | `--allow-integral` |
| `F3_bottleneck_integral_n2000.xlsx` | `F3_bottleneck_integral` | 2000 | 800 (40%) | 33 / 37 | 26 / 32 | 97.9% | 0 | `--allow-integral` |
| `F4_extreme_minority_integral_n200.xlsx` | `F4_extreme_minority_integral` | 200 | 50 (25%) | 5 / 3 | 26 / 26 | 96.2% | 0 | `--allow-integral` |
| `F4_extreme_minority_integral_n500.xlsx` | `F4_extreme_minority_integral` | 500 | 125 (25%) | 11 / 7 | 29 / 29 | 95.8% | 0 | `--allow-integral` |
| `F4_extreme_minority_integral_n1000.xlsx` | `F4_extreme_minority_integral` | 1000 | 250 (25%) | 19 / 15 | 31 / 31 | 94.9% | 0 | `--allow-integral` |
| `F4_extreme_minority_integral_n2000.xlsx` | `F4_extreme_minority_integral` | 2000 | 500 (25%) | 37 / 31 | 31 / 31 | 94.9% | 0 | `--allow-integral` |
| `F5_noisy_realistic_integral_n200.xlsx` | `F5_noisy_realistic_integral` | 200 | 40 (20%) | 5 / 3 | 30 / 30 | 83.3% | 0 | `--allow-integral` |
| `F5_noisy_realistic_integral_n500.xlsx` | `F5_noisy_realistic_integral` | 500 | 100 (20%) | 11 / 8 | 32 / 30 | 84.5% | 0 | `--allow-integral` |
| `F5_noisy_realistic_integral_n1000.xlsx` | `F5_noisy_realistic_integral` | 1000 | 200 (20%) | 22 / 16 | 32 / 30 | 84.5% | 0 | `--allow-integral` |
| `F5_noisy_realistic_integral_n2000.xlsx` | `F5_noisy_realistic_integral` | 2000 | 400 (20%) | 43 / 31 | 32 / 30 | 86.7% | 0 | `--allow-integral` |
| `F6_shift_overflow_fixed_n200.xlsx` | `F6_shift_overflow_fixed` | 200 | 0 (0%) | 3 / 4 | 28 / 31 | 96.2% | 14 | `--allow-unallocated` |
| `F6_shift_overflow_fixed_n500.xlsx` | `F6_shift_overflow_fixed` | 500 | 0 (0%) | 7 / 9 | 29 / 35 | 96.5% | 32 | `--allow-unallocated` |
| `F6_shift_overflow_fixed_n1000.xlsx` | `F6_shift_overflow_fixed` | 1000 | 0 (0%) | 13 / 19 | 30 / 34 | 96.5% | 60 | `--allow-unallocated` |
| `F6_shift_overflow_fixed_n2000.xlsx` | `F6_shift_overflow_fixed` | 2000 | 0 (0%) | 27 / 37 | 30 / 35 | 95.0% | 120 | `--allow-unallocated` |
| `F7_global_overflow_integral_n200.xlsx` | `F7_global_overflow_integral` | 200 | 50 (25%) | 3 / 4 | 26 / 26 | 109.9% | 18 | `--allow-integral` `--allow-unallocated` |
| `F7_global_overflow_integral_n500.xlsx` | `F7_global_overflow_integral` | 500 | 125 (25%) | 7 / 9 | 26 / 30 | 110.6% | 48 | `--allow-integral` `--allow-unallocated` |
| `F7_global_overflow_integral_n1000.xlsx` | `F7_global_overflow_integral` | 1000 | 250 (25%) | 13 / 18 | 28 / 30 | 110.6% | 96 | `--allow-integral` `--allow-unallocated` |
| `F7_global_overflow_integral_n2000.xlsx` | `F7_global_overflow_integral` | 2000 | 500 (25%) | 27 / 35 | 28 / 30 | 110.7% | 194 | `--allow-integral` `--allow-unallocated` |

## Descrição das Famílias

1. **`F1_modular_conflict`**: Sem alunos integrais; números ímpares/coprimos de salas, ocupação no teto máximo (~98-99.8%) e conflito modular ($r_M + r_F > |K_s|$).
2. **`F2_gender_cross_integral`**: ~30% de alunos `Integral`; Manhã fixa fortemente feminina (78% F) e Tarde fixa fortemente masculina (78% M), acoplando os dois turnos.
3. **`F3_bottleneck_integral`**: ~40% de alunos `Integral`; gargalo severo de vagas na Manhã (~93% já ocupada por alunos fixos) e ocupação global ~98%.
4. **`F4_extreme_minority_integral`**: ~25% de alunos `Integral`; escassez extrema do gênero minoritário (~18% M / ~82% F) em quantidades primas de turmas.
5. **`F5_noisy_realistic_integral`**: ~20% de alunos `Integral` + ~12% de ruído tratável de escrita/case + ~5% de homônimos + folga de salas na Manhã (permite soluções com salas vazias).
6. **`F6_shift_overflow_fixed`**: Sem alunos `Integral`; excesso de demanda localizado na Manhã (~115% das vagas da Manhã, deixando alunos na lista de espera) enquanto sobram vagas ociosas incompatíveis na Tarde.
7. **`F7_global_overflow_integral`**: ~25% de alunos `Integral`; superlotação global (~110% da capacidade total da ONG, lotando 100% das salas e deixando ~9-10% dos inscritos sem turma) combinada com inversão demográfica cruzada.

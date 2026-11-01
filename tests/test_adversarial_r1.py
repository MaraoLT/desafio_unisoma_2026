"""Adversarial stress test suite for Milestone 1 (R1: Correção do botão 'Aplicar Correção').

Executed by Challenger 1.
Validates:
1. Permutations, anagrams, weird casing, unicode accents, extreme whitespace.
2. Atypical header structures, column reordering, unmapped column preservation, ragged rows.
3. Empty cells, corrupt/impeditivo cells, empty sheets, missing sheets.
4. Repeated clicks (idempotency), undo stack length invariances.
5. Undo/Redo bidirectional consistency (deep comparison).
6. Out-of-bounds, negative, duplicate target row inputs.
7. End-to-end pipeline: Sanitize -> Save -> Reload -> Solver Execution.
"""

from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

from src.app.server import AppBackend


class TestAdversarialR1(unittest.TestCase):
    """Stress tests and edge case verifications for R1."""

    def _create_backend(
        self, alunos_rows: list[list[str]], turmas_rows: list[list[str]] | None = None
    ) -> AppBackend:
        backend = AppBackend()
        backend.sheets_data = {
            "Alunos": [list(r) for r in alunos_rows],
            "Turmas": turmas_rows
            or [
                ["Recurso", "Quantidade"],
                ["turmas_manha", "2"],
                ["turmas_tarde", "2"],
                ["vagas_manha", "30"],
                ["vagas_tarde", "30"],
            ],
        }
        backend.active_sheet = "Alunos"
        backend.validate_data()
        return backend

    def test_permutations_casing_accents_whitespace(self) -> None:
        """Adversarial test on anagrams, unusual casing, accents and mixed whitespace."""
        alunos = [
            ["Nome", "Sexo", "Disponibilidade"],
            # Manha permutations & weird casing
            ["  João   Silva  ", "mAsCuLiNo", "mahna"],         # row 2
            ["Maria   Santos\t", "FEM", "manah"],              # row 3
            ["\tLucas \n Souza  ", "homem", "namha"],          # row 4
            ["Carla   Dias", "mulher", "anham"],               # row 5
            ["Pedro Rocha", "menino", "mnaha"],                # row 6
            ["Ana Paula", "menina", "mhana"],                  # row 7
            ["Beatriz Lima", "  FEMININO  ", "MaHnA"],         # row 8
            ["Bruno Costa", "  M  ", "MÁHNA"],                 # row 9
            ["Camila Castro", "  F  ", "matutino"],            # row 10
            # Tarde permutations & weird casing
            ["Daniel Alves", "masculino", "tadre"],            # row 11
            ["Elisa Martins", "feminino", "tader"],            # row 12
            ["Felipe Gomes", "homem", "trdae"],                # row 13
            ["Gabriela Neves", "mulher", "tared"],             # row 14
            ["Hugo Ribeiro", "masc", "treda"],                 # row 15
            ["Isabela Pinto", "fem", "TaDrE"],                 # row 16
            ["Jorge Mendes", "M", "traed"],                    # row 17: anagram of tarde
            ["Larissa Faria", "F", "vespertino"],              # row 18
            # Integral permutations & synonyms
            ["Marcos Freitas", "masculino", "itnegral"],       # row 19
            ["Natália Ramos", "feminino", "inetgral"],         # row 20
            ["Otávio Barros", "homem", "itengral"],            # row 21
            ["Patrícia Cunha", "mulher", "ItNeGrAl"],          # row 22
            ["Rafael Cardoso", "masc", "livre"],               # row 23
            ["Sabrina Moreira", "fem", "ambos"],               # row 24
        ]

        b = self._create_backend(alunos)
        initial_tratadas = b.last_summary["incons_counts"]["tratadas"]
        self.assertEqual(initial_tratadas, len(alunos) - 1, "Todas as 23 linhas de dados devem ter correções tratáveis.")

        # Batch sanitize
        res = b.resolve_issue("accept_sanitize", "sanitize", [])
        self.assertTrue(res.get("success"))
        self.assertTrue(res.get("modified"))

        # Verify all Manhã rows
        for r_idx in range(1, 10):
            row = b.sheets_data["Alunos"][r_idx]
            self.assertIn(row[1], {"M", "F"}, f"Sexo inválido na linha {r_idx + 1}: {row[1]}")
            self.assertEqual(row[2], "Manhã", f"Turno não padronizado para Manhã na linha {r_idx + 1}: {row[2]}")
            # Ensure name has no tabs, newlines or double spaces
            self.assertNotIn("\t", row[0])
            self.assertNotIn("\n", row[0])
            self.assertNotIn("  ", row[0])

        # Verify all Tarde rows
        for r_idx in range(10, 18):
            row = b.sheets_data["Alunos"][r_idx]
            self.assertIn(row[1], {"M", "F"}, f"Sexo inválido na linha {r_idx + 1}: {row[1]}")
            self.assertEqual(row[2], "Tarde", f"Turno não padronizado para Tarde na linha {r_idx + 1}: {row[2]}")

        # Verify all Integral rows
        for r_idx in range(18, 24):
            row = b.sheets_data["Alunos"][r_idx]
            self.assertIn(row[1], {"M", "F"}, f"Sexo inválido na linha {r_idx + 1}: {row[1]}")
            self.assertEqual(row[2], "Integral", f"Turno não padronizado para Integral na linha {r_idx + 1}: {row[2]}")

        # Post-validation: exactly 0 tratadas
        self.assertEqual(b.last_summary["incons_counts"]["tratadas"], 0)

    def test_column_reordering_and_unmapped_columns_preservation(self) -> None:
        """Adversarial test with reordered columns, extra unmapped columns and ragged rows."""
        # Order: ID, Turno (Disp), Observação, Aluno (Nome), Extra, Gênero (Sexo), Outro
        alunos = [
            ["ID", "Turno", "Observação", "Aluno", "Idade", "Gênero", "Notas"],
            ["101", "mahna", "bolsista", "  Carlos   Drummond  ", "20", "homem", "Aprovado"],
            ["102", "tadre", "atleta", "Cecília Meireles", "19", "mulher", "Pendente"],
            ["103", "itnegral", "monitor", "Clarice Lispector", "21", "fem", "Aprovado"],
            # Ragged row (fewer columns than header)
            ["104", "matutino", "estágio", "Machado de Assis", "22", "masc"],
        ]

        b = self._create_backend(alunos)
        self.assertGreater(b.last_summary["incons_counts"]["tratadas"], 0)

        # Batch sanitize
        res = b.resolve_issue("accept_sanitize", "sanitize", [])
        self.assertTrue(res.get("success"))
        self.assertTrue(res.get("modified"))

        m = b.sheets_data["Alunos"]
        # Header untouched
        self.assertEqual(m[0], ["ID", "Turno", "Observação", "Aluno", "Idade", "Gênero", "Notas"])

        # Check Row 2
        self.assertEqual(m[1][0], "101")                   # ID preserved
        self.assertEqual(m[1][1], "Manhã")                 # Turno sanitized
        self.assertEqual(m[1][2], "bolsista")              # Unmapped preserved
        self.assertEqual(m[1][3], "Carlos Drummond")       # Nome spaces cleaned
        self.assertEqual(m[1][4], "20")                    # Unmapped preserved
        self.assertEqual(m[1][5], "M")                     # Gênero sanitized
        self.assertEqual(m[1][6], "Aprovado")              # Unmapped preserved

        # Check Row 3
        self.assertEqual(m[2][1], "Tarde")
        self.assertEqual(m[2][5], "F")
        self.assertEqual(m[2][2], "atleta")

        # Check Row 4
        self.assertEqual(m[3][1], "Integral")
        self.assertEqual(m[3][5], "F")

        # Check Row 5 (ragged row that was padded)
        self.assertEqual(m[4][1], "Manhã")
        self.assertEqual(m[4][3], "Machado de Assis")
        self.assertEqual(m[4][5], "M")

        # 0 remaining tratadas
        self.assertEqual(b.last_summary["incons_counts"]["tratadas"], 0)

    def test_empty_cells_and_corrupt_impeditivos(self) -> None:
        """Adversarial test on empty cells, none values and truly corrupt values that must NOT be guessed."""
        alunos = [
            ["Nome", "Sexo", "Disponibilidade"],
            ["Aluno Válido", "M", "Manhã"],
            ["", "F", "Manhã"],                           # Row 3: Empty name (impeditivo)
            ["Aluno Sem Sexo", "", "Tarde"],              # Row 4: Empty sexo (impeditivo)
            ["Aluno Sem Turno", "M", ""],                 # Row 5: Empty disp (impeditivo)
            ["Aluno Sexo Invalido", "X", "Manhã"],        # Row 6: Invalid sexo 'X' (impeditivo)
            ["Aluno Turno Invalido", "M", "Noite"],       # Row 7: Invalid disp 'Noite' (impeditivo)
            ["  Aluno   Misto  ", "mulher", "Madrugada"], # Row 8: Name & Sexo fixable, disp impeditivo
        ]

        b = self._create_backend(alunos)
        summary_before = b.last_summary
        impeditivas_before = summary_before["incons_counts"]["impeditivas"]
        self.assertGreaterEqual(impeditivas_before, 5)

        # Batch sanitize: only touches TRATADA issues, never touches IMPEDITIVA rows automatically
        res = b.resolve_issue("accept_sanitize", "sanitize", [])
        self.assertTrue(res.get("success"))

        m = b.sheets_data["Alunos"]
        # Row 3: Nome remains empty
        self.assertEqual(m[2][0], "")
        # Row 4: Sexo remains empty
        self.assertEqual(m[3][1], "")
        # Row 5: Disp remains empty
        self.assertEqual(m[4][2], "")
        # Row 6: Sexo 'X' NOT converted to M or F
        self.assertEqual(m[5][1], "X")
        # Row 7: Disp 'Noite' NOT converted to Manhã/Tarde
        self.assertEqual(m[6][2], "Noite")
        # Row 8: In batch mode, row 8 was classified as IMPEDITIVA (due to Madrugada), so batch left it untouched
        self.assertEqual(m[7][0], "  Aluno   Misto  ")
        self.assertEqual(m[7][2], "Madrugada")

        # Direct single invocation on Row 8: cleans fixable parts (name & sex), preserves corrupt disp
        res8 = b.resolve_issue("accept_sanitize", "sanitize", [8])
        self.assertTrue(res8.get("modified"))
        self.assertEqual(m[7][0], "Aluno Misto")
        self.assertEqual(m[7][1], "F")
        self.assertEqual(m[7][2], "Madrugada")

        # Impeditivas count must remain intact (still impeditivo because of Madrugada)
        summary_after = b.last_summary
        self.assertEqual(summary_after["incons_counts"]["impeditivas"], impeditivas_before)

    def test_idempotency_repeated_batch_and_single_clicks(self) -> None:
        """Adversarially test repeated invocations to guarantee strict idempotency."""
        alunos = [
            ["Nome", "Sexo", "Disponibilidade"],
            ["  Mariana   Souza  ", "feminino", "mahna"],
            ["Rodrigo Lima", "homem", "tadre"],
        ]
        b = self._create_backend(alunos)

        # First batch click: should modify and push 1 undo state
        self.assertEqual(len(b.undo_stack), 0)
        res1 = b.resolve_issue("accept_sanitize", "sanitize", [])
        self.assertTrue(res1.get("modified"))
        self.assertTrue(b.dirty)
        self.assertEqual(len(b.undo_stack), 1)
        matrix_after_first = copy.deepcopy(b.sheets_data["Alunos"])

        # Calls 2 to 10: MUST be idempotent
        for i in range(2, 11):
            res_i = b.resolve_issue("accept_sanitize", "sanitize", [])
            self.assertFalse(res_i.get("modified"), f"Iteração {i} retornou modified=True!")
            self.assertEqual(
                b.sheets_data["Alunos"],
                matrix_after_first,
                f"Iteração {i} alterou a matriz de dados!",
            )
            self.assertEqual(
                len(b.undo_stack),
                1,
                f"Iteração {i} empilhou snapshot indevido no undo_stack!",
            )

        # Single row clicks on already clean row: MUST also be idempotent
        res_single = b.resolve_issue("accept_sanitize", "sanitize", [2])
        self.assertFalse(res_single.get("modified"))
        self.assertEqual(len(b.undo_stack), 1)

    def test_undo_and_redo_deep_state_integrity(self) -> None:
        """Adversarially test undo and redo to guarantee exact bidirectional consistency."""
        alunos = [
            ["Nome", "Sexo", "Disponibilidade"],
            ["  Alice   Alves  ", "mulher", "mahna"],
            ["Bob Silva", "homem", "tadre"],
            ["Carlos Souza", "masc", "itnegral"],
        ]
        b = self._create_backend(alunos)
        initial_matrix = copy.deepcopy(b.sheets_data["Alunos"])
        initial_tratadas = b.last_summary["incons_counts"]["tratadas"]

        # 1. Apply batch sanitization
        b.resolve_issue("accept_sanitize", "sanitize", [])
        cleaned_matrix = copy.deepcopy(b.sheets_data["Alunos"])
        self.assertEqual(b.last_summary["incons_counts"]["tratadas"], 0)
        self.assertNotEqual(initial_matrix, cleaned_matrix)

        # 2. Undo
        undo_res = b.undo()
        self.assertTrue(undo_res.get("success"))
        self.assertEqual(b.sheets_data["Alunos"], initial_matrix, "Undo não restaurou exatamente o estado inicial!")
        self.assertEqual(b.last_summary["incons_counts"]["tratadas"], initial_tratadas)

        # 3. Redo
        redo_res = b.redo()
        self.assertTrue(redo_res.get("success"))
        self.assertEqual(b.sheets_data["Alunos"], cleaned_matrix, "Redo não restaurou exatamente o estado limpo!")
        self.assertEqual(b.last_summary["incons_counts"]["tratadas"], 0)

        # 4. Undo again, make an edit, verify redo stack cleared
        b.undo()
        self.assertEqual(len(b.redo_stack), 1)
        b.update_cell("Alunos", mat_idx=1, col=0, value="Novo Nome")
        self.assertEqual(len(b.redo_stack), 0, "Redo stack não foi limpo após nova edição!")

    def test_adversarial_target_rows_inputs(self) -> None:
        """Test out-of-bounds, negative, duplicate and invalid row numbers."""
        alunos = [
            ["Nome", "Sexo", "Disponibilidade"],
            ["Aluno 1", "M", "Manhã"],
            ["Aluno 2", "feminino", "mahna"], # Row 3
        ]
        b = self._create_backend(alunos)

        # Target rows out of bounds (positive and negative)
        res_oob = b.resolve_issue("accept_sanitize", "sanitize", [999999, -50, 0])
        self.assertTrue(res_oob.get("success"))
        self.assertFalse(res_oob.get("modified"))

        # Duplicate row numbers
        res_dup = b.resolve_issue("accept_sanitize", "sanitize", [3, 3, 3])
        self.assertTrue(res_dup.get("success"))
        self.assertTrue(res_dup.get("modified"))
        self.assertEqual(b.sheets_data["Alunos"][2][1], "F")
        self.assertEqual(b.sheets_data["Alunos"][2][2], "Manhã")
        self.assertEqual(len(b.undo_stack), 1, "Linhas duplicadas no target_rows não devem gerar múltiplos snapshots.")

        # Empty matrix
        b_empty = AppBackend()
        b_empty.sheets_data = {"Alunos": []}
        res_empty = b_empty.resolve_issue("accept_sanitize", "sanitize", [])
        self.assertTrue(res_empty.get("success"))
        self.assertFalse(res_empty.get("modified"))

        # Missing Alunos sheet
        b_no_alunos = AppBackend()
        b_no_alunos.sheets_data = {"OutraAba": [["A"]]}
        res_missing = b_no_alunos.resolve_issue("accept_sanitize", "sanitize", [])
        self.assertFalse(res_missing.get("success"))
        self.assertIn("não encontrada", res_missing.get("error", ""))

    def test_end_to_end_save_reload_and_solver(self) -> None:
        """Full pipeline test: dirty instance -> batch sanitize -> save to disk -> reload -> run_solver."""
        alunos = [
            ["Nome", "Sexo", "Disponibilidade"],
            ["  Ana   Clara  ", "mulher", "mahna"],
            ["Bernardo Silva", "homem", "tadre"],
            ["Camila Santos", "feminino", "matutino"],
            ["Diego Rocha", "masculino", "vespertino"],
            ["Eduarda Lima", " F ", " TARDE"],
            ["Fábio Costa", " M ", " MANHÃ"],
            ["Gabriela Dias", "mulher", "itnegral"],
            ["Heitor Castro", "homem", "livre"],
        ]
        turmas = [
            ["Recurso", "Quantidade"],
            ["turmas_manha", "1"],
            ["turmas_tarde", "1"],
            ["vagas_manha", "10"],
            ["vagas_tarde", "10"],
        ]
        b = self._create_backend(alunos, turmas)

        # 1. Sanitize
        res_sanitize = b.resolve_issue("accept_sanitize", "sanitize", [])
        self.assertTrue(res_sanitize.get("modified"))
        self.assertEqual(b.last_summary["incons_counts"]["tratadas"], 0)

        # 2. Save and reload
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "e2e_adversarial.xlsx"
            save_res = b.save_excel(str(file_path))
            self.assertTrue(save_res.get("success"), save_res.get("error"))
            self.assertTrue(file_path.exists())

            b2 = AppBackend()
            load_res = b2.load_excel(str(file_path))
            self.assertTrue(load_res.get("success"), load_res.get("error"))

            # Check that reloaded data has 0 inconsistencies
            self.assertEqual(b2.last_summary["incons_counts"]["tratadas"], 0)
            self.assertEqual(b2.last_summary["incons_counts"]["impeditivas"], 0)

            # 3. Solve problem on the sanitized instance
            solve_res = b2.run_ensalamento()
            self.assertTrue(solve_res.get("success"), solve_res.get("error"))
            self.assertTrue(b2.solver_result.feasible)
            self.assertEqual(len(b2.solver_result.student_to_turma), 8)

            # Check Ensalamento sheet generated
            ens_sheet = b2.sheets_data.get("Ensalamento", [])
            self.assertEqual(len(ens_sheet), 9) # 1 header + 8 students
            for row in ens_sheet[1:]:
                self.assertIn(row[1], {"M", "F"})
                self.assertIn(row[2], {"Manhã", "Tarde", "MANHÃ", "TARDE"})
                self.assertTrue(len(row[3]) > 0)


if __name__ == "__main__":
    unittest.main()

"""Testes de estresse e adversariais independentes para o Requisito R1.

Auditoria realizada pelo Challenger 2 para verificar:
1. Ausência da aba 'Alunos' ou matriz vazia.
2. Índices de 'target_rows' fora dos limites ([999999], [-1], [0], [len+1], mistos).
3. Linhas com menos colunas que max(col_nome, col_sexo, col_disp) com ordens padrão e invertidas.
4. Múltiplas resoluções sequenciais, persistência em disco (.xlsx) e resolução matemática MILP.
5. Tipos atípicos (None, números, strings vazias) e ações desconhecidas.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from src.app.server import AppBackend


class TestR1AdversarialStress(unittest.TestCase):
    """Bateria de testes de estresse adversarial sobre resolve_issue e _build_raw_from_memory."""

    def _create_backend_mock(
        self,
        alunos_rows: list[list[any]] | None = None,
        turmas_rows: list[list[any]] | None = None,
        include_alunos: bool = True,
        include_turmas: bool = True,
    ) -> AppBackend:
        b = AppBackend()
        sheets = {}
        if include_alunos:
            sheets["Alunos"] = (
                alunos_rows
                if alunos_rows is not None
                else [
                    ["Nome", "Sexo", "Disponibilidade"],
                    ["Aluno Teste", "M", "Manhã"],
                ]
            )
        if include_turmas:
            sheets["Turmas"] = (
                turmas_rows
                if turmas_rows is not None
                else [
                    ["Recurso", "Quantidade"],
                    ["turmas_manha", "2"],
                    ["turmas_tarde", "2"],
                    ["vagas_manha", "25"],
                    ["vagas_tarde", "25"],
                ]
            )
        b.sheets_data = sheets
        b.active_sheet = "Alunos" if include_alunos else "Turmas"
        return b

    # =========================================================================
    # CENÁRIO 1: Planilha sem a aba "Alunos" ou com matriz vazia
    # =========================================================================

    def test_missing_alunos_tab_resolve_issue(self) -> None:
        """Verifica comportamento defensivo de resolve_issue quando a aba 'Alunos' inexiste."""
        b = self._create_backend_mock(include_alunos=False)

        # 1. accept_sanitize
        res_sanitize = b.resolve_issue("accept_sanitize", "sanitize", [2])
        self.assertFalse(res_sanitize.get("success"))
        self.assertIn("Aba 'Alunos' não encontrada", res_sanitize.get("error", ""))

        # 2. remove_duplicates
        res_dups = b.resolve_issue("remove_duplicates", "duplicate", [2, 3])
        self.assertFalse(res_dups.get("success"))
        self.assertIn("Aba 'Alunos' não encontrada", res_dups.get("error", ""))

        # 3. quick_fix_field
        res_qf = b.resolve_issue("quick_fix_field", "field", [2], extra={"field": "sexo", "value": "F"})
        self.assertFalse(res_qf.get("success"))
        self.assertIn("Aba 'Alunos' não encontrada", res_qf.get("error", ""))

    def test_missing_alunos_tab_build_raw_from_memory(self) -> None:
        """Verifica _build_raw_from_memory quando a aba 'Alunos' inexiste."""
        b = self._create_backend_mock(include_alunos=False)
        raw = b._build_raw_from_memory()
        self.assertIsNotNone(raw)
        self.assertEqual(len(raw.students), 0)
        self.assertNotIn("Alunos", raw.sheet_names)

    def test_empty_alunos_matrix(self) -> None:
        """Verifica matriz 'Alunos' completamente vazia ([])."""
        b = self._create_backend_mock(alunos_rows=[])
        b.validate_data()

        # resolve_issue não deve gerar exceção
        res = b.resolve_issue("accept_sanitize", "sanitize", [1])
        self.assertTrue(res.get("success"))
        self.assertFalse(res.get("modified"))

        # _build_raw_from_memory com matriz vazia
        raw = b._build_raw_from_memory()
        self.assertEqual(len(raw.students), 0)

    def test_alunos_header_only(self) -> None:
        """Verifica matriz 'Alunos' contendo apenas o cabeçalho."""
        b = self._create_backend_mock(alunos_rows=[["Nome", "Sexo", "Disponibilidade"]])
        b.validate_data()

        raw = b._build_raw_from_memory()
        self.assertEqual(len(raw.students), 0)

        # Higienização de cabeçalho já limpo não deve quebrar
        res = b.resolve_issue("accept_sanitize", "sanitize", [1])
        self.assertTrue(res.get("success"))
        self.assertFalse(res.get("modified"))

    # =========================================================================
    # CENÁRIO 2: Índices de target_rows fora dos limites
    # =========================================================================

    def test_out_of_bounds_target_rows(self) -> None:
        """Testa resiliência contra target_rows out-of-bounds: [999999], [-1], [0], [len+1]."""
        alunos = [
            ["Nome", "Sexo", "Disponibilidade"],
            ["Aluno 1", "feminino", "mahna"],  # Linha 2 (válida)
        ]
        b = self._create_backend_mock(alunos_rows=alunos)
        b.validate_data()

        # Teste 1: [999999]
        res_huge = b.resolve_issue("accept_sanitize", "sanitize", [999999])
        self.assertTrue(res_huge.get("success"))
        self.assertFalse(res_huge.get("modified"))

        # Teste 2: [-1]
        res_neg = b.resolve_issue("accept_sanitize", "sanitize", [-1])
        self.assertTrue(res_neg.get("success"))
        self.assertFalse(res_neg.get("modified"))

        # Teste 3: [0] (linha 0 no Excel não existe, mat_idx seria -1)
        res_zero = b.resolve_issue("accept_sanitize", "sanitize", [0])
        self.assertTrue(res_zero.get("success"))
        self.assertFalse(res_zero.get("modified"))

        # Teste 4: [3] (len da matriz é 2, linha 3 é out of bounds)
        res_boundary = b.resolve_issue("accept_sanitize", "sanitize", [3])
        self.assertTrue(res_boundary.get("success"))
        self.assertFalse(res_boundary.get("modified"))

        # Teste 5: lista mista com índices inválidos e um índice válido [999999, -5, 2, 0]
        res_mixed = b.resolve_issue("accept_sanitize", "sanitize", [999999, -5, 2, 0])
        self.assertTrue(res_mixed.get("success"))
        self.assertTrue(res_mixed.get("modified"))
        self.assertEqual(b.sheets_data["Alunos"][1][1], "F")
        self.assertEqual(b.sheets_data["Alunos"][1][2], "Manhã")

    def test_out_of_bounds_remove_duplicates(self) -> None:
        """Testa remove_duplicates com índices out-of-bounds."""
        alunos = [
            ["Nome", "Sexo", "Disponibilidade"],
            ["Aluno 1", "M", "Manhã"],
        ]
        b = self._create_backend_mock(alunos_rows=alunos)
        # Passa índices fora dos limites
        res = b.resolve_issue("remove_duplicates", "duplicate", [999999, 888888, -1])
        self.assertTrue(res.get("success"))
        self.assertFalse(res.get("modified"))
        self.assertEqual(len(b.sheets_data["Alunos"]), 2)

    def test_out_of_bounds_quick_fix(self) -> None:
        """Testa quick_fix_field com índices out-of-bounds."""
        alunos = [
            ["Nome", "Sexo", "Disponibilidade"],
            ["Aluno 1", "M", "Manhã"],
        ]
        b = self._create_backend_mock(alunos_rows=alunos)
        res = b.resolve_issue(
            "quick_fix_field",
            "field",
            [999999, -2],
            extra={"field": "sexo", "value": "F"},
        )
        self.assertTrue(res.get("success"))
        self.assertFalse(res.get("modified"))

    # =========================================================================
    # CENÁRIO 3: Linhas com menos colunas que max(col_nome, col_sexo, col_disp)
    # =========================================================================

    def test_short_rows_standard_columns(self) -> None:
        """Linhas de dados com menos colunas do que o cabeçalho (ordem padrão 0, 1, 2)."""
        alunos = [
            ["Nome", "Sexo", "Disponibilidade"],
            ["Aluno Só Nome"],                      # len 1: falta sexo e disp
            [],                                     # len 0: linha vazia
            ["Aluno Com Sexo", "feminino"],         # len 2: falta disp
            ["Aluno Completo", "homem", "tadre"],   # len 3
        ]
        b = self._create_backend_mock(alunos_rows=alunos)
        val = b.validate_data()
        self.assertTrue(val.get("success"))

        # _build_raw_from_memory não deve falhar
        raw = b._build_raw_from_memory()
        self.assertIsNotNone(raw)
        # Linha 3 (vazia) deve ter sido pulada
        self.assertEqual(len(raw.students), 3)

        # Aplica sanitização na linha 4 (que tinha len 2)
        res4 = b.resolve_issue("accept_sanitize", "sanitize", [4])
        self.assertTrue(res4.get("success"))
        self.assertTrue(res4.get("modified"))
        # A linha deve ter sido preenchida defensivamente com "" até ter pelo menos 3 colunas
        self.assertGreaterEqual(len(b.sheets_data["Alunos"][3]), 3)
        self.assertEqual(b.sheets_data["Alunos"][3][1], "F")

        # Aplica sanitização na linha 2 (que tinha len 1)
        res2 = b.resolve_issue("accept_sanitize", "sanitize", [2])
        self.assertTrue(res2.get("success"))
        self.assertGreaterEqual(len(b.sheets_data["Alunos"][1]), 3)

    def test_short_rows_inverted_and_distant_columns(self) -> None:
        """Colunas fora de ordem e em posições distantes (ex: Disp=0, Nome=2, Sexo=4)."""
        alunos = [
            ["Disponibilidade", "Ignorada 1", "Nome do Estudante", "Ignorada 2", "Gênero"],
            ["mahna", "x", "Carla Dias"],  # len 3, mas Sexo está na coluna 4!
        ]
        b = self._create_backend_mock(alunos_rows=alunos)
        val = b.validate_data()
        self.assertTrue(val.get("success"))

        # Testa que _build_raw_from_memory lê com segurança
        raw = b._build_raw_from_memory()
        self.assertEqual(len(raw.students), 1)
        st = raw.students[0]
        self.assertEqual(st.nome, "Carla Dias")
        self.assertEqual(st.disponibilidade, "mahna")
        self.assertIsNone(st.sexo)

        # Testa resolve_issue aceitando sanitização na linha 2
        res = b.resolve_issue("accept_sanitize", "sanitize", [2])
        self.assertTrue(res.get("success"))
        self.assertTrue(res.get("modified"))
        # A linha deve ter sido expandida para ter pelo menos 5 colunas (índice 4 disponível)
        r2 = b.sheets_data["Alunos"][1]
        self.assertGreaterEqual(len(r2), 5)
        self.assertEqual(r2[0], "Manhã")
        self.assertEqual(r2[2], "Carla Dias")

    # =========================================================================
    # CENÁRIO 4: Múltiplas resoluções sequenciais, persistência e solver MILP
    # =========================================================================

    def test_sequential_resolutions_save_and_milp_solver(self) -> None:
        """Executa resoluções individuais, undo/redo, lote, salvamento e validação matemática no MILP."""
        alunos = [
            ["Nome", "Sexo", "Disponibilidade"],
            ["Ana Lima", "feminino", "mahna"],          # Linha 2
            ["Bruno Dias", "homem", "tadre"],           # Linha 3
            ["  Carla   Melo  ", "mulher", "itnegral"],  # Linha 4
            ["Diego Ramos", "masc", "matutino"],        # Linha 5
            ["Elisa Souza", " F ", " TARDE"],           # Linha 6
            ["Fabio Cruz", "M", "vespertino"],          # Linha 7
        ]
        # 3 turmas manhã (capacidade 25 cada), 3 turmas tarde (capacidade 25 cada)
        turmas = [
            ["Recurso", "Quantidade"],
            ["turmas_manha", "2"],
            ["turmas_tarde", "2"],
            ["vagas_manha", "10"],
            ["vagas_tarde", "10"],
        ]
        b = self._create_backend_mock(alunos_rows=alunos, turmas_rows=turmas)
        init_summary = b.validate_data()["summary"]
        self.assertEqual(init_summary["incons_counts"]["tratadas"], 6)

        # 1. Resolução individual da linha 2
        r2 = b.resolve_issue("accept_sanitize", "sanitize", [2])
        self.assertTrue(r2.get("modified"))
        self.assertEqual(b.sheets_data["Alunos"][1][1], "F")
        self.assertEqual(b.sheets_data["Alunos"][1][2], "Manhã")

        # 2. Resolução individual da linha 3
        r3 = b.resolve_issue("accept_sanitize", "sanitize", [3])
        self.assertTrue(r3.get("modified"))
        self.assertEqual(b.sheets_data["Alunos"][2][1], "M")
        self.assertEqual(b.sheets_data["Alunos"][2][2], "Tarde")

        # 3. Teste de Undo e Redo
        undo_res = b.undo()
        self.assertTrue(undo_res.get("success"))
        # Bruno Dias deve ter voltado para 'homem' e 'tadre'
        self.assertEqual(b.sheets_data["Alunos"][2][1], "homem")
        self.assertEqual(b.sheets_data["Alunos"][2][2], "tadre")

        redo_res = b.redo()
        self.assertTrue(redo_res.get("success"))
        # Bruno Dias volta para 'M' e 'Tarde'
        self.assertEqual(b.sheets_data["Alunos"][2][1], "M")
        self.assertEqual(b.sheets_data["Alunos"][2][2], "Tarde")

        # 4. Resolução em lote para todo o restante
        batch_res = b.resolve_issue("accept_sanitize", "sanitize", [])
        self.assertTrue(batch_res.get("success"))
        self.assertTrue(batch_res.get("modified"))
        self.assertEqual(b.last_summary["incons_counts"]["tratadas"], 0)

        # 5. Salva em disco e recarrega em outra instância
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_xlsx = Path(tmp_dir) / "stress_persistence.xlsx"
            save_res = b.save_excel(str(tmp_xlsx))
            self.assertTrue(save_res.get("success"))
            self.assertTrue(tmp_xlsx.exists())

            # Nova instância independente
            b2 = AppBackend()
            load_res = b2.load_excel(str(tmp_xlsx))
            self.assertTrue(load_res.get("success"))
            self.assertEqual(b2.last_summary["incons_counts"]["tratadas"], 0)
            self.assertEqual(b2.last_summary["incons_counts"]["impeditivas"], 0)

            # 6. Executa o Solver MILP
            solve_res = b2.run_ensalamento(allow_integral=True, allow_unallocated=False)
            self.assertTrue(solve_res.get("success"), f"Solver falhou: {solve_res.get('error')}")

            solver_result = b2.solver_result
            self.assertIsNotNone(solver_result)
            self.assertTrue(solver_result.feasible)

            # Validações matemáticas do ensalamento gerado
            ens_matrix = b2.sheets_data.get("Ensalamento", [])
            # Cabeçalho + 6 alunos alocados
            self.assertEqual(len(ens_matrix), 7, "Aba Ensalamento deve conter cabeçalho + 6 alunos.")

            # Verifica correspondência de turno e dados higienizados
            ens_by_nome = {row[0]: row for row in ens_matrix[1:]}
            self.assertIn("Ana Lima", ens_by_nome)
            self.assertEqual(ens_by_nome["Ana Lima"][1], "F")
            self.assertEqual(ens_by_nome["Ana Lima"][2], "MANHÃ")

            self.assertIn("Bruno Dias", ens_by_nome)
            self.assertEqual(ens_by_nome["Bruno Dias"][1], "M")
            self.assertEqual(ens_by_nome["Bruno Dias"][2], "TARDE")

            self.assertIn("Carla Melo", ens_by_nome)
            self.assertEqual(ens_by_nome["Carla Melo"][1], "F")
            self.assertIn(ens_by_nome["Carla Melo"][2], ["MANHÃ", "TARDE"])

    # =========================================================================
    # CENÁRIO 5: Casos Limítrofes (None, números, strings vazias, ação desconhecida)
    # =========================================================================

    def test_cells_with_none_and_numeric_values(self) -> None:
        """Células com valores None, strings numéricas (como vindas do load_excel) e campos ausentes."""
        alunos = [
            ["Nome", "Sexo", "Disponibilidade"],
            [None, None, None],                                  # Linha completamente None (deve ser pulada)
            ["Aluno Numérico", "123", "456.7"],                   # Linha com valores numéricos carregados como string
            ["Aluno Sem Sexo", None, "mahna"],                    # Linha com Sexo None e Disp tratável
        ]
        b = self._create_backend_mock(alunos_rows=alunos)
        val = b.validate_data()
        self.assertTrue(val.get("success"))

        raw = b._build_raw_from_memory()
        # Linha 2 (completamente None) deve ter sido ignorada
        self.assertEqual(len(raw.students), 2)
        self.assertEqual(raw.students[0].nome, "Aluno Numérico")
        self.assertEqual(raw.students[0].sexo, "123")
        self.assertEqual(raw.students[0].disponibilidade, "456.7")

        self.assertEqual(raw.students[1].nome, "Aluno Sem Sexo")
        self.assertIsNone(raw.students[1].sexo)
        self.assertEqual(raw.students[1].disponibilidade, "mahna")

        # resolve_issue na linha 3 (numérica) não deve alterar nada nem falhar
        res3 = b.resolve_issue("accept_sanitize", "sanitize", [3])
        self.assertTrue(res3.get("success"))
        self.assertFalse(res3.get("modified"))

        # resolve_issue na linha 4 (Sexo None, Disp tratável) deve higienizar a disp para 'Manhã'
        res4 = b.resolve_issue("accept_sanitize", "sanitize", [4])
        self.assertTrue(res4.get("success"))
        self.assertTrue(res4.get("modified"))
        self.assertEqual(b.sheets_data["Alunos"][3][2], "Manhã")

    def test_unknown_action(self) -> None:
        """Verifica que uma ação inválida/desconhecida não corrompe o estado e retorna de forma limpa."""
        alunos = [
            ["Nome", "Sexo", "Disponibilidade"],
            ["Aluno 1", "M", "Manhã"],
        ]
        b = self._create_backend_mock(alunos_rows=alunos)
        res = b.resolve_issue("unknown_action_xyz", "some_type", [2])
        self.assertTrue(res.get("success"))
        self.assertFalse(res.get("modified"))
        self.assertFalse(b.dirty)


if __name__ == "__main__":
    unittest.main()

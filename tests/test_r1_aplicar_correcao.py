"""Testes automatizados para o Requisito R1: Botão 'Aplicar Correção'.

Valida a sanitização ponta-a-ponta, correção de permutações e sinônimos,
higienização em lote, correção de cabeçalho, preservação de espaços em células brutas,
persistência via save_excel / reload e feedback visual (highlight_excel_row).
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from src.app.server import AppBackend


class TestR1AplicarCorrecao(unittest.TestCase):
    """Conjunto de testes do fluxo completo de 'Aplicar Correção'."""

    def _create_backend_with_alunos(
        self, alunos_rows: list[list[str]], turmas_rows: list[list[str]] | None = None
    ) -> AppBackend:
        """Auxiliar que inicializa um AppBackend com matrizes mockadas em memória."""
        backend = AppBackend()
        backend.sheets_data = {
            "Alunos": alunos_rows,
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

    def test_individual_sanitization_typos_and_synonyms(self) -> None:
        """Testa a higienização individual para permutações de turno, sinônimos e sexo."""
        alunos = [
            ["Nome", "Sexo", "Disponibilidade"],
            ["  Alice   Alves  ", "feminino", "mahna"],     # Linha 2
            ["Bob Silva", "homem", "tadre"],                 # Linha 3
            ["Carlos Souza", "masc", "itnegral"],            # Linha 4
            ["Diana Costa", "mulher", "matutino"],           # Linha 5
            ["Eduardo Lima", " M ", "vespertino"],           # Linha 6
            ["Fernanda Lima", " F ", " TARDE"],              # Linha 7
            ["Gabriel Santos", "m", "livre"],                # Linha 8
        ]
        b = self._create_backend_with_alunos(alunos)
        summary = b.last_summary
        self.assertIsNotNone(summary)
        self.assertGreater(summary["incons_counts"]["tratadas"], 0)

        # 1. Linha 2: '  Alice   Alves  ', 'feminino', 'mahna' -> 'Alice Alves', 'F', 'Manhã'
        res2 = b.resolve_issue("accept_sanitize", "sanitize", [2])
        self.assertTrue(res2.get("modified"))
        self.assertEqual(b.sheets_data["Alunos"][1][0], "Alice Alves")
        self.assertEqual(b.sheets_data["Alunos"][1][1], "F")
        self.assertEqual(b.sheets_data["Alunos"][1][2], "Manhã")

        # 2. Linha 3: 'homem', 'tadre' -> 'M', 'Tarde'
        res3 = b.resolve_issue("accept_sanitize", "sanitize", [3])
        self.assertTrue(res3.get("modified"))
        self.assertEqual(b.sheets_data["Alunos"][2][1], "M")
        self.assertEqual(b.sheets_data["Alunos"][2][2], "Tarde")

        # 3. Linha 4: 'masc', 'itnegral' -> 'M', 'Integral'
        res4 = b.resolve_issue("accept_sanitize", "sanitize", [4])
        self.assertTrue(res4.get("modified"))
        self.assertEqual(b.sheets_data["Alunos"][3][1], "M")
        self.assertEqual(b.sheets_data["Alunos"][3][2], "Integral")

        # 4. Linha 5: 'mulher', 'matutino' -> 'F', 'Manhã'
        res5 = b.resolve_issue("accept_sanitize", "sanitize", [5])
        self.assertTrue(res5.get("modified"))
        self.assertEqual(b.sheets_data["Alunos"][4][1], "F")
        self.assertEqual(b.sheets_data["Alunos"][4][2], "Manhã")

        # 5. Linha 6: ' M ', 'vespertino' -> 'M', 'Tarde'
        res6 = b.resolve_issue("accept_sanitize", "sanitize", [6])
        self.assertTrue(res6.get("modified"))
        self.assertEqual(b.sheets_data["Alunos"][5][1], "M")
        self.assertEqual(b.sheets_data["Alunos"][5][2], "Tarde")

        # 6. Linha 7: ' F ', ' TARDE' -> 'F', 'Tarde'
        res7 = b.resolve_issue("accept_sanitize", "sanitize", [7])
        self.assertTrue(res7.get("modified"))
        self.assertEqual(b.sheets_data["Alunos"][6][1], "F")
        self.assertEqual(b.sheets_data["Alunos"][6][2], "Tarde")

        # 7. Linha 8: 'm', 'livre' -> 'M', 'Integral'
        res8 = b.resolve_issue("accept_sanitize", "sanitize", [8])
        self.assertTrue(res8.get("modified"))
        self.assertEqual(b.sheets_data["Alunos"][7][1], "M")
        self.assertEqual(b.sheets_data["Alunos"][7][2], "Integral")

        # Revalidação final: 0 inconsistências tratadas restantes
        val_final = b.validate_data()
        self.assertTrue(val_final.get("success"))
        self.assertEqual(val_final["summary"]["incons_counts"]["tratadas"], 0)

    def test_batch_sanitization_empty_target_rows(self) -> None:
        """Testa que passar target_rows=[] aplica sanitização em lote a todas as pendências tratadas."""
        alunos = [
            ["Nome", "Sexo", "Disponibilidade"],
            ["Aluno 1", "feminino", "mahna"],
            ["Aluno 2", "masculino", "tadre"],
            ["  Aluno 3  ", "mulher", "itnegral"],
            ["Aluno 4", " M ", " TARDE"],
        ]
        b = self._create_backend_with_alunos(alunos)
        self.assertGreater(b.last_summary["incons_counts"]["tratadas"], 0)

        # Dispara resolução global em lote
        res = b.resolve_issue("accept_sanitize", "sanitize", [])
        self.assertTrue(res.get("success"))
        self.assertTrue(res.get("modified"))
        self.assertTrue(b.dirty)

        # Checa células padronizadas
        self.assertEqual(b.sheets_data["Alunos"][1][1], "F")
        self.assertEqual(b.sheets_data["Alunos"][1][2], "Manhã")
        self.assertEqual(b.sheets_data["Alunos"][2][1], "M")
        self.assertEqual(b.sheets_data["Alunos"][2][2], "Tarde")
        self.assertEqual(b.sheets_data["Alunos"][3][0], "Aluno 3")
        self.assertEqual(b.sheets_data["Alunos"][3][1], "F")
        self.assertEqual(b.sheets_data["Alunos"][3][2], "Integral")
        self.assertEqual(b.sheets_data["Alunos"][4][1], "M")
        self.assertEqual(b.sheets_data["Alunos"][4][2], "Tarde")

        # Verifica que restaram 0 tratadas
        self.assertEqual(b.last_summary["incons_counts"]["tratadas"], 0)

    def test_header_row_sanitization(self) -> None:
        """Testa correção da linha de cabeçalho (Linha 1) quando atípica."""
        # 'Opção de Estudo' não possui palavra-chave usual e aciona aviso de cabeçalho atípico
        alunos = [
            ["Nome", "Sexo", "Opção de Estudo"],
            ["Beatriz Ramos", "F", "Manhã"],
        ]
        b = self._create_backend_with_alunos(alunos)
        # Deve ter gerado warning de cabeçalho tratável
        self.assertEqual(b.last_summary["incons_counts"]["tratadas"], 1)
        inc_header = b.last_summary["inconsistencias"][0]
        self.assertEqual(inc_header["linha"], 1)

        # Aplica correção no cabeçalho
        res = b.resolve_issue("accept_sanitize", "sanitize", [1])
        self.assertTrue(res.get("modified"))
        self.assertEqual(b.sheets_data["Alunos"][0][0], "Nome")
        self.assertEqual(b.sheets_data["Alunos"][0][1], "Sexo")
        self.assertEqual(b.sheets_data["Alunos"][0][2], "Disponibilidade")

        # Após correção, aviso de cabeçalho deve ter sumido
        self.assertEqual(b.last_summary["incons_counts"]["tratadas"], 0)

    def test_save_excel_and_reload_persists_sanitized_values(self) -> None:
        """Testa que salvar a planilha após sanitização e recarregar preserva os valores limpos."""
        alunos = [
            ["Nome", "Sexo", "Disponibilidade"],
            ["  Mariana Souza  ", "mulher", "mahna"],
            ["Rodrigo Lima", "homem", "tadre"],
        ]
        b = self._create_backend_with_alunos(alunos)
        b.resolve_issue("accept_sanitize", "sanitize", [])

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "teste_sanitizado.xlsx"
            save_res = b.save_excel(str(tmp_path))
            self.assertTrue(save_res.get("success"), save_res.get("error"))
            self.assertTrue(tmp_path.exists())

            # Recarrega em nova instância do AppBackend
            b2 = AppBackend()
            load_res = b2.load_excel(str(tmp_path))
            self.assertTrue(load_res.get("success"))

            # Valida que os dados no Excel em disco estão de fato corrigidos
            loaded_alunos = b2.sheets_data["Alunos"]
            self.assertEqual(loaded_alunos[1][0], "Mariana Souza")
            self.assertEqual(loaded_alunos[1][1], "F")
            self.assertEqual(loaded_alunos[1][2], "Manhã")
            self.assertEqual(loaded_alunos[2][0], "Rodrigo Lima")
            self.assertEqual(loaded_alunos[2][1], "M")
            self.assertEqual(loaded_alunos[2][2], "Tarde")

            # Inconsistências tratadas devem permanecer 0
            self.assertEqual(b2.last_summary["incons_counts"]["tratadas"], 0)

    def test_instancia_4_batch_sanitization(self) -> None:
        """Testa sanitização na instância real 'instancia_4.xlsx'."""
        path_inst4 = Path("instances/public/instancia_4.xlsx")
        if not path_inst4.exists():
            self.skipTest("Arquivo instancia_4.xlsx não encontrado no diretório esperado.")

        b = AppBackend()
        load_res = b.load_excel(str(path_inst4))
        self.assertTrue(load_res.get("success"))

        tratadas_antes = b.last_summary["incons_counts"]["tratadas"]
        # Linha 36: sexo 'feminino'; Linha 42: disp 'manha'; Linha 46: sexo ' F ', disp ' TARDE'
        self.assertEqual(tratadas_antes, 3, "Instância 4 deve começar com 3 inconsistências tratadas (incluindo espaços de linha 46).")

        res = b.resolve_issue("accept_sanitize", "sanitize", [])
        self.assertTrue(res.get("success"))
        self.assertTrue(res.get("modified"))

        # Checa valores específicos das linhas 36, 42 e 46
        self.assertEqual(b.sheets_data["Alunos"][35][1], "F")
        self.assertEqual(b.sheets_data["Alunos"][41][2], "Manhã")
        self.assertEqual(b.sheets_data["Alunos"][45][1], "F")
        self.assertEqual(b.sheets_data["Alunos"][45][2], "Tarde")

        # Verifica que tratadas zeraram
        tratadas_depois = b.last_summary["incons_counts"]["tratadas"]
        self.assertEqual(tratadas_depois, 0, f"Esperado 0 inconsistências tratadas, restaram {tratadas_depois}.")

        # Erros impeditivos (como linha 48 'X') e alertas devem permanecer inalterados
        self.assertEqual(b.last_summary["incons_counts"]["impeditivas"], 7)
        self.assertEqual(b.last_summary["incons_counts"]["alertas"], 6)

    def test_visual_jump_and_highlight_feedback(self) -> None:
        """Verifica se resolve_issue retorna highlight_excel_row e chaveia active_sheet para Alunos."""
        alunos = [
            ["Nome", "Sexo", "Disponibilidade"],
            ["Aluno 1", "M", "Manhã"],
            ["Aluno 2", "feminino", "Manhã"],  # Linha 3
        ]
        b = self._create_backend_with_alunos(alunos)
        b.active_sheet = "Turmas"  # Simula usuário navegando em outra aba

        res = b.resolve_issue("accept_sanitize", "sanitize", [3])
        self.assertEqual(res.get("active_sheet"), "Alunos")
        self.assertEqual(res.get("highlight_excel_row"), 3)

    def test_no_modification_when_already_clean(self) -> None:
        """Garante que se a linha já estiver limpa, modified=False e dirty não é alterado."""
        alunos = [
            ["Nome", "Sexo", "Disponibilidade"],
            ["Aluno Limpo", "M", "Manhã"],
        ]
        b = self._create_backend_with_alunos(alunos)
        b.dirty = False

        res = b.resolve_issue("accept_sanitize", "sanitize", [2])
        self.assertFalse(res.get("modified"))
        self.assertFalse(b.dirty)


if __name__ == "__main__":
    unittest.main()


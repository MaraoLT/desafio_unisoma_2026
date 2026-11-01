# tests/test_r3_tutorial.py
"""
Testes automatizados para o Requisito R3:
- Renomeação dos botões "Abrir Excel" -> "Abrir Planilha" e "Otimizar Turmas" -> "Organizar Turmas"
- Presença e integridade dos elementos do Tutorial Interativo (HTML, CSS e JS)
- Endpoint /api/tutorial_status e persistência em disco (~/.unisoma_settings.json)
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.app.server import AppBackend, _load_settings, _save_settings
from src.app.__main__ import BUNDLE_ROOT, create_wsgi_app, _wsgi_call


class TestR3TutorialAndButtons(unittest.TestCase):
    def setUp(self):
        Path(".unisoma_settings.json").unlink(missing_ok=True)
        self.static_dir = BUNDLE_ROOT / "src" / "app" / "static"
        self.index_html_path = self.static_dir / "index.html"
        self.style_css_path = self.static_dir / "style.css"
        self.index_html = self.index_html_path.read_text(encoding="utf-8")
        self.style_css = self.style_css_path.read_text(encoding="utf-8")

    def tearDown(self):
        Path(".unisoma_settings.json").unlink(missing_ok=True)


    def test_no_legacy_button_texts_in_src(self):
        """Garante que não sobrou nenhuma ocorrência de 'Abrir Excel' ou 'Otimizar Turmas' em src/."""
        src_root = BUNDLE_ROOT / "src"
        legacy_terms = ["Abrir Excel", "Otimizar Turmas"]
        violations = []

        for p in src_root.rglob("*"):
            if p.is_file() and p.suffix in (".html", ".css", ".js", ".py"):
                content = p.read_text(encoding="utf-8", errors="ignore")
                for term in legacy_terms:
                    if term in content:
                        violations.append(f"{p.relative_to(BUNDLE_ROOT)} contém '{term}'")

        self.assertEqual(
            violations,
            [],
            f"Termos legados encontrados nos arquivos de código:\n" + "\n".join(violations),
        )

    def test_new_button_texts_and_attributes_in_index_html(self):
        """Verifica se os novos botões estão presentes com texto correto, IDs e atributos."""
        # Botão Abrir Planilha
        self.assertIn('id="btnOpenSheet"', self.index_html)
        self.assertIn("Abrir Planilha", self.index_html)
        self.assertIn('onclick="openExcel()"', self.index_html)

        # Botão Organizar Turmas
        self.assertIn('id="btnRunOptimization"', self.index_html)
        self.assertIn("Organizar Turmas", self.index_html)
        self.assertIn('onclick="runOptimization()"', self.index_html)

        # Botão dedicado Tutorial
        self.assertIn('id="btnTutorial"', self.index_html)
        self.assertIn("Tutorial", self.index_html)
        self.assertIn('onclick="startTutorial(false)"', self.index_html)

        # Elementos apontados pelo tutorial
        self.assertIn('id="brandBox"', self.index_html)
        self.assertIn('id="btnSaveExcel"', self.index_html)
        self.assertIn('id="optToggles"', self.index_html)
        self.assertIn('id="sidePane"', self.index_html)

    def test_tutorial_dom_elements_structure(self):
        """Valida que todos os componentes de pop-up, spotlight, card e modal existem no DOM."""
        # Backdrop e Spotlight
        self.assertIn('id="tutorialBackdrop"', self.index_html)
        self.assertIn('id="tutorialSpotlight"', self.index_html)

        # Card flutuante
        self.assertIn('id="tutorialCard"', self.index_html)
        self.assertIn('id="tutorialStepCount"', self.index_html)
        self.assertIn('id="tutorialTitle"', self.index_html)
        self.assertIn('id="tutorialText"', self.index_html)
        self.assertIn('id="tutorialArrow"', self.index_html)

        # Botões de controle do card
        self.assertIn('id="btnTutorialSkip"', self.index_html)
        self.assertIn("Pular Tutorial", self.index_html)
        self.assertIn('id="btnTutorialPrev"', self.index_html)
        self.assertIn("Anterior", self.index_html)
        self.assertIn('id="btnTutorialNext"', self.index_html)
        self.assertIn("Próximo", self.index_html)
        self.assertIn('id="btnTutorialFinish"', self.index_html)
        self.assertIn("Concluir", self.index_html)

        # Modal de boas-vindas / primeiro acesso
        self.assertIn('id="tutorialWelcomeModal"', self.index_html)
        self.assertIn('id="btnWelcomeSkip"', self.index_html)
        self.assertIn("Pular / Ignorar", self.index_html)
        self.assertIn('id="btnWelcomeStart"', self.index_html)
        self.assertIn("Iniciar Tutorial", self.index_html)

    def test_tutorial_css_classes_and_pulse_animation(self):
        """Verifica a presença de todas as regras de estilo CSS do tutorial e animação de destaque."""
        self.assertIn("#tutorialBackdrop", self.style_css)
        self.assertIn("#tutorialSpotlight", self.style_css)
        self.assertIn(".tutorial-highlight", self.style_css)
        self.assertIn("@keyframes tutorialPulse", self.style_css)
        self.assertIn("#tutorialCard", self.style_css)
        self.assertIn(".tutorial-arrow", self.style_css)
        self.assertIn("#tutorialWelcomeModal", self.style_css)
        self.assertIn(".tutorial-step-badge", self.style_css)

    def test_tutorial_steps_in_javascript(self):
        """Verifica a lista de passos do tutorial e as funções de navegação."""
        self.assertIn("tutorialSteps", self.index_html)
        expected_targets = [
            "brandBox",
            "btnOpenSheet",
            "btnSaveExcel",
            "optToggles",
            "btnRunOptimization",
            "sidePane",
            "btnTutorial",
        ]
        for t in expected_targets:
            self.assertIn(f'targetId: "{t}"', self.index_html)

        # Funções de controle
        self.assertIn("startTutorial(", self.index_html)
        self.assertIn("showTutorialStep(", self.index_html)
        self.assertIn("nextTutorialStep(", self.index_html)
        self.assertIn("prevTutorialStep(", self.index_html)
        self.assertIn("skipTutorial(", self.index_html)
        self.assertIn("finishTutorial(", self.index_html)
        self.assertIn("checkTutorialFirstRun(", self.index_html)
        self.assertIn("markTutorialSeen(", self.index_html)

    def test_assistant_deterministic_messages_updated(self):
        """Verifica se o assistente do servidor utiliza 'Abrir Planilha' e 'Organizar Turmas'."""
        backend = AppBackend()
        # Sem planilha aberta
        ans_no_sheet = backend.ask_assistant("onde está a turma b?")
        self.assertIn("Abrir Planilha", ans_no_sheet)
        self.assertNotIn("Abrir Excel", ans_no_sheet)

        # Com planilha vazia (sem summary de otimização)
        backend.sheets_data = {"Alunos": [["Nome", "Sexo", "Disponibilidade"], ["Carlos", "M", "Manhã"]]}
        ans_err = backend.ask_assistant("quais erros tem?")
        self.assertIn("Organizar Turmas", ans_err)
        self.assertNotIn("Otimizar Turmas", ans_err)

        ans_vagas = backend.ask_assistant("quantas vagas?")
        self.assertIn("Organizar Turmas", ans_vagas)
        self.assertNotIn("Otimizar Turmas", ans_vagas)

        ans_gen = backend.ask_assistant("proporção de gênero")
        self.assertIn("Organizar Turmas", ans_gen)
        self.assertNotIn("Otimizar Turmas", ans_gen)

        ans_esp = backend.ask_assistant("tem excedente na lista?")
        self.assertIn("Organizar Turmas", ans_esp)
        self.assertNotIn("Otimizar Turmas", ans_esp)

        ans_aluno = backend.ask_assistant("Carlos")
        self.assertIn("Organizar Turmas", ans_aluno)
        self.assertNotIn("Otimizar Turmas", ans_aluno)

    def test_backend_tutorial_status_and_disk_persistence(self):
        """Testa o backend get/set_tutorial_status com isolamento em diretório temporário."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_home = Path(tmpdir)
            with patch("pathlib.Path.home", return_value=fake_home):
                backend = AppBackend()

                # 1. Estado inicial sem arquivo
                status = backend.get_tutorial_status()
                self.assertFalse(status["seen"])

                # 2. Marca como visto
                res = backend.set_tutorial_status(True)
                self.assertTrue(res["seen"])
                self.assertTrue(res["success"])

                # Verifica gravação no disco em fake_home / .unisoma_settings.json
                settings_file = fake_home / ".unisoma_settings.json"
                self.assertTrue(settings_file.exists())
                saved_json = json.loads(settings_file.read_text(encoding="utf-8"))
                self.assertTrue(saved_json.get("tutorial_seen"))

                # 3. Leitura subsequente reflete o arquivo em disco
                backend2 = AppBackend()
                status2 = backend2.get_tutorial_status()
                self.assertTrue(status2["seen"])

                # 4. Redefinir para False
                backend.set_tutorial_status(False)
                self.assertFalse(backend.get_tutorial_status()["seen"])
                saved_json2 = json.loads(settings_file.read_text(encoding="utf-8"))
                self.assertFalse(saved_json2.get("tutorial_seen"))

    def test_api_tutorial_status_wsgi_endpoint(self):
        """Testa o endpoint WSGI /api/tutorial_status via GET e POST."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_home = Path(tmpdir)
            with patch("pathlib.Path.home", return_value=fake_home):
                backend = AppBackend()
                wsgi_app = create_wsgi_app(backend, {})

                def _call(method: str, path: str, payload=None):
                    st, raw = _wsgi_call(wsgi_app, method, path, payload)
                    self.assertTrue(st.startswith("200"), f"Status {st}")
                    return json.loads(raw.decode("utf-8"))

                # 1. GET inicial
                res_get1 = _call("GET", "/api/tutorial_status")
                self.assertFalse(res_get1["seen"])

                # 2. POST com {} (leitura)
                res_post_read = _call("POST", "/api/tutorial_status", {})
                self.assertFalse(res_post_read["seen"])

                # 3. POST com {"seen": True} (gravação)
                res_post_set = _call("POST", "/api/tutorial_status", {"seen": True})
                self.assertTrue(res_post_set["seen"])

                # 4. GET após gravação
                res_get2 = _call("GET", "/api/tutorial_status")
                self.assertTrue(res_get2["seen"])

                # 5. POST com {} após gravação
                res_post_read2 = _call("POST", "/api/tutorial_status", {})
                self.assertTrue(res_post_read2["seen"])


if __name__ == "__main__":
    unittest.main()

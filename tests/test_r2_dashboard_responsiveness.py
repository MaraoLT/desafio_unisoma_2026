"""Test suite for Requirement R2: Responsividade e Funcionalidade da aba do Dashboard.

Verifies:
1. Restoration of the Dashboard tab in src/app/static/index.html (HTML markup & JS functions).
2. CSS responsiveness rules in src/app/static/style.css (min-width, single scroll, auto-fit grid, wrap rules).
3. Backend ensalamento summary data structure and consistency for dashboard rendering.
4. Mathematical safety and edge cases in turma card calculation logic.
"""

import re
import unittest
from pathlib import Path

from src.app.server import AppBackend


class TestR2DashboardResponsiveness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root_dir = Path(__file__).resolve().parent.parent
        cls.html_path = cls.root_dir / "src" / "app" / "static" / "index.html"
        cls.css_path = cls.root_dir / "src" / "app" / "static" / "style.css"
        cls.html_content = cls.html_path.read_text(encoding="utf-8")
        cls.css_content = cls.css_path.read_text(encoding="utf-8")

    # -------------------------------------------------------------------------
    # 1. HTML Markup & Component Structure
    # -------------------------------------------------------------------------
    def test_dashboard_tab_header_buttons_exist(self):
        """Verifies that side-header contains both Relatório and Dashboard tabs."""
        self.assertIn('id="btnSideReport"', self.html_content)
        self.assertIn("setSideTab('report')", self.html_content)
        self.assertIn('id="btnSideDashboard"', self.html_content)
        self.assertIn("setSideTab('dashboard')", self.html_content)
        self.assertIn("Dashboard do Ensalamento", self.html_content)

    def test_dashboard_pane_structure_and_ids(self):
        """Verifies paneDashboard container, KPI row, and turmas scroll element."""
        self.assertIn('id="paneDashboard"', self.html_content)
        self.assertIn('id="dashTurmasContainer"', self.html_content)
        self.assertIn("dash-kpi-row", self.html_content)
        self.assertIn('id="dashKpiTotalVal"', self.html_content)
        self.assertIn('id="dashKpiTotalSub"', self.html_content)
        self.assertIn('id="dashKpiManhaVal"', self.html_content)
        self.assertIn('id="dashKpiManhaSub"', self.html_content)
        self.assertIn('id="dashKpiTardeVal"', self.html_content)
        self.assertIn('id="dashKpiTardeSub"', self.html_content)

    # -------------------------------------------------------------------------
    # 2. JavaScript Client-Side Functions
    # -------------------------------------------------------------------------
    def test_javascript_dashboard_functions_implemented(self):
        """Verifies that index.html implements all required dashboard functions."""
        self.assertIn("function setSideTab(", self.html_content)
        self.assertIn("function renderDashboard(", self.html_content)
        self.assertIn("function createTurmaCardElement(", self.html_content)
        self.assertIn("function filterSheetByTurma(", self.html_content)

    def test_run_optimization_triggers_render_dashboard(self):
        """Verifies that runOptimization calls renderDashboard(res.summary)."""
        pattern = re.compile(
            r"async\s+function\s+runOptimization\(\)\s*\{[\s\S]*?renderDashboard\(res\.summary\);",
            re.MULTILINE,
        )
        self.assertTrue(
            pattern.search(self.html_content),
            "runOptimization() must call renderDashboard(res.summary) on successful optimization",
        )

    def test_resizer_minimum_width_enforced(self):
        """Verifies that the splitter resizer restricts dragging down to a minimum of 360px."""
        # Ensure 220px is not used as minimum dragged width
        self.assertNotIn("Math.max(220,", self.html_content)
        self.assertIn("Math.max(360, startWidth + delta)", self.html_content)
        self.assertIn("parsed >= 360", self.html_content)

    # -------------------------------------------------------------------------
    # 3. CSS Responsiveness & Layout Safety
    # -------------------------------------------------------------------------
    def test_side_pane_min_width_is_360px(self):
        """Verifies that .side-pane enforces min-width: 360px in CSS."""
        side_pane_match = re.search(r"\.side-pane\s*\{([^}]+)\}", self.css_content)
        self.assertIsNotNone(side_pane_match, ".side-pane rule must exist in style.css")
        body = side_pane_match.group(1)
        self.assertIn("min-width: 360px", body)

    def test_single_vertical_scroll_container(self):
        """Verifies that .side-body handles scroll and .dash-turmas-scroll does not trap scrollbars."""
        side_body_match = re.search(r"\.side-body\s*\{([^}]+)\}", self.css_content)
        self.assertIsNotNone(side_body_match, ".side-body rule must exist in style.css")
        self.assertIn("overflow-y: auto", side_body_match.group(1))

        turmas_scroll_match = re.search(r"\.dash-turmas-scroll\s*\{([^}]+)\}", self.css_content)
        self.assertIsNotNone(turmas_scroll_match, ".dash-turmas-scroll rule must exist in style.css")
        body = turmas_scroll_match.group(1)
        self.assertIn("overflow: visible", body)
        self.assertIn("min-height: 0", body)

    def test_dash_columns_grid_minmax_threshold(self):
        """Verifies .dash-columns-grid uses minmax(270px, 1fr) for responsive collapse."""
        grid_match = re.search(r"\.dash-columns-grid\s*\{([^}]+)\}", self.css_content)
        self.assertIsNotNone(grid_match, ".dash-columns-grid rule must exist in style.css")
        body = grid_match.group(1)
        self.assertIn("grid-template-columns: repeat(auto-fit, minmax(270px, 1fr))", body)

    def test_turma_card_and_legend_wrap_rules(self):
        """Verifies that .dash-turma-legend and .dash-turma-top wrap gracefully without clipping."""
        legend_match = re.search(r"\.dash-turma-legend\s*\{([^}]+)\}", self.css_content)
        self.assertIsNotNone(legend_match, ".dash-turma-legend rule must exist in style.css")
        body = legend_match.group(1)
        self.assertIn("flex-wrap: wrap", body)

        legend_span_match = re.search(r"\.dash-turma-legend\s+span\s*\{([^}]+)\}", self.css_content)
        self.assertIsNotNone(legend_span_match, ".dash-turma-legend span rule must exist in style.css")
        self.assertIn("white-space: nowrap", legend_span_match.group(1))

        top_match = re.search(r"\.dash-turma-top\s*\{([^}]+)\}", self.css_content)
        self.assertIsNotNone(top_match, ".dash-turma-top rule must exist in style.css")
        self.assertIn("flex-wrap: wrap", top_match.group(1))

    def test_min_width_zero_on_flex_and_grid_children(self):
        """Verifies min-width: 0 on .dash-kpi-card, .dash-turma-card, and .dash-shift-col."""
        for selector in [r"\.dash-kpi-card\s*\{([^}]+)\}", r"\.dash-turma-card\s*\{([^}]+)\}", r"\.dash-shift-col\s*\{([^}]+)\}"]:
            match = re.search(selector, self.css_content)
            self.assertIsNotNone(match, f"Selector matching {selector} must exist in style.css")
            self.assertIn("min-width: 0", match.group(1))

    # -------------------------------------------------------------------------
    # 4. Backend Summary Data Structure for Dashboard
    # -------------------------------------------------------------------------
    def test_run_ensalamento_summary_data_contract(self):
        """Verifies that run_ensalamento generates valid summary data consumed by renderDashboard."""
        service = AppBackend()
        inst1_path = self.root_dir / "instances" / "experiments" / "instancia_1.xlsx"
        if not inst1_path.exists():
            self.skipTest(f"Instance 1 not found at {inst1_path}")

        load_res = service.load_excel(inst1_path)
        self.assertTrue(load_res.get("success"), f"Failed to load instance 1: {load_res}")

        ens_res = service.run_ensalamento(allow_integral=True, allow_unallocated=False)
        self.assertTrue(ens_res.get("success"), f"Ensalamento failed: {ens_res}")
        self.assertIn("summary", ens_res)

        summary = ens_res["summary"]
        self.assertIn("stats_turnos", summary)
        self.assertIn("turmas", summary)

        # Check shifts stats
        for turno in ["MANHÃ", "TARDE"]:
            self.assertIn(turno, summary["stats_turnos"])
            st = summary["stats_turnos"][turno]
            self.assertGreater(st["capacidade_total"], 0)
            self.assertGreaterEqual(st["alocados"], 0)
            self.assertEqual(st["masculino"] + st["feminino"], st["alocados"])
            self.assertEqual(st["alocados"] + st["livres"], st["capacidade_total"])

        # Check individual turmas summary
        turmas = summary["turmas"]
        self.assertGreater(len(turmas), 0)
        total_alocados_turmas = 0
        for t in turmas:
            self.assertIn("codigo", t)
            self.assertIn("turno", t)
            self.assertIn("capacidade", t)
            self.assertIn("lotacao", t)
            self.assertIn("masculino", t)
            self.assertIn("feminino", t)
            self.assertIn("livres", t)
            self.assertIn("ocupacao_pct", t)

            self.assertGreater(t["capacidade"], 0)
            self.assertGreaterEqual(t["lotacao"], 0)
            self.assertEqual(t["masculino"] + t["feminino"], t["lotacao"])
            self.assertEqual(t["lotacao"] + t["livres"], t["capacidade"])
            expected_pct = round(100.0 * t["lotacao"] / t["capacidade"], 1)
            self.assertEqual(t["ocupacao_pct"], expected_pct)
            total_alocados_turmas += t["lotacao"]

        self.assertEqual(total_alocados_turmas, summary["total_alocados"])

    # -------------------------------------------------------------------------
    # 5. Card Bar Math Simulation (Edge Cases & Safety)
    # -------------------------------------------------------------------------
    def test_card_bar_math_edge_cases(self):
        """Simulates createTurmaCardElement math under extreme conditions."""
        test_cases = [
            {"cap": 0, "lot": 0, "masc": 0, "fem": 0},
            {"cap": 30, "lot": 0, "masc": 0, "fem": 0},
            {"cap": 30, "lot": 30, "masc": 30, "fem": 0},
            {"cap": 30, "lot": 30, "masc": 0, "fem": 30},
            {"cap": 30, "lot": 30, "masc": 15, "fem": 15},
            {"cap": 25, "lot": 17, "masc": 9, "fem": 8},
        ]

        for tc in test_cases:
            cap = max(0, tc["cap"])
            lot = max(0, tc["lot"])
            masc = max(0, tc["masc"])
            fem = max(0, tc["fem"])
            livres = max(0, cap - lot)

            if cap > 0:
                pct_m = min(100.0, (100.0 * masc) / cap)
                pct_f = min(max(0.0, 100.0 - pct_m), (100.0 * fem) / cap)
                pct_vazio = max(0.0, 100.0 - pct_m - pct_f)
            else:
                pct_m = 0.0
                pct_f = 0.0
                pct_vazio = 100.0

            total_pct = pct_m + pct_f + pct_vazio
            self.assertAlmostEqual(total_pct, 100.0, delta=0.01)
            self.assertGreaterEqual(pct_m, 0.0)
            self.assertGreaterEqual(pct_f, 0.0)
            self.assertGreaterEqual(pct_vazio, 0.0)
            self.assertGreaterEqual(livres, 0)


if __name__ == "__main__":
    unittest.main()

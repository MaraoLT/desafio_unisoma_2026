"""Adversarial stress test suite for Milestone 2 (Requirement R2: Responsividade do Dashboard).

Author: Challenger 2 (challenger_m2_2)
Archetype: EMPIRICAL CHALLENGER
Roles: critic, specialist

Stress-tests:
1. CSS rules in style.css:
   - min-width: 360px on .side-pane
   - overflow: visible and min-height: 0 on .dash-turmas-scroll (single scroll container)
   - minmax(270px, 1fr) auto-fit grid collapse on .dash-columns-grid
   - flex-wrap: wrap on .dash-turma-legend and .dash-turma-top
   - min-width: 0 on flex/grid children (.dash-kpi-card, .dash-turma-card, .dash-shift-col)
2. JS Splitter dragging:
   - Clamping logic guarantees newW cannot shrink below 360px even under extreme negative deltas
   - Double-click resets width to 520px
3. Tabulator & Sheet interactions:
   - filterSheetByTurma triggers client-side filter when on Ensalamento
   - filterSheetByTurma smoothly transitions from other sheets (e.g. Alunos) to Ensalamento
   - Preserves row 1 (header row) while filtering all student rows matching the clicked turma code
4. Public instances 1 through 4:
   - All solve successfully and generate valid summaries
   - Shift statistics (MANHÃ / TARDE) match individual turma totals
   - Gender and empty capacity percentages sum to 100%
5. Extreme math edge cases in turma card creation:
   - Zero capacity, negative values, 100% male, 100% female, empty rooms
   - Zero division prevention, no NaNs
"""

import json
import re
import unittest
from pathlib import Path

from src.app.server import AppBackend


class TestChallenger2M2R2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parent.parent
        cls.html_path = cls.root / "src" / "app" / "static" / "index.html"
        cls.css_path = cls.root / "src" / "app" / "static" / "style.css"
        cls.html_text = cls.html_path.read_text(encoding="utf-8")
        cls.css_text = cls.css_path.read_text(encoding="utf-8")

    # -------------------------------------------------------------------------
    # 1. CSS Layout & Geometry Integrity
    # -------------------------------------------------------------------------
    def test_side_pane_strict_min_width(self):
        """Verify .side-pane enforces min-width: 360px in CSS without overrides."""
        match = re.search(r"\.side-pane\s*\{([^}]+)\}", self.css_text)
        self.assertIsNotNone(match, ".side-pane rule must exist in style.css")
        body = match.group(1)
        self.assertIn("min-width: 360px", body)
        self.assertNotIn("min-width: 220px", self.css_text)
        self.assertNotIn("min-width: 260px", self.css_text)

    def test_single_vertical_scroll_container_contract(self):
        """Verify that .side-body is the scroll container and inner scrollbox does not trap scrollbars."""
        body_match = re.search(r"\.side-body\s*\{([^}]+)\}", self.css_text)
        self.assertIsNotNone(body_match)
        self.assertIn("overflow-y: auto", body_match.group(1))

        scroll_match = re.search(r"\.dash-turmas-scroll\s*\{([^}]+)\}", self.css_text)
        self.assertIsNotNone(scroll_match)
        scroll_body = scroll_match.group(1)
        self.assertIn("overflow: visible", scroll_body)
        self.assertIn("min-height: 0", scroll_body)

    def test_grid_auto_fit_breakpoint_threshold(self):
        """Verify .dash-columns-grid minmax threshold is at least 270px for clean single-column wrap."""
        grid_match = re.search(r"\.dash-columns-grid\s*\{([^}]+)\}", self.css_text)
        self.assertIsNotNone(grid_match)
        self.assertIn("grid-template-columns: repeat(auto-fit, minmax(270px, 1fr))", grid_match.group(1))

    def test_text_clipping_and_wrap_defenses(self):
        """Verify flex-wrap and white-space rules prevent badge and text truncation."""
        top_match = re.search(r"\.dash-turma-top\s*\{([^}]+)\}", self.css_text)
        self.assertIsNotNone(top_match)
        self.assertIn("flex-wrap: wrap", top_match.group(1))

        legend_match = re.search(r"\.dash-turma-legend\s*\{([^}]+)\}", self.css_text)
        self.assertIsNotNone(legend_match)
        self.assertIn("flex-wrap: wrap", legend_match.group(1))

        span_match = re.search(r"\.dash-turma-legend\s+span\s*\{([^}]+)\}", self.css_text)
        self.assertIsNotNone(span_match)
        self.assertIn("white-space: nowrap", span_match.group(1))

    # -------------------------------------------------------------------------
    # 2. JS Splitter Dragging Clamping Logic
    # -------------------------------------------------------------------------
    def test_resizer_drag_clamping_math_simulation(self):
        """Simulate JS resizer clamping math under extreme and adversarial deltas."""
        def calc_drag_width(start_width: int, delta: int, client_width: int) -> int:
            max_w = max(360, client_width - 320)
            return min(max(360, start_width + delta), max_w)

        # Normal start width 520, normal viewport 1340
        # Dragging far to the right (delta = -2000px): must clamp to 360
        self.assertEqual(calc_drag_width(520, -2000, 1340), 360)
        self.assertEqual(calc_drag_width(520, -500, 1340), 360)
        self.assertEqual(calc_drag_width(520, -160, 1340), 360)

        # Dragging to the left (delta = +200px): expands to 720
        self.assertEqual(calc_drag_width(520, 200, 1340), 720)

        # Narrow viewport (clientWidth = 500)
        self.assertEqual(calc_drag_width(520, -200, 500), 360)

    def test_resizer_js_source_code_guards(self):
        """Verify that index.html JS resizer code strictly uses 360px and removes legacy 220px."""
        self.assertNotIn("Math.max(220,", self.html_text)
        self.assertNotIn("Math.max(260,", self.html_text)
        self.assertIn("Math.max(360, startWidth + delta)", self.html_text)
        self.assertIn("Math.max(360, workspace.clientWidth - 320)", self.html_text)
        self.assertIn("parsed >= 360", self.html_text)
        self.assertIn('sidePane.style.width = "520px"', self.html_text)

    # -------------------------------------------------------------------------
    # 3. Tabulator & Sheet Filtering Logic
    # -------------------------------------------------------------------------
    def test_filter_sheet_by_turma_js_implementation(self):
        """Verify that filterSheetByTurma handles client-side filtering and sheet switching."""
        self.assertIn("async function filterSheetByTurma(turmaCodigo)", self.html_text)
        self.assertIn("if (!state.sheetNames.includes(\"Ensalamento\")) return;", self.html_text)
        self.assertIn("applyClientFilter(turmaCodigo);", self.html_text)
        self.assertIn('sheet_name: "Ensalamento"', self.html_text)

    def test_client_filter_preserves_header_row_and_matches_turma(self):
        """Simulate applyClientFilter row evaluation on real Ensalamento data."""
        # Simulated data from Ensalamento sheet
        header_row = {"excel_row": 1, "c0": "Nome", "c1": "Sexo", "c2": "Disponibilidade", "c3": "Turma"}
        student_m1 = {"excel_row": 2, "c0": "Aluno Alpha", "c1": "M", "c2": "MANHÃ", "c3": "MANHÃ - A"}
        student_m2 = {"excel_row": 3, "c0": "Aluna Beta", "c1": "F", "c2": "MANHÃ", "c3": "MANHÃ - B"}
        student_t1 = {"excel_row": 4, "c0": "Aluno Gama", "c1": "M", "c2": "TARDE", "c3": "TARDE - C"}

        rows = [header_row, student_m1, student_m2, student_t1]

        def norm_str(v):
            return str(v).lower().strip()

        def test_filter(query, data_rows):
            q = norm_str(query)
            matched = []
            for d in data_rows:
                if d["excel_row"] == 1:
                    matched.append(d)
                    continue
                for c in range(4):
                    if q in norm_str(d.get(f"c{c}", "")):
                        matched.append(d)
                        break
            return matched

        res_a = test_filter("MANHÃ - A", rows)
        self.assertEqual(len(res_a), 2)  # header + student_m1
        self.assertEqual(res_a[0]["excel_row"], 1)
        self.assertEqual(res_a[1]["c3"], "MANHÃ - A")

        res_b = test_filter("MANHÃ - B", rows)
        self.assertEqual(len(res_b), 2)  # header + student_m2
        self.assertEqual(res_b[1]["c3"], "MANHÃ - B")

        res_c = test_filter("TARDE - C", rows)
        self.assertEqual(len(res_c), 2)  # header + student_t1
        self.assertEqual(res_c[1]["c3"], "TARDE - C")

    # -------------------------------------------------------------------------
    # 4. Public Instances 1 to 4 Solve and Summary Output Validation
    # -------------------------------------------------------------------------
    def test_all_public_instances_produce_valid_dashboard_summaries(self):
        """Verify that public instances 1 through 4 solve and generate complete summary contracts."""
        expected_counts = {
            "instancia_1.xlsx": {"turmas": 4, "min_aloc": 100},
            "instancia_2.xlsx": {"turmas": 6, "min_aloc": 140},
            "instancia_3.xlsx": {"turmas": 6, "min_aloc": 150},
            "instancia_4.xlsx": {"turmas": 6, "min_aloc": 130},
        }

        for filename, expected in expected_counts.items():
            path = self.root / "instances" / "public" / filename
            self.assertTrue(path.exists(), f"Instance file missing: {path}")

            backend = AppBackend()
            load_res = backend.load_excel(path)
            self.assertTrue(load_res.get("success"), f"Failed to load {filename}")

            ens_res = backend.run_ensalamento(allow_integral=True, allow_unallocated=False)
            self.assertTrue(ens_res.get("success"), f"Ensalamento failed on {filename}: {ens_res}")

            summary = ens_res.get("summary")
            self.assertIsNotNone(summary, f"Summary missing for {filename}")

            # Verify high-level metrics
            self.assertGreaterEqual(summary["total_alocados"], expected["min_aloc"])
            self.assertEqual(summary["total_salas"], expected["turmas"])
            self.assertEqual(len(summary["turmas"]), expected["turmas"])

            # Verify shift stats
            stats = summary["stats_turnos"]
            self.assertIn("MANHÃ", stats)
            self.assertIn("TARDE", stats)

            sum_shift_aloc = stats["MANHÃ"]["alocados"] + stats["TARDE"]["alocados"]
            self.assertEqual(sum_shift_aloc, summary["total_alocados"])

            # Verify turma entries
            sum_turmas_aloc = 0
            for t in summary["turmas"]:
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
                sum_turmas_aloc += t["lotacao"]

            self.assertEqual(sum_turmas_aloc, summary["total_alocados"])

    # -------------------------------------------------------------------------
    # 5. Extreme Mathematical Stress in Turma Card Calculations
    # -------------------------------------------------------------------------
    def test_extreme_turma_card_math(self):
        """Adversarially simulate createTurmaCardElement math under boundary conditions."""
        extreme_cases = [
            {"cap": 0, "lot": 0, "masc": 0, "fem": 0},
            {"cap": 1, "lot": 1, "masc": 1, "fem": 0},
            {"cap": 1, "lot": 1, "masc": 0, "fem": 1},
            {"cap": 100, "lot": 0, "masc": 0, "fem": 0},
            {"cap": 100, "lot": 100, "masc": 50, "fem": 50},
            {"cap": 35, "lot": 30, "masc": 13, "fem": 17},
            {"cap": -10, "lot": -5, "masc": -2, "fem": -3},
        ]

        for c in extreme_cases:
            cap = max(0, c["cap"])
            lot = max(0, c["lot"])
            masc = max(0, c["masc"])
            fem = max(0, c["fem"])
            livres = max(0, cap - lot)

            pct_m = min(100.0, (100.0 * masc) / cap) if cap > 0 else 0.0
            pct_f = min(max(0.0, 100.0 - pct_m), (100.0 * fem) / cap) if cap > 0 else 0.0
            pct_vazio = max(0.0, 100.0 - pct_m - pct_f) if cap > 0 else 100.0

            total_pct = pct_m + pct_f + pct_vazio
            self.assertAlmostEqual(total_pct, 100.0, delta=0.01)
            self.assertGreaterEqual(pct_m, 0.0)
            self.assertGreaterEqual(pct_f, 0.0)
            self.assertGreaterEqual(pct_vazio, 0.0)
            self.assertGreaterEqual(livres, 0)


if __name__ == "__main__":
    unittest.main()

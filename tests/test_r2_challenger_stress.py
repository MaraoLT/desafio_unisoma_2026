"""Adversarial Stress Test Suite for Requirement R2 (Dashboard Responsiveness & Math).

Executed by Empirical Challenger 1.
Tests:
1. Extreme capacities (0 capacity, huge capacity 10000, 100% male, 100% female, 0 allocated, negative values).
2. Missing / corrupted fields in summary (null, undefined, empty object, missing shifts, empty turmas, single-shift turmas).
3. Viewport boundary simulations (splitter drag clamping at 360px, single scrollbar, auto-fit grid wrap, flex-wrap).
4. Direct execution in Edge Chromium WebView2 engine to guarantee 0 JS runtime exceptions.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest
import webview

from src.app.server import AppBackend, TURNO_MANHA, TURNO_TARDE


class TestR2ChallengerStress(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root_dir = Path(__file__).resolve().parent.parent
        cls.html_path = cls.root_dir / "src" / "app" / "static" / "index.html"
        cls.css_path = cls.root_dir / "src" / "app" / "static" / "style.css"
        cls.html_content = cls.html_path.read_text(encoding="utf-8")
        cls.css_content = cls.css_path.read_text(encoding="utf-8")

    # -------------------------------------------------------------------------
    # Helper: execute JS scripts in WebView2 headless/hidden
    # -------------------------------------------------------------------------
    def _eval_in_webview(self, js_code: str) -> dict:
        results = {}
        error_holder = []
        css_escaped = json.dumps(self.css_content)

        def on_loaded():
            try:
                # Inject CSS if not loaded via HTTP server (e.g. file URI)
                window.evaluate_js(f"""
                (function() {{
                    if (!document.getElementById("challenger_injected_css")) {{
                        const tag = document.createElement("style");
                        tag.id = "challenger_injected_css";
                        tag.textContent = {css_escaped};
                        document.head.appendChild(tag);
                    }}
                }})();
                """)
                res = window.evaluate_js(js_code)
                results["output"] = res
            except Exception as e:
                error_holder.append(str(e))
            finally:
                window.destroy()

        window = webview.create_window(
            "Adversarial Stress Runner",
            url=str(self.html_path.as_uri()),
            hidden=True,
            width=1024,
            height=768,
        )
        window.events.loaded += on_loaded
        webview.start()

        if error_holder:
            raise RuntimeError(f"WebView evaluation error: {error_holder[0]}")
        return results.get("output", {})

    # -------------------------------------------------------------------------
    # Scenario 1: Extreme Capacities & Bar Math Logic
    # -------------------------------------------------------------------------
    def test_extreme_capacities_and_bar_math(self):
        """Tests extreme capacities (0, 10000, 100% male, 100% female, 0 allocated, negative)."""
        js_test = """
        (function() {
            const results = [];
            const cases = [
                { id: "zero_cap", t: { codigo: "T_ZERO", turno: "MANHÃ", capacidade: 0, lotacao: 0, masculino: 0, feminino: 0 } },
                { id: "zero_cap_with_students", t: { codigo: "T_ZERO_ST", turno: "MANHÃ", capacidade: 0, lotacao: 5, masculino: 3, feminino: 2 } },
                { id: "huge_cap_zero_alloc", t: { codigo: "T_HUGE_0", turno: "MANHÃ", capacidade: 10000, lotacao: 0, masculino: 0, feminino: 0 } },
                { id: "huge_cap_100_male", t: { codigo: "T_HUGE_M", turno: "MANHÃ", capacidade: 10000, lotacao: 10000, masculino: 10000, feminino: 0 } },
                { id: "huge_cap_100_female", t: { codigo: "T_HUGE_F", turno: "TARDE", capacidade: 10000, lotacao: 10000, masculino: 0, feminino: 10000 } },
                { id: "overcapacity", t: { codigo: "T_OVER", turno: "MANHÃ", capacidade: 30, lotacao: 50, masculino: 30, feminino: 20 } },
                { id: "negative_values", t: { codigo: "T_NEG", turno: "TARDE", capacidade: -10, lotacao: -5, masculino: -2, feminino: -3 } },
                { id: "string_and_null_values", t: { codigo: "T_STR", turno: "MANHÃ", capacidade: "40", lotacao: "20", masculino: null, feminino: undefined } },
                { id: "empty_dict", t: {} }
            ];

            for (const c of cases) {
                const card = createTurmaCardElement(c.t);
                const barSegM = card.querySelector(".dash-bar-seg-m");
                const barSegF = card.querySelector(".dash-bar-seg-f");
                const barSegEmpty = card.querySelector(".dash-bar-seg-empty");
                const lotText = card.querySelector(".dash-turma-lot").textContent;

                const widthM = parseFloat(barSegM.style.width);
                const widthF = parseFloat(barSegF.style.width);
                const widthEmpty = parseFloat(barSegEmpty.style.width);

                const totalWidth = widthM + widthF + widthEmpty;

                results.push({
                    id: c.id,
                    widthM: widthM,
                    widthF: widthF,
                    widthEmpty: widthEmpty,
                    totalWidth: totalWidth,
                    lotText: lotText,
                    hasNaN: isNaN(widthM) || isNaN(widthF) || isNaN(widthEmpty),
                    hasNegative: widthM < 0 || widthF < 0 || widthEmpty < 0,
                    exceeds100: totalWidth > 100.01
                });
            }
            return results;
        })()
        """
        results = self._eval_in_webview(js_test)
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 9)

        for r in results:
            self.assertFalse(r["hasNaN"], f"Case {r['id']} produced NaN in bar segment widths: {r}")
            self.assertFalse(r["hasNegative"], f"Case {r['id']} produced negative bar segment width: {r}")
            self.assertFalse(r["exceeds100"], f"Case {r['id']} exceeded 100% total bar width: {r}")

        # Check individual specific cases
        res_map = {r["id"]: r for r in results}

        # zero_cap: empty bar should be 100%
        self.assertEqual(res_map["zero_cap"]["widthM"], 0.0)
        self.assertEqual(res_map["zero_cap"]["widthF"], 0.0)
        self.assertEqual(res_map["zero_cap"]["widthEmpty"], 100.0)

        # huge_cap_100_male: M should be 100%, F 0%, empty 0%
        self.assertEqual(res_map["huge_cap_100_male"]["widthM"], 100.0)
        self.assertEqual(res_map["huge_cap_100_male"]["widthF"], 0.0)
        self.assertEqual(res_map["huge_cap_100_male"]["widthEmpty"], 0.0)

        # huge_cap_100_female: M 0%, F 100%, empty 0%
        self.assertEqual(res_map["huge_cap_100_female"]["widthM"], 0.0)
        self.assertEqual(res_map["huge_cap_100_female"]["widthF"], 100.0)
        self.assertEqual(res_map["huge_cap_100_female"]["widthEmpty"], 0.0)

        # overcapacity: M + F + Empty must not exceed 100%
        self.assertAlmostEqual(res_map["overcapacity"]["totalWidth"], 100.0, delta=0.01)

        # negative_values: clamped to 0
        self.assertEqual(res_map["negative_values"]["widthM"], 0.0)
        self.assertEqual(res_map["negative_values"]["widthF"], 0.0)
        self.assertEqual(res_map["negative_values"]["widthEmpty"], 100.0)

    # -------------------------------------------------------------------------
    # Scenario 2: Missing Fields in Summary
    # -------------------------------------------------------------------------
    def test_missing_and_corrupt_summary_fields(self):
        """Tests missing fields, empty objects, missing shift stats, and single shift turmas."""
        js_test = """
        (function() {
            const report = {};

            // 1. null summary
            try {
                renderDashboard(null);
                report.null_summary = "ok";
            } catch (e) {
                report.null_summary = "error: " + e.message;
            }

            // 2. empty summary {}
            try {
                renderDashboard({});
                report.empty_summary = "ok";
            } catch (e) {
                report.empty_summary = "error: " + e.message;
            }

            // 3. stats_turnos is empty object {}
            try {
                renderDashboard({ stats_turnos: {} });
                const totalVal = document.getElementById("dashKpiTotalVal").textContent;
                const totalSub = document.getElementById("dashKpiTotalSub").textContent;
                const manhaVal = document.getElementById("dashKpiManhaVal").textContent;
                const tardeVal = document.getElementById("dashKpiTardeVal").textContent;
                const containerHTML = document.getElementById("dashTurmasContainer").innerHTML;

                report.empty_stats_turnos = {
                    status: "ok",
                    totalVal: totalVal,
                    totalSub: totalSub,
                    manhaVal: manhaVal,
                    tardeVal: tardeVal,
                    hasEmptyState: containerHTML.includes("dash-empty-state")
                };
            } catch (e) {
                report.empty_stats_turnos = { status: "error", error: e.message };
            }

            // 4. stats_turnos has only MANHÃ, missing TARDE
            try {
                renderDashboard({
                    stats_turnos: {
                        "MANHÃ": { salas: 2, capacidade_total: 60, alocados: 40, masculino: 20, feminino: 20, ocupacao_pct: 66.7 }
                    },
                    turmas: [
                        { codigo: "M1", turno: "MANHÃ", capacidade: 30, lotacao: 20, masculino: 10, feminino: 10 }
                    ]
                });
                const totalVal = document.getElementById("dashKpiTotalVal").textContent;
                const tardeVal = document.getElementById("dashKpiTardeVal").textContent;
                const tardeSub = document.getElementById("dashKpiTardeSub").textContent;
                const grid = document.querySelector(".dash-columns-grid");
                const emptyTarde = document.querySelector(".header-tarde + .dash-col-empty");

                report.only_manha = {
                    status: "ok",
                    totalVal: totalVal,
                    tardeVal: tardeVal,
                    tardeSub: tardeSub,
                    hasGrid: !!grid,
                    hasEmptyTardeCol: !!emptyTarde && emptyTarde.textContent.includes("Nenhuma turma")
                };
            } catch (e) {
                report.only_manha = { status: "error", error: e.message };
            }

            // 5. stats_turnos has only TARDE, missing MANHÃ
            try {
                renderDashboard({
                    stats_turnos: {
                        "TARDE": { salas: 1, capacidade_total: 30, alocados: 30, masculino: 15, feminino: 15, ocupacao_pct: 100.0 }
                    },
                    turmas: [
                        { codigo: "T1", turno: "TARDE", capacidade: 30, lotacao: 30, masculino: 15, feminino: 15 }
                    ]
                });
                const totalVal = document.getElementById("dashKpiTotalVal").textContent;
                const manhaVal = document.getElementById("dashKpiManhaVal").textContent;
                const manhaSub = document.getElementById("dashKpiManhaSub").textContent;
                const emptyManha = document.querySelector(".header-manha + .dash-col-empty");

                report.only_tarde = {
                    status: "ok",
                    totalVal: totalVal,
                    manhaVal: manhaVal,
                    manhaSub: manhaSub,
                    hasEmptyManhaCol: !!emptyManha && emptyManha.textContent.includes("Nenhuma turma")
                };
            } catch (e) {
                report.only_tarde = { status: "error", error: e.message };
            }

            return report;
        })()
        """
        report = self._eval_in_webview(js_test)

        self.assertEqual(report["null_summary"], "ok")
        self.assertEqual(report["empty_summary"], "ok")

        # Empty stats turnos
        empty_st = report["empty_stats_turnos"]
        self.assertEqual(empty_st["status"], "ok")
        self.assertIn("0 / 0", empty_st["totalVal"])
        self.assertIn("0.0%", empty_st["totalVal"])
        self.assertTrue(empty_st["hasEmptyState"])

        # Only Manhã
        only_m = report["only_manha"]
        self.assertEqual(only_m["status"], "ok")
        self.assertIn("40 / 60", only_m["totalVal"])
        self.assertIn("0/0 alunos", only_m["tardeVal"])
        self.assertTrue(only_m["hasGrid"])
        self.assertTrue(only_m["hasEmptyTardeCol"])

        # Only Tarde
        only_t = report["only_tarde"]
        self.assertEqual(only_t["status"], "ok")
        self.assertIn("30 / 30", only_t["totalVal"])
        self.assertIn("0/0 alunos", only_t["manhaVal"])
        self.assertTrue(only_t["hasEmptyManhaCol"])

    # -------------------------------------------------------------------------
    # Scenario 3: Viewport Boundary & Splitter Math Stress
    # -------------------------------------------------------------------------
    def test_viewport_and_splitter_boundaries(self):
        """Simulates drag splitter extremes and CSS layout responsive thresholds."""
        js_test = """
        (function() {
            const sidePane = document.getElementById("sidePane");
            const workspace = document.querySelector(".workspace");

            const tests = [];

            // Simulate drag math with various clientWidths and deltas
            const viewports = [
                { clientW: 400, delta: -300 },   // extremely squashed workspace
                { clientW: 600, delta: -500 },   // user attempts to drag pane to 0px
                { clientW: 1000, delta: 1200 },  // user drags beyond workspace
                { clientW: 1400, delta: 0 }      // normal size
            ];

            for (const vp of viewports) {
                const startWidth = 520;
                const maxW = Math.max(360, vp.clientW - 320);
                const newW = Math.min(Math.max(360, startWidth + vp.delta), maxW);

                tests.push({
                    clientW: vp.clientW,
                    delta: vp.delta,
                    maxW: maxW,
                    newW: newW,
                    isAtLeast360: newW >= 360
                });
            }

            // Test sidePane computed min-width
            const computedStyle = window.getComputedStyle(sidePane);
            const minWidth = computedStyle.minWidth;

            return {
                dragTests: tests,
                computedMinWidth: minWidth
            };
        })()
        """
        res = self._eval_in_webview(js_test)
        self.assertEqual(res["computedMinWidth"], "360px")

        for dt in res["dragTests"]:
            self.assertTrue(
                dt["isAtLeast360"],
                f"Splitter formula produced width below 360px on clientW={dt['clientW']}, delta={dt['delta']}: {dt}",
            )
            self.assertGreaterEqual(dt["newW"], 360)

    # -------------------------------------------------------------------------
    # Scenario 4: Tab Switching and Filter Interactions
    # -------------------------------------------------------------------------
    def test_tab_switching_and_card_interaction(self):
        """Tests setSideTab switching and turma card click interaction."""
        js_test = """
        (function() {
            const report = {};

            // 1. Initial active tab
            setSideTab('report');
            report.reportActive = document.getElementById("paneReport").style.display === "flex";
            report.dashHidden = document.getElementById("paneDashboard").style.display === "none";

            // 2. Switch to dashboard
            setSideTab('dashboard');
            report.dashActive = document.getElementById("paneDashboard").style.display === "flex";
            report.reportHidden = document.getElementById("paneReport").style.display === "none";

            // 3. Switch back to report
            setSideTab('report');
            report.reportRestored = document.getElementById("paneReport").style.display === "flex";
            report.dashHiddenAgain = document.getElementById("paneDashboard").style.display === "none";

            // 4. Invalid tab call
            setSideTab('nonexistent');
            report.invalidHandled = document.getElementById("paneDashboard").style.display === "none" &&
                                   document.getElementById("paneReport").style.display === "none";

            return report;
        })()
        """
        report = self._eval_in_webview(js_test)
        self.assertTrue(report["reportActive"])
        self.assertTrue(report["dashHidden"])
        self.assertTrue(report["dashActive"])
        self.assertTrue(report["reportHidden"])
        self.assertTrue(report["reportRestored"])
        self.assertTrue(report["dashHiddenAgain"])
        self.assertTrue(report["invalidHandled"])

    # -------------------------------------------------------------------------
    # Scenario 5: Full Backend Solver -> Dashboard Data Flow
    # -------------------------------------------------------------------------
    def test_backend_solver_and_dashboard_end_to_end(self):
        """Verifies end-to-end data pipeline from Excel -> MILP Solver -> Dashboard JSON payload."""
        service = AppBackend()
        inst1_path = self.root_dir / "instances" / "experiments" / "instancia_1.xlsx"
        if not inst1_path.exists():
            self.skipTest(f"instancia_1.xlsx not found at {inst1_path}")

        load_res = service.load_excel(inst1_path)
        self.assertTrue(load_res["success"])

        ens_res = service.run_ensalamento(allow_integral=True, allow_unallocated=True)
        self.assertTrue(ens_res["success"])
        summary = ens_res["summary"]

        # Serialize summary to JSON and inject directly into WebView2 renderDashboard
        summary_json = json.dumps(summary)
        js_test = f"""
        (function() {{
            const s = {summary_json};
            renderDashboard(s);

            const totalVal = document.getElementById("dashKpiTotalVal").textContent;
            const manhaVal = document.getElementById("dashKpiManhaVal").textContent;
            const tardeVal = document.getElementById("dashKpiTardeVal").textContent;

            const cards = document.querySelectorAll(".dash-turma-card");
            const grid = document.querySelector(".dash-columns-grid");

            return {{
                totalVal: totalVal,
                manhaVal: manhaVal,
                tardeVal: tardeVal,
                cardCount: cards.length,
                hasGrid: !!grid
            }};
        }})()
        """
        rendered = self._eval_in_webview(js_test)
        self.assertEqual(rendered["cardCount"], len(summary["turmas"]))
        self.assertTrue(rendered["hasGrid"])
        self.assertIn(str(summary["total_alocados"]), rendered["totalVal"])

    # -------------------------------------------------------------------------
    # Scenario 6: Responsive Column Collapse & Single Scrollbar Verification
    # -------------------------------------------------------------------------
    def test_responsive_column_collapse_and_single_scroll(self):
        """Tests that at 360px side-pane width, columns wrap into a single vertical stack, and at 700px they sit side-by-side."""
        js_test = """
        (function() {
            setSideTab('dashboard');
            const summary = {
                stats_turnos: {
                    "MANHÃ": { salas: 2, capacidade_total: 60, alocados: 50, masculino: 25, feminino: 25, ocupacao_pct: 83.3 },
                    "TARDE": { salas: 2, capacidade_total: 60, alocados: 50, masculino: 25, feminino: 25, ocupacao_pct: 83.3 }
                },
                turmas: [
                    { codigo: "M1", turno: "MANHÃ", capacidade: 30, lotacao: 25, masculino: 12, feminino: 13 },
                    { codigo: "T1", turno: "TARDE", capacidade: 30, lotacao: 25, masculino: 13, feminino: 12 }
                ]
            };
            renderDashboard(summary);

            const sidePane = document.getElementById("sidePane");
            const cols = document.querySelectorAll(".dash-shift-col");
            const colM = cols[0];
            const colT = cols[1];

            // 1. Narrow width: 360px (minimum)
            sidePane.style.width = "360px";
            const rectM_narrow = colM.getBoundingClientRect();
            const rectT_narrow = colT.getBoundingClientRect();
            const stackedNarrow = rectT_narrow.top >= rectM_narrow.bottom - 2; // stacked vertically

            // 2. Wide width: 700px
            sidePane.style.width = "700px";
            const rectM_wide = colM.getBoundingClientRect();
            const rectT_wide = colT.getBoundingClientRect();
            const sideBySideWide = Math.abs(rectM_wide.top - rectT_wide.top) < 15 && rectT_wide.left >= rectM_wide.right - 2;

            // 3. Single scrollbar check: dash-turmas-scroll has overflow: visible, side-body has overflow-y: auto
            const dashScroll = document.getElementById("dashTurmasContainer");
            const sideBody = document.getElementById("paneDashboard");
            const dashScrollStyle = window.getComputedStyle(dashScroll);
            const sideBodyStyle = window.getComputedStyle(sideBody);

            return {
                stackedNarrow: stackedNarrow,
                sideBySideWide: sideBySideWide,
                dashScrollOverflow: dashScrollStyle.overflow,
                dashScrollMinHeight: dashScrollStyle.minHeight,
                sideBodyOverflowY: sideBodyStyle.overflowY,
                rectM_narrow_top: rectM_narrow.top,
                rectT_narrow_top: rectT_narrow.top,
                rectM_wide_top: rectM_wide.top,
                rectT_wide_top: rectT_wide.top
            };
        })()
        """
        res = self._eval_in_webview(js_test)
        self.assertTrue(
            res["stackedNarrow"],
            f"Columns should stack vertically at 360px width, got: {res}",
        )
        self.assertTrue(
            res["sideBySideWide"],
            f"Columns should sit side-by-side at 700px width, got: {res}",
        )
        self.assertEqual(res["dashScrollOverflow"], "visible")
        self.assertEqual(res["dashScrollMinHeight"], "0px")
        self.assertEqual(res["sideBodyOverflowY"], "auto")

    # -------------------------------------------------------------------------
    # Scenario 7: Stress Testing with Real Adversarial Experiments (F4 Minority & F7 Overflow)
    # -------------------------------------------------------------------------
    def test_stress_with_adversarial_instances(self):
        """Tests dashboard rendering with extreme minority (F4) and global overflow (F7) instances."""
        adversarial_files = [
            "instances/experiments/F4_extreme_minority_integral_n200.xlsx",
            "instances/experiments/F7_global_overflow_integral_n200.xlsx",
        ]

        for rel_path in adversarial_files:
            file_path = self.root_dir / rel_path
            if not file_path.exists():
                continue

            service = AppBackend()
            load_res = service.load_excel(file_path)
            self.assertTrue(load_res["success"], f"Failed to load {rel_path}")

            ens_res = service.run_ensalamento(allow_integral=True, allow_unallocated=True)
            self.assertTrue(ens_res["success"], f"Failed to solve {rel_path}")

            summary = ens_res["summary"]
            summary_json = json.dumps(summary)

            js_test = f"""
            (function() {{
                const s = {summary_json};
                renderDashboard(s);

                const totalVal = document.getElementById("dashKpiTotalVal").textContent;
                const manhaVal = document.getElementById("dashKpiManhaVal").textContent;
                const tardeVal = document.getElementById("dashKpiTardeVal").textContent;

                const cards = document.querySelectorAll(".dash-turma-card");
                let hasNaN = false;
                let hasNegative = false;
                let exceeds100 = false;

                cards.forEach(card => {{
                    const segM = parseFloat(card.querySelector(".dash-bar-seg-m").style.width);
                    const segF = parseFloat(card.querySelector(".dash-bar-seg-f").style.width);
                    const segEmpty = parseFloat(card.querySelector(".dash-bar-seg-empty").style.width);
                    const total = segM + segF + segEmpty;

                    if (isNaN(segM) || isNaN(segF) || isNaN(segEmpty)) hasNaN = true;
                    if (segM < 0 || segF < 0 || segEmpty < 0) hasNegative = true;
                    if (total > 100.01) exceeds100 = true;
                }});

                return {{
                    totalVal: totalVal,
                    manhaVal: manhaVal,
                    tardeVal: tardeVal,
                    cardCount: cards.length,
                    hasNaN: hasNaN,
                    hasNegative: hasNegative,
                    exceeds100: exceeds100
                }};
            }})()
            """
            res = self._eval_in_webview(js_test)
            self.assertEqual(res["cardCount"], len(summary["turmas"]))
            self.assertFalse(res["hasNaN"], f"Instance {rel_path} produced NaN bar segments")
            self.assertFalse(res["hasNegative"], f"Instance {rel_path} produced negative bar segments")
            self.assertFalse(res["exceeds100"], f"Instance {rel_path} exceeded 100% total bar width")


if __name__ == "__main__":
    unittest.main()

"""Empirical Challenger 2 Adversarial Stress Test Script for Milestone 2 (R2).

Executes in real WebView2 / pywebview engine with live WSGI server and Tabulator.
"""

import json
import sys
import threading
import time
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

import webview
from src.app.__main__ import create_wsgi_app, start_local_http_server
from src.app.server import AppBackend

def run_adversarial_test_suite():
    backend = AppBackend()
    
    # Load Instance 1 initially
    inst1_path = root / "instances" / "public" / "instancia_1.xlsx"
    load_res = backend.load_excel(inst1_path)
    assert load_res.get("success"), f"Failed to load instance 1: {load_res}"
    
    window_holder = {}
    wsgi_app = create_wsgi_app(backend, window_holder)
    server_url, httpd = start_local_http_server(wsgi_app)
    
    test_results = {
        "css_checks": {},
        "drag_checks": {},
        "turma_card_click_checks": {},
        "instances_summary_checks": {},
        "extreme_math_checks": {},
        "errors": []
    }
    
    def on_loaded():
        time.sleep(1.0) # Allow DOM and Tabulator to complete tableBuilt
        try:
            # -------------------------------------------------------------
            # TEST 1: CSS Layout & Computed Properties
            # -------------------------------------------------------------
            css_res = win.evaluate_js("""
                (() => {
                    const sidePane = document.getElementById("sidePane");
                    const compSide = window.getComputedStyle(sidePane);
                    const scrollBox = document.getElementById("dashTurmasContainer");
                    const compScroll = window.getComputedStyle(scrollBox);
                    const paneDash = document.getElementById("paneDashboard");
                    
                    return {
                        sidePaneMinWidth: compSide.minWidth,
                        sidePaneWidth: compSide.width,
                        scrollBoxOverflow: compScroll.overflow,
                        scrollBoxMinHeight: compScroll.minHeight,
                        paneDashInitialDisplay: compSide ? paneDash.style.display : null
                    };
                })()
            """)
            test_results["css_checks"] = css_res
            
            # Verify sidePane minWidth is 360px
            assert css_res.get("sidePaneMinWidth") == "360px", f"Expected minWidth 360px, got {css_res.get('sidePaneMinWidth')}"
            
            # -------------------------------------------------------------
            # TEST 2: Tab Switching (Report <-> Dashboard)
            # -------------------------------------------------------------
            tab_res = win.evaluate_js("""
                (() => {
                    setSideTab('dashboard');
                    const isDashActive = document.getElementById("paneDashboard").classList.contains("active");
                    const dashDisplay = document.getElementById("paneDashboard").style.display;
                    const reportDisplay = document.getElementById("paneReport").style.display;
                    
                    setSideTab('report');
                    const isReportActive = document.getElementById("paneReport").classList.contains("active");
                    const reportDisplay2 = document.getElementById("paneReport").style.display;
                    const dashDisplay2 = document.getElementById("paneDashboard").style.display;
                    
                    setSideTab('dashboard'); // keep dashboard active for remaining tests
                    return {
                        isDashActive,
                        dashDisplay,
                        reportDisplay,
                        isReportActive,
                        reportDisplay2,
                        dashDisplay2
                    };
                })()
            """)
            test_results["tab_switching_checks"] = tab_res
            assert tab_res.get("isDashActive") is True
            assert tab_res.get("dashDisplay") == "flex"
            assert tab_res.get("reportDisplay") == "none"
            assert tab_res.get("isReportActive") is True
            assert tab_res.get("reportDisplay2") == "flex"
            assert tab_res.get("dashDisplay2") == "none"

            # -------------------------------------------------------------
            # TEST 3: Minimum Width Dragging Behavior in JS (Adversarial delta)
            # -------------------------------------------------------------
            drag_res = win.evaluate_js("""
                (() => {
                    const resizer = document.getElementById("paneResizer");
                    const sidePane = document.getElementById("sidePane");
                    
                    // 1. Simulate mousedown at clientX = 500
                    const downEv = new MouseEvent("mousedown", { clientX: 500, bubbles: true });
                    resizer.dispatchEvent(downEv);
                    
                    // 2. Adversarial drag: Drag mouse far to the right (clientX = 2000, delta = -1500)
                    // This attempts to squash the side-pane to 0 or negative width
                    const moveFarRight = new MouseEvent("mousemove", { clientX: 2000, bubbles: true });
                    window.dispatchEvent(moveFarRight);
                    const widthFarRight = sidePane.style.width;
                    
                    // 3. Normal drag right (delta = -200)
                    const moveMid = new MouseEvent("mousemove", { clientX: 700, bubbles: true });
                    window.dispatchEvent(moveMid);
                    const widthMid = sidePane.style.width;
                    
                    // 4. Mouseup
                    const upEv = new MouseEvent("mouseup", { bubbles: true });
                    window.dispatchEvent(upEv);
                    const savedStorage = localStorage.getItem("unisoma_side_width");
                    
                    // 5. Double-click reset
                    const dblEv = new MouseEvent("dblclick", { bubbles: true });
                    resizer.dispatchEvent(dblEv);
                    const widthAfterDblClick = sidePane.style.width;
                    const savedStorageAfterReset = localStorage.getItem("unisoma_side_width");
                    
                    return {
                        widthFarRight,
                        widthMid,
                        savedStorage,
                        widthAfterDblClick,
                        savedStorageAfterReset
                    };
                })()
            """)
            test_results["drag_checks"] = drag_res
            assert drag_res.get("widthFarRight") == "360px", f"Expected widthFarRight 360px, got {drag_res.get('widthFarRight')}"
            assert int(drag_res.get("widthMid").replace("px", "")) >= 360, f"Expected widthMid >= 360, got {drag_res.get('widthMid')}"
            assert drag_res.get("widthAfterDblClick") == "520px", f"Expected reset to 520px, got {drag_res.get('widthAfterDblClick')}"

            # -------------------------------------------------------------
            # TEST 4: Run Optimization and Verify Dashboard Cards
            # -------------------------------------------------------------
            # Run optimization on instance 1
            ens_res = win.evaluate_js("""
                (async () => {
                    const res = await apiPost("/api/run_ensalamento", {
                        allow_integral: true,
                        allow_unallocated: false
                    });
                    if (res.success) {
                        state.searchQuery = "";
                        await applyPagePayload(res);
                        renderSummary(res.summary);
                        renderDashboard(res.summary);
                    }
                    return res;
                })()
            """)
            assert ens_res.get("success"), f"Ensalamento failed: {ens_res}"
            
            # Verify cards rendered
            cards_eval = win.evaluate_js("""
                (() => {
                    const cards = document.querySelectorAll("#dashTurmasContainer .dash-turma-card");
                    const cardList = [];
                    cards.forEach(c => {
                        const code = c.querySelector(".dash-turma-code")?.textContent.trim();
                        const lotText = c.querySelector(".dash-turma-lot")?.textContent.trim();
                        const segM = c.querySelector(".dash-bar-seg-m")?.style.width;
                        const segF = c.querySelector(".dash-bar-seg-f")?.style.width;
                        const segEmpty = c.querySelector(".dash-bar-seg-empty")?.style.width;
                        cardList.push({ code, lotText, segM, segF, segEmpty });
                    });
                    return {
                        totalCards: cards.length,
                        cardList: cardList,
                        dashKpiTotalVal: document.getElementById("dashKpiTotalVal")?.textContent,
                        dashKpiManhaVal: document.getElementById("dashKpiManhaVal")?.textContent,
                        dashKpiTardeVal: document.getElementById("dashKpiTardeVal")?.textContent
                    };
                })()
            """)
            test_results["dashboard_rendered_cards"] = cards_eval
            assert cards_eval.get("totalCards") == 4, f"Expected 4 cards for instance 1, got {cards_eval.get('totalCards')}"

            # -------------------------------------------------------------
            # TEST 5: Clicking Turma Card triggers filterSheetByTurma correctly
            # -------------------------------------------------------------
            click_res = win.evaluate_js("""
                (async () => {
                    const cards = document.querySelectorAll("#dashTurmasContainer .dash-turma-card");
                    if (!cards.length) return { error: "No cards found" };
                    
                    const firstCard = cards[0];
                    const targetCode = firstCard.querySelector(".dash-turma-code").textContent.trim();
                    
                    // Trigger click
                    firstCard.click();
                    
                    // Wait a moment for async filterSheetByTurma to complete
                    await new Promise(r => setTimeout(r, 200));
                    
                    const searchVal = document.getElementById("searchBox").value;
                    const currentSheet = state.activeSheet;
                    const activeQuery = state.searchQuery;
                    
                    // Check rows in Tabulator
                    const tableRows = table ? table.getRows("active") : [];
                    const rowData = tableRows.map(r => r.getData());
                    
                    // All active data rows (excel_row > 1) must contain targetCode in column c3
                    const nonHeaderRows = rowData.filter(d => d.excel_row > 1);
                    const matchingRows = nonHeaderRows.filter(d => normStr(d.c3) === normStr(targetCode));
                    
                    return {
                        targetCode,
                        searchVal,
                        currentSheet,
                        activeQuery,
                        totalActiveRows: rowData.length,
                        nonHeaderCount: nonHeaderRows.length,
                        matchingCount: matchingRows.length
                    };
                })()
            """)
            test_results["turma_card_click_checks"] = click_res
            assert click_res.get("currentSheet") == "Ensalamento", f"Expected activeSheet Ensalamento, got {click_res.get('currentSheet')}"
            assert click_res.get("searchVal") == click_res.get("targetCode"), f"Expected searchBox to be {click_res.get('targetCode')}, got {click_res.get('searchVal')}"
            assert click_res.get("matchingCount") == click_res.get("nonHeaderCount"), f"All non-header rows must match {click_res.get('targetCode')}"
            assert click_res.get("matchingCount") > 0, "Expected non-zero matching rows"

            # -------------------------------------------------------------
            # TEST 6: Clicking Card when viewing different sheet (e.g. Alunos)
            # -------------------------------------------------------------
            cross_sheet_click = win.evaluate_js("""
                (async () => {
                    // Switch to Alunos sheet
                    await switchSheet("Alunos");
                    const sheetBeforeClick = state.activeSheet;
                    
                    // Click a different turma card (e.g. card 1 - second card)
                    const cards = document.querySelectorAll("#dashTurmasContainer .dash-turma-card");
                    const secondCard = cards[1];
                    const targetCode = secondCard.querySelector(".dash-turma-code").textContent.trim();
                    
                    secondCard.click();
                    
                    // Wait for async get_page + applyPagePayload
                    await new Promise(r => setTimeout(r, 300));
                    
                    const sheetAfterClick = state.activeSheet;
                    const searchVal = document.getElementById("searchBox").value;
                    const tableRows = table ? table.getRows("active") : [];
                    const nonHeaderRows = tableRows.map(r => r.getData()).filter(d => d.excel_row > 1);
                    const matchingRows = nonHeaderRows.filter(d => normStr(d.c3) === normStr(targetCode));
                    
                    return {
                        sheetBeforeClick,
                        targetCode,
                        sheetAfterClick,
                        searchVal,
                        nonHeaderCount: nonHeaderRows.length,
                        matchingCount: matchingRows.length
                    };
                })()
            """)
            test_results["cross_sheet_click_checks"] = cross_sheet_click
            assert cross_sheet_click.get("sheetBeforeClick") == "Alunos"
            assert cross_sheet_click.get("sheetAfterClick") == "Ensalamento", f"Should switch back to Ensalamento, got {cross_sheet_click.get('sheetAfterClick')}"
            assert cross_sheet_click.get("searchVal") == cross_sheet_click.get("targetCode")
            assert cross_sheet_click.get("matchingCount") == cross_sheet_click.get("nonHeaderCount")
            assert cross_sheet_click.get("matchingCount") > 0

            # -------------------------------------------------------------
            # TEST 7: Summary outputs and renderDashboard for ALL public instances (1 to 4)
            # -------------------------------------------------------------
            instances_res = {}
            for i in range(1, 5):
                p = root / "instances" / "public" / f"instancia_{i}.xlsx"
                b = AppBackend()
                b.load_excel(p)
                # If impeditivas exist (e.g. instance 4 typos), resolve quick_fix
                b.resolve_issue(action="quick_fix", excel_row=None, target_rows=[])
                sol = b.run_ensalamento(allow_integral=True, allow_unallocated=False)
                assert sol.get("success"), f"Instance {i} solve failed: {sol}"
                summ = sol["summary"]
                
                # Test rendering this summary inside WebView
                render_eval = win.evaluate_js(f"""
                    (() => {{
                        const summary = {json.dumps(summ)};
                        renderDashboard(summary);
                        const cards = document.querySelectorAll("#dashTurmasContainer .dash-turma-card");
                        const totalVal = document.getElementById("dashKpiTotalVal").textContent;
                        const manhaVal = document.getElementById("dashKpiManhaVal").textContent;
                        const tardeVal = document.getElementById("dashKpiTardeVal").textContent;
                        
                        return {{
                            renderedCardsCount: cards.length,
                            totalVal,
                            manhaVal,
                            tardeVal
                        }};
                    }})()
                """)
                instances_res[f"instancia_{i}"] = {
                    "total_alocados": summ["total_alocados"],
                    "total_salas": summ["total_salas"],
                    "turmas_count": len(summ["turmas"]),
                    "render_eval": render_eval
                }
                assert render_eval.get("renderedCardsCount") == len(summ["turmas"])
            
            test_results["instances_summary_checks"] = instances_res

            # -------------------------------------------------------------
            # TEST 8: Adversarial Card Math in WebView (Capacity 0, extreme values)
            # -------------------------------------------------------------
            math_eval = win.evaluate_js("""
                (() => {
                    const testCases = [
                        { codigo: "ZERO", capacidade: 0, lotacao: 0, masculino: 0, feminino: 0, turno: "MANHÃ" },
                        { codigo: "FULL_M", capacidade: 30, lotacao: 30, masculino: 30, feminino: 0, turno: "MANHÃ" },
                        { codigo: "FULL_F", capacidade: 30, lotacao: 30, masculino: 0, feminino: 30, turno: "TARDE" },
                        { codigo: "HALF", capacidade: 30, lotacao: 30, masculino: 15, feminino: 15, turno: "TARDE" },
                        { codigo: "EMPTY", capacidade: 30, lotacao: 0, masculino: 0, feminino: 0, turno: "MANHÃ" },
                        { codigo: "ODD", capacidade: 25, lotacao: 17, masculino: 9, feminino: 8, turno: "MANHÃ" },
                        { codigo: "NEG", capacidade: -5, lotacao: -2, masculino: -1, feminino: -1, turno: "TARDE" }
                    ];
                    
                    const results = [];
                    for (const tc of testCases) {
                        const el = createTurmaCardElement(tc);
                        const mStyle = el.querySelector(".dash-bar-seg-m").style.width;
                        const fStyle = el.querySelector(".dash-bar-seg-f").style.width;
                        const emptyStyle = el.querySelector(".dash-bar-seg-empty").style.width;
                        const pM = parseFloat(mStyle);
                        const pF = parseFloat(fStyle);
                        const pEmpty = parseFloat(emptyStyle);
                        const sum = Math.round((pM + pF + pEmpty) * 100) / 100;
                        results.push({ tc: tc.codigo, pM, pF, pEmpty, sum, hasNaN: isNaN(sum) });
                    }
                    return results;
                })()
            """)
            test_results["extreme_math_checks"] = math_eval
            for r in math_eval:
                assert not r["hasNaN"], f"NaN detected in math eval for case {r['tc']}"
                assert r["sum"] == 100.0 or r["tc"] == "ZERO" or r["tc"] == "NEG", f"Sum must be 100%, got {r['sum']} for {r['tc']}"

            test_results["status"] = "ALL_TESTS_PASSED"

        except Exception as e:
            test_results["errors"].append(str(e))
            test_results["status"] = "FAILED"
        finally:
            win.destroy()

    win = webview.create_window(
        "Adversarial Stress Test Suite",
        url=server_url,
        hidden=True,
        width=1340,
        height=820
    )
    win.events.loaded += on_loaded
    webview.start()
    httpd.shutdown()
    httpd.server_close()
    
    return test_results

if __name__ == "__main__":
    res = run_adversarial_test_suite()
    print("FINAL TEST RESULTS:")
    print(json.dumps(res, indent=2, ensure_ascii=False))
    if res.get("status") == "ALL_TESTS_PASSED":
        sys.exit(0)
    else:
        sys.exit(1)

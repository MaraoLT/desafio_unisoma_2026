"""Empirical Challenger 2 Adversarial Verification Suite for Milestone 2 (R2).

Runs completely inside local sandbox via WebView2 with js_api bidirectional bridge.
"""

import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

import webview
from src.app.server import AppBackend

class AdversarialVerifierApi:
    def __init__(self, win_holder):
        self.win_holder = win_holder
        self.results = {}
        
    def report_results(self, data):
        self.results = data
        if self.win_holder.get("win"):
            self.win_holder["win"].destroy()


def run_verification():
    # 1. Prepare backend and load instance 1
    backend = AppBackend()
    inst1_path = root / "instances" / "public" / "instancia_1.xlsx"
    load_res = backend.load_excel(inst1_path)
    assert load_res.get("success"), f"Failed to load instance 1: {load_res}"
    
    # Run ensalamento on backend to obtain solved data and summary
    ens_res = backend.run_ensalamento(allow_integral=True, allow_unallocated=False)
    assert ens_res.get("success"), f"Ensalamento failed: {ens_res}"
    summary_inst1 = ens_res["summary"]
    
    alunos_page = backend.get_sheet_page("Alunos")
    ensalamento_page = backend.get_sheet_page("Ensalamento")

    # Solve instances 2, 3, 4 as well to provide their summaries to JS
    all_instance_summaries = {"instancia_1": summary_inst1}
    for i in (2, 3, 4):
        p = root / "instances" / "public" / f"instancia_{i}.xlsx"
        b = AppBackend()
        b.load_excel(p)
        sol = b.run_ensalamento(allow_integral=True, allow_unallocated=False)
        assert sol.get("success"), f"Instance {i} solve failed: {sol}"
        all_instance_summaries[f"instancia_{i}"] = sol["summary"]
    
    # 2. Build offline HTML with local asset paths and mock backend bridge
    static_dir = root / "src" / "app" / "static"
    index_html = (static_dir / "index.html").read_text(encoding="utf-8")
    
    fixed_html = index_html.replace('href="/style.css"', f'href="{static_dir.as_uri()}/style.css"')
    fixed_html = fixed_html.replace('href="/tabulator.min.css"', f'href="{static_dir.as_uri()}/tabulator.min.css"')
    fixed_html = fixed_html.replace('src="/tabulator.min.js"', f'src="{static_dir.as_uri()}/tabulator.min.js"')
    
    # Hook apiPost directly inside its definition
    hook = """
      if (window.offlineApiPost) return await window.offlineApiPost(path, body);
    """
    fixed_html = fixed_html.replace('async function apiPost(path, body = {}) {', f'async function apiPost(path, body = {{}}) {{\n{hook}')
    
    # Inject Mock Data & Automated Test Runner Script
    test_runner_script = f"""
    <script>
      window.MOCK_DATA = {{
        summary: {json.dumps(summary_inst1)},
        alunosPage: {json.dumps(alunos_page)},
        ensalamentoPage: {json.dumps(ensalamento_page)},
        allSummaries: {json.dumps(all_instance_summaries)}
      }};
      
      window.offlineApiPost = async function(path, body = {{}}) {{
        if (path === "/api/init") {{
          return Object.assign({{ success: true, summary: window.MOCK_DATA.summary }}, window.MOCK_DATA.ensalamentoPage);
        }}
        if (path === "/api/get_page") {{
          const sheet = body.sheet_name || "Ensalamento";
          if (sheet === "Alunos") return Object.assign({{ success: true }}, window.MOCK_DATA.alunosPage);
          return Object.assign({{ success: true }}, window.MOCK_DATA.ensalamentoPage);
        }}
        if (path === "/api/update_cells") {{
          return {{ success: true, dirty: false }};
        }}
        if (path === "/api/set_col_width") {{
          return {{ success: true }};
        }}
        return {{ success: true }};
      }};

      window.addEventListener("pywebviewready", async () => {{
        // Wait for Tabulator and DOM initialization
        await new Promise(r => setTimeout(r, 600));
        
        const report = {{
          css_checks: {{}},
          drag_checks: {{}},
          tab_switching_checks: {{}},
          dashboard_cards_checks: {{}},
          turma_card_click_checks: {{}},
          cross_sheet_click_checks: {{}},
          instances_summary_checks: {{}},
          extreme_math_checks: {{}},
          errors: [],
          status: "PASSED"
        }};

        try {{
          // -----------------------------------------------------------------
          // 1. CSS Layout & Computed Properties
          // -----------------------------------------------------------------
          const sidePane = document.getElementById("sidePane");
          const compSide = window.getComputedStyle(sidePane);
          const scrollBox = document.getElementById("dashTurmasContainer");
          const compScroll = window.getComputedStyle(scrollBox);
          const grid = document.querySelector(".dash-columns-grid");
          const compGrid = grid ? window.getComputedStyle(grid) : null;

          report.css_checks = {{
            sidePaneMinWidth: compSide.minWidth,
            sidePaneWidth: compSide.width,
            scrollBoxOverflow: compScroll.overflow,
            scrollBoxMinHeight: compScroll.minHeight,
            gridColumns: compGrid ? compGrid.gridTemplateColumns : null
          }};

          if (compSide.minWidth !== "360px") {{
            report.errors.push(`CSS min-width violation: expected 360px, got ${{compSide.minWidth}}`);
          }}
          if (!compScroll.overflow.includes("visible")) {{
            report.errors.push(`Scroll trap violation: expected visible, got ${{compScroll.overflow}}`);
          }}
          if (compScroll.minHeight !== "0px") {{
            report.errors.push(`Scrollbox minHeight violation: expected 0px, got ${{compScroll.minHeight}}`);
          }}

          // -----------------------------------------------------------------
          // 2. Tab Switching (Report <-> Dashboard)
          // -----------------------------------------------------------------
          setSideTab('dashboard');
          const isDashActive = document.getElementById("paneDashboard").classList.contains("active");
          const dashDisplay = document.getElementById("paneDashboard").style.display;
          const reportDisplay = document.getElementById("paneReport").style.display;

          setSideTab('report');
          const isReportActive = document.getElementById("paneReport").classList.contains("active");
          const reportDisplay2 = document.getElementById("paneReport").style.display;
          const dashDisplay2 = document.getElementById("paneDashboard").style.display;

          setSideTab('dashboard'); // restore dashboard
          report.tab_switching_checks = {{
            isDashActive,
            dashDisplay,
            reportDisplay,
            isReportActive,
            reportDisplay2,
            dashDisplay2
          }};

          if (!isDashActive || dashDisplay !== "flex" || reportDisplay !== "none") {{
            report.errors.push("Tab switching to dashboard failed");
          }}
          if (!isReportActive || reportDisplay2 !== "flex" || dashDisplay2 !== "none") {{
            report.errors.push("Tab switching to report failed");
          }}

          // -----------------------------------------------------------------
          // 3. Minimum Width Dragging Behavior in JS (Adversarial delta)
          // -----------------------------------------------------------------
          const resizer = document.getElementById("paneResizer");

          // Mousedown at clientX = 500
          resizer.dispatchEvent(new MouseEvent("mousedown", {{ clientX: 500, bubbles: true }}));

          // Adversarial drag far to the right (clientX = 2500, delta = -2000)
          window.dispatchEvent(new MouseEvent("mousemove", {{ clientX: 2500, bubbles: true }}));
          const widthFarRight = sidePane.style.width;

          // Drag to intermediate position (delta = -200)
          window.dispatchEvent(new MouseEvent("mousemove", {{ clientX: 700, bubbles: true }}));
          const widthMid = sidePane.style.width;

          // Mouseup
          window.dispatchEvent(new MouseEvent("mouseup", {{ bubbles: true }}));
          const savedStorage = localStorage.getItem("unisoma_side_width");

          // Double-click reset
          resizer.dispatchEvent(new MouseEvent("dblclick", {{ bubbles: true }}));
          const widthAfterDblClick = sidePane.style.width;
          const savedStorageAfterReset = localStorage.getItem("unisoma_side_width");

          report.drag_checks = {{
            widthFarRight,
            widthMid,
            savedStorage,
            widthAfterDblClick,
            savedStorageAfterReset
          }};

          if (widthFarRight !== "360px") {{
            report.errors.push(`Splitter drag clamping failed: expected 360px, got ${{widthFarRight}}`);
          }}
          if (parseInt(widthMid, 10) < 360) {{
            report.errors.push(`Splitter allowed width below 360px: ${{widthMid}}`);
          }}
          if (widthAfterDblClick !== "520px") {{
            report.errors.push(`Splitter double-click reset failed: expected 520px, got ${{widthAfterDblClick}}`);
          }}

          // -----------------------------------------------------------------
          // 4. Render Dashboard Cards & KPI Checks
          // -----------------------------------------------------------------
          const cards = document.querySelectorAll("#dashTurmasContainer .dash-turma-card");
          const cardList = [];
          cards.forEach(c => {{
            const code = c.querySelector(".dash-turma-code")?.textContent.trim();
            const lotText = c.querySelector(".dash-turma-lot")?.textContent.trim();
            const segM = c.querySelector(".dash-bar-seg-m")?.style.width;
            const segF = c.querySelector(".dash-bar-seg-f")?.style.width;
            const segEmpty = c.querySelector(".dash-bar-seg-empty")?.style.width;
            cardList.push({{ code, lotText, segM, segF, segEmpty }});
          }});

          report.dashboard_cards_checks = {{
            totalCards: cards.length,
            cardList: cardList,
            dashKpiTotalVal: document.getElementById("dashKpiTotalVal")?.textContent,
            dashKpiManhaVal: document.getElementById("dashKpiManhaVal")?.textContent,
            dashKpiTardeVal: document.getElementById("dashKpiTardeVal")?.textContent
          }};

          if (cards.length !== 4) {{
            report.errors.push(`Expected 4 cards for instance 1, found ${{cards.length}}`);
          }}

          // -----------------------------------------------------------------
          // 5. Turma Card Click -> filterSheetByTurma Interaction
          // -----------------------------------------------------------------
          const firstCard = cards[0];
          const targetCode = firstCard.querySelector(".dash-turma-code").textContent.trim();

          firstCard.click();
          await new Promise(r => setTimeout(r, 200));

          const searchVal = document.getElementById("searchBox").value;
          const currentSheet = state.activeSheet;
          const activeQuery = state.searchQuery;

          const tableRows = table ? table.getRows("active") : [];
          const rowData = tableRows.map(r => r.getData());
          const nonHeaderRows = rowData.filter(d => d.excel_row > 1);
          const matchingRows = nonHeaderRows.filter(d => normStr(d.c3) === normStr(targetCode));

          report.turma_card_click_checks = {{
            targetCode,
            searchVal,
            currentSheet,
            activeQuery,
            totalActiveRows: rowData.length,
            nonHeaderCount: nonHeaderRows.length,
            matchingCount: matchingRows.length
          }};

          if (currentSheet !== "Ensalamento") {{
            report.errors.push(`Expected activeSheet Ensalamento, got ${{currentSheet}}`);
          }}
          if (searchVal !== targetCode) {{
            report.errors.push(`Expected searchBox value ${{targetCode}}, got ${{searchVal}}`);
          }}
          if (matchingRows.length !== nonHeaderRows.length || nonHeaderRows.length === 0) {{
            report.errors.push(`Filtering mismatch: ${{matchingRows.length}} of ${{nonHeaderRows.length}} matched ${{targetCode}}`);
          }}

          // -----------------------------------------------------------------
          // 6. Cross-Sheet Click Interaction (Alunos -> Ensalamento)
          // -----------------------------------------------------------------
          await switchSheet("Alunos");
          const sheetBeforeClick = state.activeSheet;

          const secondCard = cards[1];
          const targetCode2 = secondCard.querySelector(".dash-turma-code").textContent.trim();
          secondCard.click();
          await new Promise(r => setTimeout(r, 300));

          const sheetAfterClick = state.activeSheet;
          const searchVal2 = document.getElementById("searchBox").value;
          const tableRows2 = table ? table.getRows("active") : [];
          const nonHeaderRows2 = tableRows2.map(r => r.getData()).filter(d => d.excel_row > 1);
          const matchingRows2 = nonHeaderRows2.filter(d => normStr(d.c3) === normStr(targetCode2));

          report.cross_sheet_click_checks = {{
            sheetBeforeClick,
            targetCode: targetCode2,
            sheetAfterClick,
            searchVal: searchVal2,
            nonHeaderCount: nonHeaderRows2.length,
            matchingCount: matchingRows2.length
          }};

          if (sheetBeforeClick !== "Alunos") {{
            report.errors.push(`Expected sheetBeforeClick Alunos, got ${{sheetBeforeClick}}`);
          }}
          if (sheetAfterClick !== "Ensalamento") {{
            report.errors.push(`Expected sheetAfterClick Ensalamento, got ${{sheetAfterClick}}`);
          }}
          if (searchVal2 !== targetCode2) {{
            report.errors.push(`Expected searchBox value ${{targetCode2}}, got ${{searchVal2}}`);
          }}
          if (matchingRows2.length !== nonHeaderRows2.length || nonHeaderRows2.length === 0) {{
            report.errors.push(`Cross-sheet filter mismatch: ${{matchingRows2.length}} of ${{nonHeaderRows2.length}} matched ${{targetCode2}}`);
          }}

          // -----------------------------------------------------------------
          // 7. Summary Rendering for ALL public instances (1 to 4)
          // -----------------------------------------------------------------
          const instChecks = {{}};
          for (let i = 1; i <= 4; i++) {{
            const sKey = `instancia_${{i}}`;
            const summ = window.MOCK_DATA.allSummaries[sKey];
            renderDashboard(summ);

            const rendCards = document.querySelectorAll("#dashTurmasContainer .dash-turma-card");
            const totVal = document.getElementById("dashKpiTotalVal").textContent;
            const manVal = document.getElementById("dashKpiManhaVal").textContent;
            const tarVal = document.getElementById("dashKpiTardeVal").textContent;

            instChecks[sKey] = {{
              expectedCards: summ.turmas.length,
              renderedCards: rendCards.length,
              totVal,
              manVal,
              tarVal
            }};

            if (rendCards.length !== summ.turmas.length) {{
              report.errors.push(`${{sKey}}: expected ${{summ.turmas.length}} cards, got ${{rendCards.length}}`);
            }}
          }}
          report.instances_summary_checks = instChecks;

          // -----------------------------------------------------------------
          // 8. Adversarial Card Math in WebView (Capacity 0, extreme values)
          // -----------------------------------------------------------------
          const testCases = [
            {{ codigo: "ZERO", capacidade: 0, lotacao: 0, masculino: 0, feminino: 0, turno: "MANHÃ" }},
            {{ codigo: "FULL_M", capacidade: 30, lotacao: 30, masculino: 30, feminino: 0, turno: "MANHÃ" }},
            {{ codigo: "FULL_F", capacidade: 30, lotacao: 30, masculino: 0, feminino: 30, turno: "TARDE" }},
            {{ codigo: "HALF", capacidade: 30, lotacao: 30, masculino: 15, feminino: 15, turno: "TARDE" }},
            {{ codigo: "EMPTY", capacidade: 30, lotacao: 0, masculino: 0, feminino: 0, turno: "MANHÃ" }},
            {{ codigo: "ODD", capacidade: 25, lotacao: 17, masculino: 9, feminino: 8, turno: "MANHÃ" }},
            {{ codigo: "NEG", capacidade: -5, lotacao: -2, masculino: -1, feminino: -1, turno: "TARDE" }}
          ];

          const mathResults = [];
          for (const tc of testCases) {{
            const el = createTurmaCardElement(tc);
            const mStyle = el.querySelector(".dash-bar-seg-m").style.width;
            const fStyle = el.querySelector(".dash-bar-seg-f").style.width;
            const emptyStyle = el.querySelector(".dash-bar-seg-empty").style.width;
            const pM = parseFloat(mStyle);
            const pF = parseFloat(fStyle);
            const pEmpty = parseFloat(emptyStyle);
            const sum = Math.round((pM + pF + pEmpty) * 100) / 100;
            mathResults.push({{ tc: tc.codigo, pM, pF, pEmpty, sum, hasNaN: isNaN(sum) }});
            if (isNaN(sum)) {{
              report.errors.push(`NaN detected in card math for case ${{tc.codigo}}`);
            }}
          }}
          report.extreme_math_checks = mathResults;

        }} catch (err) {{
          report.errors.push(String(err));
          report.status = "FAILED";
        }}

        if (report.errors.length > 0) {{
          report.status = "FAILED";
          report.verdict = "REJECT";
        }} else {{
          report.status = "PASSED";
          report.verdict = "APPROVE";
        }}

        await window.pywebview.api.report_results(report);
      }});
    </script>
    """
    fixed_html = fixed_html.replace('</head>', f'{test_runner_script}\n</head>')

    runner_html = root / "scratch" / "complete_runner.html"
    runner_html.write_text(fixed_html, encoding="utf-8")

    win_holder = {}
    verifier_api = AdversarialVerifierApi(win_holder)
    
    win = webview.create_window(
        "Adversarial Stress Test Suite",
        url=str(runner_html.as_uri()),
        js_api=verifier_api,
        hidden=True,
        width=1340,
        height=820
    )
    win_holder["win"] = win
    webview.start()
    
    return verifier_api.results


if __name__ == "__main__":
    res = run_verification()
    print("FINAL ADVERSARIAL VERIFICATION REPORT:")
    print(json.dumps(res, indent=2, ensure_ascii=False))
    if res.get("status") == "PASSED" and res.get("verdict") == "APPROVE":
        sys.exit(0)
    else:
        sys.exit(1)

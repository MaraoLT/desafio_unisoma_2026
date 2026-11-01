import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from src.app.server import AppBackend

def test_instances():
    for i in range(1, 5):
        p = root / "instances" / "public" / f"instancia_{i}.xlsx"
        print(f"\n--- Checking {p.name} ---")
        backend = AppBackend()
        load_res = backend.load_excel(p)
        print(f"load_excel success={load_res.get('success')}, sheets={list(backend.sheets_data.keys())}")
        
        # Check if there are issues
        issues = load_res.get("issues", [])
        print(f"Initial issues count: {len(issues)}")
        imped = [iss for iss in issues if iss.get("severidade") == "IMPEDITIVA"]
        print(f"Impeditivas: {len(imped)}")
        
        # If impeditivas exist (e.g. instance 4 with typos), apply sanitization
        if imped:
            print("Applying sanitization for impeditivas...")
            res_fix = backend.resolve_issue(action="quick_fix", excel_row=None, target_rows=[])
            print(f"Batch sanitize result: success={res_fix.get('success')}, modified={res_fix.get('modified')}")
            
        res_ens = backend.run_ensalamento(allow_integral=True, allow_unallocated=False)
        print(f"run_ensalamento success={res_ens.get('success')}")
        if not res_ens.get("success"):
            print(f"Error: {res_ens.get('error')}")
            continue
            
        summary = res_ens.get("summary")
        print(f"Summary keys: {list(summary.keys()) if summary else None}")
        if summary:
            print(f"Total alocados: {summary.get('total_alocados')}, Total salas: {summary.get('total_salas')}")
            print(f"Stats turnos: {summary.get('stats_turnos')}")
            turmas = summary.get("turmas", [])
            print(f"Turmas count: {len(turmas)}")
            if turmas:
                print(f"Sample turma: {turmas[0]}")

if __name__ == "__main__":
    test_instances()

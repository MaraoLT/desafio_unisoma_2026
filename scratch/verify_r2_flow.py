import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from src.app.server import AppBackend

def run_checks():
    backend = AppBackend()
    inst_path = root / "instances" / "experiments" / "instancia_1.xlsx"
    assert inst_path.exists(), f"Instance 1 not found at {inst_path}"

    # 1. Load Excel
    load_res = backend.load_excel(inst_path)
    assert load_res.get("success") is True, f"load_excel failed: {load_res}"

    # 2. Validate data
    val_res = backend.validate_data()
    assert val_res.get("success") is True, f"validate_data failed: {val_res}"
    summary = val_res.get("summary", {})
    assert "stats_turnos" in summary
    assert "turmas" in summary

    # 3. Run ensalamento
    ens_res = backend.run_ensalamento(allow_integral=True, allow_unallocated=False)
    assert ens_res.get("success") is True, f"run_ensalamento failed: {ens_res}"
    opt_summary = ens_res.get("summary", {})
    assert "stats_turnos" in opt_summary
    assert "turmas" in opt_summary
    assert len(opt_summary["turmas"]) > 0

    # 4. Verify Ensalamento sheet exists
    assert "Ensalamento" in backend.sheets_data, "Ensalamento sheet not generated"
    ens_mat = backend.sheets_data["Ensalamento"]
    assert len(ens_mat) > 1, "Ensalamento sheet has no rows"
    header = ens_mat[0]
    assert any("turma" in str(h).lower() or "sala" in str(h).lower() for h in header), f"Unexpected header: {header}"

    # 5. Check each turma in summary
    for t in opt_summary["turmas"]:
        assert t["capacidade"] > 0
        assert t["lotacao"] <= t["capacidade"]
        assert t["masculino"] + t["feminino"] == t["lotacao"]
        assert t["livres"] == t["capacidade"] - t["lotacao"]
        assert 0.0 <= t["ocupacao_pct"] <= 100.0

    # 6. Test get_page for Ensalamento sheet
    page_res = backend.get_sheet_page("Ensalamento", page=1, search_query="")
    assert page_res.get("success") is True
    assert len(page_res.get("rows", [])) > 0

    print("All backend checks for Dashboard passed successfully!")

if __name__ == "__main__":
    run_checks()

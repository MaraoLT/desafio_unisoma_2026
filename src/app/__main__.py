"""Ponto de entrada do aplicativo Desktop — Desafio UniSoma 2026.

Executa um servidor WSGI local em memória (Bottle + PyWebView WebView2 nativo)
que funciona 100% offline tanto via código-fonte Python quanto empacotado em .exe.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
from socketserver import ThreadingMixIn
import sys
import tempfile
import threading
from typing import Any, Optional
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

if sys.platform == "win32" and getattr(sys, "frozen", False):
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")


def _get_bundle_root() -> Path:
    """Retorna a raiz onde os recursos estáticos foram empacotados (suporta PyInstaller _MEIPASS)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS")).resolve()
    return Path(__file__).resolve().parent.parent.parent


BUNDLE_ROOT = _get_bundle_root()
if str(BUNDLE_ROOT) not in sys.path:
    sys.path.insert(0, str(BUNDLE_ROOT))

import bottle
import webview

from src.app.server import AppBackend


def _find_initial_excel() -> Optional[Path]:
    """Procura uma planilha inicial no diretório de execução ou no pacote de exemplo."""
    candidates: list[Path] = []
    cwd = Path.cwd().resolve()
    candidates.append(cwd / "instances" / "public" / "instancia_1.xlsx")

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "instancia_1.xlsx")
        candidates.append(exe_dir.parent.parent / "instances" / "public" / "instancia_1.xlsx")

    candidates.append(BUNDLE_ROOT / "instances" / "public" / "instancia_1.xlsx")

    for cand in candidates:
        if cand.exists() and cand.is_file():
            # Se vier de dentro de _internal (_MEIPASS), não marca current_filepath lá dentro
            return cand
    return None


def create_wsgi_app(backend: AppBackend, window_holder: dict[str, Any]) -> bottle.Bottle:
    """Cria a aplicação web local servida internamente para a janela nativa."""
    app = bottle.Bottle()
    static_dir = BUNDLE_ROOT / "src" / "app" / "static"

    def _read_json() -> dict[str, Any]:
        raw = bottle.request.body.read()
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _json_resp(payload: dict[str, Any]) -> str:
        bottle.response.content_type = "application/json; charset=utf-8"
        return json.dumps(payload, ensure_ascii=False)

    @app.get("/")
    def index():
        return bottle.static_file("index.html", root=str(static_dir))

    @app.get("/style.css")
    def stylesheet():
        return bottle.static_file("style.css", root=str(static_dir))

    @app.post("/api/init")
    def api_init():
        if backend.sheets_data:
            res = backend.get_sheet_page(backend.active_sheet, page=1, search_query="")
            if backend.current_filepath:
                res["filename"] = backend.current_filepath.name
                res["filepath"] = str(backend.current_filepath)
            else:
                res["filename"] = "Planilha sem título"
                res["filepath"] = "Nova planilha — clique em 'Abrir Excel' ou 'Salvar'"
            return _json_resp(res)

        # Inicia com planilha vazia estilo Excel/Sheets (linha de cabeçalho padrão + linhas em branco)
        empty_rows = [["", "", ""] for _ in range(35)]
        backend.sheets_data = {
            "Alunos": [["Nome", "Sexo", "Disponibilidade"]] + empty_rows,
            "Turmas": [
                ["Recursos", "Quantidade"],
                ["turmas_manha", ""],
                ["turmas_tarde", ""],
                ["vagas_manha", ""],
                ["vagas_tarde", ""],
            ] + [["", ""] for _ in range(25)],
        }
        backend.active_sheet = "Alunos"
        backend.current_filepath = None
        backend.dirty = False

        res = backend.get_sheet_page("Alunos", page=1, search_query="")
        res["filename"] = "Planilha sem título"
        res["filepath"] = "Nova planilha — clique em 'Abrir Excel' para carregar seus dados"
        return _json_resp(res)

    @app.post("/api/get_page")
    def api_get_page():
        body = _read_json()
        return _json_resp(
            backend.get_sheet_page(
                sheet_name=str(body.get("sheet_name", backend.active_sheet)),
                page=int(body.get("page", 1)),
                search_query=str(body.get("search_query", "")),
            )
        )

    @app.post("/api/jump_row")
    def api_jump_row():
        body = _read_json()
        return _json_resp(
            backend.jump_to_row(
                sheet_name=str(body.get("sheet_name", "Alunos")),
                excel_row=int(body.get("excel_row", 2)),
            )
        )

    @app.post("/api/update_cell")
    def api_update_cell():
        body = _read_json()
        return _json_resp(
            backend.update_cell(
                sheet_name=str(body.get("sheet_name", backend.active_sheet)),
                mat_idx=int(body.get("mat_idx", 0)),
                col=int(body.get("col", 0)),
                value=str(body.get("value", "")),
            )
        )

    @app.post("/api/add_row")
    def api_add_row():
        body = _read_json()
        return _json_resp(
            backend.add_row(sheet_name=str(body.get("sheet_name", backend.active_sheet)))
        )

    @app.post("/api/delete_row")
    def api_delete_row():
        body = _read_json()
        return _json_resp(
            backend.delete_row(
                sheet_name=str(body.get("sheet_name", backend.active_sheet)),
                mat_idx=int(body.get("mat_idx", 1)),
                page=int(body.get("page", 1)),
                search_query=str(body.get("search_query", "")),
            )
        )

    @app.post("/api/resolve_issue")
    def api_resolve_issue():
        body = _read_json()
        return _json_resp(
            backend.resolve_issue(
                action=str(body.get("action", "")),
                issue_type=str(body.get("issue_type", "")),
                target_rows=[int(x) for x in body.get("target_rows", []) if str(x).isdigit()],
                extra=body.get("extra", {}),
            )
        )

    @app.post("/api/open_dialog")
    def api_open_dialog():
        win = window_holder.get("win")
        if win is None:
            return _json_resp({"success": False, "error": "Janela não inicializada."})

        start_dir = str(backend.current_filepath.parent) if backend.current_filepath else ""
        selected = win.create_file_dialog(
            webview.FileDialog.OPEN,
            directory=start_dir,
            allow_multiple=False,
            file_types=("Planilhas Excel (*.xlsx)",),
        )
        if not selected:
            return _json_resp({"cancelled": True})

        chosen_path = selected[0] if isinstance(selected, (list, tuple)) else str(selected)
        return _json_resp(backend.load_excel(chosen_path))

    @app.post("/api/save_excel")
    def api_save_excel():
        body = _read_json()
        save_as = bool(body.get("save_as", False))
        target_str: Optional[str] = None

        if save_as or backend.current_filepath is None:
            win = window_holder.get("win")
            if win is None:
                return _json_resp({"success": False, "error": "Janela não inicializada."})
            start_dir = str(backend.current_filepath.parent) if backend.current_filepath else ""
            default_name = (
                backend.current_filepath.name if backend.current_filepath else "ensalamento.xlsx"
            )
            selected = win.create_file_dialog(
                webview.FileDialog.SAVE,
                directory=start_dir,
                save_filename=default_name,
                file_types=("Planilhas Excel (*.xlsx)",),
            )
            if not selected:
                return _json_resp({"cancelled": True})
            target_str = selected[0] if isinstance(selected, (list, tuple)) else str(selected)
            if not target_str.lower().endswith(".xlsx"):
                target_str += ".xlsx"

        return _json_resp(backend.save_excel(save_as_path=target_str))

    @app.post("/api/run_ensalamento")
    def api_run_ensalamento():
        body = _read_json()
        return _json_resp(
            backend.run_ensalamento(
                allow_integral=bool(body.get("allow_integral", True)),
                allow_unallocated=bool(body.get("allow_unallocated", True)),
            )
        )

    @app.post("/api/export_pdf_dialog")
    def api_export_pdf_dialog():
        win = window_holder.get("win")
        if win is None:
            return _json_resp({"success": False, "error": "Janela não inicializada."})

        stem = backend.current_filepath.stem if backend.current_filepath else "ensalamento"
        default_pdf = f"Turmas_{stem}.pdf"
        start_dir = str(backend.current_filepath.parent) if backend.current_filepath else ""

        selected = win.create_file_dialog(
            webview.FileDialog.SAVE,
            directory=start_dir,
            save_filename=default_pdf,
            file_types=("Documento PDF (*.pdf)",),
        )
        if not selected:
            return _json_resp({"cancelled": True})

        pdf_target = selected[0] if isinstance(selected, (list, tuple)) else str(selected)
        if not pdf_target.lower().endswith(".pdf"):
            pdf_target += ".pdf"

        return _json_resp(backend.export_pdf(pdf_target))

    @app.post("/api/ask")
    def api_ask():
        body = _read_json()
        prompt = str(body.get("prompt", ""))
        return _json_resp({"answer": backend.ask_assistant(prompt)})

    return app


class _QuietWSGIHandler(WSGIRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass


class _ThreadedWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def start_local_http_server(wsgi_app: bottle.Bottle) -> tuple[str, _ThreadedWSGIServer]:
    """Inicia um servidor HTTP local (127.0.0.1) em porta livre já pronta para conexões."""
    httpd = make_server(
        "127.0.0.1",
        0,
        wsgi_app,
        server_class=_ThreadedWSGIServer,
        handler_class=_QuietWSGIHandler,
    )
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{port}/", httpd


def _wsgi_call(
    wsgi_app: bottle.Bottle,
    method: str,
    path: str,
    payload: Optional[dict[str, Any]] = None,
) -> tuple[str, bytes]:
    """Executa uma requisição WSGI em memória para autoverificação."""
    raw_body = json.dumps(payload).encode("utf-8") if payload is not None else b""
    status_holder: list[str] = ["200 OK"]

    def _start_response(status: str, headers: list[tuple[str, str]], exc_info: Any = None) -> Any:
        status_holder[0] = status
        return lambda _b: None

    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "SERVER_NAME": "127.0.0.1",
        "SERVER_PORT": "80",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": "http",
        "wsgi.input": io.BytesIO(raw_body),
        "wsgi.errors": sys.stderr,
        "wsgi.multithread": True,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
        "CONTENT_LENGTH": str(len(raw_body)),
        "CONTENT_TYPE": "application/json" if payload is not None else "text/plain",
    }
    chunks = list(wsgi_app(environ, _start_response))
    return status_holder[0], b"".join(chunks)


def _run_self_test(out_json_path: str) -> int:
    """Executa autoverificação ponta a ponta (WSGI + Excel + Solver CBC + PDF + Chat) sem abrir GUI."""
    report: dict[str, Any] = {"ok": False, "bundle_root": str(BUNDLE_ROOT)}
    httpd: Optional[_ThreadedWSGIServer] = None
    try:
        static_dir = BUNDLE_ROOT / "src" / "app" / "static"
        report["index_exists"] = (static_dir / "index.html").is_file()
        report["css_exists"] = (static_dir / "style.css").is_file()
        assert report["index_exists"] and report["css_exists"], f"Arquivos estáticos ausentes em {static_dir}"

        # Verifica inicialização das DLLs nativas WinForms + WebView2 (EdgeChromium)
        import webview.platforms.winforms  # noqa: F401
        import webview.platforms.edgechromium  # noqa: F401
        report["webview_edgechromium_ok"] = True

        backend = AppBackend()
        wsgi_app = create_wsgi_app(backend, {})
        base_url, httpd = start_local_http_server(wsgi_app)
        report["base_url"] = base_url

        # 1. Verifica rotas estáticas (index.html e style.css)
        st_idx, body_idx = _wsgi_call(wsgi_app, "GET", "/")
        assert st_idx.startswith("200") and b"<!DOCTYPE html>" in body_idx, f"Falha em GET /: {st_idx}"
        st_css, body_css = _wsgi_call(wsgi_app, "GET", "/style.css")
        assert st_css.startswith("200") and b"--green" in body_css, f"Falha em GET /style.css: {st_css}"

        def _post(path: str, data: dict[str, Any]) -> dict[str, Any]:
            st, raw = _wsgi_call(wsgi_app, "POST", path, data)
            assert st.startswith("200"), f"HTTP {st} em {path}"
            return json.loads(raw.decode("utf-8"))

        # 2. Inicializa planilha vazia
        init_res = _post("/api/init", {})
        assert init_res.get("success") is True, f"Falha em /api/init: {init_res}"
        report["initial_filename"] = init_res.get("filename")

        # Carrega exemplo para testar solver e exportação no self-test
        init_xlsx = _find_initial_excel()
        if init_xlsx:
            backend.load_excel(str(init_xlsx))

        # 3. Testa edição, adição, salto de linha e remoção na grade
        upd_res = _post("/api/update_cell", {"sheet_name": "Alunos", "mat_idx": 1, "col": 2, "value": "Manhã"})
        assert upd_res.get("success") is True, f"Falha em /api/update_cell: {upd_res}"
        add_res = _post("/api/add_row", {"sheet_name": "Alunos"})
        assert add_res.get("success") is True, f"Falha em /api/add_row: {add_res}"
        del_res = _post(
            "/api/delete_row",
            {
                "sheet_name": "Alunos",
                "mat_idx": int(add_res["highlight_excel_row"]) - 1,
                "page": 1,
                "search_query": "",
            },
        )
        assert del_res.get("success") is True, f"Falha em /api/delete_row: {del_res}"

        # 4. Executa otimização MILP (testa PuLP + binário cbc.exe empacotado)
        opt_res = _post("/api/run_ensalamento", {"allow_integral": True, "allow_unallocated": True})
        assert opt_res.get("success") is True, f"Falha em /api/run_ensalamento: {opt_res}"
        report["allocated"] = opt_res["summary"]["total_alocados"]
        report["classes_opened"] = opt_res["summary"]["total_salas"]

        # 5. Testa salto para linha e assistente local (resumo + busca por turma)
        jmp_res = _post("/api/jump_row", {"sheet_name": "Alunos", "excel_row": 5})
        assert jmp_res.get("success") is True, f"Falha em /api/jump_row: {jmp_res}"
        ask_res = _post("/api/ask", {"prompt": "Resumo das vagas"})
        assert "Resumo exato" in ask_res.get("answer", ""), f"Falha em /api/ask: {ask_res}"
        ask_cls = _post("/api/ask", {"prompt": "Manhã - A"})
        assert "MANHÃ" in ask_cls.get("answer", "").upper(), f"Falha em busca de turma: {ask_cls}"

        # 6. Testa exportação de PDF limpo p/ alunos e salvamento de Excel em diretório temporário
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_pdf = str(Path(tmpdir) / "turmas_teste.pdf")
            pdf_res = backend.export_pdf(tmp_pdf)
            assert pdf_res.get("success") is True and Path(tmp_pdf).stat().st_size > 1000, f"Falha PDF: {pdf_res}"
            report["pdf_bytes"] = Path(tmp_pdf).stat().st_size

            tmp_xlsx = str(Path(tmpdir) / "planilha_salva.xlsx")
            xlsx_res = backend.save_excel(save_as_path=tmp_xlsx)
            assert xlsx_res.get("success") is True and Path(tmp_xlsx).stat().st_size > 1000, f"Falha XLSX: {xlsx_res}"
            report["xlsx_bytes"] = Path(tmp_xlsx).stat().st_size

        report["ok"] = True
        Path(out_json_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        Path(out_json_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return 1
    finally:
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()


def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == "--self-test":
        raise SystemExit(_run_self_test(sys.argv[2]))

    backend = AppBackend()
    window_holder: dict[str, Any] = {}
    wsgi_app = create_wsgi_app(backend, window_holder)
    server_url, httpd = start_local_http_server(wsgi_app)

    try:
        win = webview.create_window(
            title="UniSoma — Ensalamento Inteligente",
            url=server_url,
            width=1340,
            height=820,
            min_size=(980, 600),
        )
        window_holder["win"] = win
        webview.start(debug=False)
    finally:
        httpd.shutdown()
        httpd.server_close()


if __name__ == "__main__":
    main()

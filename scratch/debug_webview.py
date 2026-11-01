import sys
import json
import time
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

import webview
from src.app.__main__ import create_wsgi_app, start_local_http_server
from src.app.server import AppBackend

def check():
    backend = AppBackend()
    inst1_path = root / "instances" / "public" / "instancia_1.xlsx"
    backend.load_excel(inst1_path)
    
    wsgi_app = create_wsgi_app(backend, {})
    server_url, httpd = start_local_http_server(wsgi_app)
    print("Server URL:", server_url)
    
    def on_loaded():
        time.sleep(1.0)
        try:
            title = win.evaluate_js("document.title")
            print("Document Title:", title)
            url = win.evaluate_js("window.location.href")
            print("Location href:", url)
            sidePaneExists = win.evaluate_js("!!document.getElementById('sidePane')")
            print("sidePane exists:", sidePaneExists)
            if not sidePaneExists:
                body_html = win.evaluate_js("document.body ? document.body.innerHTML.slice(0, 300) : 'NO BODY'")
                print("Body snippet:", body_html)
        except Exception as e:
            print("Error in on_loaded:", e)
        finally:
            win.destroy()
            
    win = webview.create_window("Debug", url=server_url, hidden=True)
    win.events.loaded += on_loaded
    webview.start()
    httpd.shutdown()
    httpd.server_close()

if __name__ == "__main__":
    check()

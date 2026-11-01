import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

import webview

def test_relative_html():
    static_dir = root / "src" / "app" / "static"
    index_html = (static_dir / "index.html").read_text(encoding="utf-8")
    
    # Replace absolute root paths with relative paths
    fixed_html = index_html.replace('href="/style.css"', f'href="{static_dir.as_uri()}/style.css"')
    fixed_html = fixed_html.replace('href="/tabulator.min.css"', f'href="{static_dir.as_uri()}/tabulator.min.css"')
    fixed_html = fixed_html.replace('src="/tabulator.min.js"', f'src="{static_dir.as_uri()}/tabulator.min.js"')
    
    test_html_file = root / "scratch" / "test_runner.html"
    test_html_file.write_text(fixed_html, encoding="utf-8")
    
    results = {}
    
    def on_loaded():
        time.sleep(1.0)
        try:
            results["title"] = win.evaluate_js("document.title")
            results["sidePaneExists"] = win.evaluate_js("!!document.getElementById('sidePane')")
            results["sidePaneMinWidth"] = win.evaluate_js("window.getComputedStyle(document.getElementById('sidePane')).minWidth")
            results["hasTabulator"] = win.evaluate_js("typeof Tabulator !== 'undefined'")
        except Exception as e:
            results["error"] = str(e)
        finally:
            win.destroy()
            
    win = webview.create_window("Offline Test", url=str(test_html_file.as_uri()), hidden=True)
    win.events.loaded += on_loaded
    webview.start()
    print("RESULTS:", results)

if __name__ == "__main__":
    test_relative_html()

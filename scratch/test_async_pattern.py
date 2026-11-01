import sys
import time
import threading
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

import webview

def test_async_pattern():
    results = {}
    
    def on_loaded():
        def run_checks():
            time.sleep(0.2)
            win.evaluate_js("""
                (async () => {
                    await new Promise(r => setTimeout(r, 50));
                    window._async_res = { answer: 42, text: "success" };
                })()
            """)
            time.sleep(0.2)
            results["val"] = win.evaluate_js("window._async_res")
            win.destroy()
            
        threading.Thread(target=run_checks).start()
        
    win = webview.create_window("Test", html="<html><body>Hello</body></html>", hidden=True)
    win.events.loaded += on_loaded
    webview.start()
    print("RESULTS:", results)

if __name__ == "__main__":
    test_async_pattern()

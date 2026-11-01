import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

import webview

class Api:
    def __init__(self):
        self.results = {}
        
    def report(self, data):
        self.results.update(data)
        win.destroy()

api = Api()
win = webview.create_window(
    "Test",
    html="""
    <html>
      <body>
        <script>
          window.addEventListener('pywebviewready', async () => {
            await new Promise(r => setTimeout(r, 50));
            await window.pywebview.api.report({ answer: 42, status: "OK" });
          });
        </script>
      </body>
    </html>
    """,
    js_api=api,
    hidden=True
)
webview.start()
print("API RESULTS:", api.results)

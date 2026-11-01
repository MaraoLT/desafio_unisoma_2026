import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

import webview
from src.app.server import AppBackend
from src.app.__main__ import create_wsgi_app, start_local_http_server

print("Imports succeeded!")

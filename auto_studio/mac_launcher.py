"""macOS Desktop Application Runner for AI Studio Pro.
Hosts the local FastAPI server and embeds it into a native macOS Cocoa/WebKit window via pywebview.
Includes fallback to default browser, AppKit activation, and AppleScript notifications.
"""
from __future__ import annotations
import os
import sys
import time
import threading
import urllib.request
import webbrowser
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HOST = "127.0.0.1"
PORT = 8888
SERVER_URL = f"http://{HOST}:{PORT}"


def start_uvicorn():
    try:
        import uvicorn
        from auto_studio.api import app
        uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
    except Exception as e:
        print(f"Uvicorn notice: {e}")


def wait_for_server(timeout: float = 15.0) -> bool:
    start_time = time.monotonic()
    while time.monotonic() - start_time < timeout:
        try:
            with urllib.request.urlopen(f"{SERVER_URL}/api/dashboard/stats", timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False


def activate_macos_app():
    """Activates macOS application policy so it appears in Dock and foreground."""
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyRegular
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        app.activateIgnoringOtherApps_(True)
    except Exception:
        pass


def main():
    print("=" * 60)
    print("  AI Studio Pro — macOS Desktop Application")
    print(f"  Target: {SERVER_URL}")
    print("=" * 60)

    # Check if server is already running
    if not wait_for_server(timeout=0.6):
        server_thread = threading.Thread(target=start_uvicorn, daemon=True, name="FastAPIServer")
        server_thread.start()
        if not wait_for_server(timeout=15.0):
            print("Error: FastAPI server failed to start within timeout.")
            sys.exit(1)

    print("Server online! Activating native macOS desktop environment...")
    activate_macos_app()

    # Check if browser mode requested
    if "--browser" in sys.argv:
        print(f"Opening browser at {SERVER_URL} ...")
        webbrowser.open(SERVER_URL)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            sys.exit(0)

    # Launch native Cocoa WebKit Window
    try:
        import webview
        window = webview.create_window(
            title="AI Studio Pro — Auto Gen Video (Drama AI, UGC, Meta AI & Google Flow)",
            url=SERVER_URL,
            width=1320,
            height=880,
            min_size=(980, 640),
            background_color="#070b14",
            text_select=True,
            zoomable=True
        )
        webview.start(debug=False)
    except Exception as exc:
        print(f"Notice: WebKit window could not be opened ({exc}). Launching default browser...")
        webbrowser.open(SERVER_URL)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            sys.exit(0)


if __name__ == "__main__":
    main()

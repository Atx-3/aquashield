"""
run.py - One-click launcher for the AQUA SHIELD web application.

How to use:  python run.py
What it does:
  1. Prints a startup banner.
  2. Opens http://localhost:8000 in your default browser (after a short delay).
  3. Starts the Uvicorn web server, which serves the FastAPI app defined in backend/app.py.
"""
import os
import sys
import time
import webbrowser
import uvicorn

def main():
    # Startup banner shown in the terminal
    print("=" * 65)
    print(" AQUA SHIELD V2: Autonomous Ocean Intelligence System")
    print(" Starting Tactical Core Backend on http://localhost:8000...")
    print("=" * 65)

    # Open browser automatically after 1.5s.
    # We wait a moment so the server has time to start before the browser hits it.
    def open_browser():
        time.sleep(1.5)
        webbrowser.open("http://localhost:8000")

    # Run the browser opener in a background ("daemon") thread so it does not
    # block the server from starting. Daemon = it dies automatically with the program.
    import threading
    threading.Thread(target=open_browser, daemon=True).start()

    # Launch Uvicorn server.
    #   "backend.app:app" -> import the module backend/app.py and use its variable `app`
    #   host="0.0.0.0"    -> listen on all network interfaces (reachable from other devices on the LAN)
    #   port=8000         -> the URL port
    #   reload=True       -> auto-restart the server whenever a .py file changes (development mode)
    uvicorn.run("backend.app:app", host="0.0.0.0", port=8000, reload=True)

# Only run main() when this file is executed directly (not when imported)
if __name__ == "__main__":
    main()

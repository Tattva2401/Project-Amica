"""
===============================================================================
Project Amica - Master Boot Script (run.py)
===============================================================================
Concurrent launcher for Project Amica Decoupled Architecture (Milestone v0.2).
Manages both:
1. FastAPI Backend (Brain Service): `uvicorn backend.main:app --port 8000`
2. Flet Desktop Client (Face Interface): `flet run frontend/app.py`

Features:
- Polls backend health check before launching frontend to prevent race conditions.
- Handles SIGINT (Ctrl+C) and SIGTERM with graceful teardown of child processes.
- Cross-platform compatible process cleanup.
===============================================================================
"""

import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import shutil

# Backend connection settings
BACKEND_HEALTH_URL = "http://127.0.0.1:8000/health"
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = "8000"

# Tracking running child processes
child_processes = []


def resolve_executable(name: str) -> str | None:
    """Finds binary in PATH or adjacent to current Python interpreter."""
    found = shutil.which(name)
    if found:
        return found
    # Check directory of active python binary (e.g. .venv/bin/)
    venv_candidate = os.path.join(os.path.dirname(sys.executable), name)
    if os.path.exists(venv_candidate):
        return venv_candidate
    return None


_terminating = False


def terminate_processes(signum=None, frame=None):
    """Gracefully terminates all managed background processes."""
    global _terminating
    if _terminating:
        return
    _terminating = True

    print("\n[Project Amica] Shutting down services...")
    for proc in child_processes:
        if proc.poll() is None:
            try:
                print(f"[Project Amica] Terminating process (PID: {proc.pid})...")
                proc.terminate()
            except Exception as e:
                print(f"[Project Amica] Error terminating PID {proc.pid}: {e}")

    # Give processes a short grace window to exit cleanly
    time.sleep(1.0)

    # Force-kill any lingering processes
    for proc in child_processes:
        if proc.poll() is None:
            try:
                print(f"[Project Amica] Force killing process (PID: {proc.pid})...")
                proc.kill()
            except Exception:
                pass

    print("[Project Amica] All services stopped. Goodbye!")
    sys.exit(0)


def wait_for_backend(backend_proc=None, timeout_seconds: int = 15) -> bool:
    """Polls the FastAPI health endpoint until it is ready or times out."""
    print(f"[Project Amica] Awaiting backend health at {BACKEND_HEALTH_URL}...")
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        if backend_proc and backend_proc.poll() is not None:
            print(f"[Project Amica] Backend exited prematurely with code {backend_proc.returncode}!")
            return False
        try:
            req = urllib.request.Request(BACKEND_HEALTH_URL, headers={"User-Agent": "AmicaBoot/1.0"})
            with urllib.request.urlopen(req, timeout=1.5) as response:
                if response.status == 200:
                    print("[Project Amica] Backend is online and healthy!")
                    return True
        except (urllib.error.URLError, ConnectionRefusedError, TimeoutError):
            pass
        time.sleep(0.5)

    print("[Project Amica] Warning: Backend health check timed out. Proceeding anyway...")
    return False


def main():
    # Register termination signals
    signal.signal(signal.SIGINT, terminate_processes)
    signal.signal(signal.SIGTERM, terminate_processes)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)

    print("=" * 70)
    print("Project Amica - Master Boot Script (v0.3)")
    print("=" * 70)

    # 1. Determine Backend Command
    uvicorn_bin = resolve_executable("uvicorn")
    if uvicorn_bin:
        backend_cmd = [uvicorn_bin, "backend.main:app", "--host", BACKEND_HOST, "--port", BACKEND_PORT]
    else:
        backend_cmd = [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", BACKEND_HOST, "--port", BACKEND_PORT]

    print(f"[Project Amica] Launching Backend: {' '.join(backend_cmd)}")
    backend_proc = subprocess.Popen(
        backend_cmd,
        cwd=base_dir,
    )
    child_processes.append(backend_proc)

    # 2. Wait for Backend Readiness
    if not wait_for_backend(backend_proc, timeout_seconds=12):
        print("[Project Amica] Aborting startup due to backend failure.")
        terminate_processes()
        return

    # 3. Determine Frontend Command
    flet_bin = resolve_executable("flet")
    if flet_bin:
        frontend_cmd = [flet_bin, "run", "frontend/app.py"]
    else:
        frontend_cmd = [sys.executable, "frontend/app.py"]

    print(f"[Project Amica] Launching Frontend: {' '.join(frontend_cmd)}")
    frontend_proc = subprocess.Popen(
        frontend_cmd,
        cwd=base_dir,
    )
    child_processes.append(frontend_proc)

    print("[Project Amica] Both services launched successfully.")
    print("[Project Amica] Press Ctrl+C at any time to gracefully terminate both services.")
    print("=" * 70)

    # 4. Monitor Process Lifecycles
    try:
        while True:
            # If backend crashes unexpectedly
            if backend_proc.poll() is not None:
                print(f"[Project Amica] Backend exited unexpectedly with code {backend_proc.returncode}.")
                break

            # If frontend window is closed by user
            if frontend_proc.poll() is not None:
                print(f"[Project Amica] Frontend window closed (exit code: {frontend_proc.returncode}).")
                break

            time.sleep(0.5)

    except KeyboardInterrupt:
        pass
    finally:
        terminate_processes()


if __name__ == "__main__":
    main()

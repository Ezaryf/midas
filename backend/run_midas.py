import sys
import os
import subprocess
import threading
import datetime
import glob
import time
import socket

# Configuration
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

def get_log_filename():
    """Generates the log filename for the current day."""
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    return os.path.join(LOG_DIR, f"midas-{date_str}.log")

def cleanup_old_logs():
    """Keeps only logs from the last 7 days and deletes older ones."""
    try:
        log_files = glob.glob(os.path.join(LOG_DIR, "midas-*.log"))
        now = datetime.datetime.now()
        for f in log_files:
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(f))
            if (now - mtime).days > 7:
                try:
                    os.remove(f)
                except OSError:
                    pass
    except Exception:
        pass

def write_log(line):
    """Writes a line to the terminal and to the daily log file."""
    sys.stdout.write(line)
    sys.stdout.flush()
    try:
        with open(get_log_filename(), "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass

def stream_reader(pipe):
    """Reads lines from a subprocess pipe and pushes to the unified log."""
    try:
        for line in iter(pipe.readline, b''):
            decoded = line.decode("utf-8", errors="replace")
            write_log(decoded)
    except ValueError:
        pass  # Handle closed file during shutdown

def start_process(command):
    """Spawns a subprocess and starts a thread to read its stdout/stderr."""
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # Merge stderr into stdout
        cwd=os.path.dirname(os.path.abspath(__file__)) or ".",
        env=os.environ.copy()
    )
    
    thread = threading.Thread(target=stream_reader, args=(process.stdout,), daemon=True)
    thread.start()
    return process


def restart_process(name, command, current_process):
    if current_process is None:
        if port_is_listening(8000):
            return None
        write_log(
            f"{datetime.datetime.now().strftime('%H:%M:%S')} [WARNING] [run_midas] "
            f"{name} is unmanaged and port 8000 is down. Starting managed backend...\n"
        )
        return start_process(command)

    exit_code = current_process.poll()
    if exit_code is None:
        return current_process
    write_log(
        f"{datetime.datetime.now().strftime('%H:%M:%S')} [WARNING] [run_midas] "
        f"{name} exited with code {exit_code}. Restarting...\n"
    )
    return start_process(command)


def port_is_listening(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def wait_for_port(port, timeout_seconds=25):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if port_is_listening(port):
            return True
        time.sleep(0.25)
    return False


def _listening_pids_for_port(port):
    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return set()

    pids = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        proto, local_addr, _, state, pid = parts[:5]
        if proto.upper() != "TCP" or state.upper() != "LISTENING":
            continue
        if not local_addr.endswith(f":{port}"):
            continue
        try:
            pids.add(int(pid))
        except ValueError:
            continue
    return pids


def _process_details(pid):
    script = (
        f"$p = Get-CimInstance Win32_Process -Filter \"ProcessId = {pid}\"; "
        "if ($p) { "
        "$lines = @(); "
        "if ($p.CommandLine) { $lines += $p.CommandLine }; "
        "if ($p.ExecutablePath) { $lines += $p.ExecutablePath }; "
        "$lines -join \"`n\" "
        "}"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
        )
        return (result.stdout or "").strip()
    except Exception:
        return ""


def _process_image_name(pid):
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return ""

    line = (result.stdout or "").strip().splitlines()
    if not line:
        return ""
    first = line[0].strip()
    if not first or first.upper().startswith("INFO:"):
        return ""
    try:
        return first.split('","', 1)[0].strip('"')
    except Exception:
        return ""


def release_stale_backend_port(port):
    backend_dir = os.path.dirname(os.path.abspath(__file__)).lower()
    terminated = []

    for pid in sorted(_listening_pids_for_port(port)):
        if pid == os.getpid():
            continue
        details = _process_details(pid).lower()
        image_name = _process_image_name(pid).lower()
        is_workspace_backend = backend_dir in details and (
            "main.py" in details or "uvicorn" in details or "python" in details
        )
        is_opaque_python_listener = not details and image_name.startswith("python")
        if not is_workspace_backend and not is_opaque_python_listener:
            continue

        write_log(
            f"{datetime.datetime.now().strftime('%H:%M:%S')} [WARNING] [run_midas] "
            f"Port {port} is already in use by stale backend PID {pid}. Terminating it before restart.\n"
        )
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        terminated.append(pid)

    if terminated:
        deadline = time.time() + 8
        while time.time() < deadline:
            if not port_is_listening(port):
                break
            time.sleep(0.25)

    return terminated

if __name__ == "__main__":
    cleanup_old_logs()
    released_pids = release_stale_backend_port(8000)
    
    # Define commands with unbuffered python execution
    backend_cmd = [sys.executable, "-u", "main.py"]
    bridge_cmd = [sys.executable, "-u", "mt5_bridge.py"] + sys.argv[1:]
    
    msg = f"{datetime.datetime.now().strftime('%H:%M:%S')} [INFO] [run_midas] Starting Unified Midas System...\n"
    write_log(msg)
    if released_pids:
        write_log(
            f"{datetime.datetime.now().strftime('%H:%M:%S')} [INFO] [run_midas] "
            f"Released stale backend PID(s): {', '.join(str(pid) for pid in released_pids)}\n"
        )
    existing_backend = port_is_listening(8000)
    elif_msg = None
    if not released_pids and existing_backend:
        elif_msg = (
            f"{datetime.datetime.now().strftime('%H:%M:%S')} [WARNING] [run_midas] "
            "Port 8000 is already occupied by a live backend. Reusing it instead of spawning a duplicate.\n"
        )
        write_log(elif_msg)
    elif port_is_listening(8000):
        write_log(
            f"{datetime.datetime.now().strftime('%H:%M:%S')} [WARNING] [run_midas] "
            "Port 8000 is already occupied by another process. The new backend may not start cleanly.\n"
        )
    
    backend_proc = None if existing_backend and not released_pids else start_process(backend_cmd)
    if wait_for_port(8000):
        write_log(
            f"{datetime.datetime.now().strftime('%H:%M:%S')} [INFO] [run_midas] "
            "Backend is listening on port 8000. Starting MT5 bridge...\n"
        )
    else:
        write_log(
            f"{datetime.datetime.now().strftime('%H:%M:%S')} [WARNING] [run_midas] "
            "Backend did not open port 8000 within 25s. Starting bridge anyway so restart watchdog can recover.\n"
        )
    bridge_proc = start_process(bridge_cmd)
    
    try:
        while True:
            time.sleep(1)
            backend_proc = restart_process("Backend", backend_cmd, backend_proc)
            bridge_proc = restart_process("MT5 bridge", bridge_cmd, bridge_proc)
            
            # Periodic log rotation/cleanup check exactly at midnight
            now = datetime.datetime.now()
            if now.hour == 0 and now.minute == 0 and now.second < 2:
                cleanup_old_logs()
                time.sleep(2)
                
    except KeyboardInterrupt:
        write_log(f"{datetime.datetime.now().strftime('%H:%M:%S')} [INFO] [run_midas] Shutting down Midas System...\n")
        
        # Graceful terminate
        if backend_proc.poll() is None:
            backend_proc.terminate()
        if bridge_proc.poll() is None:
            bridge_proc.terminate()
            
        try:
            backend_proc.wait(timeout=5)
            bridge_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            backend_proc.kill()
            bridge_proc.kill()

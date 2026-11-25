"""
Desk-Pal Companion Siderunner & Services Supervisor
Manages lightweight companion Python services, daemons, and microservices
running directly on the Raspberry Pi alongside Desk-Pal.
"""

import collections
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from typing import Dict, List, Optional, Any

logger = logging.getLogger("CompanionSupervisor")


class CompanionService:
    def __init__(self, service_id: str, service_dir: str, manifest: dict):
        self.id = service_id
        self.service_dir = service_dir
        self.manifest = manifest
        self.name = manifest.get("name", service_id)
        self.description = manifest.get("description", "")
        self.entrypoint = manifest.get("entrypoint", "main.py")
        self.port = manifest.get("port")
        self.auto_start = bool(manifest.get("auto_start", False))
        self.env = manifest.get("env", {})

        self.process: Optional[subprocess.Popen] = None
        self.pid: Optional[int] = None
        self.start_time: Optional[float] = None
        self.status: str = "stopped"  # stopped, running, crashed
        self.exit_code: Optional[int] = None

        self.logs: collections.deque = collections.deque(maxlen=300)
        self.log_file_path: Optional[str] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._stop_requested: bool = False

        self.restart_times: List[float] = []

    def to_dict(self) -> dict:
        uptime = 0
        if self.status == "running" and self.start_time:
            uptime = int(time.time() - self.start_time)
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "entrypoint": self.entrypoint,
            "port": self.port,
            "auto_start": self.auto_start,
            "status": self.status,
            "pid": self.pid,
            "uptime_seconds": uptime,
            "exit_code": self.exit_code,
            "recent_logs": list(self.logs)[-20:],
            "log_count": len(self.logs),
        }


class CompanionSupervisor:
    def __init__(self, services_dir: str, logs_dir: Optional[str] = None):
        self.services_dir = os.path.abspath(services_dir)
        self.logs_dir = os.path.abspath(logs_dir) if logs_dir else os.path.join(self.services_dir, "..", "logs", "services")
        os.makedirs(self.services_dir, exist_ok=True)
        os.makedirs(self.logs_dir, exist_ok=True)

        self.services: Dict[str, CompanionService] = {}
        self._lock = threading.RLock()
        self._monitor_thread: Optional[threading.Thread] = None
        self._running: bool = True

        self.discover_services()
        self._start_monitor_loop()

    def discover_services(self) -> List[dict]:
        with self._lock:
            if not os.path.exists(self.services_dir):
                return []

            found_ids = set()
            for item in os.listdir(self.services_dir):
                full_path = os.path.join(self.services_dir, item)

                if os.path.isdir(full_path):
                    service_id = item
                    manifest_file = os.path.join(full_path, "service.json")
                    if os.path.exists(manifest_file):
                        try:
                            with open(manifest_file, "r", encoding="utf-8") as f:
                                manifest = json.load(f)
                        except Exception as e:
                            logger.warning(f"Error loading {manifest_file}: {e}")
                            manifest = {"id": service_id, "name": service_id, "entrypoint": "main.py"}
                    else:
                        entrypoint = "main.py" if os.path.exists(os.path.join(full_path, "main.py")) else ""
                        if not entrypoint:
                            py_files = [f for f in os.listdir(full_path) if f.endswith(".py")]
                            entrypoint = py_files[0] if py_files else "main.py"
                        manifest = {
                            "id": service_id,
                            "name": service_id.replace("_", " ").title(),
                            "entrypoint": entrypoint,
                            "auto_start": False,
                        }

                    found_ids.add(service_id)
                    if service_id not in self.services:
                        svc = CompanionService(service_id, full_path, manifest)
                        svc.log_file_path = os.path.join(self.logs_dir, f"{service_id}.log")
                        self.services[service_id] = svc
                    else:
                        # Update metadata
                        svc = self.services[service_id]
                        svc.manifest = manifest
                        svc.name = manifest.get("name", service_id)
                        svc.description = manifest.get("description", "")
                        svc.entrypoint = manifest.get("entrypoint", "main.py")
                        svc.port = manifest.get("port")
                        svc.auto_start = bool(manifest.get("auto_start", False))
                        svc.env = manifest.get("env", {})

                elif item.endswith(".py"):
                    service_id = os.path.splitext(item)[0]
                    found_ids.add(service_id)
                    if service_id not in self.services:
                        manifest = {
                            "id": service_id,
                            "name": service_id.replace("_", " ").title(),
                            "entrypoint": item,
                            "auto_start": False,
                        }
                        svc = CompanionService(service_id, self.services_dir, manifest)
                        svc.log_file_path = os.path.join(self.logs_dir, f"{service_id}.log")
                        self.services[service_id] = svc

            # Clean up removed services that are stopped
            for sid in list(self.services.keys()):
                if sid not in found_ids and self.services[sid].status != "running":
                    del self.services[sid]

            return [svc.to_dict() for svc in self.services.values()]

    def start_auto_services(self):
        with self._lock:
            self.discover_services()
            for sid, svc in self.services.items():
                if svc.auto_start and svc.status != "running":
                    self.start_service(sid)

    def start_service(self, service_id: str) -> dict:
        with self._lock:
            if service_id not in self.services:
                self.discover_services()
            if service_id not in self.services:
                return {"success": False, "error": f"Service '{service_id}' not found"}

            svc = self.services[service_id]
            if svc.status == "running" and svc.process and svc.process.poll() is None:
                return {"success": True, "message": "Already running", "service": svc.to_dict()}

            script_path = os.path.join(svc.service_dir, svc.entrypoint)
            if not os.path.exists(script_path):
                return {"success": False, "error": f"Entrypoint not found: {script_path}"}

            run_env = os.environ.copy()
            run_env["PYTHONUNBUFFERED"] = "1"
            if svc.port:
                run_env["PORT"] = str(svc.port)
            if svc.env:
                for k, v in svc.env.items():
                    run_env[str(k)] = str(v)

            svc._stop_requested = False
            try:
                svc.process = subprocess.Popen(
                    [sys.executable, "-u", script_path],
                    cwd=svc.service_dir,
                    env=run_env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                svc.pid = svc.process.pid
                svc.start_time = time.time()
                svc.status = "running"
                svc.exit_code = None

                # Start background log reader
                svc._reader_thread = threading.Thread(
                    target=self._log_reader,
                    args=(svc,),
                    name=f"svc-log-{service_id}",
                    daemon=True,
                )
                svc._reader_thread.start()

                logger.info(f"Started companion service {service_id} (PID: {svc.pid})")
                return {"success": True, "message": "Service started", "service": svc.to_dict()}

            except Exception as e:
                svc.status = "crashed"
                svc.exit_code = -1
                logger.error(f"Failed to start service {service_id}: {e}")
                return {"success": False, "error": str(e)}

    def stop_service(self, service_id: str, mark_stopped: bool = True) -> dict:
        with self._lock:
            if service_id not in self.services:
                return {"success": False, "error": f"Service '{service_id}' not found"}

            svc = self.services[service_id]
            svc._stop_requested = mark_stopped

            if not svc.process or svc.process.poll() is not None:
                if mark_stopped:
                    svc.status = "stopped"
                    svc.pid = None
                return {"success": True, "message": "Already stopped", "service": svc.to_dict()}

            proc = svc.process
            pid = svc.pid
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2.0)
            except Exception as e:
                logger.warning(f"Error terminating service {service_id}: {e}")

            if mark_stopped:
                svc.status = "stopped"
                svc.pid = None
                svc.exit_code = proc.returncode

            logger.info(f"Stopped companion service {service_id} (was PID: {pid})")
            return {"success": True, "message": "Service stopped", "service": svc.to_dict()}

    def restart_service(self, service_id: str) -> dict:
        with self._lock:
            self.stop_service(service_id, mark_stopped=False)
            time.sleep(0.5)
            return self.start_service(service_id)

    def get_service_code(self, service_id: str) -> dict:
        with self._lock:
            if service_id not in self.services:
                self.discover_services()
            if service_id not in self.services:
                return {"success": False, "error": f"Service '{service_id}' not found"}

            svc = self.services[service_id]
            script_path = os.path.join(svc.service_dir, svc.entrypoint)
            if not os.path.exists(script_path):
                return {"success": False, "error": "Script file does not exist"}

            try:
                with open(script_path, "r", encoding="utf-8") as f:
                    code = f.read()
                return {"success": True, "code": code, "manifest": svc.manifest}
            except Exception as e:
                return {"success": False, "error": str(e)}

    def save_service(
        self,
        service_id: str,
        name: str,
        description: str,
        code: str,
        entrypoint: str = "main.py",
        auto_start: bool = False,
        port: Optional[int] = None,
        env: Optional[dict] = None,
    ) -> dict:
        with self._lock:
            clean_id = "".join(c for c in service_id.strip() if c.isalnum() or c in ("_", "-")).lower()
            if not clean_id:
                return {"success": False, "error": "Invalid service ID"}

            svc_dir = os.path.join(self.services_dir, clean_id)
            os.makedirs(svc_dir, exist_ok=True)

            manifest = {
                "id": clean_id,
                "name": name or clean_id.title(),
                "description": description or "",
                "entrypoint": entrypoint or "main.py",
                "auto_start": bool(auto_start),
                "port": int(port) if port else None,
                "env": env or {},
            }

            manifest_file = os.path.join(svc_dir, "service.json")
            script_file = os.path.join(svc_dir, manifest["entrypoint"])

            try:
                with open(manifest_file, "w", encoding="utf-8") as f:
                    json.dump(manifest, f, indent=2)
                with open(script_file, "w", encoding="utf-8") as f:
                    f.write(code)
            except Exception as e:
                return {"success": False, "error": f"Failed to save service files: {e}"}

            self.discover_services()
            # If it was running, restart it to load new code
            svc = self.services.get(clean_id)
            if svc and svc.status == "running":
                self.restart_service(clean_id)

            return {"success": True, "service": svc.to_dict() if svc else manifest}

    def delete_service(self, service_id: str) -> dict:
        with self._lock:
            if service_id not in self.services:
                return {"success": False, "error": "Service not found"}

            svc = self.services[service_id]
            self.stop_service(service_id)

            if svc.service_dir != self.services_dir and os.path.exists(svc.service_dir):
                try:
                    shutil.rmtree(svc.service_dir)
                except Exception as e:
                    return {"success": False, "error": f"Failed to remove directory: {e}"}
            else:
                # Standalone file in services/
                script_path = os.path.join(svc.service_dir, svc.entrypoint)
                if os.path.exists(script_path):
                    try:
                        os.remove(script_path)
                    except Exception as e:
                        return {"success": False, "error": f"Failed to remove script: {e}"}

            del self.services[service_id]
            return {"success": True, "message": f"Service '{service_id}' deleted"}

    def get_logs(self, service_id: str, max_lines: int = 100) -> List[str]:
        with self._lock:
            svc = self.services.get(service_id)
            if not svc:
                return []
            return list(svc.logs)[-max_lines:]

    def shutdown_all(self):
        logger.info("Shutting down all companion services...")
        self._running = False
        with self._lock:
            for sid, svc in self.services.items():
                if svc.status == "running":
                    try:
                        self.stop_service(sid)
                    except Exception as e:
                        logger.warning(f"Error stopping service {sid} during shutdown: {e}")

    def _log_reader(self, svc: CompanionService):
        proc = svc.process
        if not proc or not proc.stdout:
            return

        log_f = None
        if svc.log_file_path:
            try:
                if os.path.exists(svc.log_file_path) and os.path.getsize(svc.log_file_path) > 1_000_000:
                    backup = svc.log_file_path + ".1"
                    if os.path.exists(backup):
                        try: os.remove(backup)
                        except Exception: pass
                    try: os.rename(svc.log_file_path, backup)
                    except Exception: pass
                log_f = open(svc.log_file_path, "a", encoding="utf-8")
            except Exception:
                pass

        try:
            for line in proc.stdout:
                line_str = line.rstrip()
                timestamp = time.strftime("%H:%M:%S")
                entry = f"[{timestamp}] {line_str}"
                svc.logs.append(entry)
                if log_f:
                    try:
                        log_f.write(entry + "\n")
                        log_f.flush()
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            if log_f:
                try:
                    log_f.close()
                except Exception:
                    pass

    def _start_monitor_loop(self):
        def monitor():
            while self._running:
                time.sleep(2.0)
                if not self._running:
                    break
                with self._lock:
                    now = time.time()
                    for sid, svc in list(self.services.items()):
                        if svc.status == "running" and svc.process:
                            ret = svc.process.poll()
                            if ret is not None:
                                svc.exit_code = ret
                                svc.pid = None
                                if svc._stop_requested:
                                    svc.status = "stopped"
                                    logger.info(f"Service {sid} stopped normally (exit: {ret})")
                                else:
                                    # Unexpected termination!
                                    svc.status = "crashed"
                                    logger.warning(f"Service {sid} exited unexpectedly (code {ret})")
                                    # Check auto-restart eligibility
                                    if svc.auto_start:
                                        # Prune restarts older than 60s
                                        svc.restart_times = [t for t in svc.restart_times if now - t < 60]
                                        if len(svc.restart_times) < 5:
                                            svc.restart_times.append(now)
                                            logger.info(f"Auto-restarting crashed service {sid} (attempt {len(svc.restart_times)}/5)...")
                                            threading.Thread(target=self.start_service, args=(sid,), daemon=True).start()
                                        else:
                                            logger.error(f"Service {sid} exceeded restart rate limit; leaving crashed.")

        self._monitor_thread = threading.Thread(target=monitor, name="companion-supervisor-mon", daemon=True)
        self._monitor_thread.start()

"""Infra dos testes de integração: daemon isolado + stubs de ferramentas."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
DAEMON_DIR = TESTS_DIR.parent
REPO = DAEMON_DIR.parent
STUBS = TESTS_DIR / "stubs"
RULE_ASSET = REPO / "assets/kwin/Transparencia-Global.kwinrule"
RULE_FALLBACK = REPO / "Transparência Global.kwinrule"


class Harness:
    """Sobe um daemon com HOME/runtime isolados e PATH com stubs."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = Path(tmp)
        self.home = self.tmp / "home"
        (self.home / ".config").mkdir(parents=True, exist_ok=True)
        self.run_dir = self.tmp / "run"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.state = self.tmp / "state"
        self.state.mkdir(parents=True, exist_ok=True)
        self.calls = self.tmp / "calls.log"

        assets = self.home / ".local/share/agenticos/assets"
        assets.mkdir(parents=True, exist_ok=True)
        source = RULE_ASSET if RULE_ASSET.exists() else RULE_FALLBACK
        shutil.copy2(source, assets / "Transparencia-Global.kwinrule")

        env = dict(os.environ)
        env.update(
            {
                "AGENTICOS_HOME_DIR": str(self.home),
                "AGENTICOS_RUNTIME_DIR": str(self.run_dir),
                "AGENTICOS_STUB_STATE": str(self.state),
                "AGENTICOS_STUB_LOG": str(self.calls),
                "PATH": f"{STUBS}:{env.get('PATH', '')}",
                "PYTHONPATH": str(DAEMON_DIR) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""),
            }
        )
        self.env = env
        self.socket = self.run_dir / "agenticd.sock"
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "agenticos.daemon", "--socket", str(self.socket)],
            env=env,
            cwd=str(DAEMON_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self._wait_socket()

    def _wait_socket(self, timeout: float = 10.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.socket.exists():
                return
            if self.proc.poll() is not None:
                output = self.proc.stdout.read().decode("utf-8", "replace") if self.proc.stdout else ""
                raise RuntimeError(f"daemon morreu na inicialização:\n{output}")
            time.sleep(0.05)
        raise RuntimeError("timeout esperando o socket do daemon")

    def call(self, action: str, params: dict | None = None, **extra) -> dict:
        request = {"id": 1, "action": action, "params": params or {}, "actor": "test", **extra}
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(30)
            client.connect(str(self.socket))
            client.sendall(json.dumps(request, ensure_ascii=False).encode("utf-8") + b"\n")
            buffer = b""
            while b"\n" not in buffer:
                chunk = client.recv(65536)
                if not chunk:
                    break
                buffer += chunk
        return json.loads(buffer.split(b"\n", 1)[0].decode("utf-8"))

    def cli(self, *args: str) -> tuple[int, dict | None]:
        proc = subprocess.run(
            [sys.executable, "-m", "agenticos.cli", "--socket", str(self.socket), "--json", *args],
            env=self.env,
            cwd=str(DAEMON_DIR),
            capture_output=True,
            text=True,
            timeout=60,
        )
        try:
            payload = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.stdout.strip() else None
        except (json.JSONDecodeError, IndexError):
            payload = None
        return proc.returncode, payload

    def stub_calls(self) -> str:
        return self.calls.read_text(encoding="utf-8") if self.calls.exists() else ""

    def make_widget(self, widget_id: str = "com.agenticos.testwidget") -> Path:
        path = self.home / "widget-src"
        path.mkdir(parents=True, exist_ok=True)
        (path / "metadata.json").write_text(
            json.dumps({"KPlugin": {"Id": widget_id, "Name": "Test Widget"}}), encoding="utf-8"
        )
        return path

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        if self.proc.stdout:
            self.proc.stdout.close()

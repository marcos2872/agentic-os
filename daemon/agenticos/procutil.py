"""Execução de processos: sempre argv explícito, nunca shell=True."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass

# Variáveis necessárias para ferramentas KDE/Qt conversarem com a sessão gráfica.
SESSION_ENV_KEYS = (
    "DBUS_SESSION_BUS_ADDRESS",
    "WAYLAND_DISPLAY",
    "DISPLAY",
    "XAUTHORITY",
    "XDG_RUNTIME_DIR",
    "XDG_SESSION_TYPE",
    "XDG_CURRENT_DESKTOP",
    "XDG_SESSION_DESKTOP",
    "KDE_FULL_SESSION",
    "KDE_SESSION_VERSION",
    "QT_QPA_PLATFORM",
)


@dataclass
class Result:
    ok: bool
    code: int | None
    out: str
    err: str
    argv: list[str]

    def summary(self) -> str:
        if self.ok:
            return f"{self.argv[0]}: ok"
        detail = (self.err or self.out).strip().splitlines()
        first = detail[0] if detail else f"exit {self.code}"
        return f"{self.argv[0]}: {first}"


def which(name: str) -> str | None:
    return shutil.which(name)


def run(
    argv: list[str],
    *,
    timeout: float | None = None,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
) -> Result:
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=cwd,
            check=False,
        )
    except FileNotFoundError:
        return Result(False, None, "", f"binário não encontrado: {argv[0]}", argv)
    except subprocess.TimeoutExpired:
        return Result(False, None, "", f"timeout após {timeout}s", argv)
    except OSError as exc:  # permissão, executável inválido etc.
        return Result(False, None, "", f"falha ao executar {argv[0]}: {exc}", argv)
    return Result(proc.returncode == 0, proc.returncode, proc.stdout or "", proc.stderr or "", argv)


def spawn_detached(argv: list[str], *, env: dict[str, str] | None = None, cwd: str | None = None) -> int:
    """Lança um app gráfico desacoplado do daemon. Retorna o PID."""
    proc = subprocess.Popen(
        argv,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        env=env,
        cwd=cwd,
    )
    return proc.pid


def _session_ready(env: dict[str, str]) -> bool:
    return bool(env.get("DBUS_SESSION_BUS_ADDRESS")) and bool(
        env.get("WAYLAND_DISPLAY") or env.get("DISPLAY")
    )


def session_env() -> dict[str, str]:
    """Ambiente para falar com a sessão gráfica.

    Daemon roda como serviço systemd --user; dependendo da distro ele já
    herda as variáveis da sessão. Se faltar algo, tenta:
    1) `systemctl --user show-environment`;
    2) varredura de /proc/<pid>/environ de processos do mesmo uid.
    """
    env = dict(os.environ)
    if _session_ready(env):
        return env

    res = run(["systemctl", "--user", "show-environment"], timeout=5)
    if res.ok:
        for line in res.out.splitlines():
            key, sep, value = line.partition("=")
            if sep and key in SESSION_ENV_KEYS and key not in env and value:
                env[key] = value
    if _session_ready(env):
        return env

    uid = os.getuid()
    scanned = 0
    try:
        for entry in sorted(os.listdir("/proc"), reverse=True):
            if scanned >= 400:
                break
            if not entry.isdigit():
                continue
            pid_dir = f"/proc/{entry}"
            try:
                if os.stat(pid_dir).st_uid != uid:
                    continue
                scanned += 1
                with open(f"{pid_dir}/environ", "rb") as handle:
                    blob = handle.read(65536)
            except (OSError, PermissionError):
                continue
            found: dict[str, str] = {}
            for chunk in blob.split(b"\0"):
                if b"=" not in chunk:
                    continue
                key_b, _, value_b = chunk.partition(b"=")
                key = key_b.decode("utf-8", "replace")
                if key in SESSION_ENV_KEYS:
                    found[key] = value_b.decode("utf-8", "replace")
            if _session_ready(found):
                for key, value in found.items():
                    env.setdefault(key, value)
                return env
    except OSError:
        pass
    return env

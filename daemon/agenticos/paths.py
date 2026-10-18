"""Resolução de caminhos do Agentic OS.

Tudo vive em $HOME e no runtime do usuário (sem root). As variáveis
AGENTICOS_* permitem testes isolados com HOME temporário.
"""

from __future__ import annotations

import os
from pathlib import Path


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    if not value:
        return None
    return Path(value).expanduser()


class Paths:
    """Diretórios do Agentic OS."""

    def __init__(self) -> None:
        self.home: Path = _env_path("AGENTICOS_HOME_DIR") or Path.home()
        self.data: Path = _env_path("AGENTICOS_DATA_DIR") or (self.home / ".local/share/agenticos")
        runtime_root = _env_path("AGENTICOS_RUNTIME_DIR") or (
            Path(os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/agenticos-{os.getuid()}") / "agenticos"
        )
        self.runtime: Path = runtime_root
        self.config: Path = _env_path("AGENTICOS_CONFIG_DIR") or (self.home / ".config/agenticos")

        self.assets: Path = self.data / "assets"
        self.undo_dir: Path = self.data / "undo"
        self.undo_applied: Path = self.undo_dir / "applied"
        self.backups: Path = self.data / "backups"
        self.audit_file: Path = self.data / "audit.jsonl"
        self.socket: Path = self.runtime / "agenticd.sock"

    def ensure(self) -> None:
        for path in (
            self.data,
            self.runtime,
            self.config,
            self.assets,
            self.undo_dir,
            self.undo_applied,
            self.backups,
        ):
            path.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.runtime, 0o700)
        except OSError:
            pass

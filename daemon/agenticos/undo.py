"""Backup de arquivos + registro de undo.

Cada ação mutável registra um "undo" (ação inversa + parâmetros). O chat
pode desfazer com `undo.last`. Arquivos modificados ganham cópia em
`~/.local/share/agenticos/backups/` antes da escrita.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from .paths import Paths

MAX_ENTRIES = 100
MAX_BACKUPS = 50


def backup_file(paths: Paths, target: Path) -> str | None:
    """Copia o arquivo antes de alterá-lo. Retorna o caminho do backup."""
    if not target.exists():
        return None
    paths.backups.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    digest = hashlib.sha256(str(target).encode("utf-8")).hexdigest()[:8]
    dest = paths.backups / f"{stamp}-{digest}-{target.name}"
    shutil.copy2(target, dest)
    _prune_backups(paths)
    return str(dest)


def _prune_backups(paths: Paths) -> None:
    backups = sorted(path for path in paths.backups.glob("*") if path.is_file())
    for path in backups[: max(0, len(backups) - MAX_BACKUPS)]:
        try:
            path.unlink()
        except OSError:
            pass


def register(
    paths: Paths,
    *,
    action: str,
    params: dict[str, Any],
    undo: dict[str, Any] | None,
    summary: str,
) -> str | None:
    """Registra entrada de undo. Retorna o id (None se nada a desfazer)."""
    if undo is None:
        return None
    paths.undo_dir.mkdir(parents=True, exist_ok=True)
    # Prefixo com nanossegundos garante ordenação estável (mesmo segundo).
    entry_id = f"{time.time_ns()}-{uuid.uuid4().hex[:8]}"
    entry = {
        "id": entry_id,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        "action": action,
        "params": params,
        "undo": undo,
        "summary": summary,
    }
    (paths.undo_dir / f"{entry_id}.json").write_text(
        json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _prune(paths)
    return entry_id


def _entry_files(paths: Paths) -> list[Path]:
    if not paths.undo_dir.exists():
        return []
    return sorted(
        (p for p in paths.undo_dir.glob("*.json") if p.is_file()),
        key=lambda p: p.name,
    )


def _prune(paths: Paths) -> None:
    files = _entry_files(paths)
    if len(files) <= MAX_ENTRIES:
        return
    paths.undo_applied.mkdir(parents=True, exist_ok=True)
    for path in files[: len(files) - MAX_ENTRIES]:
        try:
            shutil.move(str(path), str(paths.undo_applied / path.name))
        except OSError:
            pass


def list_entries(paths: Paths, limit: int = 20) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in reversed(_entry_files(paths)[-limit:]):
        try:
            entries.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return entries


def pop_last(paths: Paths) -> dict[str, Any] | None:
    """Remove e retorna a última entrada de undo (ordem: mais recente)."""
    files = _entry_files(paths)
    if not files:
        return None
    path = files[-1]
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    paths.undo_applied.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(path), str(paths.undo_applied / path.name))
    except OSError:
        pass
    return entry


def restore_backup(paths: Paths, backup_path: str, target: Path) -> None:
    source = Path(backup_path)
    if not source.exists():
        raise FileNotFoundError(f"backup não encontrado: {backup_path}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)

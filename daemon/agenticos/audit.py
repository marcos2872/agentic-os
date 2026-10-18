"""Auditoria: toda ação (pedido, plano, resultado) vira uma linha JSONL."""

from __future__ import annotations

import json
import time
from collections import deque
from typing import Any

from .paths import Paths


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def append(paths: Paths, record: dict[str, Any]) -> None:
    record = {"ts": _now_iso(), **record}
    paths.data.mkdir(parents=True, exist_ok=True)
    with paths.audit_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def tail(paths: Paths, n: int = 20) -> list[dict[str, Any]]:
    n = max(1, min(int(n), 200))
    if not paths.audit_file.exists():
        return []
    # Streaming com deque: memória constante mesmo com auditoria grande.
    lines: deque[str] = deque(maxlen=n)
    with paths.audit_file.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if line:
                lines.append(line)
    entries: list[dict[str, Any]] = []
    for line in lines:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries

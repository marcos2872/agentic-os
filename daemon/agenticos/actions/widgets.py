"""Ações: widget.list / widget.install / widget.remove — plasmoids no usuário.

Plasmoids ficam em ~/.local/share/plasma/plasmoids (camada mutável, fora da
base imutável) e são gerenciados com kpackagetool6.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from .. import procutil
from ..policy import ActionError
from . import Ctx, register

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _kpt() -> str:
    binary = procutil.which("kpackagetool6")
    if binary is None:
        raise ActionError("kpackagetool6 não encontrado (pacote plasma-workspace/plasma-sdk)")
    return binary


def _installed() -> list[str]:
    result = procutil.run([_kpt(), "-t", "Plasma/Applet", "--list"], timeout=60)
    if not result.ok:
        raise ActionError(result.summary())
    return [line.strip() for line in result.out.splitlines() if line.strip()]


def _registry_path(ctx: Ctx) -> Path:
    return ctx.paths.data / "widgets.json"


def _load_registry(ctx: Ctx) -> dict[str, Any]:
    path = _registry_path(ctx)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_registry(ctx: Ctx, data: dict[str, Any]) -> None:
    ctx.paths.data.mkdir(parents=True, exist_ok=True)
    _registry_path(ctx).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _kbuildsycoca() -> None:
    binary = procutil.which("kbuildsycoca6")
    if binary:
        procutil.run([binary], timeout=60)


@register("widget.list")
def widget_list(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    installed = _installed()
    registry = _load_registry(ctx)
    widgets = []
    for widget_id in installed:
        info = registry.get(widget_id) or {}
        widgets.append({"id": widget_id, "source": info.get("source"), "managed": bool(info)})
    return {"result": {"widgets": widgets, "count": len(widgets)}, "undo": None, "summary": f"{len(widgets)} widgets"}


@register("widget.install")
def widget_install(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(params["path"])).expanduser().resolve()
    allowed = [ctx.paths.home.resolve(), Path("/tmp"), Path("/var/tmp")]
    if not any(path == base or base in path.parents for base in allowed):
        raise ActionError("widget.install aceita apenas diretórios dentro de $HOME, /tmp ou /var/tmp")

    meta_file = path / "metadata.json"
    if not meta_file.is_file():
        raise ActionError(f"metadata.json ausente em {path}")
    try:
        metadata = json.loads(meta_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ActionError(f"metadata.json inválido: {exc}") from exc
    widget_id = str((metadata.get("KPlugin") or {}).get("Id") or "").strip()
    if not ID_RE.match(widget_id):
        raise ActionError("metadata.json sem KPlugin.Id válido")

    was_installed = widget_id in _installed()
    flag = "-u" if was_installed else "-i"
    result = procutil.run([_kpt(), "-t", "Plasma/Applet", flag, str(path)], timeout=180)
    if not result.ok:
        raise ActionError("falha ao instalar widget: " + (result.err or result.out).strip()[:300])
    _kbuildsycoca()

    registry = _load_registry(ctx)
    registry[widget_id] = {"source": str(path), "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    _save_registry(ctx, registry)

    inverse = None if was_installed else {"action": "widget.remove", "params": {"id": widget_id}}
    return {
        "result": {"installed": widget_id, "updated": was_installed, "source": str(path)},
        "undo": inverse,
        "summary": f"{'atualizar' if was_installed else 'instalar'} widget {widget_id}",
    }


@register("widget.remove")
def widget_remove(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    widget_id = str(params["id"]).strip()
    if not ID_RE.match(widget_id):
        raise ActionError(f"id de widget inválido: {widget_id!r}")
    if widget_id not in _installed():
        raise ActionError(f"widget não instalado: {widget_id}")

    result = procutil.run([_kpt(), "-t", "Plasma/Applet", "-r", widget_id], timeout=60)
    if not result.ok:
        raise ActionError("falha ao remover widget: " + (result.err or result.out).strip()[:300])
    _kbuildsycoca()

    registry = _load_registry(ctx)
    source = (registry.get(widget_id) or {}).get("source")
    registry.pop(widget_id, None)
    _save_registry(ctx, registry)

    inverse = None
    if source and Path(source).is_dir():
        inverse = {"action": "widget.install", "params": {"path": source}}
    return {
        "result": {"removed": widget_id, "source": source},
        "undo": inverse,
        "summary": f"remover widget {widget_id}",
    }

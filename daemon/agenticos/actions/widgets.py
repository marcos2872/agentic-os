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

from .. import initext, procutil
from ..policy import ActionError
from . import Ctx, register

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SCRATCH_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}$")
MAX_FILE_BYTES = 128 * 1024
MAX_READ_BYTES = 64 * 1024
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates/plasmoid"


def _workspace_root(ctx: Ctx) -> Path:
    return ctx.paths.data / "workspace"


def _check_scratch_name(name: str) -> str:
    if not SCRATCH_NAME_RE.match(name):
        raise ActionError(
            f"nome de widget inválido: {name!r} (use a-z, 0-9 e hífen, começando por letra)"
        )
    return name


def _scratch_dir(ctx: Ctx, name: str) -> Path:
    return _workspace_root(ctx) / _check_scratch_name(name)


def _safe_rel_path(base: Path, rel: str) -> Path:
    raw = str(rel).strip()
    if not raw or raw.startswith("/") or ".." in Path(raw).parts or len(raw) > 300:
        raise ActionError("'path' deve ser um caminho relativo dentro do widget")
    target = (base / raw).resolve()
    if not (target == base or base in target.parents):
        raise ActionError("'path' escapa da pasta do widget (bloqueado)")
    return target


def _render_template(path: Path, replacements: dict[str, str]) -> str:
    text = path.read_text(encoding="utf-8")
    for key, value in replacements.items():
        text = text.replace(f"@{key}@", value)
    return text


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

    scratch: list[dict[str, Any]] = []
    root = _workspace_root(ctx)
    if root.is_dir():
        for directory in sorted(root.iterdir()):
            meta_file = directory / "metadata.json"
            if not (directory.is_dir() and meta_file.is_file()):
                continue
            try:
                metadata = json.loads(meta_file.read_text(encoding="utf-8"))
                widget_id = str((metadata.get("KPlugin") or {}).get("Id") or "")
            except (OSError, json.JSONDecodeError):
                widget_id = ""
            scratch.append({"name": directory.name, "id": widget_id, "path": str(directory)})

    return {
        "result": {"widgets": widgets, "count": len(widgets), "workspace": scratch},
        "undo": None,
        "summary": f"{len(widgets)} widgets instalados, {len(scratch)} em workspace",
    }


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


# ---------------------------------------------------------------------------
# Criação de widgets pelo agente: scaffold/write/read/lint no workspace
# (~/.local/share/agenticos/workspace/<nome>), e widget.install para instalar.
# ---------------------------------------------------------------------------


@register("widget.scaffold")
def widget_scaffold(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    name = _check_scratch_name(str(params["name"]).strip())
    description = str(params.get("description") or "Widget criado pelo Agentic OS").strip()
    if not description or "\n" in description or len(description) > 120:
        raise ActionError("description deve ter até 120 caracteres, sem quebra de linha")

    directory = _scratch_dir(ctx, name)
    if directory.exists():
        raise ActionError(f"workspace '{name}' já existe; use widget.write_file para editar")

    widget_id = f"com.agenticos.{name}"
    files = {
        "metadata.json": (TEMPLATES_DIR / "metadata.json", {"ID": widget_id, "NAME": name, "DESCRIPTION": description}),
        "contents/ui/main.qml": (TEMPLATES_DIR / "contents/ui/main.qml", {"NAME": name, "DESCRIPTION": description}),
    }
    for rel, (template, replacements) in files.items():
        target = _safe_rel_path(directory, rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        initext.write_text_atomic(target, _render_template(template, replacements))

    return {
        "result": {"name": name, "id": widget_id, "path": str(directory), "files": sorted(files)},
        "undo": {"action": "widget.workspace_remove", "params": {"name": name}},
        "summary": f"criar esqueleto do widget '{name}'",
    }


@register("widget.write_file")
def widget_write_file(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    name = _check_scratch_name(str(params["name"]).strip())
    content = str(params["content"])
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_FILE_BYTES:
        raise ActionError(f"conteúdo grande demais ({len(encoded)} bytes; máximo {MAX_FILE_BYTES})")
    if "\0" in content:
        raise ActionError("conteúdo binário não é suportado")

    directory = _scratch_dir(ctx, name)
    if not (directory / "metadata.json").is_file():
        raise ActionError(f"workspace '{name}' não existe; use widget.scaffold primeiro")
    target = _safe_rel_path(directory, str(params["path"]))

    previous: str | None = None
    if target.exists():
        if not target.is_file():
            raise ActionError(f"'path' aponta para algo que não é arquivo: {target}")
        try:
            previous = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            previous = None

    target.parent.mkdir(parents=True, exist_ok=True)
    initext.write_text_atomic(target, content)

    if previous is None:
        inverse = {"action": "widget.delete_file", "params": {"name": name, "path": str(params["path"])}}
    else:
        inverse = {
            "action": "widget.write_file",
            "params": {"name": name, "path": str(params["path"]), "content": previous},
        }
    return {
        "result": {
            "name": name,
            "path": str(target.relative_to(directory)),
            "bytes": len(encoded),
            "created": previous is None,
        },
        "undo": inverse,
        "summary": f"escrever {params['path']} em '{name}'",
    }


@register("widget.read_file")
def widget_read_file(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    name = _check_scratch_name(str(params["name"]).strip())
    directory = _scratch_dir(ctx, name)
    target = _safe_rel_path(directory, str(params.get("path") or "contents/ui/main.qml"))
    if not target.is_file():
        raise ActionError(f"arquivo não encontrado: {target}")
    raw = target.read_bytes()
    truncated = len(raw) > MAX_READ_BYTES
    blob = raw[:MAX_READ_BYTES]
    if b"\0" in blob:
        raise ActionError("arquivo binário: leitura não suportada")
    return {
        "result": {
            "name": name,
            "path": str(target.relative_to(directory)),
            "truncated": truncated,
            "content": blob.decode("utf-8", "replace"),
        },
        "undo": None,
        "summary": f"ler {params.get('path') or 'contents/ui/main.qml'} de '{name}'",
    }


@register("widget.delete_file")
def widget_delete_file(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    name = _check_scratch_name(str(params["name"]).strip())
    directory = _scratch_dir(ctx, name)
    target = _safe_rel_path(directory, str(params["path"]))
    if not target.is_file():
        raise ActionError(f"arquivo não encontrado: {target}")
    previous = target.read_text(encoding="utf-8", errors="replace")
    target.unlink()
    return {
        "result": {"name": name, "path": str(target.relative_to(directory))},
        "undo": {
            "action": "widget.write_file",
            "params": {"name": name, "path": str(params["path"]), "content": previous},
        },
        "summary": f"remover {params['path']} de '{name}'",
    }


@register("widget.lint")
def widget_lint(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    name = _check_scratch_name(str(params["name"]).strip())
    directory = _scratch_dir(ctx, name)
    if not (directory / "metadata.json").is_file():
        raise ActionError(f"workspace '{name}' não existe; use widget.scaffold primeiro")

    problems: list[str] = []
    try:
        json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        problems.append(f"metadata.json inválido: {exc}")

    linter = None
    for candidate in ("qmllint6", "qmllint"):
        linter = procutil.which(candidate)
        if linter:
            break

    qml_files = sorted(directory.rglob("*.qml"))[:20]
    lint_output = ""
    if linter and qml_files:
        result = procutil.run([linter, *[str(path) for path in qml_files]], timeout=120)
        lint_output = ((result.err or "") + (result.out or "")).strip()
        if not result.ok and lint_output:
            problems.append(lint_output[:2000])
    elif not linter:
        lint_output = "qmllint não instalado; validação de QML pulada"

    return {
        "result": {
            "name": name,
            "ok": not problems,
            "problems": problems,
            "lint_output": lint_output[:4000],
            "checked_files": [str(path.relative_to(directory)) for path in qml_files],
        },
        "undo": None,
        "summary": f"validar widget '{name}'",
    }


@register("widget.workspace_remove")
def widget_workspace_remove(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    name = _check_scratch_name(str(params["name"]).strip())
    directory = _scratch_dir(ctx, name)
    if not directory.is_dir():
        raise ActionError(f"workspace '{name}' não existe")

    ctx.paths.backups.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = ctx.paths.backups / f"workspace-{name}-{stamp}"
    directory.rename(dest)
    return {
        "result": {"name": name, "moved_to": str(dest), "note": "conteúdo preservado em backups"},
        "undo": None,
        "summary": f"remover workspace do widget '{name}' (movido para backups)",
    }

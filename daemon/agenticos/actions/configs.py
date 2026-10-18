"""Ações: config.get / config.set / config.unset — INI em ~/.config com backup.

Prefere as ferramentas do KDE (kreadconfig6/kwriteconfig6), que falam o
dialeto completo dos arquivos KDE; sem elas, edita linha a linha com
initext (preservando o restante do arquivo).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .. import initext, procutil, undo
from ..policy import ActionError
from . import Ctx, register

NAME_RE = re.compile(r"^[^\n\r\[\]=]{1,128}$")


def resolve_config_file(ctx: Ctx, file: str) -> Path:
    raw = str(file).strip()
    if not raw or raw.startswith("/") or ".." in Path(raw).parts:
        raise ActionError("'file' deve ser um caminho relativo dentro de ~/.config")
    base = (ctx.paths.home / ".config").resolve()
    target = (base / raw).resolve()
    if not (target == base or base in target.parents):
        raise ActionError("'file' fora de ~/.config (bloqueado por segurança)")
    return target


def _check_group_key(group: str, key: str) -> None:
    if not NAME_RE.match(group) or not NAME_RE.match(key):
        raise ActionError("grupo/chave inválidos (sem quebras de linha, '[' ou ']')")


def _check_value(value: str) -> None:
    if "\n" in value or "\r" in value:
        raise ActionError("valor não pode conter quebras de linha")


def ini_get(ctx: Ctx, path: Path, group: str, key: str) -> str | None:
    kread = procutil.which("kreadconfig6")
    if kread:
        result = procutil.run([kread, "--file", str(path), "--group", group, "--key", key], timeout=15)
        if result.ok:
            return result.out.rstrip("\n")
        return None
    if not path.exists():
        return None
    return initext.load(path).get(group, key)


def ini_set(ctx: Ctx, path: Path, group: str, key: str, value: str) -> None:
    kwrite = procutil.which("kwriteconfig6")
    if kwrite:
        result = procutil.run(
            [kwrite, "--file", str(path), "--group", group, "--key", key, value], timeout=15
        )
        if not result.ok:
            raise ActionError(result.summary())
        return
    doc = initext.load(path)
    doc.set(group, key, value)
    initext.write_text_atomic(path, doc.render())


def ini_unset(ctx: Ctx, path: Path, group: str, key: str) -> None:
    kwrite = procutil.which("kwriteconfig6")
    if kwrite:
        result = procutil.run(
            [kwrite, "--file", str(path), "--group", group, "--key", key, "--delete"], timeout=15
        )
        if not result.ok:
            raise ActionError(result.summary())
        return
    doc = initext.load(path)
    doc.unset(group, key)
    initext.write_text_atomic(path, doc.render())


@register("config.get")
def config_get(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    path = resolve_config_file(ctx, params["file"])
    group, key = str(params["group"]), str(params["key"])
    _check_group_key(group, key)
    value = ini_get(ctx, path, group, key)
    if value is None:
        raise ActionError(f"chave ausente: [{group}] {key} em {params['file']}")
    return {
        "result": {"file": str(path), "group": group, "key": key, "value": value},
        "undo": None,
        "summary": f"ler {params['file']} [{group}] {key}",
    }


@register("config.set")
def config_set(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    path = resolve_config_file(ctx, params["file"])
    group, key, value = str(params["group"]), str(params["key"]), str(params["value"])
    _check_group_key(group, key)
    _check_value(value)
    backup = undo.backup_file(ctx.paths, path)
    previous = ini_get(ctx, path, group, key) if path.exists() else None
    ini_set(ctx, path, group, key, value)

    if previous is None:
        inverse = {"action": "config.unset", "params": {"file": params["file"], "group": group, "key": key}}
    else:
        inverse = {
            "action": "config.set",
            "params": {"file": params["file"], "group": group, "key": key, "value": previous},
        }
    return {
        "result": {
            "file": str(path),
            "group": group,
            "key": key,
            "value": value,
            "previous": previous,
            "backup": backup,
        },
        "undo": inverse,
        "summary": f"config.set {params['file']} [{group}] {key}={value}",
    }


@register("config.unset")
def config_unset(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    path = resolve_config_file(ctx, params["file"])
    group, key = str(params["group"]), str(params["key"])
    _check_group_key(group, key)
    backup = undo.backup_file(ctx.paths, path)
    previous = ini_get(ctx, path, group, key)
    if previous is None:
        raise ActionError(f"chave ausente: [{group}] {key} em {params['file']}")
    ini_unset(ctx, path, group, key)
    inverse = {
        "action": "config.set",
        "params": {"file": params["file"], "group": group, "key": key, "value": previous},
    }
    return {
        "result": {"file": str(path), "group": group, "key": key, "previous": previous, "backup": backup},
        "undo": inverse,
        "summary": f"config.unset {params['file']} [{group}] {key}",
    }

"""Ações: flatpak.list / flatpak.search / flatpak.install / flatpak.uninstall."""

from __future__ import annotations

import re
from typing import Any

from .. import procutil
from ..policy import ActionError, Escalate
from . import Ctx, register

APP_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
FLATHUB_REPO = "https://dl.flathub.org/repo/flathub.flatpakrepo"


def _flatpak() -> str:
    binary = procutil.which("flatpak")
    if binary is None:
        raise ActionError("flatpak não está instalado nesta máquina")
    return binary


def _rows(output: str) -> list[list[str]]:
    rows = []
    for line in output.splitlines():
        if not line.strip():
            continue
        rows.append(line.split("\t"))
    return rows


def _scope_flag(scope: str | None) -> str:
    scope = (scope or "user").strip().lower()
    if scope not in ("user", "system"):
        raise ActionError("scope deve ser 'user' ou 'system'")
    return f"--{scope}"


@register("flatpak.list")
def flatpak_list(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    result = procutil.run(
        [_flatpak(), "list", "--app", "--columns=application,name,version,origin,installation"],
        timeout=60,
    )
    if not result.ok:
        raise ActionError(result.summary())
    apps = [
        {"app_id": row[0], "name": row[1] if len(row) > 1 else row[0], "version": row[2] if len(row) > 2 else "", "origin": row[3] if len(row) > 3 else "", "installation": row[4] if len(row) > 4 else ""}
        for row in _rows(result.out)
    ]
    return {"result": {"apps": apps, "count": len(apps)}, "undo": None, "summary": f"{len(apps)} apps flatpak"}


@register("flatpak.search")
def flatpak_search(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    query = str(params["query"]).strip()
    if not query:
        raise ActionError("query vazia")
    result = procutil.run(
        [_flatpak(), "search", "--columns=application,name,description,version", query],
        timeout=120,
    )
    if not result.ok:
        raise ActionError(result.summary())
    apps = [
        {
            "app_id": row[0],
            "name": row[1] if len(row) > 1 else row[0],
            "description": row[2] if len(row) > 2 else "",
            "version": row[3] if len(row) > 3 else "",
        }
        for row in _rows(result.out)
    ]
    return {"result": {"apps": apps, "count": len(apps)}, "undo": None, "summary": f"busca flatpak por '{query}'"}


def _ensure_flathub(binary: str, scope_flag: str) -> None:
    remotes = procutil.run([binary, "remotes", scope_flag, "--columns=name"], timeout=30)
    if remotes.ok and any(line.strip() == "flathub" for line in remotes.out.splitlines()):
        return
    add = procutil.run(
        [binary, "remote-add", scope_flag, "--if-not-exists", "flathub", FLATHUB_REPO],
        timeout=120,
    )
    if not add.ok:
        raise ActionError(f"não consegui configurar o remoto flathub: {(add.err or add.out).strip()[:200]}")


@register("flatpak.install")
def flatpak_install(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    app_id = str(params["app_id"]).strip()
    if not APP_ID_RE.match(app_id):
        raise ActionError(f"app_id inválido: {app_id!r}")
    scope_flag = _scope_flag(params.get("scope"))
    if scope_flag == "--system" and not ctx.escalated:
        raise Escalate(
            f"instalar '{app_id}' no escopo system pede autenticação de administrador "
            "(polkit); prefira o escopo user quando possível"
        )
    remote = str(params.get("remote") or "flathub").strip()
    if not APP_ID_RE.match(remote):
        raise ActionError(f"remote inválido: {remote!r}")

    binary = _flatpak()
    if remote == "flathub":
        _ensure_flathub(binary, scope_flag)
    result = procutil.run(
        [binary, "install", scope_flag, "-y", "--noninteractive", remote, app_id],
        timeout=1800,
    )
    tail = (result.out or result.err).strip().splitlines()[-3:]
    if not result.ok:
        raise ActionError("falha ao instalar: " + " | ".join(tail))

    return {
        "result": {
            "app_id": app_id,
            "scope": scope_flag.lstrip("-"),
            "remote": remote,
            "output_tail": tail,
        },
        "undo": {"action": "flatpak.uninstall", "params": {"app_id": app_id, "scope": scope_flag.lstrip("-")}},
        "summary": f"flatpak install {app_id} ({scope_flag.lstrip('-')})",
    }


@register("flatpak.uninstall")
def flatpak_uninstall(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    app_id = str(params["app_id"]).strip()
    if not APP_ID_RE.match(app_id):
        raise ActionError(f"app_id inválido: {app_id!r}")
    scope_flag = _scope_flag(params.get("scope"))
    if scope_flag == "--system" and not ctx.escalated:
        raise Escalate(f"desinstalar '{app_id}' do escopo system pede autenticação de administrador")

    result = procutil.run(
        [_flatpak(), "uninstall", scope_flag, "-y", "--noninteractive", app_id],
        timeout=600,
    )
    tail = (result.out or result.err).strip().splitlines()[-3:]
    if not result.ok:
        raise ActionError("falha ao desinstalar: " + " | ".join(tail))

    return {
        "result": {"app_id": app_id, "scope": scope_flag.lstrip("-"), "output_tail": tail},
        "undo": {"action": "flatpak.install", "params": {"app_id": app_id, "scope": scope_flag.lstrip("-")}},
        "summary": f"flatpak uninstall {app_id} ({scope_flag.lstrip('-')})",
    }

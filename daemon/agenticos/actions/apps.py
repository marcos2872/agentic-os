"""Ações: apps.list / apps.launch — catálogo .desktop e abertura de apps."""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

from .. import procutil
from ..policy import ActionError
from . import Ctx, register

FIELD_CODES = re.compile(r"%[fFuUdDnNickvm]")

DESKTOP_DIRS = (
    "/usr/share/applications",
    "/usr/local/share/applications",
    "/var/lib/flatpak/exports/share/applications",
    "~/.local/share/flatpak/exports/share/applications",
    "~/.local/share/applications",
)


def _desktop_dirs(ctx: Ctx) -> list[Path]:
    dirs = []
    for entry in DESKTOP_DIRS:
        if entry.startswith("~/"):
            dirs.append(ctx.paths.home / entry[2:])
        else:
            dirs.append(Path(entry))
    return dirs


def _parse_desktop(path: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    in_entry = False
    data: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            in_entry = line == "[Desktop Entry]"
            continue
        if not in_entry or not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if sep:
            data[key.strip()] = value.strip()
    if data.get("Type", "Application") != "Application":
        return None
    if data.get("NoDisplay", "").lower() == "true":
        return None
    if not data.get("Exec"):
        return None
    return {
        "id": path.name,
        "name": data.get("Name", path.stem),
        "exec": data.get("Exec", ""),
        "comment": data.get("Comment", ""),
    }


def _catalog(ctx: Ctx) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for directory in _desktop_dirs(ctx):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.desktop")):
            entry = _parse_desktop(path)
            if entry and entry["id"] not in seen:
                seen[entry["id"]] = entry
    return list(seen.values())


@register("apps.list")
def apps_list(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    query = str(params.get("query") or "").strip().casefold()
    apps = _catalog(ctx)
    if query:
        apps = [app for app in apps if query in app["name"].casefold() or query in app["id"].casefold()]
    return {"result": {"apps": apps, "count": len(apps)}, "undo": None, "summary": f"{len(apps)} apps .desktop"}


@register("apps.launch")
def apps_launch(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    wanted = str(params["app"]).strip()
    catalog = _catalog(ctx)
    match = None
    for app in catalog:
        if app["id"] == wanted or app["id"] == f"{wanted}.desktop" or app["name"].casefold() == wanted.casefold():
            match = app
            break
    if match is None:
        needles = [app for app in catalog if wanted.casefold() in app["name"].casefold()]
        if len(needles) == 1:
            match = needles[0]
        elif needles:
            names = ", ".join(sorted(app["name"] for app in needles[:8]))
            raise ActionError(f"'{wanted}' é ambíguo; candidatos: {names}")
        else:
            raise ActionError(f"app não encontrado: {wanted!r} (use apps.list para ver os disponíveis)")

    command = FIELD_CODES.sub("", match["exec"]).strip()
    argv = shlex.split(command)
    if not argv:
        raise ActionError(f"entrada .desktop sem Exec válido: {match['id']}")
    pid = procutil.spawn_detached(argv, env=ctx.env)
    return {
        "result": {"app": match["id"], "name": match["name"], "argv": argv, "pid": pid},
        "undo": None,
        "summary": f"abrir {match['name']}",
    }

"""Ações: routine.list/create/remove/run — timers systemd --user.

Rotinas são arquivos `agenticos-<nome>.{service,timer}` em
~/.config/systemd/user. O comando é validado contra uma allowlist mínima.
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

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")
PREFIX = "agenticos-"
CALENDAR_FALLBACK_RE = re.compile(r"^[0-9A-Za-z*/:.,+~ \-]{1,120}$")
ALLOWED_COMMANDS = ("flatpak", "notify-send", "kbuildsycoca6")


def _systemctl() -> str:
    binary = procutil.which("systemctl")
    if binary is None:
        raise ActionError("systemctl não encontrado (rotinas dependem do systemd --user)")
    return binary


def _unit_dir(ctx: Ctx) -> Path:
    return ctx.paths.home / ".config/systemd/user"


def _registry_path(ctx: Ctx) -> Path:
    return ctx.paths.data / "routines.json"


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


def _check_name(name: str) -> str:
    if not NAME_RE.match(name):
        raise ActionError(f"nome de rotina inválido: {name!r} (use a-z, 0-9 e hífen)")
    return name


def _check_calendar(calendar: str) -> None:
    if not calendar or calendar.startswith("-"):
        raise ActionError(f"expressão de calendário inválida: {calendar!r}")
    # Sempre valida o charset (defesa independente do systemd-analyze).
    if not CALENDAR_FALLBACK_RE.match(calendar):
        raise ActionError(f"expressão de calendário suspeita: {calendar!r}")
    binary = procutil.which("systemd-analyze")
    if binary:
        result = procutil.run([binary, "calendar", calendar], timeout=15)
        if not result.ok:
            raise ActionError(f"expressão de calendário inválida: {calendar!r}")


def _check_argv(ctx: Ctx, argv: list[str]) -> list[str]:
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) for item in argv):
        raise ActionError("argv deve ser uma lista de strings não vazia")
    head = Path(argv[0]).name
    if head == "flatpak":
        flags = {"--user", "-y", "--noninteractive"}
        rest = [item for item in argv[1:] if item not in flags]
        if rest != ["update"]:
            raise ActionError("em rotinas, flatpak aceita apenas: flatpak [--user] update [-y]")
    elif head == "notify-send":
        joined = " ".join(argv)
        if len(joined) > 300 or "\n" in joined:
            raise ActionError("notify-send: mensagem muito longa")
        # $ e \\ seriam expandidos/reescritos pelo systemd no ExecStart.
        if ("$" in joined) or ("\\" in joined):
            raise ActionError("notify-send: mensagem não pode conter '$' nem '\\'")
    elif head == "kbuildsycoca6":
        if len(argv) > 1:
            raise ActionError("kbuildsycoca6 não aceita argumentos em rotinas")
    else:
        raise ActionError(
            f"comando não permitido em rotinas: {head!r} (permitidos: {', '.join(ALLOWED_COMMANDS)})"
        )
    resolved = procutil.which(head)
    if resolved is None:
        raise ActionError(f"binário não encontrado no PATH: {head}")
    return [resolved, *argv[1:]]


def _quote(arg: str) -> str:
    """Escapa um argumento para ExecStart (systemd).

    '%' vira '%%' (specifier) e args não triviais vão entre aspas.
    """
    escaped = arg.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    if re.fullmatch(r"[A-Za-z0-9@+=:,./_{}-]+", escaped):
        return escaped
    return f'"{escaped}"'


def _write_units(ctx: Ctx, name: str, calendar: str, argv: list[str]) -> None:
    unit_dir = _unit_dir(ctx)
    unit_dir.mkdir(parents=True, exist_ok=True)
    service = unit_dir / f"{PREFIX}{name}.service"
    timer = unit_dir / f"{PREFIX}{name}.timer"
    exec_start = " ".join(_quote(item) for item in argv)
    service.write_text(
        "[Unit]\n"
        f"Description=Agentic OS routine: {name}\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"ExecStart={exec_start}\n",
        encoding="utf-8",
    )
    timer.write_text(
        "[Unit]\n"
        f"Description=Agentic OS routine timer: {name}\n"
        "\n"
        "[Timer]\n"
        f"OnCalendar={calendar}\n"
        "Persistent=true\n"
        "\n"
        "[Install]\n"
        "WantedBy=timers.target\n",
        encoding="utf-8",
    )


@register("routine.create")
def routine_create(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    name = _check_name(str(params["name"]).strip())
    calendar = str(params["calendar"]).strip()
    _check_calendar(calendar)
    argv = _check_argv(ctx, list(params["argv"]))

    timer = _unit_dir(ctx) / f"{PREFIX}{name}.timer"
    if timer.exists():
        raise ActionError(f"rotina '{name}' já existe (remova antes de recriar)")

    _write_units(ctx, name, calendar, argv)
    systemctl = _systemctl()
    procutil.run([systemctl, "--user", "daemon-reload"], timeout=60)
    result = procutil.run([systemctl, "--user", "enable", "--now", timer.name], timeout=60)
    if not result.ok:
        raise ActionError("falha ao habilitar rotina: " + (result.err or result.out).strip()[:300])

    registry = _load_registry(ctx)
    registry[name] = {
        "calendar": calendar,
        "argv": argv,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    _save_registry(ctx, registry)

    return {
        "result": {"name": name, "calendar": calendar, "argv": argv, "unit": timer.name},
        "undo": {"action": "routine.remove", "params": {"name": name}},
        "summary": f"rotina '{name}' ({calendar})",
    }


@register("routine.remove")
def routine_remove(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    name = _check_name(str(params["name"]).strip())
    unit_dir = _unit_dir(ctx)
    service = unit_dir / f"{PREFIX}{name}.service"
    timer = unit_dir / f"{PREFIX}{name}.timer"
    if not timer.exists() and not service.exists():
        raise ActionError(f"rotina '{name}' não existe")

    systemctl = procutil.which("systemctl")
    if systemctl:
        procutil.run([systemctl, "--user", "disable", "--now", timer.name], timeout=60)

    registry = _load_registry(ctx)
    info = registry.pop(name, None)
    _save_registry(ctx, registry)

    for path in (timer, service):
        if path.exists():
            path.unlink()
    if systemctl:
        procutil.run([systemctl, "--user", "daemon-reload"], timeout=60)

    inverse = None
    if info:
        inverse = {
            "action": "routine.create",
            "params": {"name": name, "calendar": info["calendar"], "argv": info["argv"]},
        }
    return {"result": {"removed": name}, "undo": inverse, "summary": f"remover rotina '{name}'"}


@register("routine.list")
def routine_list(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    unit_dir = _unit_dir(ctx)
    routines: list[dict[str, Any]] = []
    for timer in sorted(unit_dir.glob(f"{PREFIX}*.timer")) if unit_dir.is_dir() else []:
        name = timer.name[len(PREFIX) : -len(".timer")]
        calendar = ""
        try:
            for line in timer.read_text(encoding="utf-8").splitlines():
                if line.startswith("OnCalendar="):
                    calendar = line.split("=", 1)[1].strip()
        except OSError:
            pass
        routines.append({"name": name, "calendar": calendar, "timer": timer.name, "next": None})

    systemctl = procutil.which("systemctl")
    if systemctl and routines:
        result = procutil.run(
            [systemctl, "--user", "list-timers", "--no-legend", "--plain"], timeout=30
        )
        if result.ok:
            by_unit = {}
            for line in result.out.splitlines():
                parts = line.split()
                if parts:
                    by_unit[parts[-1]] = parts
            for routine in routines:
                parts = by_unit.get(routine["timer"])
                if parts:
                    routine["next"] = " ".join(parts[:3])
    return {"result": {"routines": routines, "count": len(routines)}, "undo": None, "summary": f"{len(routines)} rotinas"}


@register("routine.run")
def routine_run(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    name = _check_name(str(params["name"]).strip())
    service = _unit_dir(ctx) / f"{PREFIX}{name}.service"
    if not service.exists():
        raise ActionError(f"rotina '{name}' não existe")
    systemctl = _systemctl()
    result = procutil.run([systemctl, "--user", "start", service.name], timeout=120)
    if not result.ok:
        raise ActionError("falha ao executar rotina: " + (result.err or result.out).strip()[:300])
    return {"result": {"started": name}, "undo": None, "summary": f"executar rotina '{name}' agora"}

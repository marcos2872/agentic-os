"""Ações: service.user / service.user_failed — serviços systemd --user."""

from __future__ import annotations

import re
from typing import Any

from .. import procutil
from ..policy import ActionError
from . import Ctx, register

UNIT_RE = re.compile(r"^[A-Za-z0-9@:._-]{1,128}\.(service|timer|socket|target|path|mount)$")
OPS = {"enable", "disable", "start", "stop", "restart", "status"}


def _systemctl() -> str:
    binary = procutil.which("systemctl")
    if binary is None:
        raise ActionError("systemctl não encontrado")
    return binary


@register("service.user")
def service_user(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    unit = str(params["unit"]).strip()
    op = str(params["op"]).strip().lower()
    if not UNIT_RE.match(unit):
        raise ActionError(f"unit inválida: {unit!r} (ex.: meu-servico.timer)")
    if op not in OPS:
        raise ActionError(f"operação inválida: {op!r} (use: {', '.join(sorted(OPS))})")
    binary = _systemctl()

    if op == "status":
        active = procutil.run([binary, "--user", "is-active", unit], timeout=15)
        enabled = procutil.run([binary, "--user", "is-enabled", unit], timeout=15)
        show = procutil.run(
            [binary, "--user", "show", unit, "--property=ActiveState,UnitFileState,Description", "--no-pager"],
            timeout=15,
        )
        properties = {}
        for line in show.out.splitlines():
            key, sep, value = line.partition("=")
            if sep:
                properties[key] = value
        return {
            "result": {
                "unit": unit,
                "active": active.out.strip() or "unknown",
                "enabled": enabled.out.strip() or "unknown",
                "properties": properties,
            },
            "undo": None,
            "summary": f"status {unit}",
        }

    result = procutil.run([binary, "--user", op, unit], timeout=180)
    if not result.ok:
        raise ActionError(f"systemctl --user {op} {unit} falhou: " + (result.err or result.out).strip()[:300])

    inverse = None
    if op == "enable":
        inverse = {"action": "service.user", "params": {"unit": unit, "op": "disable"}}
    elif op == "disable":
        inverse = {"action": "service.user", "params": {"unit": unit, "op": "enable"}}
    return {
        "result": {"unit": unit, "op": op, "output": (result.out or "").strip()[:500]},
        "undo": inverse,
        "summary": f"systemctl --user {op} {unit}",
    }


@register("service.user_failed")
def service_user_failed(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    binary = _systemctl()
    result = procutil.run(
        [binary, "--user", "list-units", "--failed", "--no-legend", "--plain"], timeout=30
    )
    if not result.ok:
        raise ActionError(result.summary())
    units = []
    for line in result.out.splitlines():
        parts = line.split()
        if parts:
            units.append(parts[0])
    return {"result": {"units": units, "count": len(units)}, "undo": None, "summary": f"{len(units)} units com falha"}

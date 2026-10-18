"""Ações de introspecção: ping, tools, audit.tail, undo.list."""

from __future__ import annotations

from typing import Any

from .. import __version__, audit, policy, undo
from . import Ctx, register


@register("ping")
def ping(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    return {"result": {"pong": True, "version": __version__}, "undo": None, "summary": "ping"}


@register("tools")
def tools(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    actions = policy.tools_doc()
    return {
        "result": {"actions": actions, "count": len(actions)},
        "undo": None,
        "summary": f"{len(actions)} ações disponíveis",
    }


@register("audit.tail")
def audit_tail(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    n = int(params.get("n") or 20)
    entries = audit.tail(ctx.paths, n)
    return {"result": {"entries": entries, "count": len(entries)}, "undo": None, "summary": f"últimas {n} entradas"}


@register("undo.list")
def undo_list(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    entries = undo.list_entries(ctx.paths)
    slim = [
        {
            "id": entry.get("id"),
            "ts": entry.get("ts"),
            "summary": entry.get("summary"),
            "action": entry.get("action"),
        }
        for entry in entries
    ]
    return {"result": {"entries": slim, "count": len(slim)}, "undo": None, "summary": f"{len(slim)} ações reversíveis"}

"""Ações: kwin.list_rules / kwin.add_rule / kwin.remove_rule.

`add_rule` aceita um arquivo .kwinrule (fluxo normal) ou `fields` (usado
pelo undo para restaurar uma regra removida).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import kwinrules, undo
from ..policy import ActionError
from . import Ctx, register


def _rule_from_fields(payload: dict[str, Any]) -> dict[str, Any]:
    fields = payload.get("fields")
    if not isinstance(fields, dict):
        raise ActionError("'fields' deve ser um objeto com os campos da regra")
    description = str(fields.get("Description") or payload.get("description") or "regra restaurada")
    rule_id = str(payload.get("id") or "").strip() or None
    clean = {str(key): str(value) for key, value in fields.items()}
    clean.pop("Id", None)
    return {"id": rule_id, "description": description, "fields": clean}


@register("kwin.list_rules")
def kwin_list_rules(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    rc_path = kwinrules.default_rc_path(ctx.paths.home)
    rules = kwinrules.list_rules(rc_path)
    slim = [
        {"id": rule["id"], "description": rule["description"], "enabled": rule["enabled"]}
        for rule in rules
    ]
    return {"result": {"rules": slim, "count": len(slim)}, "undo": None, "summary": f"{len(slim)} regras KWin"}


@register("kwin.add_rule")
def kwin_add_rule(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    file_param = params.get("file")
    fields_param = params.get("fields")
    if bool(file_param) == bool(fields_param):
        raise ActionError("informe 'file' (arquivo .kwinrule) OU 'fields' (objeto), não ambos")

    if file_param:
        path = Path(str(file_param)).expanduser()
        if not path.is_file():
            raise ActionError(f"arquivo .kwinrule não encontrado: {path}")
        parsed = kwinrules.parse_rule_file(path.read_text(encoding="utf-8", errors="replace"))
    else:
        parsed = _rule_from_fields(params)

    rc_path = kwinrules.default_rc_path(ctx.paths.home)
    undo.backup_file(ctx.paths, rc_path)
    applied = kwinrules.upsert_rule(rc_path, parsed)
    reconf = kwinrules.reconfigure()

    inverse: dict[str, Any] | None
    if applied["created"]:
        inverse = {"action": "kwin.remove_rule", "params": {"id": applied["id"]}}
    elif applied["previous"] is not None:
        inverse = {
            "action": "kwin.add_rule",
            "params": {"fields": applied["previous"], "id": applied["id"]},
        }
    else:
        inverse = None

    return {
        "result": {
            "id": applied["id"],
            "description": parsed["description"],
            "created": applied["created"],
            "reconfigure": reconf,
        },
        "undo": inverse,
        "summary": f"{'criar' if applied['created'] else 'atualizar'} regra KWin '{parsed['description']}'",
    }


@register("kwin.remove_rule")
def kwin_remove_rule(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    rule_id = params.get("id")
    description = params.get("description")
    if not rule_id and not description:
        raise ActionError("informe 'id' ou 'description' da regra")

    rc_path = kwinrules.default_rc_path(ctx.paths.home)
    rule = kwinrules.find_rule(
        rc_path, rule_id=str(rule_id) if rule_id else None, description=str(description) if description else None
    )
    if rule is None:
        raise ActionError("regra não encontrada no kwinrulesrc")

    undo.backup_file(ctx.paths, rc_path)
    removed = kwinrules.remove_rule(
        rc_path, rule_id=rule["id"], description=rule["description"]
    )
    reconf = kwinrules.reconfigure()
    return {
        "result": {"id": removed["id"], "description": removed["description"], "reconfigure": reconf},
        "undo": {
            "action": "kwin.add_rule",
            "params": {"fields": removed["fields"], "id": removed["id"], "description": removed["description"]},
        },
        "summary": f"remover regra KWin '{removed['description']}'",
    }

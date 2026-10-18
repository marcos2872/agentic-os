"""Leitura/escrita de regras do KWin (~/.config/kwinrulesrc).

O arquivo é um INI igual ao formato .kwinrule exportado pelo System Settings.
Cada regra é um grupo cujo nome é o UUID e vive na lista `rules` do [General].
A edição preserva o restante do arquivo (ver initext.py).
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from . import initext, procutil


def _read(path: Path) -> initext.IniDoc:
    return initext.load(path)


def _rules_list(doc: initext.IniDoc) -> list[str]:
    raw = doc.get("General", "rules") or ""
    return [item.strip() for item in raw.split(",") if item.strip()]


def parse_rule_file(text: str) -> dict[str, Any]:
    """Extrai a primeira seção útil de um arquivo .kwinrule."""
    doc = initext.IniDoc(text)
    sections = [name for name in doc.section_names() if name != "General"]
    if not sections:
        raise ValueError("arquivo .kwinrule sem seção de regra")
    section = sections[0]
    fields = doc.options(section)
    description = fields.get("Description", section)
    rule_id = fields.pop("Id", "").strip() or str(uuid.uuid4())
    return {"id": rule_id, "description": description, "fields": fields}


def list_rules(path: Path) -> list[dict[str, Any]]:
    doc = _read(path)
    rules = []
    for rule_id in _rules_list(doc):
        if not doc.has_section(rule_id):
            continue
        fields = doc.options(rule_id)
        rules.append(
            {
                "id": rule_id,
                "description": fields.get("Description", rule_id),
                "enabled": fields.get("Enabled", "true").lower() != "false",
                "fields": fields,
            }
        )
    return rules


def find_rule(
    path: Path, *, rule_id: str | None = None, description: str | None = None
) -> dict[str, Any] | None:
    for rule in list_rules(path):
        if rule_id and rule["id"] == rule_id:
            return rule
        if description and rule["description"].casefold() == description.casefold():
            return rule
    return None


def upsert_rule(path: Path, rule: dict[str, Any]) -> dict[str, Any]:
    """Instala/atualiza uma regra. Retorna {id, created, previous}."""
    doc = _read(path)

    existing = find_rule(path, rule_id=rule["id"]) or find_rule(
        path, description=rule["description"]
    )
    created = existing is None
    rule_id = existing["id"] if existing else rule["id"]
    previous = existing["fields"] if existing else None

    fields = dict(rule["fields"])
    fields["Description"] = rule["description"]
    fields["Enabled"] = str(fields.get("Enabled", "true")).lower()
    for key, value in fields.items():
        doc.set(rule_id, str(key), str(value))

    rules = [item for item in _rules_list(doc) if item != rule_id]
    rules.append(rule_id)
    doc.set("General", "count", str(len(rules)))
    doc.set("General", "rules", ",".join(rules))

    initext.write_text_atomic(path, doc.render())
    return {"id": rule_id, "created": created, "previous": previous}


def remove_rule(path: Path, *, rule_id: str, description: str) -> dict[str, Any]:
    """Remove a regra. Retorna {id, description, fields} para permitir undo."""
    doc = _read(path)
    fields = doc.options(rule_id) if doc.has_section(rule_id) else {}
    doc.remove_section(rule_id)
    rules = [item for item in _rules_list(doc) if item != rule_id]
    doc.set("General", "count", str(len(rules)))
    doc.set("General", "rules", ",".join(rules))
    initext.write_text_atomic(path, doc.render())
    return {"id": rule_id, "description": description, "fields": fields}


def kwin_running() -> bool:
    for name in ("kwin_wayland", "kwin_x11", "kwin"):
        if procutil.run(["pgrep", "-x", name], timeout=5).ok:
            return True
    return False


def reconfigure() -> dict[str, Any]:
    """Pede ao KWin para recarregar regras; regras também valem no próximo login."""
    attempts = [
        ["qdbus6", "org.kde.KWin", "/KWin", "reconfigure"],
        ["qdbus-qt6", "org.kde.KWin", "/KWin", "reconfigure"],
        ["qdbus", "org.kde.KWin", "/KWin", "reconfigure"],
        [
            "dbus-send",
            "--session",
            "--type=method_call",
            "--dest=org.kde.KWin",
            "/KWin",
            "org.kde.KWin.reconfigure",
        ],
        [
            "gdbus",
            "call",
            "--session",
            "--dest",
            "org.kde.KWin",
            "--object-path",
            "/KWin",
            "--method",
            "org.kde.KWin.reconfigure",
        ],
    ]
    for argv in attempts:
        if procutil.which(argv[0]) is None:
            continue
        result = procutil.run(argv, timeout=10)
        if result.ok:
            return {"applied": True, "via": argv[0]}
        return {
            "applied": False,
            "via": argv[0],
            "detail": (result.err or result.out).strip()[:200] or "KWin não respondeu",
        }
    return {"applied": False, "detail": "qdbus/dbus-send indisponíveis; regra vale no próximo login"}


def default_rc_path(home: Path) -> Path:
    override = os.environ.get("AGENTICOS_KWINRULESRC")
    return Path(override) if override else home / ".config/kwinrulesrc"

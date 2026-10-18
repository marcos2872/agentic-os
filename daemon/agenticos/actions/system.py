"""Ação: system.info — contexto da máquina para o agente."""

from __future__ import annotations

import os
import platform
from typing import Any

from .. import __version__, procutil
from . import Ctx, register


def _os_release() -> dict[str, str]:
    data: dict[str, str] = {}
    try:
        with open("/etc/os-release", encoding="utf-8") as handle:
            for line in handle:
                key, sep, value = line.partition("=")
                if sep:
                    data[key.strip()] = value.strip().strip('"')
    except OSError:
        pass
    return data


@register("system.info")
def system_info(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    osr = _os_release()
    tools = {}
    for name in (
        "flatpak",
        "kpackagetool6",
        "kwriteconfig6",
        "kreadconfig6",
        "konsole",
        "plasma-apply-colorscheme",
        "qdbus6",
        "qdbus-qt6",
        "qdbus",
        "dbus-send",
        "systemctl",
        "systemd-analyze",
    ):
        tools[name] = procutil.which(name) is not None

    return {
        "result": {
            "agenticd_version": __version__,
            "distro": {
                "name": osr.get("NAME", "desconhecida"),
                "version": osr.get("VERSION_ID", ""),
                "variant": osr.get("VARIANT", ""),
                "variant_id": osr.get("VARIANT_ID", ""),
            },
            "kernel": platform.release(),
            "immutable_base": procutil.which("rpm-ostree") is not None,
            "session": {
                "type": os.environ.get("XDG_SESSION_TYPE", "desconhecida"),
                "desktop": os.environ.get("XDG_CURRENT_DESKTOP", "desconhecido"),
            },
            "tools": tools,
            "paths": {
                "home": str(ctx.paths.home),
                "data": str(ctx.paths.data),
                "config": str(ctx.paths.config),
            },
        },
        "undo": None,
        "summary": "informações do sistema coletadas",
    }

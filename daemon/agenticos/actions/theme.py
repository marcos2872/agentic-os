"""Ações de tema/aparência: plasma.set_color_scheme, plasma.set_wallpaper,
theme.apply_preset (escuro + transparência global via regra do KWin).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .. import kwinrules, procutil, undo
from ..policy import ActionError
from . import Ctx, register
from .configs import ini_get, ini_set

SCHEME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ +-]{0,63}$")
DEFAULT_PRESET = "dark-transparency"
DEFAULT_RULE_NAME = "Transparencia-Global.kwinrule"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".avif", ".heic"}


def _set_scheme(ctx: Ctx, scheme: str) -> dict[str, Any]:
    """Aplica o esquema; retorna {applied_via, previous}."""
    kdeglobals = ctx.paths.home / ".config/kdeglobals"
    previous = ini_get(ctx, kdeglobals, "General", "ColorScheme") if kdeglobals.exists() else None
    binary = procutil.which("plasma-apply-colorscheme")
    if binary:
        result = procutil.run([binary, scheme], timeout=60, env=ctx.env)
        if not result.ok:
            raise ActionError(f"plasma-apply-colorscheme falhou: {(result.err or result.out).strip()[:200]}")
        return {"applied_via": "plasma-apply-colorscheme", "previous": previous}
    # Fallback sem Plasma rodando: grava kdeglobals (vale no próximo login).
    undo.backup_file(ctx.paths, kdeglobals)
    ini_set(ctx, kdeglobals, "General", "ColorScheme", scheme)
    return {"applied_via": "kdeglobals (fallback)", "previous": previous}


def _rule_file(ctx: Ctx, explicit: str | None = None) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
    else:
        path = ctx.paths.assets / DEFAULT_RULE_NAME
    if not path.exists():
        raise ActionError(f"arquivo de regra KWin não encontrado: {path}")
    return path


@register("plasma.set_color_scheme")
def plasma_set_color_scheme(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    scheme = str(params["scheme"]).strip()
    if not SCHEME_RE.match(scheme):
        raise ActionError(f"nome de esquema inválido: {scheme!r}")
    info = _set_scheme(ctx, scheme)
    inverse = None
    if info["previous"]:
        inverse = {"action": "plasma.set_color_scheme", "params": {"scheme": info["previous"]}}
    return {
        "result": {"scheme": scheme, "applied_via": info["applied_via"], "previous": info["previous"]},
        "undo": inverse,
        "summary": f"esquema de cores → {scheme}",
    }


@register("plasma.set_wallpaper")
def plasma_set_wallpaper(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(params["path"])).expanduser().resolve()
    if not path.is_file():
        raise ActionError(f"imagem não encontrada: {path}")
    if path.suffix.lower() not in IMAGE_EXTS:
        raise ActionError(f"extensão não suportada: {path.suffix} (use png/jpg/webp)")
    if "'" in str(path) or "\\" in str(path) or "\n" in str(path):
        raise ActionError("caminho com caracteres não suportados (' \\ quebra de linha)")

    script = (
        "var ds = desktops();"
        "for (var i = 0; i < ds.length; i++) {"
        "ds[i].wallpaperPlugin = 'org.kde.image';"
        "ds[i].currentConfigGroup = ['Wallpaper', 'org.kde.image', 'General'];"
        f"ds[i].writeConfig('Image', '{path}');"
        "}"
    )
    for name in ("qdbus6", "qdbus-qt6", "qdbus"):
        binary = procutil.which(name)
        if binary:
            result = procutil.run(
                [binary, "org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell.evaluateScript", script],
                timeout=60,
                env=ctx.env,
            )
            if result.ok:
                return {
                    "result": {"path": str(path), "applied_via": name, "note": "undo não suportado para wallpaper"},
                    "undo": None,
                    "summary": f"papel de parede → {path.name}",
                }
            raise ActionError(
                f"plasmashell não respondeu via {name}: {(result.err or result.out).strip()[:200]}"
            )
    raise ActionError("qdbus6/qdbus indisponíveis; não consigo falar com o plasmashell")


@register("theme.apply_preset")
def theme_apply_preset(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    preset = str(params.get("preset") or DEFAULT_PRESET).strip().lower()
    if preset != DEFAULT_PRESET:
        raise ActionError(f"preset desconhecido: {preset!r} (disponível: {DEFAULT_PRESET})")

    steps: list[str] = []
    ops: list[dict[str, Any]] = []

    scheme_info = _set_scheme(ctx, "BreezeDark")
    steps.append(f"esquema de cores BreezeDark via {scheme_info['applied_via']}")
    if scheme_info["previous"]:
        ops.append({"action": "plasma.set_color_scheme", "params": {"scheme": scheme_info["previous"]}})

    rule_path = _rule_file(ctx, params.get("rule_file"))
    parsed = kwinrules.parse_rule_file(rule_path.read_text(encoding="utf-8", errors="replace"))
    rc_path = kwinrules.default_rc_path(ctx.paths.home)
    undo.backup_file(ctx.paths, rc_path)
    applied = kwinrules.upsert_rule(rc_path, parsed)
    steps.append(
        f"regra KWin '{parsed['description']}' {'criada' if applied['created'] else 'atualizada'} "
        f"(opacidade 94%, ativa)"
    )
    reconf = kwinrules.reconfigure()
    if not reconf.get("applied"):
        steps.append(f"KWin não recarregado agora ({reconf.get('detail', 'sem detalhe')}); vale no próximo login")
    ops.append({"action": "kwin.remove_rule", "params": {"id": applied["id"]}})

    return {
        "result": {"preset": preset, "steps": steps, "rule_id": applied["id"]},
        "undo": {"action": "__batch__", "params": {"ops": ops}},
        "summary": "preset escuro + transparência global (regra KWin)",
    }

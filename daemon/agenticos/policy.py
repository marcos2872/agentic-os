"""Política de ações: allowlist, risco (verde/amarelo/vermelho) e validação.

O agente nunca executa comandos arbitrários: ele pede ações nomeadas. Cada
ação declara parâmetros tipados, e o daemon valida antes de executar.
"""

from __future__ import annotations

import json
from typing import Any

GREEN = "green"
YELLOW = "yellow"
RED = "red"


class ActionError(Exception):
    """Erro de ação/validação devolvido ao chamador (mensagem amigável)."""


class Escalate(Exception):
    """Ação verde que, com estes parâmetros, exige confirmação (amarela)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _param(type_: str, desc: str, required: bool = False, **extra: Any) -> dict[str, Any]:
    data: dict[str, Any] = {"type": type_, "desc": desc, "required": required}
    data.update(extra)
    return data


# Especificação das ações: risco, resumo e parâmetros.
SPEC: dict[str, dict[str, Any]] = {
    "ping": {"risk": GREEN, "summary": "Verifica se o daemon está vivo.", "params": {}},
    "tools": {
        "risk": GREEN,
        "summary": "Lista as ações disponíveis com parâmetros e risco.",
        "params": {},
    },
    "system.info": {
        "risk": GREEN,
        "summary": "Informações da distro, sessão gráfica e ferramentas disponíveis.",
        "params": {},
    },
    "fs.read": {
        "risk": GREEN,
        "summary": "Lê arquivo de texto em $HOME, /etc ou /var/log (máx. 64 KiB).",
        "params": {
            "path": _param("string", "Caminho absoluto do arquivo.", required=True),
        },
    },
    "flatpak.list": {
        "risk": GREEN,
        "summary": "Lista aplicativos Flatpak instalados.",
        "params": {},
    },
    "flatpak.search": {
        "risk": GREEN,
        "summary": "Busca aplicativos no remoto Flatpak.",
        "params": {"query": _param("string", "Termo de busca.", required=True)},
    },
    "flatpak.install": {
        "risk": GREEN,
        "summary": "Instala aplicativo Flatpak (escopo user por padrão).",
        "params": {
            "app_id": _param("string", "ID do app (ex.: com.brave.Browser).", required=True),
            "remote": _param("string", "Remoto Flatpak (padrão: flathub)."),
            "scope": _param("string", "user ou system (system exige confirmação)."),
        },
    },
    "flatpak.uninstall": {
        "risk": GREEN,
        "summary": "Desinstala aplicativo Flatpak.",
        "params": {
            "app_id": _param("string", "ID do app.", required=True),
            "scope": _param("string", "user ou system (system exige confirmação)."),
        },
    },
    "apps.list": {
        "risk": GREEN,
        "summary": "Lista aplicativos com entrada .desktop instalada.",
        "params": {"query": _param("string", "Filtro opcional por nome.")},
    },
    "apps.launch": {
        "risk": GREEN,
        "summary": "Abre um aplicativo pelo ID .desktop ou nome.",
        "params": {"app": _param("string", "ID .desktop ou nome do app.", required=True)},
    },
    "theme.apply_preset": {
        "risk": YELLOW,
        "summary": "Aplica preset visual (escuro + transparência global).",
        "params": {
            "preset": _param("string", "Nome do preset (padrão: dark-transparency)."),
            "rule_file": _param("string", "Arquivo .kwinrule alternativo (padrão: asset embarcado)."),
        },
    },
    "plasma.set_color_scheme": {
        "risk": YELLOW,
        "summary": "Troca o esquema de cores do Plasma.",
        "params": {"scheme": _param("string", "Nome do esquema (ex.: BreezeDark).", required=True)},
    },
    "plasma.set_wallpaper": {
        "risk": YELLOW,
        "summary": "Troca o papel de parede do Plasma.",
        "params": {"path": _param("string", "Caminho da imagem.", required=True)},
    },
    "kwin.list_rules": {
        "risk": GREEN,
        "summary": "Lista as regras de janela do KWin.",
        "params": {},
    },
    "kwin.add_rule": {
        "risk": YELLOW,
        "summary": "Instala uma regra de janela do KWin (arquivo .kwinrule ou campos).",
        "params": {
            "file": _param("string", "Caminho do arquivo .kwinrule."),
            "fields": _param("object", "Campos da regra (uso interno do undo)."),
            "id": _param("string", "UUID ao restaurar campos (uso interno do undo)."),
            "description": _param("string", "Descrição ao restaurar campos (uso interno do undo)."),
        },
    },
    "kwin.remove_rule": {
        "risk": YELLOW,
        "summary": "Remove regra do KWin por id ou descrição.",
        "params": {
            "id": _param("string", "UUID da regra."),
            "description": _param("string", "Descrição da regra."),
        },
    },
    "widget.list": {
        "risk": GREEN,
        "summary": "Lista plasmoids instalados no usuário.",
        "params": {},
    },
    "widget.install": {
        "risk": GREEN,
        "summary": "Instala/atualiza um plasmoid a partir de um diretório local.",
        "params": {"path": _param("string", "Diretório do plasmoid.", required=True)},
    },
    "widget.remove": {
        "risk": GREEN,
        "summary": "Remove um plasmoid instalado no usuário.",
        "params": {"id": _param("string", "ID do plasmoid (ex.: com.agenticos.appcarousel).", required=True)},
    },
    "service.user": {
        "risk": GREEN,
        "summary": "Controla um serviço systemd --user (enable/disable/start/stop/restart/status).",
        "params": {
            "unit": _param("string", "Nome da unit (ex.: foo.timer).", required=True),
            "op": _param(
                "string",
                "Operação: enable, disable, start, stop, restart ou status.",
                required=True,
            ),
        },
    },
    "service.user_failed": {
        "risk": GREEN,
        "summary": "Lista units systemd --user com falha.",
        "params": {},
    },
    "routine.list": {
        "risk": GREEN,
        "summary": "Lista rotinas (timers systemd --user do Agentic OS).",
        "params": {},
    },
    "routine.create": {
        "risk": GREEN,
        "summary": "Cria rotina (timer systemd --user) com comando permitido.",
        "params": {
            "name": _param("string", "Nome curto (a-z, 0-9, hífen).", required=True),
            "calendar": _param("string", "Expressão OnCalendar (systemd).", required=True),
            "argv": _param("list", "Comando permitido (ex.: [\"notify-send\",\"oi\"]).", required=True),
        },
    },
    "routine.remove": {
        "risk": GREEN,
        "summary": "Remove rotina criada pelo Agentic OS.",
        "params": {"name": _param("string", "Nome da rotina.", required=True)},
    },
    "routine.run": {
        "risk": GREEN,
        "summary": "Executa a rotina agora (dispara o serviço uma vez).",
        "params": {"name": _param("string", "Nome da rotina.", required=True)},
    },
    "config.get": {
        "risk": GREEN,
        "summary": "Lê chave de arquivo INI em ~/.config.",
        "params": {
            "file": _param("string", "Caminho relativo em ~/.config (ex.: kdeglobals).", required=True),
            "group": _param("string", "Grupo INI.", required=True),
            "key": _param("string", "Chave INI.", required=True),
        },
    },
    "config.set": {
        "risk": GREEN,
        "summary": "Escreve chave em arquivo INI de ~/.config (com backup e undo).",
        "params": {
            "file": _param("string", "Caminho relativo em ~/.config.", required=True),
            "group": _param("string", "Grupo INI.", required=True),
            "key": _param("string", "Chave INI.", required=True),
            "value": _param("string", "Valor.", required=True),
        },
    },
    "config.unset": {
        "risk": GREEN,
        "summary": "Remove chave de arquivo INI de ~/.config (com backup e undo).",
        "params": {
            "file": _param("string", "Caminho relativo em ~/.config.", required=True),
            "group": _param("string", "Grupo INI.", required=True),
            "key": _param("string", "Chave INI.", required=True),
        },
    },
    "undo.last": {"risk": GREEN, "summary": "Desfaz a última ação reversível.", "params": {}},
    "undo.list": {"risk": GREEN, "summary": "Lista ações reversíveis recentes.", "params": {}},
    "audit.tail": {
        "risk": GREEN,
        "summary": "Mostra as últimas entradas da auditoria.",
        "params": {"n": _param("integer", "Quantidade (padrão: 20, máx.: 200).")},
    },
}

# Ações de leitura pura (não serializam com mutações e não geram undo).
READ_ONLY = {
    "ping",
    "tools",
    "system.info",
    "fs.read",
    "flatpak.list",
    "flatpak.search",
    "apps.list",
    "kwin.list_rules",
    "widget.list",
    "service.user_failed",
    "routine.list",
    "config.get",
    "undo.list",
    "audit.tail",
}

# Ações vermelhas: bloqueadas por design. Ficam documentadas para o agente
# (e para humanos) saberem o motivo quando tentarem algo fora do escopo.
RED_ACTIONS: dict[str, str] = {
    "base.write": "Alterar a base do sistema (/usr, rpm-ostree, dnf) quebra o rollback e não é permitido.",
    "system.reboot": "Reiniciar/desligar a máquina é decisão manual do usuário.",
    "security.pam": "Alterar PAM/SELinux/kernel/drivers exige procedimento manual documentado.",
    "ssh.keys": "Chaves SSH/GPG nunca são acessadas pelo agente.",
}


# Mapeamento tool do chat (pi) → ação do daemon. É o contrato público:
# o teste de contrato compara este mapa com o nome das tools no arquivo
# pi-package/extensions/agentic-os.ts.
TOOL_NAMES: dict[str, str] = {
    "os_system_info": "system.info",
    "os_fs_read": "fs.read",
    "os_apps_list": "apps.list",
    "os_apps_installed": "flatpak.list",
    "os_apps_search": "flatpak.search",
    "os_apps_install": "flatpak.install",
    "os_apps_remove": "flatpak.uninstall",
    "os_app_launch": "apps.launch",
    "os_theme_preset": "theme.apply_preset",
    "os_plasma_color_scheme": "plasma.set_color_scheme",
    "os_plasma_wallpaper": "plasma.set_wallpaper",
    "os_kwin_rules": "kwin.list_rules",
    "os_kwin_rule_add": "kwin.add_rule",
    "os_kwin_rule_remove": "kwin.remove_rule",
    "os_widget_list": "widget.list",
    "os_widget_install": "widget.install",
    "os_widget_remove": "widget.remove",
    "os_service_user": "service.user",
    "os_routine_list": "routine.list",
    "os_routine_create": "routine.create",
    "os_routine_remove": "routine.remove",
    "os_routine_run": "routine.run",
    "os_config_get": "config.get",
    "os_config_set": "config.set",
    "os_config_unset": "config.unset",
    "os_undo": "undo.last",
    "os_history": "audit.tail",
}


def risk_of(action: str) -> str:
    if action in RED_ACTIONS:
        return RED
    entry = SPEC.get(action)
    if entry is None:
        return RED
    return str(entry["risk"])


def _coerce_value(action: str, name: str, meta: dict[str, Any], value: Any) -> Any:
    """Coerção tolerante: CLI/espaços passam strings; JSON passa tipos ricos."""
    type_ = meta["type"]
    if type_ == "string":
        if isinstance(value, str):
            return value
        raise ActionError(f"parâmetro {name} deve ser string")
    if type_ == "integer":
        if isinstance(value, bool):
            raise ActionError(f"parâmetro {name} deve ser inteiro")
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(value.strip())
            except ValueError as exc:
                raise ActionError(f"parâmetro {name} deve ser inteiro") from exc
        raise ActionError(f"parâmetro {name} deve ser inteiro")
    if type_ == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in ("true", "false", "1", "0", "sim", "não", "nao"):
            return value.strip().lower() in ("true", "1", "sim")
        raise ActionError(f"parâmetro {name} deve ser booleano")
    if type_ == "list":
        parsed = value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ActionError(f"parâmetro {name}: lista JSON inválida") from exc
        if not isinstance(parsed, (list, tuple)) or not all(isinstance(item, str) for item in parsed):
            raise ActionError(f"parâmetro {name} deve ser uma lista de strings")
        return list(parsed)
    if type_ == "object":
        parsed = value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ActionError(f"parâmetro {name}: objeto JSON inválido") from exc
        if not isinstance(parsed, dict):
            raise ActionError(f"parâmetro {name} deve ser um objeto")
        return parsed
    raise ActionError(f"tipo desconhecido para {name} em {action}: {type_}")


def validate_params(action: str, params: dict[str, Any] | None) -> dict[str, Any]:
    """Valida e normaliza os parâmetros declarados na SPEC."""
    entry = SPEC.get(action)
    if entry is None:
        raise ActionError(f"ação desconhecida: {action}")
    params = dict(params or {})
    spec_params: dict[str, dict[str, Any]] = entry["params"]

    unknown = set(params) - set(spec_params)
    if unknown:
        raise ActionError(f"parâmetros desconhecidos em {action}: {', '.join(sorted(unknown))}")

    normalized: dict[str, Any] = {}
    for name, meta in spec_params.items():
        if name not in params:
            if meta.get("required"):
                raise ActionError(f"parâmetro obrigatório ausente em {action}: {name}")
            continue
        normalized[name] = _coerce_value(action, name, meta, params[name])
    return normalized


def tools_doc() -> list[dict[str, Any]]:
    """Documento legível por máquina com ações, risco e parâmetros."""
    doc = []
    for action, entry in SPEC.items():
        doc.append(
            {
                "action": action,
                "risk": entry["risk"],
                "summary": entry["summary"],
                "params": entry["params"],
            }
        )
    for action, reason in RED_ACTIONS.items():
        doc.append({"action": action, "risk": RED, "summary": f"BLOQUEADO: {reason}", "params": {}})
    return doc

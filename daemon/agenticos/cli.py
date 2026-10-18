"""CLI `agenticctl`: cliente do daemon (também usado pelas tools do pi).

Uso:
  agenticctl call <acao> [--params-json '<json>'] [chave=valor ...]
                         [--confirm <plan_id>] [--yes] [--json]
  agenticctl <acao> [chave=valor ...] [--json]        # atalho
  agenticctl tools [--json]
"""

from __future__ import annotations

import json
import socket
import sys
from typing import Any

from . import __version__
from .paths import Paths

USAGE = __doc__ or "agenticctl"

HELP = """\
agenticctl — controle do Agentic OS via daemon (socket Unix)

Ações verdes executam direto; amarelas retornam needs_confirmation com um
plan_id e exigem `--yes` (usuário) ou `--confirm <plan_id>`.

Opções:
  --json                saída JSON pura (para scripts/tools)
  --params-json '<j>'   parâmetros como objeto JSON
  chave=valor           parâmetros simples (valor vira string)
  --confirm <plan_id>   confirma um plano amarelo pendente
  --yes                 confirma direto (uso humano explícito)
  --socket <caminho>    socket alternativo do daemon
  --timeout <segundos>  timeout do socket (padrão: 3600)
  -h, --help            esta ajuda
  --version             versão
"""


class UsageError(Exception):
    pass


def _parse_args(argv: list[str]) -> dict[str, Any]:
    options: dict[str, Any] = {
        "json": False,
        "yes": False,
        "confirm": None,
        "socket": None,
        "timeout": 3600.0,
        "params_json": None,
        "positionals": [],
        "keyvals": [],
    }
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in ("-h", "--help"):
            options["help"] = True
        elif arg == "--version":
            options["version"] = True
        elif arg == "--json":
            options["json"] = True
        elif arg == "--yes":
            options["yes"] = True
        elif arg in ("--confirm", "--socket", "--timeout", "--params-json"):
            index += 1
            if index >= len(argv):
                raise UsageError(f"{arg} exige um valor")
            value = argv[index]
            if arg == "--confirm":
                options["confirm"] = value
            elif arg == "--socket":
                options["socket"] = value
            elif arg == "--timeout":
                try:
                    options["timeout"] = float(value)
                except ValueError as exc:
                    raise UsageError("--timeout deve ser um número") from exc
            else:
                options["params_json"] = value
        elif arg.startswith("--"):
            raise UsageError(f"opção desconhecida: {arg}")
        elif "=" in arg and options["positionals"]:
            key, _, value = arg.partition("=")
            options["keyvals"].append((key, value))
        else:
            options["positionals"].append(arg)
        index += 1
    return options


def _build_request(options: dict[str, Any]) -> dict[str, Any]:
    positionals = options["positionals"]
    if not positionals:
        raise UsageError("informe uma ação (ex.: agenticctl system.info)")
    if positionals[0] == "call":
        if len(positionals) < 2:
            raise UsageError("uso: agenticctl call <acao> [chave=valor ...]")
        action = positionals[1]
        rest = positionals[2:]
    else:
        action = positionals[0]
        rest = positionals[1:]

    for item in rest:
        if "=" not in item:
            raise UsageError(f"parâmetro inválido: {item!r} (use chave=valor)")
        key, _, value = item.partition("=")
        options["keyvals"].append((key, value))

    params: dict[str, Any] = {}
    if options["params_json"]:
        try:
            parsed = json.loads(options["params_json"])
        except json.JSONDecodeError as exc:
            raise UsageError(f"--params-json inválido: {exc}") from exc
        if not isinstance(parsed, dict):
            raise UsageError("--params-json deve ser um objeto JSON")
        params.update(parsed)
    for key, value in options["keyvals"]:
        params[key] = value

    request: dict[str, Any] = {"action": action, "params": params, "actor": "agenticctl"}
    if options["yes"]:
        request["yes"] = True
    if options["confirm"]:
        request["confirm"] = options["confirm"]
    return request


def _call_daemon(socket_path: str, request: dict[str, Any], timeout: float) -> dict[str, Any]:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(socket_path)
            payload = json.dumps(request, ensure_ascii=False).encode("utf-8") + b"\n"
            client.sendall(payload)
            buffer = b""
            while b"\n" not in buffer:
                chunk = client.recv(65536)
                if not chunk:
                    break
                buffer += chunk
    except FileNotFoundError as exc:
        raise SystemExit(
            f"erro: daemon não está rodando ({socket_path}). Inicie com: systemctl --user start agenticd"
        ) from exc
    except ConnectionRefusedError as exc:
        raise SystemExit(f"erro: daemon recusou a conexão em {socket_path}") from exc
    except TimeoutError as exc:
        raise SystemExit(f"erro: timeout após {timeout:.0f}s aguardando o daemon") from exc

    line = buffer.split(b"\n", 1)[0].decode("utf-8", "replace").strip()
    if not line:
        raise SystemExit("erro: resposta vazia do daemon")
    try:
        return json.loads(line)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"erro: resposta inválida do daemon: {line[:200]}") from exc


def _print_human(response: dict[str, Any]) -> None:
    if response.get("needs_confirmation"):
        plan = response.get("plan") or {}
        params_json = json.dumps(plan.get("params", {}), ensure_ascii=False)
        print("⚠️  ação AMARELA — precisa de confirmação")
        print(f"    {plan.get('explain', plan.get('summary', ''))}")
        print(f"    parâmetros: {params_json}")
        print(
            "    confirme com: "
            f"agenticctl call {plan.get('action')} --params-json '{params_json}' --confirm {response.get('plan_id')}"
        )
        return
    if response.get("ok"):
        summary = response.get("summary")
        if summary:
            print(f"✓ {summary}")
        print(json.dumps(response.get("result"), ensure_ascii=False, indent=2))
        if response.get("undo_id"):
            print(f"(undo disponível: {response['undo_id']} — use `agenticctl undo.last`)")
    else:
        print(f"✗ {response.get('error', 'erro desconhecido')}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        options = _parse_args(argv)
    except UsageError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        print(HELP, file=sys.stderr)
        return 2

    if options.get("help") or not argv:
        print(HELP)
        return 0
    if options.get("version"):
        print(f"agenticctl {__version__}")
        return 0

    try:
        request = _build_request(options)
    except UsageError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2

    paths = Paths()
    socket_path = options["socket"] or str(paths.socket)
    response = _call_daemon(socket_path, request, options["timeout"])

    if options["json"]:
        print(json.dumps(response, ensure_ascii=False))
    else:
        _print_human(response)
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

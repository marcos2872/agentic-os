"""Daemon de políticas do Agentic OS.

Protocolo: socket Unix (`$XDG_RUNTIME_DIR/agenticos/agenticd.sock`), uma
linha JSON por requisição/resposta:

  {"id": 1, "action": "flatpak.install", "params": {...}, "yes": false,
   "confirm": "plan-id", "actor": "agenticctl"}

Resposta:
  {"id": 1, "ok": true, "risk": "green", "result": {...}, "undo_id": "..."}
  {"id": 1, "ok": true, "needs_confirmation": true, "plan_id": "...", "plan": {...}}
  {"id": 1, "ok": false, "error": "..."}

Regras: ações verdes executam direto (com log); amarelas só com confirmação
(`yes` ou `confirm` de um plano); vermelhas são bloqueadas com explicação.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import socketserver
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

from . import __version__, audit, policy, undo
from .actions import REGISTRY, Ctx, load_all
from .paths import Paths

PLAN_TTL_SECONDS = 600
MAX_LINE = 256 * 1024


class Daemon:
    def __init__(self, paths: Paths) -> None:
        self.paths = paths
        self._mutation_lock = threading.Lock()
        self._plans: dict[str, dict[str, Any]] = {}
        self._plans_lock = threading.Lock()
        load_all()

    # ------------------------------------------------------------------ API
    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = request.get("id")
        action = str(request.get("action") or "").strip()
        params = request.get("params") or {}
        if not isinstance(params, dict):
            return {"id": request_id, "ok": False, "error": "params deve ser um objeto JSON"}

        base: dict[str, Any] = {"id": request_id, "action": action}
        started = time.monotonic()

        try:
            if action == "undo.last":
                return {**base, **self._undo_last(request_id)}
            if action not in policy.SPEC:
                reason = policy.RED_ACTIONS.get(action, "ação desconhecida")
                self._audit(action, params, risk=policy.RED, ok=False, error=reason, started=started)
                return {
                    **base,
                    "ok": False,
                    "risk": policy.RED,
                    "error": f"ação bloqueada: {reason}",
                }

            risk = policy.risk_of(action)
            if risk == policy.RED:
                reason = policy.RED_ACTIONS.get(action, "ação vermelha")
                self._audit(action, params, risk=risk, ok=False, error=reason, started=started)
                return {**base, "ok": False, "risk": risk, "error": f"ação bloqueada: {reason}"}

            params = policy.validate_params(action, params)
            plan = self._consume_plan(str(request.get("confirm") or ""), action)
            confirmed = bool(request.get("yes")) or plan is not None
            if plan is not None:
                params = plan["params"]

            if risk == policy.YELLOW and not confirmed:
                return {**base, **self._make_plan(action, params, risk)}

            try:
                response = self._execute(
                    action,
                    params,
                    escalated=confirmed,
                    actor=str(request.get("actor") or ("confirm" if plan else "agenticctl")),
                )
            except policy.Escalate as escalate:
                return {**base, **self._make_plan(action, params, policy.YELLOW, reason=str(escalate))}

            self._audit(
                action,
                params,
                risk=risk,
                ok=True,
                started=started,
                undo_id=response.get("undo_id"),
                confirmed=confirmed,
            )
            return {**base, "ok": True, "risk": risk, **response}

        except policy.ActionError as exc:
            self._audit(action, params, risk=policy.risk_of(action), ok=False, error=str(exc), started=started)
            return {**base, "ok": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001 — daemon nunca deve morrer por uma ação
            traceback.print_exc(limit=3)
            self._audit(action, params, risk=policy.risk_of(action), ok=False, error=f"interna: {exc}", started=started)
            return {**base, "ok": False, "error": "erro interno do daemon (veja o log do serviço)"}

    # ------------------------------------------------------------- interno
    def _execute(
        self,
        action: str,
        params: dict[str, Any],
        *,
        escalated: bool,
        actor: str,
        is_undo: bool = False,
    ) -> dict[str, Any]:
        handler = REGISTRY.get(action)
        if handler is None:
            raise policy.ActionError(f"ação sem implementação: {action}")
        ctx = Ctx(self.paths, actor=actor, escalated=escalated)
        ctx.is_undo = is_undo

        lock = None if action in policy.READ_ONLY else self._mutation_lock
        if lock is not None:
            lock.acquire()
        try:
            response = handler(ctx, params)
        finally:
            if lock is not None:
                lock.release()

        undo_id = None
        if not is_undo and response.get("undo"):
            undo_id = undo.register(
                self.paths,
                action=action,
                params=params,
                undo=response["undo"],
                summary=response.get("summary", action),
            )
        return {
            "result": response.get("result"),
            "summary": response.get("summary"),
            "undo_id": undo_id,
        }

    def _make_plan(
        self, action: str, params: dict[str, Any], risk: str, reason: str | None = None
    ) -> dict[str, Any]:
        plan_id = uuid.uuid4().hex[:12]
        with self._plans_lock:
            self._expire_plans()
            self._plans[plan_id] = {"action": action, "params": params, "ts": time.time(), "risk": risk}
        summary = policy.SPEC[action]["summary"]
        audit.append(
            self.paths,
            {
                "action": action,
                "params": params,
                "risk": risk,
                "ok": True,
                "event": "plan",
                "plan_id": plan_id,
                "reason": reason,
            },
        )
        return {
            "ok": True,
            "risk": risk,
            "needs_confirmation": True,
            "plan_id": plan_id,
            "plan": {
                "action": action,
                "summary": summary,
                "explain": reason or summary,
                "params": params,
                "expires_in_s": PLAN_TTL_SECONDS,
            },
        }

    def _consume_plan(self, plan_id: str, action: str) -> dict[str, Any] | None:
        if not plan_id:
            return None
        with self._plans_lock:
            self._expire_plans()
            plan = self._plans.pop(plan_id, None)
        if plan is None:
            raise policy.ActionError("plano de confirmação expirado ou inexistente; refaça a ação")
        if plan["action"] != action:
            raise policy.ActionError(
                f"o plano {plan_id} é de '{plan['action']}', não de '{action}'"
            )
        return plan

    def _expire_plans(self) -> None:
        now = time.time()
        expired = [key for key, plan in self._plans.items() if now - plan["ts"] > PLAN_TTL_SECONDS]
        for key in expired:
            self._plans.pop(key, None)

    def _undo_last(self, request_id: Any) -> dict[str, Any]:
        entry = undo.pop_last(self.paths)
        if entry is None:
            return {
                "id": request_id,
                "ok": True,
                "risk": policy.GREEN,
                "result": {"undone": None, "ops": [], "note": "nada para desfazer"},
                "summary": "nada para desfazer",
            }

        target = entry.get("undo") or {}
        ops = target.get("params", {}).get("ops", []) if target.get("action") == "__batch__" else [target]
        results = []
        errors = []
        # Batch é desfeito em ordem reversa (LIFO), como uma pilha de ações.
        for op in reversed(ops):
            op_action = str(op.get("action") or "")
            op_params = op.get("params") or {}
            try:
                if op_action not in policy.SPEC or policy.risk_of(op_action) == policy.RED:
                    raise policy.ActionError(f"undo com ação não permitida: {op_action}")
                validated = policy.validate_params(op_action, op_params)
                response = self._execute(op_action, validated, escalated=True, actor="undo", is_undo=True)
                results.append({"action": op_action, "result": response.get("result")})
            except Exception as exc:  # noqa: BLE001
                errors.append({"action": op_action, "error": str(exc)})

        audit.append(
            self.paths,
            {
                "action": "undo.last",
                "undo_of": entry.get("id"),
                "undone": entry.get("summary"),
                "ok": not errors,
                "errors": errors,
            },
        )
        return {
            "id": request_id,
            "ok": not errors,
            "risk": policy.GREEN,
            "result": {"undone": entry.get("summary"), "undo_id": entry.get("id"), "ops": results, "errors": errors},
            "summary": f"desfeito: {entry.get('summary')}",
        }

    def _audit(
        self,
        action: str,
        params: dict[str, Any],
        *,
        risk: str,
        ok: bool,
        started: float,
        error: str | None = None,
        undo_id: str | None = None,
        confirmed: bool = False,
    ) -> None:
        audit.append(
            self.paths,
            {
                "action": action,
                "params": params,
                "risk": risk,
                "ok": ok,
                "error": error,
                "undo_id": undo_id,
                "confirmed": confirmed,
                "duration_ms": int((time.monotonic() - started) * 1000),
            },
        )


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:  # noqa: D102
        line = self.rfile.readline(MAX_LINE)
        if not line:
            return
        try:
            request = json.loads(line.decode("utf-8", "replace"))
            if not isinstance(request, dict):
                raise ValueError("requisição deve ser um objeto JSON")
        except (json.JSONDecodeError, ValueError) as exc:
            response = {"id": None, "ok": False, "error": f"requisição inválida: {exc}"}
        else:
            daemon: Daemon = self.server.daemon  # type: ignore[attr-defined]
            try:
                response = daemon.handle(request)
            except Exception as exc:  # noqa: BLE001
                response = {"id": request.get("id"), "ok": False, "error": f"erro interno: {exc}"}
        payload = json.dumps(response, ensure_ascii=False).encode("utf-8") + b"\n"
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass


class _Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True


def _socket_alive(socket_path: Path, timeout: float = 2.0) -> bool:
    """Pergunta ao socket se já existe um daemon escutando."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(str(socket_path))
            client.sendall(b'{"id":0,"action":"ping"}\n')
            data = client.recv(4096)
        return b'"pong"' in data
    except OSError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agenticd", description="Daemon de políticas do Agentic OS")
    parser.add_argument("--socket", help="caminho alternativo do socket Unix")
    parser.add_argument("--force", action="store_true", help="substitui um daemon já em execução")
    parser.add_argument("--version", action="version", version=f"agenticd {__version__}")
    args = parser.parse_args(argv)

    paths = Paths()
    if args.socket:
        paths.socket = Path(args.socket)
    paths.ensure()

    if paths.socket.exists():
        if _socket_alive(paths.socket) and not args.force:
            print(
                f"erro: já existe um agenticd rodando em {paths.socket} (use --force para substituir)",
                file=sys.stderr,
            )
            return 3
        paths.socket.unlink()

    server = _Server(str(paths.socket), _Handler)
    server.daemon = Daemon(paths)  # type: ignore[attr-defined]
    os.chmod(paths.socket, 0o600)

    def shutdown(signum: int, frame: Any) -> None:  # noqa: ARG001
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    print(f"agenticd {__version__} ouvindo em {paths.socket}", file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        try:
            paths.socket.unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

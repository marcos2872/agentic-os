"""Contexto de execução das ações e registro central de handlers."""

from __future__ import annotations

from typing import Any, Callable

from ..paths import Paths
from ..procutil import session_env


class Ctx:
    """Estado repassado a cada handler."""

    def __init__(self, paths: Paths, *, actor: str = "agenticctl", escalated: bool = False) -> None:
        self.paths = paths
        self.actor = actor
        self.escalated = escalated
        self.is_undo = False
        self._env: dict[str, str] | None = None

    @property
    def env(self) -> dict[str, str]:
        """Ambiente com as variáveis da sessão gráfica (lazy: pode custar caro)."""
        if self._env is None:
            self._env = session_env()
        return self._env


Handler = Callable[[Ctx, dict[str, Any]], dict[str, Any]]

REGISTRY: dict[str, Handler] = {}


def register(*actions: str) -> Callable[[Handler], Handler]:
    def decorator(func: Handler) -> Handler:
        for action in actions:
            REGISTRY[action] = func
        return func

    return decorator


def load_all() -> None:
    """Importa os módulos de ações para popular o REGISTRY."""
    from . import (  # noqa: F401
        apps,
        configs,
        flatpak,
        fsread,
        kwin,
        ops,
        routines,
        services,
        system,
        theme,
        widgets,
    )

"""Agentic OS — daemon de políticas e CLI de controle.

MVP: tudo em escopo de usuário (sem root). O agente nunca executa shell:
ele emite ações estruturadas que o daemon valida contra uma allowlist de
ações e binários, com dry-run/backup/undo e auditoria.
"""

__version__ = "0.1.0"

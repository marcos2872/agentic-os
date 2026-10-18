"""Ação: fs.read — leitura de texto permitida (com bloqueios de segredo).

Somente leitura. Restrito a $HOME, /etc, /var/log, /tmp e /var/tmp, com
limite de tamanho e sem arquivos sensíveis (chaves, keyrings, cookies).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..policy import ActionError
from . import Ctx, register

MAX_BYTES = 64 * 1024
ALLOWED_ROOTS = ("/etc", "/var/log", "/tmp", "/var/tmp")
DENY_PARTS = (
    ".ssh/",
    "/.gnupg/",
    "kwallet",
    "keyring",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    ".pem",
    ".netrc",
    ".aws/",
    ".config/gh/",
    "login data",
    "cookies",
    "/etc/shadow",
    "/etc/gshadow",
    "/etc/fstab",
    "/etc/mdadm.conf",
    "/etc/krb5.keytab",
    "ssh_host_",
)


def _allowed_root(path: Path, home: Path) -> bool:
    if path == home or home in path.parents:
        return True
    for root in ALLOWED_ROOTS:
        base = Path(root)
        if path == base or base in path.parents:
            return True
    return False


@register("fs.read")
def fs_read(ctx: Ctx, params: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(params["path"])).expanduser().resolve()
    folded = "/" + str(path).casefold().lstrip("/")

    if not _allowed_root(path, ctx.paths.home.resolve()):
        raise ActionError("leitura permitida apenas em $HOME, /etc, /var/log, /tmp e /var/tmp")
    for denied in DENY_PARTS:
        if denied in folded:
            raise ActionError(f"caminho bloqueado por segurança (conteúdo sensível): {path}")
    if not path.is_file():
        raise ActionError(f"arquivo não encontrado: {path}")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ActionError(f"não consegui acessar o arquivo ({exc.strerror or 'erro de I/O'})") from exc
    try:
        with path.open("rb") as handle:
            blob = handle.read(MAX_BYTES + 1)
    except OSError as exc:
        raise ActionError(f"não consegui ler o arquivo ({exc.strerror or 'erro de I/O'})") from exc
    truncated = len(blob) > MAX_BYTES
    blob = blob[:MAX_BYTES]
    if b"\0" in blob:
        raise ActionError("arquivo binário: leitura não suportada")

    return {
        "result": {
            "path": str(path),
            "size": size,
            "truncated": truncated,
            "content": blob.decode("utf-8", "replace"),
        },
        "undo": None,
        "summary": f"ler {path}",
    }

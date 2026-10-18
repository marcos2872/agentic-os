"""Edição de arquivos INI preservando o conteúdo (formato KDE).

O configparser reescreve o arquivo inteiro e descarta linhas que não
entende (comentários, sintaxe KDE fora do padrão). Aqui a edição é feita
linha a linha: só a seção/chave alvo muda; o resto fica byte a byte igual.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _section_name(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped[0] in "#;":
        return None
    if len(stripped) >= 3 and stripped.startswith("[") and stripped.endswith("]"):
        return stripped[1:-1].strip()
    return None


def _key_of(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped[0] in "#;[":
        return None
    key, sep, _ = stripped.partition("=")
    return key.strip() if sep else None


class IniDoc:
    """Documento INI preservando linha a linha."""

    def __init__(self, text: str = "") -> None:
        self.blocks: list[tuple[str | None, list[str]]] = []
        current_name: str | None = None
        current: list[str] = []
        for line in text.splitlines():
            name = _section_name(line)
            if name is not None:
                self.blocks.append((current_name, current))
                current_name, current = name, []
            else:
                current.append(line)
        self.blocks.append((current_name, current))
        self._drop_empty_leading_block()

    def _drop_empty_leading_block(self) -> None:
        if self.blocks and self.blocks[0][0] is None and not any(
            line.strip() for line in self.blocks[0][1]
        ):
            self.blocks.pop(0)

    # ------------------------------------------------------------ leitura
    def section_names(self) -> list[str]:
        return [name for name, _ in self.blocks if name is not None]

    def has_section(self, section: str) -> bool:
        return any(name == section for name, _ in self.blocks)

    def options(self, section: str) -> dict[str, str]:
        data: dict[str, str] = {}
        for name, lines in self.blocks:
            if name != section:
                continue
            for line in lines:
                key = _key_of(line)
                if key is not None and key not in data:
                    _, _, value = line.strip().partition("=")
                    data[key] = value.strip()
        return data

    def get(self, section: str, key: str) -> str | None:
        return self.options(section).get(key)

    # ------------------------------------------------------------ edição
    def set(self, section: str, key: str, value: str) -> None:
        for name, lines in self.blocks:
            if name != section:
                continue
            new_line = f"{key}={value}"
            found = False
            output: list[str] = []
            for line in lines:
                if _key_of(line) == key:
                    if not found:
                        output.append(new_line)
                        found = True
                    continue  # duplicatas da mesma chave são consolidadas
                output.append(line)
            if not found:
                output.append(new_line)
            lines[:] = output
            return
        self.blocks.append((section, [f"{key}={value}"]))

    def unset(self, section: str, key: str) -> bool:
        for name, lines in self.blocks:
            if name != section:
                continue
            kept = [line for line in lines if _key_of(line) != key]
            removed = len(kept) != len(lines)
            lines[:] = kept
            return removed
        return False

    def remove_section(self, section: str) -> bool:
        before = len(self.blocks)
        self.blocks = [(name, lines) for name, lines in self.blocks if name != section]
        return len(self.blocks) != before

    def render(self) -> str:
        lines: list[str] = []
        for name, block in self.blocks:
            if name is not None:
                lines.append(f"[{name}]")
            lines.extend(block)
        return "\n".join(lines) + "\n"


def write_text_atomic(path: Path, text: str) -> None:
    """Grava via arquivo temporário + rename (não deixa arquivo pela metade)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def load(path: Path) -> IniDoc:
    if path.exists():
        return IniDoc(path.read_text(encoding="utf-8", errors="replace"))
    return IniDoc()

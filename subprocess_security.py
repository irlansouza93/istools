# -*- coding: utf-8 -*-
"""Validação compartilhada para executáveis PostgreSQL chamados pelo plugin."""

import os
import shutil
from pathlib import Path


_ALLOWED_EXECUTABLES = {"pg_dump", "pg_dump.exe", "psql", "psql.exe"}


def validate_postgres_command(command):
    """Retorna um comando seguro, sem shell, para pg_dump ou psql.

    O executável é resolvido para um arquivo real e todos os argumentos são
    rejeitados quando contêm caracteres de controle. A função não interpreta
    nem concatena uma linha de comando: o resultado deve ser passado como uma
    sequência para ``subprocess`` com ``shell=False``.
    """
    if not isinstance(command, (list, tuple)) or not command:
        raise ValueError("O comando PostgreSQL deve ser uma lista não vazia.")

    normalized = []
    for argument in command:
        if not isinstance(argument, (str, os.PathLike)):
            raise ValueError("Todos os argumentos do comando devem ser texto ou caminho.")
        value = os.fspath(argument)
        if not value or any(character in value for character in ("\x00", "\r", "\n")):
            raise ValueError("O comando contém um argumento vazio ou inválido.")
        normalized.append(value)

    executable = Path(normalized[0]).expanduser()
    if executable.name.lower() not in _ALLOWED_EXECUTABLES:
        raise ValueError("Somente pg_dump e psql podem ser executados pelo ISTools.")

    has_directory = executable.is_absolute() or executable.parent != Path(".")
    if has_directory:
        try:
            resolved = executable.resolve(strict=True)
        except OSError as error:
            raise ValueError("O executável PostgreSQL informado não existe.") from error
    else:
        located = shutil.which(str(executable))
        if not located:
            raise ValueError(f"O executável '{executable.name}' não foi encontrado no PATH.")
        resolved = Path(located).resolve()

    if not resolved.is_file() or resolved.name.lower() not in _ALLOWED_EXECUTABLES:
        raise ValueError("O caminho não aponta para um executável PostgreSQL permitido.")

    normalized[0] = str(resolved)
    return normalized

"""Small, platform-neutral parser for the integrated Git command bar."""
from __future__ import annotations


def split_command(command: str) -> list[str]:
    """Split a Git sub-command while preserving quoted arguments and paths.

    ``str.split`` breaks messages such as ``commit -m "hello world"`` and
    POSIX ``shlex`` treats backslashes in Windows paths as escapes.  This
    parser supports single/double quotes and only treats a backslash as an
    escape when it precedes the active quote character.
    """

    args: list[str] = []
    current: list[str] = []
    quote: str | None = None
    token_started = False
    index = 0

    while index < len(command):
        char = command[index]

        if quote is not None:
            if char == quote:
                quote = None
            elif char == "\\" and index + 1 < len(command) and command[index + 1] == quote:
                current.append(quote)
                index += 1
            else:
                current.append(char)
            token_started = True
        elif char in ('"', "'"):
            quote = char
            token_started = True
        elif char.isspace():
            if token_started:
                args.append("".join(current))
                current.clear()
                token_started = False
        else:
            current.append(char)
            token_started = True

        index += 1

    if quote is not None:
        raise ValueError("Guillemet non fermé dans la commande.")
    if token_started:
        args.append("".join(current))
    return args

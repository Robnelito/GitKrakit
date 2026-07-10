"""
diff_parser.py
Transforme un diff unifié (sortie de `git diff` / `git show`) en lignes
alignées côte à côte (ancien/nouveau), pour un rendu façon GitKraken.
Aucune dépendance Qt : testable en isolation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)$")


@dataclass
class DiffRow:
    """Une ligne de la vue côte à côte.

    kind: "context" (identique des deux côtés), "add" (ajout, colonne
    gauche vide), "del" (suppression, colonne droite vide), "mod" (ligne
    remplacée : suppression + ajout appariés sur la même rangée), ou
    "hunk" (séparateur "@@ -a,b +c,d @@", occupe toute la largeur).
    """
    kind: str
    old_no: int | None = None
    old_text: str | None = None
    new_no: int | None = None
    new_text: str | None = None
    label: str = ""


def parse_unified_diff(diff_text: str) -> list[DiffRow]:
    rows: list[DiffRow] = []
    old_no = new_no = 0
    in_hunk = False
    pending_dels: list[str] = []
    pending_adds: list[str] = []

    def flush_pending() -> None:
        nonlocal old_no, new_no
        count = max(len(pending_dels), len(pending_adds))
        for i in range(count):
            d = pending_dels[i] if i < len(pending_dels) else None
            a = pending_adds[i] if i < len(pending_adds) else None
            if d is not None and a is not None:
                rows.append(DiffRow("mod", old_no, d, new_no, a))
                old_no += 1
                new_no += 1
            elif d is not None:
                rows.append(DiffRow("del", old_no, d, None, None))
                old_no += 1
            elif a is not None:
                rows.append(DiffRow("add", None, None, new_no, a))
                new_no += 1
        pending_dels.clear()
        pending_adds.clear()

    for line in diff_text.splitlines():
        if line.startswith("@@"):
            flush_pending()
            match = _HUNK_RE.match(line)
            if match:
                old_no = int(match.group(1))
                new_no = int(match.group(2))
            rows.append(DiffRow("hunk", label=line))
            in_hunk = True
            continue

        if not in_hunk:
            continue  # métadonnées avant le premier hunk (diff --git, ---, +++, index…)

        if line.startswith("-"):
            pending_dels.append(line[1:])
        elif line.startswith("+"):
            pending_adds.append(line[1:])
        elif line.startswith("\\"):
            continue  # "\ No newline at end of file"
        else:
            flush_pending()
            text = line[1:] if line else ""
            rows.append(DiffRow("context", old_no, text, new_no, text))
            old_no += 1
            new_no += 1

    flush_pending()
    return rows

"""
syntax.py
Coloration syntaxique légère pour la vue de diff : détection du langage
par extension de fichier, puis surlignage par expressions régulières
(mots-clés, chaînes, nombres, commentaires, décorateurs/annotations).

Ce n'est pas un vrai lexeur : chaque ligne est traitée indépendamment,
sans état partagé entre lignes — un commentaire ou une chaîne multiligne
ne sera donc pas colorée correctement sur toute sa longueur. C'est un
compromis volontaire pour rester simple et rapide dans une vue de diff.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from gitkrakit import theme


@dataclass(frozen=True)
class LanguageSpec:
    keywords: frozenset[str] = field(default_factory=frozenset)
    line_comment: str | None = None
    case_insensitive: bool = False
    extra_string_delims: tuple[str, ...] = ()  # ex: backtick pour les template literals JS


_PY = frozenset(
    "def class import from return if elif else for while in not and or is None True False "
    "try except finally with as pass break continue lambda yield global nonlocal assert del "
    "raise async await self cls".split()
)
_JS = frozenset(
    "function return if else for while var let const class extends new this import export "
    "from default try catch finally throw typeof instanceof in of async await yield null "
    "undefined true false break continue switch case do void delete static get set super".split()
)
_TS_EXTRA = frozenset(
    "interface type enum implements namespace declare readonly public private protected abstract".split()
)
_JAVA = frozenset(
    "public private protected class interface extends implements new return if else for while "
    "do try catch finally throw throws import package static final void int long short byte "
    "boolean char float double this super null true false switch case break continue abstract "
    "synchronized volatile enum instanceof".split()
)
_C = frozenset(
    "int long short char float double void struct union enum typedef return if else for while "
    "do switch case break continue static const unsigned signed sizeof goto default extern "
    "volatile register auto".split()
)
_CPP = _C | frozenset(
    "class public private protected new delete this namespace using template typename virtual "
    "override try catch throw nullptr true false bool auto constexpr friend operator inline".split()
)
_CSHARP = _CPP | frozenset(
    "var string object null using namespace get set async await foreach in is as readonly "
    "internal sealed partial yield".split()
)
_GO = frozenset(
    "func package import return if else for range switch case default break continue var const "
    "type struct interface map chan go defer select nil true false fallthrough goto".split()
)
_RUST = frozenset(
    "fn let mut return if else for in while loop match struct enum impl trait pub use mod crate "
    "self Self true false break continue as where move ref static const dyn async await unsafe".split()
)
_PHP = frozenset(
    "function return if else elseif for foreach while do switch case break continue class "
    "interface extends implements new public private protected static const namespace use try "
    "catch finally throw echo print array null true false this abstract final trait match fn".split()
)
_RUBY = frozenset(
    "def end class module return if elsif else unless for while until do case when break next "
    "require require_relative include extend attr_accessor attr_reader attr_writer true false "
    "nil self yield begin rescue ensure raise then lambda proc".split()
)
_SQL = frozenset(
    "select from where insert into values update set delete join inner left right outer on "
    "group by order having as and or not null is in like limit create table alter drop primary "
    "key foreign references index distinct union all case when then end exists".split()
)
_KOTLIN = frozenset(
    "fun val var return if else for while do when class interface object package import is in "
    "as null true false override private public protected internal companion data sealed enum "
    "try catch finally throw suspend".split()
)
_SWIFT = frozenset(
    "func var let return if else for while switch case default class struct enum protocol "
    "extension import guard defer true false nil self Self try catch throw init deinit static "
    "private public internal fileprivate open".split()
)
_SHELL = frozenset(
    "if then else elif fi for while do done case esac function return exit export local echo in".split()
)
_JSON_LITERALS = frozenset(["true", "false", "null"])

LANGUAGES: dict[str, LanguageSpec] = {
    "python": LanguageSpec(_PY, line_comment="#"),
    "javascript": LanguageSpec(_JS, line_comment="//", extra_string_delims=("`",)),
    "typescript": LanguageSpec(_JS | _TS_EXTRA, line_comment="//", extra_string_delims=("`",)),
    "java": LanguageSpec(_JAVA, line_comment="//"),
    "c": LanguageSpec(_C, line_comment="//"),
    "cpp": LanguageSpec(_CPP, line_comment="//"),
    "csharp": LanguageSpec(_CSHARP, line_comment="//"),
    "go": LanguageSpec(_GO, line_comment="//"),
    "rust": LanguageSpec(_RUST, line_comment="//"),
    "php": LanguageSpec(_PHP, line_comment="//"),
    "ruby": LanguageSpec(_RUBY, line_comment="#"),
    "sql": LanguageSpec(_SQL, line_comment="--", case_insensitive=True),
    "kotlin": LanguageSpec(_KOTLIN, line_comment="//"),
    "swift": LanguageSpec(_SWIFT, line_comment="//"),
    "shell": LanguageSpec(_SHELL, line_comment="#"),
    "yaml": LanguageSpec(line_comment="#"),
    "json": LanguageSpec(_JSON_LITERALS),
    "css": LanguageSpec(),
}

_EXTENSION_MAP: dict[str, str] = {
    ".py": "python", ".pyw": "python",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".java": "java",
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".hpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hh": "cpp",
    ".cs": "csharp",
    ".go": "go",
    ".rs": "rust",
    ".php": "php",
    ".rb": "ruby",
    ".sql": "sql",
    ".kt": "kotlin", ".kts": "kotlin",
    ".swift": "swift",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell",
    ".yml": "yaml", ".yaml": "yaml",
    ".json": "json",
    ".css": "css", ".scss": "css", ".less": "css",
}

def _syntax_colors() -> dict[str, str]:
    return {
        "comment": theme.TEXT_MUTED,
        "string": theme.LANE_COLORS[5],
        "number": theme.LANE_COLORS[6],
        "decorator": theme.LANE_COLORS[2],
        "keyword": theme.LANE_COLORS[4],
    }


def detect_language(path: str) -> str | None:
    return _EXTENSION_MAP.get(Path(path).suffix.lower())


@lru_cache(maxsize=None)
def _compiled_pattern(language: str) -> re.Pattern | None:
    spec = LANGUAGES.get(language)
    if spec is None:
        return None

    parts = []
    if spec.line_comment:
        parts.append(f"(?P<comment>{re.escape(spec.line_comment)}.*$)")

    string_alt = r'"(?:\\.|[^"\\])*"' + r"|'(?:\\.|[^'\\])*'"
    for delim in spec.extra_string_delims:
        escaped = re.escape(delim)
        string_alt += f"|{escaped}(?:\\\\.|[^{escaped}\\\\])*{escaped}"
    parts.append(f"(?P<string>{string_alt})")

    parts.append(r"(?P<number>\b\d+\.?\d*\b)")
    parts.append(r"(?P<decorator>@\w+)")

    if spec.keywords:
        kw_alt = "|".join(re.escape(k) for k in sorted(spec.keywords, key=len, reverse=True))
        parts.append(f"(?P<keyword>\\b(?:{kw_alt})\\b)")

    flags = re.IGNORECASE if spec.case_insensitive else 0
    return re.compile("|".join(parts), flags)


def _escape(text: str) -> str:
    # &nbsp; au lieu d'espaces : Qt (comme le HTML) réduit les espaces
    # simples, ce qui casserait l'indentation du code sans ça.
    return html.escape(text, quote=False).replace(" ", "&nbsp;")


def highlight_line(text: str, language: str | None) -> str:
    """Retourne `text` en HTML riche (compatible QLabel), avec les jetons
    reconnus enveloppés dans des <span style=color:...>. Si le langage est
    inconnu ou non supporté, retourne le texte simplement échappé."""
    pattern = _compiled_pattern(language) if language else None
    if pattern is None or not text:
        return _escape(text)

    html_parts: list[str] = []
    colors = _syntax_colors()
    last_end = 0
    for match in pattern.finditer(text):
        if match.start() > last_end:
            html_parts.append(_escape(text[last_end : match.start()]))
        color = colors.get(match.lastgroup)
        token = _escape(match.group())
        html_parts.append(f'<span style="color:{color}">{token}</span>' if color else token)
        last_end = match.end()
    if last_end < len(text):
        html_parts.append(_escape(text[last_end:]))
    return "".join(html_parts)

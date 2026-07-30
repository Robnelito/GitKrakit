"""
preferences.py
Préférences utilisateur persistées via QSettings, au même endroit que le
thème. Aucune logique Git : seulement la lecture/écriture des choix de
l'utilisateur et leur normalisation.
"""
from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QSettings

from gitkrakit.core.acp_commit import ACP_PROVIDERS

# Ordre d'affichage des agents, aligné sur la déclaration des fournisseurs.
ACP_PROVIDER_ORDER: tuple[str, ...] = tuple(ACP_PROVIDERS)

_ACP_ENABLED_PREFIX = "acp/enabled"
_SIDEBAR_COLLAPSED_KEY = "sidebar/collapsed_folders"


def _settings() -> QSettings:
    return QSettings("GitKrakit", "GitKrakit")


def as_bool(value: object, default: bool = True) -> bool:
    """Interpret a QSettings value, which may come back as a string."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in ("true", "1", "yes", "on"):
        return True
    if text in ("false", "0", "no", "off"):
        return False
    return default


def normalize_provider_ids(values: Iterable[str] | str | None) -> list[str]:
    """Keep known provider ids only, deduplicated and in display order."""
    if isinstance(values, str):
        values = [values]
    selected = {str(value) for value in (values or ())}
    return [provider_id for provider_id in ACP_PROVIDER_ORDER if provider_id in selected]


def acp_provider_choices() -> list[tuple[str, str]]:
    """Return every ACP agent as (id, label), enabled or not."""
    return [(provider_id, ACP_PROVIDERS[provider_id].label) for provider_id in ACP_PROVIDER_ORDER]


def enabled_acp_providers() -> list[str]:
    """Return the ids of the agents the user left switched on (all by default)."""
    settings = _settings()
    return [
        provider_id
        for provider_id in ACP_PROVIDER_ORDER
        if as_bool(settings.value(f"{_ACP_ENABLED_PREFIX}/{provider_id}", True))
    ]


def enabled_acp_provider_choices() -> list[tuple[str, str]]:
    """Return the switched-on agents as (id, label), ready for a combo box."""
    enabled = set(enabled_acp_providers())
    return [choice for choice in acp_provider_choices() if choice[0] in enabled]


def save_enabled_acp_providers(provider_ids: Iterable[str] | str | None) -> list[str]:
    """Persist the switched-on agents and return the normalized selection."""
    enabled = normalize_provider_ids(provider_ids)
    settings = _settings()
    for provider_id in ACP_PROVIDER_ORDER:
        settings.setValue(f"{_ACP_ENABLED_PREFIX}/{provider_id}", provider_id in enabled)
    return enabled


def collapsed_sidebar_folders() -> set[str]:
    """Return the sidebar folders the user last left closed."""
    stored = _settings().value(_SIDEBAR_COLLAPSED_KEY)
    if stored is None:
        return set()
    # QSettings rend une chaîne nue quand la liste ne contenait qu'un élément.
    if isinstance(stored, str):
        stored = [stored]
    return {str(value) for value in stored if str(value)}


def save_collapsed_sidebar_folders(keys: Iterable[str]) -> None:
    """Persist the closed sidebar folders, so they survive a restart."""
    _settings().setValue(_SIDEBAR_COLLAPSED_KEY, sorted(str(key) for key in keys if key))

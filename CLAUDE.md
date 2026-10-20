# GitKrakit

## Versioning

À chaque changement apporté au projet, incrémenter la version dans `gitkrakit/__init__.py` (`__version__`) selon la convention SemVer `MAJOR.MINOR.PATCH` :

- **PATCH** (`1.1.0` → `1.1.1`) : correction de bug, ajustement mineur, refactoring sans impact fonctionnel.
- **MINOR** (`1.1.0` → `1.2.0`) : nouvelle fonctionnalité rétrocompatible.
- **MAJOR** (`1.1.0` → `2.0.0`) : changement incompatible (rupture de comportement, de format de données ou de configuration).

Un incrément de niveau supérieur remet les niveaux inférieurs à `0`.

`gitkrakit.__version__` est la seule source de vérité (lue par `pyproject.toml`, l'UI, l'updater et le workflow de release). Ne pas dupliquer la version ailleurs.

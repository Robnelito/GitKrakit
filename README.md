# GitKrakit

Client Git graphique minimal écrit en Python (PySide6 + GitPython), inspiré
de GitKraken. Projet personnel / d'apprentissage — ce n'est **pas** un clone
complet de GitKraken (voir "Limites" plus bas).

## Fonctionnalités

- Graphe de commits visuel avec lanes colorées (branches, merges)
- Liste des branches locales / distantes, tags, regroupées en dossiers ; les
  dossiers repliés le restent après un rafraîchissement et après un redémarrage
- Checkout d'une branche en double-clic
- Création de branche
- Zone de staging : indexer / désindexer des fichiers, commit
- Fetch / Pull / Push sur `origin`
- Synchronisation automatique en arrière-plan, sans bloquer l'interface
- Détails d'un commit (auteur, date, parents, refs, message)
- Diff côte à côte par fichier avec coloration syntaxique
- Git Flow : initialisation, feature, release et hotfix
- Génération de messages Conventional Commits via ACP avec Codex CLI ou Claude Code
- Mise à jour automatique signée, téléchargée en arrière-plan depuis GitHub Releases
- Mini-terminal git intégré avec arguments entre guillemets
- Espaces de travail : groupes nommés de dépôts + dépôts récents, persistés
  dans `~/.gitkrakit/workspaces.json`

## Installation

```bash
python -m venv venv
source venv/bin/activate  # ou venv\Scripts\activate sous Windows
pip install -r requirements.txt
```

Pour une installation modifiable avec les outils de développement :

```bash
pip install -e ".[dev]"
```

### Génération de message via ACP

GitKrakit est un client [Agent Client Protocol](https://agentclientprotocol.com/).
Il démarre un adaptateur ACP local via `npx`, puis lui transmet uniquement le
diff indexé et un prompt conforme à
[Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/).

Prérequis :

- Node.js avec `npx` disponible dans le `PATH` ;
- Codex CLI ou Claude Code installé et déjà authentifié ;
- les dépendances Python du projet installées.

Les adaptateurs sont téléchargés à la demande et mis en cache par `npx` :

- Codex : `@agentclientprotocol/codex-acp`
- Claude Code : `@agentclientprotocol/claude-agent-acp`

Dans le panneau **Staging**, indexe les fichiers, choisis l'agent, puis clique
sur **Générer via ACP**. Le résultat remplit l'éditeur ; GitKrakit ne crée
jamais le commit automatiquement.

**Fichier > Préférences…** (`Ctrl+,`) ouvre un interrupteur par agent : seuls
les agents activés apparaissent dans la liste du panneau Staging, et un agent
désactivé n'est jamais démarré. Les deux agents sont actifs par défaut ; si
aucun ne l'est, le bouton **Générer via ACP** reste indisponible. Le choix est
persisté dans les réglages de l'application.

La session de génération est isolée en lecture seule. Les permissions d'outil
sont refusées, les instructions éventuellement présentes dans le diff sont
traitées comme des données non fiables, et les sorties non conformes à
Conventional Commits sont rejetées.

## Lancement

```bash
python main.py                      # puis Fichier > Ouvrir un dépôt
python main.py /chemin/vers/un/repo # ouvre directement ce dépôt
```

## Mises à jour et publications Windows

L'installateur place GitKrakit dans
`%LOCALAPPDATA%\Robnelito\GitKrakit`. Ce dossier appartient à l'utilisateur :
PyUpdater peut donc remplacer l'exécutable et le relancer sans élévation UAC.
Au démarrage, l'application installée vérifie silencieusement la présence d'une
version plus récente. Une bannière non modale permet de lancer ou reporter le
téléchargement ; le paquet et son manifeste sont vérifiés avec la clé publique
Ed25519 présente dans `gitkrakit/client_config.py` avant le redémarrage.

PyUpdater 4.0 nécessite l'environnement de build Python 3.11 défini dans le
workflow. Le développement courant de l'application n'a pas besoin d'installer
PyUpdater ; les outils de publication sont disponibles via l'extra `release`.

### Configuration unique du secret de signature

La clé privée n'est jamais versionnée. Le keypack créé hors ligne doit être
conservé dans un emplacement sûr, puis ajouté au dépôt GitHub comme secret
`PYUPDATER_KEYPACK_B64`. Depuis PowerShell, à partir de la copie sécurisée :

```powershell
$keypack = [Convert]::ToBase64String(
    [IO.File]::ReadAllBytes('C:\chemin\securise\keypack.pyu')
)
$keypack | gh secret set PYUPDATER_KEYPACK_B64 --repo Robnelito/GitKrakit
Remove-Variable keypack
```

Ne jamais afficher cette valeur, la placer dans un artefact Actions, ni ajouter
`keypack.pyu` ou `.pyupdater/` au dépôt.

### Couper une version

1. Mettre à jour `gitkrakit.__version__` au format `MAJOR.MINOR.PATCH`, par
   exemple `1.0.1`, puis inclure ce changement dans le commit à publier.
2. Pousser le commit sur `main`.
3. Le push déclenche automatiquement le workflow : il lit la version depuis
   `gitkrakit.__version__`, exécute les tests, lance `pyupdater build`, signe via
   `pyupdater pkg --process --sign`, construit l'installateur puis publie les
   fichiers sur la release fixe `latest-updates`.

Le workflow vérifie également qu'un manifeste valide est accepté, puis qu'un
manifeste modifié et une clé de signature différente sont tous deux rejetés.
Le petit shim dans `scripts/pyupdater_compat/` corrige uniquement l'analyse des
noms d'archives de PyUpdater 4 avec les versions modernes de `packaging` ; il
n'est pas chargé par l'application.

La première publication doit être installée avec
`GitKrakit-Setup-<version>.exe`. Les versions suivantes sont distribuées par
l'application. La signature PyUpdater protège les charges de mise à jour ; elle
ne remplace pas une signature Windows Authenticode. Tant qu'aucun certificat
Authenticode n'est configuré, SmartScreen peut donc avertir lors du premier
lancement de l'installateur ou de l'exécutable.

## Structure du projet

```
GitKrakit/
├── main.py                        # point d'entrée (mince : QApplication + MainWindow)
├── gitkrakit/
│   ├── theme.py                   # palette et feuille de style centralisées
│   ├── preferences.py             # préférences persistées (agents ACP actifs)
│   ├── core/                      # logique métier, aucune dépendance Qt
│   │   ├── command_parser.py      # arguments du terminal intégré
│   │   ├── acp_commit.py          # client ACP + prompt Conventional Commits
│   │   ├── diff_parser.py         # diff unifié vers vue côte à côte
│   │   ├── git_backend.py         # toute la logique Git (GitPython)
│   │   ├── gitflow.py             # opérations Git Flow
│   │   └── graph_model.py         # algorithme d'attribution des lanes du graphe
│   ├── workspace/
│   │   └── manager.py             # espaces de travail + récents (JSON, sans Qt)
│   └── ui/                        # couche PySide6
│       ├── main_window.py         # orchestration : relie backend et panneaux
│       ├── graph_view.py          # rendu du graphe (QGraphicsView)
│       ├── preferences_dialog.py  # interrupteurs d'activation des agents ACP
│       └── panels/                # vues "muettes" (signaux, pas de logique Git)
│           ├── sidebar_panel.py   # dépôts, workspaces, branches, tags, Git Flow
│           ├── staging_panel.py   # stage/unstage + message de commit
│           ├── details_panel.py   # détails du commit sélectionné
│           ├── diff_panel.py      # diff côte à côte
│           └── terminal_dock.py   # mini-terminal git
├── tests/                         # tests du cœur sans interface graphique
├── installer/GitKrakit.iss        # installateur Windows par utilisateur
├── scripts/set_version.py         # mise à jour de la version source
├── win.spec                       # build PyUpdater/PyInstaller Windows
├── pyproject.toml                 # packaging et configuration de test
└── requirements.txt
```

Règles d'architecture :
- `core/` et `workspace/` n'importent jamais Qt → testables sans interface
- les panneaux de `ui/panels/` n'appellent jamais le backend : ils émettent
  des signaux que `main_window.py` relie à `GitBackend`
- les couleurs/styles vivent uniquement dans `theme.py`
- les opérations Git potentiellement lentes sont sérialisées dans un thread
  de travail afin de garder l'interface réactive

## Tests

La suite couvre le parseur de commandes, les diffs, le graphe, les espaces de
travail et les opérations Git de base dans un dépôt temporaire :

```bash
python -m unittest discover -s tests -v
```

## Limites connues (par rapport à GitKraken)

- Pas d'IA (résumés de PR, génération de messages de commit, etc.)
- Pas d'intégration native GitHub/GitLab/Bitbucket/Azure DevOps (pull
  requests, forks) — seulement fetch/pull/push génériques sur les remotes Git
- Pas de résolution de conflits visuelle avancée (merge tool side-by-side) ;
  en cas de conflit, utiliser le terminal intégré ou un outil externe
- Le rendu du graphe n'est pas optimisé pour des historiques de dizaines de
  milliers de commits (limite par défaut : 300 commits chargés)

## Pistes d'évolution

- Support de plusieurs remotes (actuellement `origin` par défaut)
- Résolution de conflits via une vue à 3 panneaux (local / base / distant)
- Tests d'interaction Qt pour les parcours utilisateur principaux

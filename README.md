# GitKrakit

Client Git graphique minimal écrit en Python (PySide6 + GitPython), inspiré
de GitKraken. Projet personnel / d'apprentissage — ce n'est **pas** un clone
complet de GitKraken (voir "Limites" plus bas).

## Fonctionnalités incluses (MVP)

- Graphe de commits visuel avec lanes colorées (branches, merges)
- Liste des branches locales / distantes, tags
- Checkout d'une branche en double-clic
- Création de branche
- Zone de staging : indexer / désindexer des fichiers, commit
- Fetch / Pull / Push sur `origin`
- Détails d'un commit (auteur, date, parents, refs, message)
- Mini-terminal git intégré (tape une sous-commande, ex: `log --oneline -5`)
- Espaces de travail : groupes nommés de dépôts + dépôts récents, persistés
  dans `~/.gitkrakit/workspaces.json` (onglet "Espaces", double-clic pour ouvrir)

## Installation

```bash
python -m venv venv
source venv/bin/activate  # ou venv\Scripts\activate sous Windows
pip install -r requirements.txt
```

## Lancement

```bash
python main.py                      # puis Fichier > Ouvrir un dépôt
python main.py /chemin/vers/un/repo # ouvre directement ce dépôt
```

## Structure du projet

```
GitKrakit/
├── main.py                        # point d'entrée (mince : QApplication + MainWindow)
├── gitkrakit/
│   ├── theme.py                   # palette et feuille de style centralisées
│   ├── core/                      # logique métier, aucune dépendance Qt
│   │   ├── git_backend.py         # toute la logique Git (GitPython)
│   │   └── graph_model.py         # algorithme d'attribution des lanes du graphe
│   ├── workspace/
│   │   └── manager.py             # espaces de travail + récents (JSON, sans Qt)
│   └── ui/                        # couche PySide6
│       ├── main_window.py         # orchestration : relie backend et panneaux
│       ├── graph_view.py          # rendu du graphe (QGraphicsView)
│       └── panels/                # vues "muettes" (signaux, pas de logique Git)
│           ├── workspace_panel.py # arbre espaces de travail / récents
│           ├── branches_panel.py  # branches locales/distantes, tags
│           ├── staging_panel.py   # stage/unstage + message de commit
│           ├── details_panel.py   # détails du commit sélectionné
│           └── terminal_dock.py   # mini-terminal git
└── requirements.txt
```

Règles d'architecture :
- `core/` et `workspace/` n'importent jamais Qt → testables sans interface
- les panneaux de `ui/panels/` n'appellent jamais le backend : ils émettent
  des signaux que `main_window.py` relie à `GitBackend`
- les couleurs/styles vivent uniquement dans `theme.py`

## Limites connues (par rapport à GitKraken)

- Pas d'IA (résumés de PR, génération de messages de commit, etc.)
- Pas d'intégration native GitHub/GitLab/Bitbucket/Azure DevOps (pull
  requests, forks) — seulement fetch/pull/push génériques sur les remotes Git
- Pas de résolution de conflits visuelle avancée (merge tool side-by-side) ;
  en cas de conflit, utiliser le terminal intégré ou un outil externe
- Le rendu du graphe n'est pas optimisé pour des historiques de dizaines de
  milliers de commits (limite par défaut : 300 commits chargés)

## Pistes d'évolution

- Ajouter un vrai diff viewer par fichier (le backend expose déjà
  `diff_for_file`, il manque juste l'affichage dans l'UI)
- Support de plusieurs remotes (actuellement `origin` par défaut)
- Résolution de conflits via une vue à 3 panneaux (local / base / distant)

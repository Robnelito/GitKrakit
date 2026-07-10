"""
graph_model.py
Transforme une liste de CommitInfo (ordre topologique, du plus récent au
plus ancien) en une structure prête à dessiner : chaque commit se voit
assigner une colonne ("lane") et une couleur, façon GitKraken / git log --graph.

Algorithme (simplifié, inspiré de l'algorithme utilisé par `git log --graph`) :
- On maintient une liste de "lanes actives", chacune attend un sha précis
  (le prochain parent à rencontrer dans cette colonne).
- Pour chaque commit rencontré (en parcourant du plus récent au plus ancien) :
    - si son sha est attendu par une lane -> il prend cette colonne
    - sinon -> on ouvre une nouvelle lane (nouvelle branche visible)
    - une fois placé, la lane est mise à jour pour attendre son premier parent
    - les parents supplémentaires (merge) ouvrent chacun une nouvelle lane
      qui attend ce parent
- Les lanes libérées (dont le commit attendu vient d'être consommé par une
  autre lane, cas de merge/fast-forward) sont refermées pour être réutilisées.
"""
from __future__ import annotations

from dataclasses import dataclass

from gitkrakit.core.git_backend import CommitInfo
from gitkrakit.theme import LANE_COLORS


@dataclass
class GraphNode:
    commit: CommitInfo
    row: int
    lane: int
    color: str
    # positions (lane, row) des parents, pour tracer les lignes
    parent_lanes: list[tuple[int, int]]


class GraphLayout:
    def __init__(self, commits: list[CommitInfo]):
        self.commits = commits
        self.nodes: list[GraphNode] = []
        self._build()

    def _build(self) -> None:
        # lanes[i] = sha attendu dans cette colonne, ou None si libre
        lanes: list[str | None] = []
        sha_to_row: dict[str, int] = {}

        for row, commit in enumerate(self.commits):
            sha_to_row[commit.sha] = row

            # 1. trouver une lane qui attend ce commit
            lane_idx = None
            for i, expected in enumerate(lanes):
                if expected == commit.sha:
                    lane_idx = i
                    break

            if lane_idx is None:
                # nouvelle branche : réutiliser une lane libre ou en créer une
                lane_idx = None
                for i, expected in enumerate(lanes):
                    if expected is None:
                        lane_idx = i
                        break
                if lane_idx is None:
                    lane_idx = len(lanes)
                    lanes.append(None)

            color = LANE_COLORS[lane_idx % len(LANE_COLORS)]

            # 2. libérer toutes les lanes qui attendaient ce même sha
            #    (cas où plusieurs branches convergent vers ce commit)
            for i, expected in enumerate(lanes):
                if expected == commit.sha:
                    lanes[i] = None

            # 3. assigner les parents à des lanes
            parent_lane_positions: list[tuple[int, int]] = []
            if commit.parents:
                first_parent, *extra_parents = commit.parents
                lanes[lane_idx] = first_parent

                for parent_sha in extra_parents:
                    # chercher une lane déjà en attente de ce parent (merge déjà vu)
                    existing = next(
                        (i for i, e in enumerate(lanes) if e == parent_sha), None
                    )
                    if existing is not None:
                        continue
                    free_idx = next(
                        (i for i, e in enumerate(lanes) if e is None), None
                    )
                    if free_idx is None:
                        free_idx = len(lanes)
                        lanes.append(None)
                    lanes[free_idx] = parent_sha
            else:
                lanes[lane_idx] = None  # commit racine, lane libérée

            self.nodes.append(
                GraphNode(
                    commit=commit,
                    row=row,
                    lane=lane_idx,
                    color=color,
                    parent_lanes=parent_lane_positions,  # rempli au 2e passage
                )
            )

        # 2e passage : maintenant qu'on connaît la row de chaque sha,
        # on peut résoudre lane+row des parents pour tracer les segments.
        node_by_sha = {n.commit.sha: n for n in self.nodes}
        for node in self.nodes:
            for parent_sha in node.commit.parents:
                parent_node = node_by_sha.get(parent_sha)
                if parent_node is not None:
                    node.parent_lanes.append((parent_node.lane, parent_node.row))

    @property
    def lane_count(self) -> int:
        return max((n.lane for n in self.nodes), default=0) + 1

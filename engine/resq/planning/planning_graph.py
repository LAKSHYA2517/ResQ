"""Planning graph (Graphplan): alternating proposition and action levels with mutex links.

Level S0 holds the initial atoms. Action level Ai holds every action whose preconditions are
in Si and pairwise non-mutex, plus a no-op per atom of Si (persistence). S(i+1) holds
everything those actions add. Mutex (cannot both happen / both hold at this level):

  actions:  inconsistent effects (one deletes what the other adds), interference (one deletes
            a precondition of the other), or competing needs (their preconditions are mutex)
  atoms:    every way of achieving one is mutex with every way of achieving the other

The first level at which all goal atoms appear pairwise non-mutex is a lower bound on the
number of (parallel) steps of any plan. The graph is polynomial in size, unlike the state space.
"""

from dataclasses import dataclass
from itertools import combinations

from ..logic.terms import Atom
from ..trace import GraphLevelBuilt, Trace
from .strips import Action, StripsProblem

type Pair = frozenset[str]


@dataclass(frozen=True)
class Level:
    index: int
    atoms: tuple[str, ...]  # S_index
    atom_mutex: tuple[tuple[str, str], ...]
    actions: tuple[str, ...]  # A_index (empty on the last level); no-ops are "keep <atom>"
    action_mutex: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class PlanningGraph:
    levels: tuple[Level, ...]
    goal: tuple[str, ...]
    goal_level: int | None  # first level with all goals present and non-mutex; None: never
    leveled_off: bool  # the last two proposition levels are identical: nothing new can appear


def _noop(a: Atom) -> Action:
    return Action("keep", (str(a),), frozenset({a}), frozenset({a}), frozenset(), 0.0)


def _label(a: Action) -> str:
    return f"keep {a.params[0]}" if a.name == "keep" else a.label


def _pairs(pairs: set[Pair]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((a, b) for a, b in (sorted(p) for p in pairs)))


def build_planning_graph(
    problem: StripsProblem, max_levels: int = 20
) -> tuple[PlanningGraph, Trace]:
    atoms: set[Atom] = set(problem.initial)
    atom_mutex: set[frozenset[Atom]] = set()
    levels: list[Level] = []
    trace: Trace = []
    goal_level: int | None = None
    leveled = False

    def goals_reached() -> bool:
        return problem.goal <= atoms and not any(
            frozenset(p) in atom_mutex for p in combinations(problem.goal, 2)
        )

    for i in range(max_levels + 1):
        if goal_level is None and goals_reached():
            goal_level = i
        # actions applicable at this level
        candidates = [*problem.actions, *(_noop(a) for a in sorted(atoms, key=str))]
        acts = [
            a
            for a in candidates
            if a.pre <= atoms
            and not any(frozenset(p) in atom_mutex for p in combinations(a.pre, 2))
        ]
        act_mutex: set[frozenset[str]] = set()
        for a, b in combinations(acts, 2):
            inconsistent = a.delete & b.add or b.delete & a.add
            interference = a.delete & b.pre or b.delete & a.pre
            competing = any(frozenset({p, q}) in atom_mutex for p in a.pre for q in b.pre if p != q)
            if inconsistent or interference or competing:
                act_mutex.add(frozenset({_label(a), _label(b)}))
        nxt: set[Atom] = set().union(*(a.add for a in acts)) if acts else set()
        achievers = {p: [_label(a) for a in acts if p in a.add] for p in nxt}
        nxt_mutex: set[frozenset[Atom]] = {
            frozenset({p, q})
            for p, q in combinations(sorted(nxt, key=str), 2)
            if all(
                x != y and frozenset({x, y}) in act_mutex
                for x in achievers[p]
                for y in achievers[q]
            )
        }
        leveled = nxt == atoms and nxt_mutex == atom_mutex
        last = leveled or i == max_levels
        levels.append(
            Level(
                index=i,
                atoms=tuple(sorted(map(str, atoms))),
                atom_mutex=_pairs({frozenset(map(str, m)) for m in atom_mutex}),
                actions=() if last else tuple(sorted(_label(a) for a in acts)),
                action_mutex=() if last else _pairs(act_mutex),
            )
        )
        trace.append(GraphLevelBuilt(i, len(atoms), len(atom_mutex), 0 if last else len(acts)))
        if last:
            break
        atoms, atom_mutex = nxt, nxt_mutex
    graph = PlanningGraph(tuple(levels), tuple(sorted(map(str, problem.goal))), goal_level, leveled)
    return graph, trace

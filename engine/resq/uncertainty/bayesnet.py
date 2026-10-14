"""Discrete Bayesian networks over Boolean variables."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import product
from typing import Any

type Assignment = Mapping[str, bool]


@dataclass(frozen=True)
class Node:
    """``cpt[parent_values]`` is P(node = True | parents = parent_values); the False row is its
    complement, so every row of the full table sums to 1 by construction."""

    name: str
    parents: tuple[str, ...]
    cpt: Mapping[tuple[bool, ...], float]


class BayesNet:
    def __init__(self, nodes: Iterable[Node]) -> None:
        by_name = {n.name: n for n in nodes}
        problems = []
        for n in by_name.values():
            for parent in n.parents:
                if parent not in by_name:
                    problems.append(f"{n.name}: unknown parent {parent!r}")
            rows = set(product((True, False), repeat=len(n.parents)))
            if set(n.cpt) != rows:
                problems.append(
                    f"{n.name}: CPT needs exactly {len(rows)} rows (one per parent case)"
                )
            for row, p in n.cpt.items():
                if not 0.0 <= p <= 1.0:
                    problems.append(f"{n.name}: P(true | {row}) = {p} is not a probability")
        if problems:
            raise ValueError("; ".join(problems))
        # topological order (parents first); fails on a cycle
        order: list[str] = []
        pending = dict(by_name)
        while pending:
            ready = [n for n in pending.values() if all(p in order for p in n.parents)]
            if not ready:
                raise ValueError(f"the network has a cycle among {sorted(pending)}")
            for n in ready:
                order.append(n.name)
                del pending[n.name]
        self.order = tuple(order)
        self.nodes = {name: by_name[name] for name in order}

    def p(self, name: str, value: bool, assignment: Assignment) -> float:
        """P(name = value | its parents as given in ``assignment``)."""
        node = self.nodes[name]
        p_true = node.cpt[tuple(assignment[parent] for parent in node.parents)]
        return p_true if value else 1.0 - p_true

    def children(self, name: str) -> list[str]:
        return [n.name for n in self.nodes.values() if name in n.parents]

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [
                {
                    "name": n.name,
                    "parents": list(n.parents),
                    "cpt": [
                        {"given": list(row), "p_true": n.cpt[row]}
                        for row in product((True, False), repeat=len(n.parents))
                    ],
                }
                for n in self.nodes.values()
            ]
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "BayesNet":
        try:
            nodes = [
                Node(
                    str(n["name"]),
                    tuple(str(p) for p in n["parents"]),
                    {
                        tuple(bool(v) for v in row["given"]): float(row["p_true"])
                        for row in n["cpt"]
                    },
                )
                for n in raw["nodes"]
            ]
        except (KeyError, TypeError) as err:
            raise ValueError(f"malformed network: {err!r}") from err
        return cls(nodes)

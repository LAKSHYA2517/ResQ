from dataclasses import dataclass
from enum import StrEnum


class Terrain(StrEnum):
    FLOOR = "floor"
    RUBBLE = "rubble"
    WALL = "wall"
    EXIT = "exit"


# Characters used in scenario JSON terrain rows. Exits are placed via the ``exits`` list.
CHAR_TO_TERRAIN = {".": Terrain.FLOOR, "r": Terrain.RUBBLE, "#": Terrain.WALL}


@dataclass(frozen=True)
class CostModel:
    """Cost of *entering* a cell. Hot-zone cells add ``hot_extra`` on top of their terrain cost."""

    floor: float = 1.0
    rubble: float = 3.0
    exit: float = 1.0
    hot_extra: float = 4.0
    pickup: float = 1.0  # abstract actions: one tick each
    dropoff: float = 1.0

    def terrain_cost(self, terrain: Terrain) -> float | None:
        """Base entering cost, or ``None`` if the terrain is blocked."""
        match terrain:
            case Terrain.FLOOR:
                return self.floor
            case Terrain.RUBBLE:
                return self.rubble
            case Terrain.EXIT:
                return self.exit
            case Terrain.WALL:
                return None

    @property
    def min_step(self) -> float:
        """Cheapest possible single step; scales the Manhattan heuristic (hot_extra only adds)."""
        return min(self.floor, self.rubble, self.exit)

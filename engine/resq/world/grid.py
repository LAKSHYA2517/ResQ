"""Grid geometry. Coordinates are ``(row, col)``."""

from collections.abc import Iterator

type Cell = tuple[int, int]

# The order of this tuple is part of the deterministic tie-breaking contract:
# successors are generated up, down, left, right.
MOVES: tuple[tuple[str, int, int], ...] = (("U", -1, 0), ("D", 1, 0), ("L", 0, -1), ("R", 0, 1))


def in_bounds(cell: Cell, rows: int, cols: int) -> bool:
    return 0 <= cell[0] < rows and 0 <= cell[1] < cols


def moves(cell: Cell, rows: int, cols: int) -> Iterator[tuple[str, Cell]]:
    """In-bounds 4-neighbours as ``(action, cell)`` in MOVES order."""
    for name, dr, dc in MOVES:
        n = (cell[0] + dr, cell[1] + dc)
        if in_bounds(n, rows, cols):
            yield name, n


def cell_name(cell: Cell) -> str:
    """Logic constant for a cell: ``(3, 4)`` -> ``"c3_4"``."""
    return f"c{cell[0]}_{cell[1]}"


def name_cell(name: str) -> Cell:
    r, c = name[1:].split("_")
    return (int(r), int(c))

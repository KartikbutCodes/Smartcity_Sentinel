"""Aggregate density-grid and heatmap calculations without identity tracking."""

from __future__ import annotations

from collections.abc import Iterable


def density_grid(
    points: Iterable[tuple[float, float]], rows: int = 8, columns: int = 8
) -> list[list[int]]:
    """Bin normalized (x, y) points into a two-dimensional density grid."""
    if rows < 1 or columns < 1:
        raise ValueError("Grid dimensions must be positive.")
    grid = [[0 for _ in range(columns)] for _ in range(rows)]
    for x, y in points:
        if not (0 <= x <= 1 and 0 <= y <= 1):
            continue
        column = min(int(x * columns), columns - 1)
        row = min(int(y * rows), rows - 1)
        grid[row][column] += 1
    return grid


def stampede_risk(grid: list[list[int]], capacity_per_cell: int = 8) -> float:
    """Calculate an interpretable [0, 1] congestion risk from cell occupancy."""
    if capacity_per_cell < 1 or not grid or not grid[0]:
        raise ValueError("Grid and positive cell capacity are required.")
    peak = max(max(row) for row in grid)
    mean = sum(map(sum, grid)) / (len(grid) * len(grid[0]))
    return min(1.0, 0.7 * peak / capacity_per_cell + 0.3 * mean / capacity_per_cell)


def heatmap(grid: list[list[int]]) -> list[list[float]]:
    """Normalize density cells to [0, 1] for chart rendering."""
    peak = max((max(row) for row in grid), default=0)
    if peak == 0:
        return [[0.0 for _ in row] for row in grid]
    return [[value / peak for value in row] for row in grid]

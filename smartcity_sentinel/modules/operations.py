"""Alert prioritization and local emergency-route planning primitives."""

from __future__ import annotations

import heapq
from collections.abc import Mapping


def prioritize_alert(
    severity: float, impact: float = 0.5, confidence: float = 1.0
) -> dict[str, float | str]:
    """Score an alert from bounded severity, impact, and confidence inputs."""
    for name, value in (("severity", severity), ("impact", impact), ("confidence", confidence)):
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be between zero and one.")
    score = 0.55 * severity + 0.30 * impact + 0.15 * confidence
    priority = "high" if score >= 0.75 else "medium" if score >= 0.45 else "low"
    return {"score": round(score, 4), "priority": priority}


def shortest_route(
    graph: Mapping[str, Mapping[str, float]], start: str, destination: str
) -> tuple[list[str], float]:
    """Return shortest weighted route through a small nonnegative city graph."""
    if start not in graph or destination not in graph:
        raise ValueError("Start and destination must be graph nodes.")
    distances = {start: 0.0}
    previous: dict[str, str] = {}
    queue: list[tuple[float, str]] = [(0.0, start)]
    while queue:
        distance, node = heapq.heappop(queue)
        if distance != distances.get(node):
            continue
        if node == destination:
            break
        for neighbor, weight in graph[node].items():
            if weight < 0:
                raise ValueError("Route weights must be nonnegative.")
            candidate = distance + weight
            if candidate < distances.get(neighbor, float("inf")):
                distances[neighbor] = candidate
                previous[neighbor] = node
                heapq.heappush(queue, (candidate, neighbor))
    if destination not in distances:
        raise ValueError(f"No route from {start!r} to {destination!r}.")
    path = [destination]
    while path[-1] != start:
        path.append(previous[path[-1]])
    path.reverse()
    return path, distances[destination]


DEMO_CITY_GRAPH: dict[str, dict[str, float]] = {
    "Central": {"North": 2.0, "River": 3.0},
    "North": {"Central": 2.0, "Market": 2.0},
    "River": {"Central": 3.0, "Market": 1.0},
    "Market": {"North": 2.0, "River": 1.0},
}

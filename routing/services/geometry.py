"""Line simplification for returning routes to clients."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def simplify_path(
    path: Sequence[tuple[float, float]], tolerance: float
) -> list[tuple[float, float]]:
    """Ramer–Douglas–Peucker simplification.

    Drops points that lie within ``tolerance`` (in the path's own units, here
    degrees) of the line between the points kept around them, so the shape
    is preserved with far fewer points. Used only for display: route
    calculations use the full path.
    """
    if len(path) < 3:
        return list(path)

    points = np.asarray(path, dtype=float)
    keep = np.zeros(len(points), dtype=bool)
    keep[[0, -1]] = True
    pending = [(0, len(points) - 1)]
    while pending:
        first, last = pending.pop()
        if last - first < 2:
            continue
        distances = _distances_to_segment(points[first + 1 : last], points[first], points[last])
        farthest = int(np.argmax(distances))
        if distances[farthest] > tolerance:
            split = first + 1 + farthest
            keep[split] = True
            pending.extend(((first, split), (split, last)))
    return [tuple(point) for point in points[keep].tolist()]


def _distances_to_segment(points: np.ndarray, start: np.ndarray, end: np.ndarray) -> np.ndarray:
    segment = end - start
    length_squared = float(segment @ segment)
    if length_squared == 0:
        return np.linalg.norm(points - start, axis=1)
    t = np.clip((points - start) @ segment / length_squared, 0.0, 1.0)
    return np.linalg.norm(points - (start + t[:, None] * segment), axis=1)

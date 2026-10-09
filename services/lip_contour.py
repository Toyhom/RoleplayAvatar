"""Track a continuous painted lip instead of independent column minima."""

import numpy as np


def trace_lip(gray, x0, x1, ymin, ymax):
    """Find a dark, connected path through the landmark-defined mouth window.

    A darker chin shadow may win a few columns independently. A global path
    with bounded slope cannot jump down to that shadow and tear the lip warp.
    Column centering preserves contrast under uneven face illumination.
    """
    gray = np.asarray(gray, dtype=np.float64)
    if gray.ndim != 2 or not np.isfinite([x0, x1, ymin, ymax]).all():
        raise ValueError("Invalid lip search window")
    left, right = max(0, int(x0)), min(gray.shape[1] - 1, int(x1))
    top, bottom = max(0, int(ymin)), min(gray.shape[0] - 1, int(ymax))
    if right <= left or bottom <= top:
        raise ValueError("Lip search window is empty")
    window = gray[top:bottom + 1, left:right + 1]
    if not np.isfinite(window).all():
        raise ValueError("Non-finite mouth pixels")
    cost = (window - np.median(window, axis=0)) / 32.0
    rows, columns = cost.shape
    parents = np.zeros((rows, columns), dtype=np.int32)
    total = cost[:, 0].copy()
    for x in range(1, columns):
        # At most one vertical pixel per horizontal pixel; a small bend cost
        # favors the lip crease through weak or interrupted painted strokes.
        choices = np.stack([
            np.r_[np.inf, total[:-1] + 0.35],
            total,
            np.r_[total[1:] + 0.35, np.inf],
        ])
        step = choices.argmin(axis=0)
        parents[:, x] = np.arange(rows) + step - 1
        total = choices[step, np.arange(rows)] + cost[:, x]
    path = np.empty(columns, dtype=np.int32)
    path[-1] = total.argmin()
    for x in range(columns - 1, 0, -1):
        path[x - 1] = parents[path[x], x]
    return np.arange(left, right + 1), path.astype(float) + top

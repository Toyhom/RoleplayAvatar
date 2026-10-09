import numpy as np
import pytest

from services.lip_contour import trace_lip


def test_lip_does_not_jump_to_darker_shadow_below_its_center():
    gray = np.full((60, 100), 220.0)
    gray[20, :] = 90
    gray[37:40, 45:51] = 25
    assert np.argmax(gray.argmin(axis=0)) in range(45, 51)
    xs, ys = trace_lip(gray, 0, 99, 12, 44)
    assert len(xs) == 100
    assert np.max(np.abs(ys - 20)) < 1


def test_curved_lip_survives_lighting_gradient_and_short_gap():
    xs = np.arange(100)
    expected = np.rint(20 + 6 * np.sin(xs * np.pi / 99)).astype(int)
    gray = np.tile(np.linspace(140, 245, 100), (60, 1))
    gray[expected, xs] -= 85
    gray[:, 49:52] = 190
    _, ys = trace_lip(gray, 0, 99, 12, 44)
    assert np.max(np.abs(ys - expected)) <= 1
    assert np.max(np.abs(np.diff(ys))) <= 1


def test_search_window_is_clipped_and_empty_window_rejected():
    gray = np.full((30, 40), 220.0)
    gray[10] = 60
    xs, ys = trace_lip(gray, -5, 45, -2, 33)
    assert (xs[0], xs[-1]) == (0, 39)
    assert np.all(ys == 10)
    with pytest.raises(ValueError, match="empty"):
        trace_lip(gray, 50, 55, 1, 2)

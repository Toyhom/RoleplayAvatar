from pathlib import Path

import pytest

from roleplay_avatar.assets import catalog

ROOT = Path(__file__).resolve().parents[1]


def pytest_configure(config):
    # Pytest creates the base temp directory, but expects its parent to exist.
    (config.rootpath / ".cache").mkdir(exist_ok=True)


@pytest.fixture
def characters():
    return catalog(ROOT / "fixtures/characters_m0")

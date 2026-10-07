import pandas as pd
import pytest

pd.set_option("mode.copy_on_write", True)

from faultline.eval import protocol as P  # noqa: E402
from faultline.sim.world import WorldConfig, simulate  # noqa: E402


@pytest.fixture(scope="session")
def world():
    """사이트 6곳(습관 유형이 하나씩)의 작은 세계."""
    return simulate(WorldConfig(seed=3, n_sites=6))


@pytest.fixture(scope="session")
def prep(world):
    return P.prepare(world)

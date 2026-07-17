import pytest
from pathlib import Path


def pytest_addoption(parser):
    parser.addoption(
        "--output_path", action="store", type=str, default=None, help="output directory for test functions"
    )

@pytest.fixture
def output_path(request):
    p = request.config.getoption("--output_path")
    return Path(p) if p is not None else None

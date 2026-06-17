import pytest
import respx

from reportnet import ReportnetClient


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run live integration tests (requires keyring credentials and network access)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if not config.getoption("--integration"):
        skip = pytest.mark.skip(reason="live API test — pass --integration to run")
        for item in items:
            if item.get_closest_marker("integration"):
                item.add_marker(skip)


@pytest.fixture
def mock_router():
    with respx.mock(base_url="https://api.reportnet.europa.eu", assert_all_called=False) as router:
        yield router


@pytest.fixture
def client():
    return ReportnetClient(api_key="test-key")

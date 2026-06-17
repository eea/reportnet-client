import pytest
import respx

from reportnet import ReportnetClient


@pytest.fixture
def mock_router():
    with respx.mock(base_url="https://api.reportnet.europa.eu", assert_all_called=False) as router:
        yield router


@pytest.fixture
def client():
    return ReportnetClient(api_key="test-key")

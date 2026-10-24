import re
from collections.abc import Callable

import httpx
import pytest
from fastapi.testclient import TestClient

_STATIC_ASSET = re.compile(r'<(?:script src|link rel="stylesheet" href)="(/static/[^"]+)"')


@pytest.fixture
def page_with_assets() -> Callable[[TestClient, httpx.Response], str]:
    """Text of a page response followed by its `/static/` styles and scripts (same client)."""

    def read(client: TestClient, response: httpx.Response) -> str:
        assets = [client.get(path) for path in _STATIC_ASSET.findall(response.text)]
        assert [asset.status_code for asset in assets] == [200] * len(assets)
        return response.text + "".join(asset.text for asset in assets)

    return read

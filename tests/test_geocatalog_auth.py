import json

from brin_hotspot.config import Settings
from brin_hotspot.geocatalog import GeoCatalogClient


class TokenResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps({"access_token": "service-token", "expires_in": 300}).encode()


def test_service_access_token_is_requested_and_cached(monkeypatch):
    calls = []

    def open_token(request, timeout):
        calls.append((request, timeout))
        return TokenResponse()

    monkeypatch.setattr("brin_hotspot.geocatalog.urlopen", open_token)
    client = GeoCatalogClient(
        Settings(
            HOTSPOT_GEOCATALOG_OIDC_TOKEN_URL="http://keycloak/token",
            HOTSPOT_GEOCATALOG_OIDC_CLIENT_ID="hotspot-geocatalog-service",
            HOTSPOT_GEOCATALOG_OIDC_CLIENT_SECRET="secret",
        )
    )

    assert client._service_access_token() == "service-token"
    assert client._service_access_token() == "service-token"
    assert len(calls) == 1

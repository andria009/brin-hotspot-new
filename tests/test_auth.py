import asyncio

import httpx

from brin_hotspot import auth
from brin_hotspot.auth import application_roles
from brin_hotspot.config import Settings


def test_application_roles_are_client_scoped():
    claims = {
        "resource_access": {
            "hotspot-new": {"roles": ["sage", "unrelated"]},
            "geocatalog": {"roles": ["god"]},
        }
    }

    assert application_roles(claims, "hotspot-new") == {"sage"}


def test_activity_request_sends_bearer_and_service_secret(monkeypatch):
    def respond(request):
        assert request.headers["authorization"] == "Bearer user-token"
        assert request.headers["x-hotspot-activity-secret"] == "service-secret"
        return httpx.Response(201, json={"recorded": True})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        auth.httpx, "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    result = asyncio.run(auth.access_management_request(
        Settings(HOTSPOT_ACCESS_MANAGEMENT_URL="http://access.test/api/v1"),
        "user-token", "POST", "/activity/hotspot",
        json_body={"activity": "hotspot_scene_requested"},
        activity_secret="service-secret",
    ))
    assert result == {"recorded": True}

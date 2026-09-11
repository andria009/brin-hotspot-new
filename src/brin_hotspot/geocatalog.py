from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from brin_hotspot.config import Settings


class GeoCatalogError(RuntimeError):
    pass


class GeoCatalogClient:
    def __init__(self, settings: Settings):
        self._base_url = settings.geocatalog_api_url.rstrip("/")
        self._access_token = settings.geocatalog_access_token.get_secret_value()
        self._timeout = settings.geocatalog_timeout_seconds

    def request_scene(self, payload: dict) -> dict:
        if not self._access_token:
            raise GeoCatalogError("HOTSPOT_GEOCATALOG_ACCESS_TOKEN is not configured")
        request = Request(
            f"{self._base_url}/scene-requests",
            data=json.dumps(payload).encode(),
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                result = json.loads(response.read().decode())
        except HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:1000]
            raise GeoCatalogError(f"GeoCatalog returned HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise GeoCatalogError(f"GeoCatalog request failed: {exc}") from exc
        if not isinstance(result, dict):
            raise GeoCatalogError("GeoCatalog returned an invalid scene response")
        return result

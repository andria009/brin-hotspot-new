from __future__ import annotations

import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from brin_hotspot.config import Settings


class GeoCatalogError(RuntimeError):
    pass


class GeoCatalogClient:
    def __init__(self, settings: Settings):
        self._base_url = settings.geocatalog_api_url.rstrip("/")
        self._access_token = settings.geocatalog_access_token.get_secret_value()
        self._token_url = settings.geocatalog_oidc_token_url
        self._client_id = settings.geocatalog_oidc_client_id
        self._client_secret = settings.geocatalog_oidc_client_secret.get_secret_value()
        self._cached_token = ""
        self._cached_token_expires_at = 0.0
        self._timeout = settings.geocatalog_timeout_seconds

    def request_scene(self, payload: dict) -> dict:
        access_token = self._service_access_token()
        request = Request(
            f"{self._base_url}/scene-requests",
            data=json.dumps(payload).encode(),
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
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

    def _service_access_token(self) -> str:
        if self._cached_token and time.monotonic() < self._cached_token_expires_at:
            return self._cached_token
        if self._token_url and self._client_id and self._client_secret:
            request = Request(
                self._token_url,
                data=urlencode(
                    {
                        "grant_type": "client_credentials",
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                    }
                ).encode(),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            try:
                with urlopen(request, timeout=self._timeout) as response:
                    result = json.loads(response.read().decode())
            except HTTPError as exc:
                detail = exc.read().decode(errors="replace")[:1000]
                raise GeoCatalogError(
                    f"Keycloak service login returned HTTP {exc.code}: {detail}"
                ) from exc
            except (URLError, TimeoutError, json.JSONDecodeError) as exc:
                raise GeoCatalogError(f"Keycloak service login failed: {exc}") from exc
            token = str(result.get("access_token") or "")
            if not token:
                raise GeoCatalogError("Keycloak service login returned no access token")
            self._cached_token = token
            self._cached_token_expires_at = time.monotonic() + max(
                1, int(result.get("expires_in") or 60) - 30
            )
            return token
        if self._access_token:
            return self._access_token
        raise GeoCatalogError("Hotspot-to-GeoCatalog authentication is not configured")
